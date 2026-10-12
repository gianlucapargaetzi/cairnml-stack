from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from mlops_common.schemas import (
    ArtifactUrlRequest,
    GitInfo,
    GitTokenRequest,
    GitTokenResponse,
    JobOut,
    JobSpec,
    JobStatusUpdate,
    StsResponse,
    TokenResponse,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Agent, Artifact, Experiment, Job, Project
from mlops_server.routers.experiments import apply_status
from mlops_server.security.deps import READERS, Principal, get_session, require
from mlops_server.services import access, audit
from mlops_server.services.github import GitHubError, RepoNotAccessible

router = APIRouter()
agent_only = require("agent")
client_only = require("client")

# Agent-reported transitions. Terminal states have no outgoing edges, so a finished job
# can no longer be written to by its agent.
ALLOWED = {
    "assigned": {"running", "failed", "cancelled"},
    "running": {"finished", "failed", "cancelled"},
}


def job_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id, experiment_id=job.experiment_id, status=job.status, queue=job.queue,
        agent_id=job.agent_id, exit_code=job.exit_code, message=job.message,
        created_at=job.created_at,
    )


def _check_commits(request: Request, spec: JobSpec) -> None:
    pairs = set()
    if spec.code:
        pairs.add((spec.code.repo, spec.code.commit))
    for dataset in spec.data:
        if dataset.repo and dataset.commit:
            pairs.add((dataset.repo, dataset.commit))
    if not pairs:
        return
    github = request.app.state.github
    if github is None:
        raise HTTPException(503, "GitHub is not configured")
    for repo, commit in sorted(pairs):
        try:
            found = github.commit_exists(repo, commit)
        except RepoNotAccessible:
            raise HTTPException(422, f"GitHub App is not installed on {repo}") from None
        except GitHubError:
            raise HTTPException(502, "GitHub request failed") from None
        if not found:
            raise HTTPException(
                422, f"commit not found on GitHub: push it first ({repo}@{commit[:8]})"
            )


def _check_keys(session: Session, project_slug: str, spec: JobSpec) -> None:
    keys = [i.key for i in spec.inputs]
    if spec.code and spec.code.patch_key:
        keys.append(spec.code.patch_key)
    for key in keys:
        if not key.startswith(project_slug + "/"):
            raise HTTPException(422, f"key {key!r} does not belong to project {project_slug}")
        if session.scalar(select(Artifact.id).where(Artifact.key == key)) is None:
            raise HTTPException(422, f"unknown artifact key {key!r}")


@router.post("/jobs", response_model=JobOut)
def dispatch(
    spec: JobSpec,
    request: Request,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
):
    project = access.ensure_member(session, principal, spec.project)
    _check_commits(request, spec)
    _check_keys(session, project.slug, spec)

    runtime = spec.runtime
    is_python = runtime.type == "python"
    git = None
    if spec.code:
        git = GitInfo(
            repo=spec.code.repo, commit=spec.code.commit, cwd=spec.code.workdir,
            dirty=bool(spec.code.patch_key), patch_key=spec.code.patch_key,
        ).model_dump()
    experiment = Experiment(
        id=new_id("exp"), project_id=project.id, owner_id=principal.user_id, name=spec.name,
        status="queued", source="job", params=spec.params, git=git,
        datasets=[d.model_dump() for d in spec.data],
        requirements=list(runtime.requirements) if is_python else [],
        argv=list(runtime.command) if is_python else [],
        python_version=runtime.python if is_python else None,
    )
    job = Job(
        id=new_id("job"), experiment_id=experiment.id, project_id=project.id,
        created_by=principal.user_id, spec=spec.model_dump(mode="json"), queue=spec.queue,
        cpu=spec.resources.cpu, memory_gb=spec.resources.memory_gb, gpu=spec.resources.gpu,
        labels=list(spec.resources.labels),
    )
    experiment.job_id = job.id
    session.add_all([experiment, job])
    audit.record(session, principal.id, "job.dispatched", request, job_id=job.id, queue=spec.queue)
    session.commit()
    return job_out(job)


def _agent_job(session: Session, principal: Principal, job_id: str, lock: bool = False) -> Job:
    # lock serialises concurrent writers on the job row (the status check must see the
    # committed status of any other in-flight transition).
    job = session.get(Job, job_id, with_for_update=True) if lock else session.get(Job, job_id)
    if job is None or job.agent_id != principal.id:
        raise HTTPException(404, "job not found")
    return job


def _active_agent_job(session: Session, principal: Principal, job_id: str) -> Job:
    job = _agent_job(session, principal, job_id)
    if job.status not in ("assigned", "running"):
        raise HTTPException(409, f"job is {job.status}")
    return job


def _client_job(session: Session, principal: Principal, job_id: str, lock: bool = False) -> Job:
    job = session.get(Job, job_id, with_for_update=lock) if lock else session.get(Job, job_id)
    project = session.get(Project, job.project_id) if job else None
    if job is None or not access.is_member(session, principal, project):
        raise HTTPException(404, "job not found")
    return job


@router.post("/jobs/{job_id}/status", response_model=JobOut)
def set_status(
    job_id: str,
    body: JobStatusUpdate,
    request: Request,
    principal: Annotated[Principal, Depends(agent_only)],
    session: Annotated[Session, Depends(get_session)],
):
    job = _agent_job(session, principal, job_id, lock=True)
    if body.status not in ALLOWED.get(job.status, set()):
        raise HTTPException(409, f"cannot go from {job.status} to {body.status}")
    # apply_status locks and refreshes the experiment; it must run before any write to it.
    apply_status(session.get(Experiment, job.experiment_id), body.status)
    job.status = body.status
    job.exit_code = body.exit_code
    job.message = body.message
    if body.status != "running":
        job.finished_at = datetime.now(UTC)
    audit.record(session, principal.id, "job.status", request, job_id=job.id, status=body.status)
    session.commit()
    return job_out(job)


@router.post("/jobs/{job_id}/run-token", response_model=TokenResponse)
def run_token(
    job_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(agent_only)],
    session: Annotated[Session, Depends(get_session)],
):
    job = _active_agent_job(session, principal, job_id)
    # sub must equal job.id: the principal dependency refuses run tokens whose sub differs.
    token, expires_in = request.app.state.tokens.issue(
        job.id, "run", uid=job.created_by, experiment_id=job.experiment_id,
        job_id=job.id, ttl=request.app.state.settings.run_token_ttl,
    )
    audit.record(session, principal.id, "run_token.issued", request, job_id=job.id)
    session.commit()
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/jobs/{job_id}/git-token", response_model=GitTokenResponse)
def git_token(
    job_id: str,
    body: GitTokenRequest,
    request: Request,
    principal: Annotated[Principal, Depends(agent_only)],
    session: Annotated[Session, Depends(get_session)],
):
    job = _active_agent_job(session, principal, job_id)
    spec = JobSpec.model_validate(job.spec)
    allowed = {spec.code.repo} if spec.code else set()
    allowed |= {d.repo for d in spec.data if d.repo}
    if body.repo not in allowed:
        raise HTTPException(403, "repository is not part of this job")
    github = request.app.state.github
    if github is None:
        raise HTTPException(503, "GitHub is not configured")
    try:
        token = github.installation_token(body.repo)
    except RepoNotAccessible:
        raise HTTPException(404, "GitHub App is not installed on this repository") from None
    except GitHubError:
        raise HTTPException(502, "GitHub request failed") from None
    audit.record(session, principal.id, "git_token.issued", request, job_id=job.id, repo=body.repo)
    session.commit()
    return GitTokenResponse(token=token.token, expires_at=token.expires_at)


@router.post("/jobs/{job_id}/sts", response_model=StsResponse)
def job_sts(
    job_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(agent_only)],
    session: Annotated[Session, Depends(get_session)],
):
    job = _active_agent_job(session, principal, job_id)
    storage = request.app.state.storage
    if storage is None:
        raise HTTPException(503, "storage is not configured")
    slug = session.get(Project, job.project_id).slug
    creds = storage.sts_credentials(slug, False)  # read-only: jobs never write artifacts directly
    audit.record(session, principal.id, "sts.issued", request, job_id=job.id, write=False)
    session.commit()
    return creds


@router.post("/jobs/{job_id}/artifact-url")
def artifact_url(
    job_id: str,
    body: ArtifactUrlRequest,
    request: Request,
    principal: Annotated[Principal, Depends(agent_only)],
    session: Annotated[Session, Depends(get_session)],
):
    job = _active_agent_job(session, principal, job_id)
    spec = JobSpec.model_validate(job.spec)
    allowed = {i.key for i in spec.inputs}
    if spec.code and spec.code.patch_key:
        allowed.add(spec.code.patch_key)
    if body.key not in allowed:
        raise HTTPException(403, "key is not part of this job")
    storage = request.app.state.storage
    if storage is None:
        raise HTTPException(503, "storage is not configured")
    return {"url": storage.presign_get(body.key)}


@router.get("/jobs")
def list_jobs(
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    status: str | None = None,
    project: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    projects = session.scalars(select(Project))
    ids = [p.id for p in projects if access.is_member(session, principal, p)]
    if project:
        ids = [access.ensure_member(session, principal, project).id]
    query = (
        select(Job, Experiment.name, Project.slug, Agent.name)
        .join(Experiment, Experiment.id == Job.experiment_id)
        .join(Project, Project.id == Job.project_id)
        .outerjoin(Agent, Agent.id == Job.agent_id)
        .where(Job.project_id.in_(ids))
    )
    if status:
        query = query.where(Job.status == status)
    query = query.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit)
    return [
        {
            "id": j.id, "experiment_id": j.experiment_id, "experiment_name": name,
            "project": slug, "status": j.status, "queue": j.queue, "agent_id": j.agent_id,
            "agent_name": agent_name, "cpu": j.cpu, "memory_gb": j.memory_gb, "gpu": j.gpu,
            "labels": j.labels, "exit_code": j.exit_code, "message": j.message,
            "created_at": j.created_at, "assigned_at": j.assigned_at, "finished_at": j.finished_at,
        }
        for j, name, slug, agent_name in session.execute(query)
    ]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
):
    return job_out(_client_job(session, principal, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(client_only)],
    session: Annotated[Session, Depends(get_session)],
):
    # Lock the job row before reading its status: claim_next locks the same row, so a
    # queued job cannot be assigned to an agent while it is being cancelled.
    job = _client_job(session, principal, job_id, lock=True)
    if job.status == "queued":
        apply_status(session.get(Experiment, job.experiment_id), "cancelled")
        job.status = "cancelled"
        job.finished_at = datetime.now(UTC)
    elif job.status in ("assigned", "running"):
        job.cancel_requested = True
    else:
        raise HTTPException(409, f"job already {job.status}")
    audit.record(session, principal.id, "job.cancel_requested", request, job_id=job.id)
    session.commit()
    return job_out(job)

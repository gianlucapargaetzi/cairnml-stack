from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from mlops_common.schemas import GitInfo, JobOut, JobSpec
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Artifact, Experiment, Job
from mlops_server.security.deps import Principal, get_session, require
from mlops_server.services import access, audit
from mlops_server.services.github import GitHubError, RepoNotAccessible

router = APIRouter()


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

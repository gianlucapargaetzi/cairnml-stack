from __future__ import annotations

import dataclasses
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from mlops_common.schemas import MemberAdd, ProjectCreate, ProjectOut
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Experiment, Project, ProjectMember, ProjectRepo, Run, User
from mlops_server.security.deps import READERS, Principal, get_session, require
from mlops_server.services import access, audit
from mlops_server.services.experiments import DEFAULT_EXPERIMENT
from mlops_server.services.github import GitHubError, RepoNotAccessible, valid_repo
from mlops_server.services.repo_graph import build_graph

router = APIRouter()


@router.post("/projects", response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    request: Request,
    principal: Annotated[Principal, Depends(require("client", admin=True))],
    session: Annotated[Session, Depends(get_session)],
) -> ProjectOut:
    session.add(Project(id=new_id("prj"), slug=body.slug, name=body.name))
    audit.record(session, principal.id, "project.created", request, slug=body.slug)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "project already exists") from None
    return ProjectOut(slug=body.slug, name=body.name)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
) -> list[ProjectOut]:
    projects = session.scalars(select(Project).order_by(Project.slug)).all()
    return [
        ProjectOut(slug=p.slug, name=p.name)
        for p in projects
        if access.is_member(session, principal, p)
    ]


@router.post("/project-members")
def add_member(
    body: MemberAdd,
    request: Request,
    principal: Annotated[Principal, Depends(require("client", admin=True))],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, bool]:
    project = access.get_project(session, body.project)
    user = session.scalar(select(User).where(User.username == body.username))
    if user is None:
        raise HTTPException(404, "user not found")
    if session.get(ProjectMember, (project.id, user.id)) is None:
        session.add(ProjectMember(project_id=project.id, user_id=user.id))
        audit.record(
            session, principal.id, "project.member_added", request,
            project=project.slug, user=user.id,
        )
        session.commit()
    return {"added": True}


class RepoLink(BaseModel):
    project: str
    repo: str
    role: Literal["code", "data"] = "code"

    @field_validator("repo")
    @classmethod
    def _owner_name(cls, value: str) -> str:
        if not valid_repo(value):
            raise ValueError("repo must be owner/name")
        return value


@router.post("/projects/repos")
def link_repo(
    body: RepoLink,
    request: Request,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    project = access.ensure_member(session, principal, body.project)
    github = request.app.state.github
    if github is None:
        raise HTTPException(503, "GitHub is not configured")
    try:
        github.get_default_branch(body.repo)
    except RepoNotAccessible:
        raise HTTPException(422, f"GitHub App is not installed on {body.repo}") from None
    except GitHubError:
        raise HTTPException(502, "GitHub request failed") from None
    link = session.get(ProjectRepo, (project.id, body.repo))
    if link is None:
        session.add(ProjectRepo(project_id=project.id, repo=body.repo, role=body.role))
        audit.record(
            session, principal.id, "project.repo_linked", request,
            project=project.slug, repo=body.repo, role=body.role,
        )
    else:
        link.role = body.role
    session.commit()
    return {"project": project.slug, "repo": body.repo, "role": body.role}


@router.get("/projects/repos")
def list_repos(
    project: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, str]]:
    proj = access.ensure_member(session, principal, project)
    rows = session.scalars(
        select(ProjectRepo).where(ProjectRepo.project_id == proj.id).order_by(ProjectRepo.repo)
    )
    return [{"project": proj.slug, "repo": r.repo, "role": r.role} for r in rows]


@router.delete("/projects/repos")
def unlink_repo(
    project: str,
    repo: str,
    request: Request,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, bool]:
    proj = access.ensure_member(session, principal, project)
    session.delete(access.ensure_linked(session, proj, repo))
    audit.record(
        session, principal.id, "project.repo_unlinked", request, project=proj.slug, repo=repo
    )
    session.commit()
    return {"removed": True}


def _linked_github(
    request: Request, session: Session, principal: Principal, project: str, repo: str
):
    """Membership, then the link, then the configured GitHub App; returns (github, cache)."""
    proj = access.ensure_member(session, principal, project)
    access.ensure_linked(session, proj, repo)
    github = request.app.state.github
    if github is None:
        raise HTTPException(503, "GitHub is not configured")
    return github, request.app.state.cache


def _read(cache, key, github_call):
    """Run one GitHub read through the TTL cache, mapping failures to HTTP errors."""
    try:
        return cache.get_or_set(key, github_call)
    except RepoNotAccessible:
        raise HTTPException(404, "GitHub App is not installed on this repository") from None
    except GitHubError:
        raise HTTPException(502, "GitHub request failed") from None


def _ref(cache, github, repo: str, ref: str | None) -> str:
    if ref:
        return ref
    return _read(cache, ("default", repo), lambda: github.get_default_branch(repo))


def _safe_path(path: str) -> str:
    if not path or path.startswith("/") or any(p in ("", ".", "..") for p in path.split("/")):
        raise HTTPException(422, "path must be a relative repository path")
    return path


@router.get("/projects/repos/branches")
def repo_branches(
    request: Request,
    project: str,
    repo: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, str]]:
    github, cache = _linked_github(request, session, principal, project, repo)
    branches = _read(cache, ("branches", repo), lambda: github.list_branches(repo))
    return [dataclasses.asdict(b) for b in branches]


@router.get("/projects/repos/commits")
def repo_commits(
    request: Request,
    project: str,
    repo: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    ref: Annotated[str | None, Query()] = None,
) -> list[dict]:
    github, cache = _linked_github(request, session, principal, project, repo)
    ref = _ref(cache, github, repo, ref)
    commits = _read(cache, ("commits", repo, ref), lambda: github.list_commits(repo, ref))
    return [dataclasses.asdict(c) for c in commits]


@router.get("/projects/repos/tree")
def repo_tree(
    request: Request,
    project: str,
    repo: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    ref: Annotated[str | None, Query()] = None,
) -> dict:
    github, cache = _linked_github(request, session, principal, project, repo)
    ref = _ref(cache, github, repo, ref)
    paths, truncated = _read(cache, ("tree", repo, ref), lambda: github.list_tree(repo, ref))
    return {"ref": ref, "paths": paths, "truncated": truncated}


@router.get("/projects/repos/file")
def repo_file(
    request: Request,
    project: str,
    repo: str,
    path: Annotated[str, Query()],
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    ref: Annotated[str | None, Query()] = None,
) -> dict:
    path = _safe_path(path)
    github, cache = _linked_github(request, session, principal, project, repo)
    ref = _ref(cache, github, repo, ref)
    text = _read(cache, ("file", repo, ref, path), lambda: github.read_file(repo, path, ref))
    if text is None:
        raise HTTPException(404, "file not found or too large to show")
    return {"path": path, "ref": ref, "text": text}


@router.get("/projects/repos/file-history")
def repo_file_history(
    request: Request,
    project: str,
    repo: str,
    path: Annotated[str, Query()],
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    ref: Annotated[str | None, Query()] = None,
) -> list[dict]:
    path = _safe_path(path)
    github, cache = _linked_github(request, session, principal, project, repo)
    ref = _ref(cache, github, repo, ref)
    commits = _read(
        cache, ("file-history", repo, ref, path),
        lambda: github.list_path_commits(repo, path, ref),
    )
    return [dataclasses.asdict(c) for c in commits]


@router.get("/projects/graph")
def repo_graph(
    request: Request,
    project: str,
    repo: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=10, le=200)] = 60,
    refresh: bool = False,
) -> dict:
    proj = access.ensure_member(session, principal, project)
    access.ensure_linked(session, proj, repo)
    github = request.app.state.github
    if github is None:
        raise HTTPException(503, "GitHub is not configured")
    cache = request.app.state.cache
    if refresh:
        cache.clear()
    try:
        graph = cache.get_or_set(("graph", repo, limit), lambda: build_graph(github, repo, limit))
    except RepoNotAccessible:
        raise HTTPException(404, "GitHub App is not installed on this repository") from None
    except GitHubError:
        raise HTTPException(502, "GitHub request failed") from None
    # Run annotations depend on the project, not the cache key, so they are read per request.
    shown = {c["sha"] for c in graph["commits"]}
    runs: dict[str, list[dict]] = {}
    query = (
        select(Run, Experiment.name)
        .outerjoin(Experiment, Experiment.id == Run.experiment_id)
        .where(Run.project_id == proj.id)
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(2000)
    )
    for exp, experiment_name in session.execute(query):
        git = exp.git or {}
        commit = git.get("commit")
        if git.get("repo") != repo or commit not in shown:
            continue
        bucket = runs.setdefault(commit, [])
        if len(bucket) < 20:
            bucket.append(
                {
                    "id": exp.id,
                    "name": exp.name,
                    "status": exp.status,
                    "experiment": experiment_name or DEFAULT_EXPERIMENT,
                }
            )
    return {**graph, "runs": runs}

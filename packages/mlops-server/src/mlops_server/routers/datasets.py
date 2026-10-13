from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Experiment, Project, ProjectRepo, Task
from mlops_server.security.deps import READERS, Principal, get_session, require
from mlops_server.services import access
from mlops_server.services.datasets import catalog, dataset_detail
from mlops_server.services.github import GitHubError, RepoNotAccessible, valid_repo
from mlops_server.services.tasks import DEFAULT_TASK

router = APIRouter()
_SAFE = re.compile(r"[A-Za-z0-9._/-]{1,255}")
USED_BY_LIMIT = 20
USED_BY_SCAN = 1000


def _safe_path(path: str) -> str:
    if not _SAFE.fullmatch(path) or any(p in ("", ".", "..") for p in path.split("/")):
        raise HTTPException(422, "path must be a safe relative repository path")
    return path


def _github(request: Request):
    if request.app.state.github is None:
        raise HTTPException(503, "GitHub is not configured")
    return request.app.state.github


def _catalog(github, cache, repo: str, ref: str) -> dict:
    return cache.get_or_set(("catalog", repo, ref), lambda: catalog(github, repo, ref))


def _default_branch(request: Request, repo: str) -> str:
    github = _github(request)
    try:
        return request.app.state.cache.get_or_set(
            ("default", repo), lambda: github.get_default_branch(repo)
        )
    except RepoNotAccessible:
        raise HTTPException(404, "GitHub App is not installed on this repository") from None
    except GitHubError:
        raise HTTPException(502, "GitHub request failed") from None


@router.get("/datasets")
def datasets(
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    project: str | None = None,
) -> list[dict]:
    if project:
        projects = [access.ensure_member(session, principal, project)]
    else:
        projects = [
            p
            for p in session.scalars(select(Project).order_by(Project.slug))
            if access.is_member(session, principal, p)
        ]
    github, cache = _github(request), request.app.state.dataset_cache
    out: list[dict] = []
    warnings: set[str] = set()
    for proj in projects:
        links = session.scalars(
            select(ProjectRepo).where(ProjectRepo.project_id == proj.id).order_by(ProjectRepo.repo)
        )
        for link in links:
            try:
                ref = _default_branch(request, link.repo)
                listing = _catalog(github, cache, link.repo, ref)
            except (HTTPException, GitHubError):
                warnings.add(link.repo)
                continue
            if listing["truncated"]:
                warnings.add(f"{link.repo} (listing truncated by GitHub)")
            out += [
                {"project": proj.slug, "repo": link.repo, "ref": ref, **e}
                for e in listing["entries"]
            ]
    if warnings:
        response.headers["X-Dataset-Warnings"] = ", ".join(sorted(warnings))
    return out


def _used_by(session: Session, proj: Project, repo: str, path: str) -> dict:
    query = (
        select(Experiment, Task.name)
        .outerjoin(Task, Task.id == Experiment.task_id)
        .where(Experiment.project_id == proj.id)
        .order_by(Experiment.created_at.desc())
        .limit(USED_BY_SCAN)
    )
    users = []
    for exp, task_name in session.execute(query):
        if any(d.get("path") == path and d.get("repo") in (None, repo) for d in exp.datasets or []):
            users.append(
                {
                    "id": exp.id,
                    "name": exp.name,
                    "status": exp.status,
                    "task": task_name or DEFAULT_TASK,
                    "created_at": exp.created_at.isoformat(),
                }
            )
    return {"count": len(users), "experiments": users[:USED_BY_LIMIT]}


@router.get("/datasets/detail")
def detail(
    request: Request,
    project: str,
    repo: str,
    path: Annotated[str, Query()],
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    ref: Annotated[str | None, Query()] = None,
) -> dict:
    if not valid_repo(repo):
        raise HTTPException(422, "repo must be owner/name")
    path = _safe_path(path)
    if ref is not None and not _SAFE.fullmatch(ref):
        raise HTTPException(422, "invalid ref")
    proj = access.ensure_member(session, principal, project)
    access.ensure_linked(session, proj, repo)
    github, cache = _github(request), request.app.state.dataset_cache
    ref = ref or _default_branch(request, repo)
    try:
        body = cache.get_or_set(
            ("detail", repo, path, ref),
            lambda: dataset_detail(github, repo, path, ref),
            store_if=lambda value: value is not None,  # misses are not cached
        )
    except RepoNotAccessible:
        raise HTTPException(404, "GitHub App is not installed on this repository") from None
    except GitHubError:
        raise HTTPException(502, "GitHub request failed") from None
    if body is None:
        raise HTTPException(404, "dataset not found")
    return {**body, "used_by": _used_by(session, proj, repo, path)}

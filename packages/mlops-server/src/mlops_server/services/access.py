"""Authorization rules shared by all routers."""

from __future__ import annotations

from fastapi import HTTPException
from mlops_common.schemas import TERMINAL_STATUSES
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Run, Job, Project, ProjectMember, ProjectRepo, Experiment
from mlops_server.security.deps import Principal


def get_project(session: Session, slug: str) -> Project:
    project = session.scalar(select(Project).where(Project.slug == slug))
    if project is None:
        raise HTTPException(404, "project not found")
    return project


def is_member(session: Session, principal: Principal, project: Project) -> bool:
    if principal.kind not in ("client", "web") or principal.user_id is None:
        return False
    if principal.is_admin:
        return True
    return session.get(ProjectMember, (project.id, principal.user_id)) is not None


def ensure_member(session: Session, principal: Principal, slug: str) -> Project:
    project = get_project(session, slug)
    if not is_member(session, principal, project):
        raise HTTPException(404, "project not found")
    return project


def repo_visible(session: Session, principal: Principal, repo: str) -> bool:
    """True when `repo` is linked to a project the caller belongs to (any project for admins)."""
    if principal.is_admin:
        return True
    if principal.kind != "client" or principal.user_id is None:
        return False
    stmt = (
        select(ProjectRepo.repo)
        .join(ProjectMember, ProjectMember.project_id == ProjectRepo.project_id)
        .where(ProjectRepo.repo == repo, ProjectMember.user_id == principal.user_id)
        .limit(1)
    )
    return session.scalar(stmt) is not None


def ensure_linked(session: Session, project: Project, repo: str) -> ProjectRepo:
    link = session.get(ProjectRepo, (project.id, repo))
    if link is None:
        raise HTTPException(404, "repository is not linked to this project")
    return link


def load_run(
    session: Session, principal: Principal, run_id: str, write: bool
) -> Run:
    """Return the run if `principal` may read (or write) it, else 404."""
    if write:
        # Lock the row so a concurrent status change cannot interleave with this write.
        run = session.get(Run, run_id, with_for_update=True, populate_existing=True)
    else:
        run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if principal.kind == "run":
        allowed = run.id == principal.experiment_id
        if write and run.status in TERMINAL_STATUSES:
            allowed = False  # a finished run's token can no longer change its record
    elif principal.kind == "agent":
        job = session.get(Job, run.job_id) if run.job_id else None
        allowed = job is not None and job.agent_id == principal.id
        if write and run.status in TERMINAL_STATUSES:
            allowed = False
    else:
        project = session.get(Project, run.project_id)
        allowed = is_member(session, principal, project)
        if allowed and write:
            allowed = principal.kind == "client" and (
                run.owner_id == principal.user_id or principal.is_admin
            )
    if not allowed:
        raise HTTPException(404, "run not found")
    return run


def load_experiment(
    session: Session, principal: Principal, experiment_id: str, write: bool
) -> Run:
    """Deprecated alias for backward compatibility during migration. Use load_run instead."""
    return load_run(session, principal, experiment_id, write)

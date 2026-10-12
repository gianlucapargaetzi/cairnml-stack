"""Authorization rules shared by all routers."""

from __future__ import annotations

from fastapi import HTTPException
from mlops_common.schemas import TERMINAL_STATUSES
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Experiment, Job, Project, ProjectMember
from mlops_server.security.deps import Principal


def get_project(session: Session, slug: str) -> Project:
    project = session.scalar(select(Project).where(Project.slug == slug))
    if project is None:
        raise HTTPException(404, "project not found")
    return project


def is_member(session: Session, principal: Principal, project: Project) -> bool:
    if principal.kind != "client" or principal.user_id is None:
        return False
    if principal.is_admin:
        return True
    return session.get(ProjectMember, (project.id, principal.user_id)) is not None


def ensure_member(session: Session, principal: Principal, slug: str) -> Project:
    project = get_project(session, slug)
    if not is_member(session, principal, project):
        raise HTTPException(404, "project not found")
    return project


def load_experiment(
    session: Session, principal: Principal, experiment_id: str, write: bool
) -> Experiment:
    """Return the experiment if `principal` may read (or write) it, else 404."""
    if write:
        # Lock the row so a concurrent status change cannot interleave with this write.
        exp = session.get(Experiment, experiment_id, with_for_update=True, populate_existing=True)
    else:
        exp = session.get(Experiment, experiment_id)
    if exp is None:
        raise HTTPException(404, "experiment not found")
    if principal.kind == "run":
        allowed = exp.id == principal.experiment_id
        if write and exp.status in TERMINAL_STATUSES:
            allowed = False  # a finished run's token can no longer change its record
    elif principal.kind == "agent":
        job = session.get(Job, exp.job_id) if exp.job_id else None
        allowed = job is not None and job.agent_id == principal.id
        if write and exp.status in TERMINAL_STATUSES:
            allowed = False
    else:
        project = session.get(Project, exp.project_id)
        allowed = is_member(session, principal, project)
        if allowed and write:
            allowed = exp.owner_id == principal.user_id or principal.is_admin
    if not allowed:
        raise HTTPException(404, "experiment not found")
    return exp

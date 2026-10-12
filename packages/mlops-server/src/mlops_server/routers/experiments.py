from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from mlops_common.schemas import (
    TERMINAL_STATUSES,
    ExperimentCreate,
    ExperimentOut,
    ExperimentPatch,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Experiment, Project, ProjectMember, User
from mlops_server.security.deps import Principal, get_session, require
from mlops_server.services import access

router = APIRouter()
any_principal = require("client", "agent", "run")
# Fields that may be explicitly cleared with null; every other null in a PATCH body is ignored.
NULLABLE_FIELDS = {"git", "python_version", "platform", "script", "notes"}


def experiment_out(session: Session, exp: Experiment) -> ExperimentOut:
    project = session.get(Project, exp.project_id)
    owner = session.get(User, exp.owner_id)
    return ExperimentOut(
        id=exp.id, project=project.slug, name=exp.name, status=exp.status, source=exp.source,
        owner=owner.username, parent_id=exp.parent_id, job_id=exp.job_id, config=exp.config,
        params=exp.params, git=exp.git, datasets=exp.datasets, requirements=exp.requirements,
        argv=exp.argv, env=exp.env, python_version=exp.python_version, platform=exp.platform,
        script=exp.script, notes=exp.notes, created_at=exp.created_at,
        started_at=exp.started_at, finished_at=exp.finished_at,
    )


def apply_status(exp: Experiment, status: str) -> None:
    """Shared by the PATCH endpoint and the job lifecycle (Task 18)."""
    if exp.status in TERMINAL_STATUSES and status != exp.status:
        raise HTTPException(409, f"experiment already {exp.status}")
    now = datetime.now(UTC)
    if status == "running" and exp.started_at is None:
        exp.started_at = now
    if status in TERMINAL_STATUSES and exp.finished_at is None:
        exp.finished_at = now
    exp.status = status


@router.post("/experiments", response_model=ExperimentOut)
def create_experiment(
    body: ExperimentCreate,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
):
    project = access.ensure_member(session, principal, body.project)
    exp = Experiment(
        id=new_id("exp"), project_id=project.id, owner_id=principal.user_id, name=body.name,
        source=body.source, parent_id=body.parent_id, config=body.config,
    )
    session.add(exp)
    session.commit()
    return experiment_out(session, exp)


@router.get("/experiments", response_model=list[ExperimentOut])
def list_experiments(
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
    project: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    query = select(Experiment).order_by(Experiment.created_at.desc()).limit(limit)
    if not principal.is_admin:
        member_projects = select(ProjectMember.project_id).where(
            ProjectMember.user_id == principal.user_id
        )
        query = query.where(Experiment.project_id.in_(member_projects))
    if status:
        query = query.where(Experiment.status == status)
    if project:
        query = query.where(
            Experiment.project_id == access.ensure_member(session, principal, project).id
        )
    return [experiment_out(session, exp) for exp in session.scalars(query)]


@router.get("/experiments/{experiment_id}", response_model=ExperimentOut)
def get_experiment(
    experiment_id: str,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    return experiment_out(session, access.load_experiment(session, principal, experiment_id, False))


@router.patch("/experiments/{experiment_id}", response_model=ExperimentOut)
def patch_experiment(
    experiment_id: str,
    body: ExperimentPatch,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    exp = access.load_experiment(session, principal, experiment_id, True)
    fields = {
        name: value
        for name, value in body.model_dump(exclude_unset=True).items()
        if value is not None or name in NULLABLE_FIELDS
    }
    if "status" in fields:
        if principal.kind != "client":
            raise HTTPException(403, "only clients may set the status directly")
        apply_status(exp, fields.pop("status"))
    if "params" in fields:
        exp.params = {**exp.params, **fields.pop("params")}
    for name, value in fields.items():
        setattr(exp, name, value)
    session.commit()
    return experiment_out(session, exp)

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from mlops_common.schemas import ExperimentCreate, ExperimentOut, ExperimentPatch
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Experiment, Project
from mlops_server.security.deps import READERS, Principal, get_session, require, require_writer
from mlops_server.services import access

router = APIRouter()


def experiment_out(session: Session, experiment: Experiment) -> ExperimentOut:
    return ExperimentOut(
        id=experiment.id, project=session.get(Project, experiment.project_id).slug,
        name=experiment.name, kind=experiment.kind, description=experiment.description,
        primary_metric=experiment.primary_metric, direction=experiment.direction,
        created_at=experiment.created_at,
    )


def load_experiment(session: Session, principal: Principal, experiment_id: str) -> Experiment:
    experiment = session.get(Experiment, experiment_id)
    project = session.get(Project, experiment.project_id) if experiment else None
    if experiment is None or not access.is_member(session, principal, project):
        raise HTTPException(404, "experiment not found")
    return experiment


@router.get("/experiments", response_model=list[ExperimentOut])
def list_experiments(
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    project: str | None = None,
):
    if project:
        ids = [access.ensure_member(session, principal, project).id]
    else:
        projects = session.scalars(select(Project))
        ids = [p.id for p in projects if access.is_member(session, principal, p)]
    rows = session.scalars(
        select(Experiment).where(Experiment.project_id.in_(ids)).order_by(Experiment.name)
    )
    return [experiment_out(session, t) for t in rows]


@router.post("/experiments", response_model=ExperimentOut)
def create_experiment(
    body: ExperimentCreate,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
):
    project = access.ensure_member(session, principal, body.project)
    experiment = Experiment(
        id=new_id("exp"), project_id=project.id, name=body.name, kind=body.kind,
        description=body.description, primary_metric=body.primary_metric,
        direction=body.direction,
    )
    session.add(experiment)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "experiment already exists") from None
    return experiment_out(session, experiment)


@router.get("/experiments/{experiment_id}", response_model=ExperimentOut)
def get_experiment(
    experiment_id: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
):
    return experiment_out(session, load_experiment(session, principal, experiment_id))


@router.patch("/experiments/{experiment_id}", response_model=ExperimentOut)
def patch_experiment(
    experiment_id: str,
    body: ExperimentPatch,
    principal: Annotated[Principal, Depends(require_writer("client"))],
    session: Annotated[Session, Depends(get_session)],
):
    experiment = load_experiment(session, principal, experiment_id)
    for name, value in body.model_dump(exclude_unset=True).items():
        if name == "kind" and value is None:
            continue  # the kind is required; an explicit null leaves it as it is
        setattr(experiment, name, value)
    session.commit()
    return experiment_out(session, experiment)

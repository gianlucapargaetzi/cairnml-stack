from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from mlops_common.schemas import (
    TERMINAL_STATUSES,
    RunCreate,
    RunOut,
    RunPatch,
)
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session, object_session

from mlops_server.ids import new_id
from mlops_server.models import Experiment, MetricPoint, Project, Run, User
from mlops_server.security.deps import READERS, Principal, get_session, require
from mlops_server.services import access
from mlops_server.services.experiments import DEFAULT_EXPERIMENT, get_or_create_experiment

router = APIRouter()
any_principal = require("client", "agent", "run")
read_principal = require("client", "agent", "run", "web")
# Fields that may be explicitly cleared with null; every other null in a PATCH body is ignored.
NULLABLE_FIELDS = {"git", "python_version", "platform", "script", "notes"}


def run_out(session: Session, exp: Run) -> RunOut:
    project = session.get(Project, exp.project_id)
    owner = session.get(User, exp.owner_id)
    experiment = session.get(Experiment, exp.experiment_id) if exp.experiment_id else None
    return RunOut(
        id=exp.id, project=project.slug, name=exp.name, status=exp.status, source=exp.source,
        owner=owner.username, experiment=experiment.name if experiment else DEFAULT_EXPERIMENT,
        parent_id=exp.parent_id, job_id=exp.job_id, config=exp.config,
        params=exp.params, git=exp.git, datasets=exp.datasets, requirements=exp.requirements,
        argv=exp.argv, env=exp.env, python_version=exp.python_version, platform=exp.platform,
        script=exp.script, notes=exp.notes, created_at=exp.created_at,
        started_at=exp.started_at, finished_at=exp.finished_at,
    )


def apply_status(exp: Run, status: str) -> None:
    """Shared by the PATCH endpoint and the job lifecycle (Experiment 18).

    Locks the row and re-reads it, so concurrent status changes serialise. The caller
    must commit; the lock is held until then.
    """
    object_session(exp).refresh(exp, with_for_update=True)
    if exp.status in TERMINAL_STATUSES:
        raise HTTPException(409, f"run already {exp.status}")
    now = datetime.now(UTC)
    if status == "running" and exp.started_at is None:
        exp.started_at = now
    if status in TERMINAL_STATUSES and exp.finished_at is None:
        exp.finished_at = now
    exp.status = status


@router.post("/runs", response_model=RunOut)
def create_run(
    body: RunCreate,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
):
    project = access.ensure_member(session, principal, body.project)
    experiment = get_or_create_experiment(
        session, project.id, body.experiment, body.primary_metric, body.direction
    )
    exp = Run(
        id=new_id("run"), project_id=project.id, owner_id=principal.user_id, name=body.name,
        source=body.source, parent_id=body.parent_id, config=body.config,
        experiment_id=experiment.id,
    )
    session.add(exp)
    session.commit()
    return run_out(session, exp)


SORTS = {"created_at": Run.created_at, "name": Run.name, "status": Run.status}
MAX_COMPARE, MAX_POINTS = 10, 500


def _accessible_project_ids(session: Session, principal: Principal) -> list[str]:
    projects = session.scalars(select(Project))
    return [p.id for p in projects if access.is_member(session, principal, p)]


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    response: Response,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    project: str | None = None,
    experiment: str | None = None,
    status: str | None = None,
    q: str | None = None,
    sort: str = Query("created_at", pattern="^(created_at|name|status)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    ids = _accessible_project_ids(session, principal)
    if project:
        ids = [access.ensure_member(session, principal, project).id]
    query = select(Run).where(Run.project_id.in_(ids))
    if experiment:
        query = query.join(Experiment, Experiment.id == Run.experiment_id).where(
            Experiment.name == experiment
        )
    if status:
        query = query.where(Run.status == status)
    if q:
        query = query.where(Run.name.icontains(q, autoescape=True))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    column = SORTS[sort]
    query = query.order_by(column.desc() if order == "desc" else column.asc(), Run.id)
    response.headers["X-Total-Count"] = str(total)
    return [
        run_out(session, e) for e in session.scalars(query.limit(limit).offset(offset))
    ]


def _sample_ranks(count: int) -> list[int]:
    """1-based ranks of at most MAX_POINTS evenly spaced points, first and last included."""
    if count <= MAX_POINTS:
        return list(range(1, count + 1))
    span = count - 1
    return sorted({round(i * span / (MAX_POINTS - 1)) + 1 for i in range(MAX_POINTS)})


def _series(session: Session, run_id: str, name: str, count: int) -> list[list]:
    rank = func.row_number().over(
        order_by=(MetricPoint.step, MetricPoint.ts, MetricPoint.id)
    ).label("rn")
    inner = (
        select(MetricPoint.step, MetricPoint.value, rank)
        .where(MetricPoint.run_id == run_id, MetricPoint.name == name)
        .subquery()
    )
    query = select(inner.c.step, inner.c.value, inner.c.rn).where(
        inner.c.rn.in_(_sample_ranks(count))
    )
    return [
        [step if step is not None else rn, value]
        for step, value, rn in session.execute(query.order_by(inner.c.rn))
    ]


@router.get("/runs/compare")
def compare(
    ids: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
):
    wanted = list(dict.fromkeys(i for i in ids.split(",") if i))
    if not 2 <= len(wanted) <= MAX_COMPARE:
        raise HTTPException(422, f"compare between 2 and {MAX_COMPARE} runs")
    runs = [access.load_run(session, principal, i, False) for i in wanted]
    out = []
    for exp in runs:
        stats = session.execute(
            select(
                MetricPoint.name, func.count(), func.min(MetricPoint.value),
                func.max(MetricPoint.value),
            )
            .where(MetricPoint.run_id == exp.id)
            .group_by(MetricPoint.name)
        ).all()
        last = {
            row.name: row.value
            for row in session.execute(
                select(MetricPoint.name, MetricPoint.value)
                .where(MetricPoint.run_id == exp.id)
                .ext(distinct_on(MetricPoint.name))
                .order_by(
                    MetricPoint.name, MetricPoint.step.desc().nulls_last(), MetricPoint.ts.desc()
                )
            )
        }
        metrics = {
            name: {
                "count": count, "min": low, "max": high, "last": last[name],
                "series": _series(session, exp.id, name, count),
            }
            for name, count, low, high in stats
        }
        out.append({**run_out(session, exp).model_dump(mode="json"), "metrics": metrics})
    return {"runs": out}


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(
    run_id: str,
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    return run_out(session, access.load_run(session, principal, run_id, False))


@router.patch("/runs/{run_id}", response_model=RunOut)
def patch_run(
    run_id: str,
    body: RunPatch,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    exp = access.load_run(session, principal, run_id, True)
    fields = {
        name: value
        for name, value in body.model_dump(exclude_unset=True).items()
        if value is not None or name in NULLABLE_FIELDS
    }
    if "status" in fields:
        if principal.kind != "client":
            raise HTTPException(403, "only clients may set the status directly")
        if exp.job_id is not None:
            # The job is authoritative: a client status write here could block its agent's
            # terminal report (apply_status 409s on terminal runs).
            raise HTTPException(403, "status of a job run is controlled by its job")
        apply_status(exp, fields.pop("status"))
    if "params" in fields:
        exp.params = {**exp.params, **fields.pop("params")}
    for name, value in fields.items():
        setattr(exp, name, value)
    session.commit()
    return run_out(session, exp)

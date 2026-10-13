"""Explorer search: runs and their metric traces, filtered by the query language and limited to
the projects the caller may read. The response shapes are documented in
docs/explorer_api.md."""

from __future__ import annotations

from typing import Any

from mlops_common.schemas import TERMINAL_STATUSES
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mlops_server.models import (
    Experiment,
    MetricPoint,
    MetricSeries,
    Project,
    Run,
    RunTag,
    Tag,
    User,
)
from mlops_server.security.deps import Principal
from mlops_server.services import access
from mlops_server.services.metrics import sample_ranks
from mlops_server.services.query import DEFAULT_EXPERIMENT, FilterError, compile_filter

MAX_TRACES_PER_RUN = 50
MAX_PARAM_RUNS = 1000  # runs scanned to list a project's parameters


def search(
    session: Session,
    principal: Principal,
    *,
    query: str | None,
    project: str | None,
    limit: int,
    offset: int,
    density: int,
    metric_search: bool,
) -> tuple[dict[str, Any], int]:
    """Runs matching `query`, each with its props, params and sampled traces, and the total."""
    compiled = compile_filter(query)
    if compiled.metric is not None and not metric_search:
        raise FilterError("metric.* filters belong to /api/v1/explorer/runs/search/metric")
    ids = access.accessible_project_ids(session, principal)
    if project is not None:
        project_id = session.scalar(select(Project.id).where(Project.slug == project))
        ids = [project_id] if project_id in ids else []
    conditions = [Run.project_id.in_(ids)]
    if compiled.run is not None:
        conditions.append(compiled.run)
    if compiled.metric is not None:
        conditions.append(Run.id.in_(select(MetricSeries.run_id).where(compiled.metric)))
    total = session.scalar(select(func.count()).select_from(Run).where(*conditions))
    runs = session.scalars(
        select(Run).where(*conditions)
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(limit).offset(offset)
    ).all()
    props = _props(session, runs)
    body = {
        run.id: {
            "props": props[run.id],
            "params": run.params,
            "traces": _traces(session, run.id, compiled.metric, density),
        }
        for run in runs
    }
    return {"runs": body, "progress": [len(body), len(body)]}, total


def run_info(session: Session, run: Run) -> dict[str, Any]:
    """The props and params of one run, and the list of its metric series (without points)."""
    series = session.execute(
        select(MetricSeries.name, MetricSeries.context)
        .where(MetricSeries.run_id == run.id)
        .order_by(MetricSeries.name, MetricSeries.id)
    ).all()
    return {
        "props": _props(session, [run])[run.id],
        "params": run.params,
        "traces": {"metric": [{"name": name, "context": context} for name, context in series]},
        "artifacts": [],
    }


def _props(session: Session, runs: list[Run]) -> dict[str, dict[str, Any]]:
    """Display fields for each run. Project, experiment, creator and tags are read once per page."""
    if not runs:
        return {}
    slugs = dict(session.execute(
        select(Project.id, Project.slug).where(Project.id.in_({r.project_id for r in runs}))
    ).all())
    experiment_ids = {run.experiment_id for run in runs if run.experiment_id}
    experiments = {
        row.id: row for row in session.execute(
            select(Experiment.id, Experiment.name, Experiment.description)
            .where(Experiment.id.in_(experiment_ids))
        )
    } if experiment_ids else {}
    owners = dict(session.execute(
        select(User.id, User.username).where(User.id.in_({r.owner_id for r in runs}))
    ).all())
    tags: dict[str, list[dict[str, Any]]] = {}
    for run_id, tag_id, name, color in session.execute(
        select(RunTag.run_id, Tag.id, Tag.name, Tag.color)
        .join(Tag, Tag.id == RunTag.tag_id)
        .where(RunTag.run_id.in_([run.id for run in runs]))
        .order_by(Tag.name)
    ):
        tags.setdefault(run_id, []).append({"id": tag_id, "name": name, "color": color})
    out = {}
    for run in runs:
        experiment = experiments.get(run.experiment_id)
        out[run.id] = {
            "name": run.name,
            "description": run.description or "",
            "archived": run.archived,
            "status": run.status,
            "active": run.status not in TERMINAL_STATUSES,
            "project": slugs[run.project_id],
            "experiment": (
                {"id": experiment.id, "name": experiment.name,
                 "description": experiment.description or ""}
                if experiment else
                {"id": None, "name": DEFAULT_EXPERIMENT, "description": ""}
            ),
            "creator": {"username": owners.get(run.owner_id)},
            "creation_time": run.created_at.timestamp(),
            "end_time": run.finished_at.timestamp() if run.finished_at else None,
            "created_at": run.created_at.isoformat(),
            "tags": tags.get(run.id, []),
        }
    return out


def _traces(
    session: Session, run_id: str, metric_clause, density: int
) -> list[dict[str, Any]]:
    query = select(MetricSeries).where(MetricSeries.run_id == run_id)
    if metric_clause is not None:
        query = query.where(metric_clause)
    series = session.scalars(query.order_by(MetricSeries.name, MetricSeries.id)
                             .limit(MAX_TRACES_PER_RUN)).all()
    return [
        {"name": s.name, "context": s.context, **_sampled_points(session, s.id, density)}
        for s in series
    ]


def _sampled_points(session: Session, series_id: int, density: int) -> dict[str, Any]:
    """`count`, the `last` value and at most `density` evenly spaced [step, value] pairs."""
    count = session.scalar(
        select(func.count()).select_from(MetricPoint).where(MetricPoint.series_id == series_id)
    )
    if not count:
        return {"count": 0, "last": None, "points": []}
    rank = func.row_number().over(
        order_by=(MetricPoint.step, MetricPoint.ts, MetricPoint.id)
    ).label("rn")
    inner = (
        select(MetricPoint.step, MetricPoint.value, MetricPoint.epoch, MetricPoint.ts, rank)
        .where(MetricPoint.series_id == series_id)
        .subquery()
    )
    rows = session.execute(
        select(inner.c.step, inner.c.value, inner.c.epoch, inner.c.ts, inner.c.rn)
        .where(inner.c.rn.in_(sample_ranks(count, density)))
        .order_by(inner.c.rn)
    ).all()
    points = [
        [step if step is not None else rn, value, epoch, ts]
        for step, value, epoch, ts, rn in rows
    ]
    # The last rank is always sampled, so its value is the series' last value.
    return {"count": count, "last": points[-1][1], "points": points}


def project_params(session: Session, project_id: str) -> dict[str, Any]:
    """Parameter paths and metric names (with their context keys) used in one project."""
    recent = session.scalars(
        select(Run.params).where(Run.project_id == project_id)
        .order_by(Run.created_at.desc()).limit(MAX_PARAM_RUNS)
    ).all()
    paths: set[str] = set()
    for params in recent:
        paths.update(_paths(params))
    metric: dict[str, set[str]] = {}
    for name, context in session.execute(
        select(MetricSeries.name, MetricSeries.context)
        .join(Run, Run.id == MetricSeries.run_id)
        .where(Run.project_id == project_id)
        .distinct()
    ):
        metric.setdefault(name, set()).update(context.keys())
    return {
        "params": sorted(paths),
        "metric": {name: sorted(keys) for name, keys in sorted(metric.items())},
    }


def _paths(value: Any, prefix: str = "") -> list[str]:
    """Dotted paths to every leaf of a params dict, such as hparams.lr."""
    if not isinstance(value, dict):
        return [prefix] if prefix else []
    found: list[str] = []
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict) and child:
            found.extend(_paths(child, path))
        else:
            found.append(path)
    return found

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
    Sequence,
    SequenceItem,
    Tag,
    User,
)
from mlops_server.security.deps import Principal
from mlops_server.services import access
from mlops_server.services.metrics import sample_ranks
from mlops_server.services.query import (
    DEFAULT_EXPERIMENT,
    SEQUENCE_KINDS,
    FilterError,
    compile_filter,
)

MAX_TRACES_PER_RUN = 50
MAX_SEQUENCES_PER_RUN = 50
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
    if compiled.sequences:
        kind = next(iter(compiled.sequences))
        raise FilterError(
            f"{_plural(kind)}.* filters belong to /api/v1/explorer/runs/search/{_plural(kind)}"
        )
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


def search_sequences(
    session: Session,
    principal: Principal,
    *,
    kind: str,
    query: str | None,
    project: str | None,
    limit: int,
    offset: int,
    record_range: tuple[int, int] | None,
    record_density: int,
    index_range: tuple[int, int] | None,
    index_density: int,
    blob_url,
) -> tuple[dict[str, Any], int]:
    """Runs with at least one sequence of `kind` that matches `query`, each with its sequences'
    sampled items. `blob_url(key)` gives a presigned GET for a stored blob, or None."""
    compiled = compile_filter(query)
    if compiled.metric is not None:
        raise FilterError("metric.* filters belong to /api/v1/explorer/runs/search/metric")
    for other in compiled.sequences:
        if other != kind:
            raise FilterError(
                f"{_plural(other)}.* filters belong to "
                f"/api/v1/explorer/runs/search/{_plural(other)}"
            )
    ids = access.accessible_project_ids(session, principal)
    if project is not None:
        project_id = session.scalar(select(Project.id).where(Project.slug == project))
        ids = [project_id] if project_id in ids else []
    sequence_clause = compiled.sequences.get(kind, Sequence.kind == kind)
    conditions = [
        Run.project_id.in_(ids), Run.id.in_(select(Sequence.run_id).where(sequence_clause)),
    ]
    if compiled.run is not None:
        conditions.append(compiled.run)
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
            "sequences": _sequences(
                session, run, kind, sequence_clause, record_range, record_density,
                index_range, index_density, blob_url,
            ),
        }
        for run in runs
    }
    ranges = _ranges(session, sequence_clause, conditions, body)
    for run_body in body.values():
        run_body["ranges"] = ranges
    return {"runs": body, "progress": [len(body), len(body)]}, total


def _ranges(session: Session, sequence_clause, conditions, body) -> dict[str, list[int]]:
    """The step and index ranges the explorer's sliders read: `total` covers every matching item
    of the search, `used` the items in this response. Each range is [low, high + 1]."""
    low_step, high_step, low_idx, high_idx = session.execute(
        select(
            func.min(SequenceItem.step), func.max(SequenceItem.step),
            func.min(SequenceItem.idx), func.max(SequenceItem.idx),
        )
        .join(Sequence, Sequence.id == SequenceItem.sequence_id)
        .where(Sequence.run_id.in_(select(Run.id).where(*conditions)), sequence_clause)
    ).one()
    items = [item for run_body in body.values() for seq in run_body["sequences"]
             for item in seq["items"]]
    steps = [item["step"] for item in items if item["step"] is not None]
    indices = [item["idx"] for item in items]
    return {
        "record_range_total": _closed_range(low_step, high_step),
        "index_range_total": _closed_range(low_idx, high_idx),
        "record_range_used": _closed_range(min(steps, default=None), max(steps, default=None)),
        "index_range_used": _closed_range(min(indices, default=None), max(indices, default=None)),
    }


def _closed_range(low: int | None, high: int | None) -> list[int]:
    if low is None or high is None:
        return [0, 1]
    return [low, high + 1]


def _plural(kind: str) -> str:
    return next(plural for plural, singular in SEQUENCE_KINDS.items() if singular == kind)


def _sequences(
    session: Session, run: Run, kind: str, clause, record_range, record_density,
    index_range, index_density, blob_url,
) -> list[dict[str, Any]]:
    sequences = session.scalars(
        select(Sequence).where(Sequence.run_id == run.id, Sequence.kind == kind, clause)
        .order_by(Sequence.name, Sequence.id).limit(MAX_SEQUENCES_PER_RUN)
    ).all()
    return [
        {
            "name": sequence.name,
            "context": sequence.context,
            "count": session.scalar(
                select(func.count()).select_from(SequenceItem)
                .where(SequenceItem.sequence_id == sequence.id)
            ),
            "items": _sampled_items(
                session, sequence.id, record_range, record_density, index_range,
                index_density, blob_url,
            ),
        }
        for sequence in sequences
    ]


def _sampled_items(
    session: Session, sequence_id: int, record_range, record_density, index_range,
    index_density, blob_url,
) -> list[dict[str, Any]]:
    """Items of the sampled steps, and at most `index_density` evenly spaced indices per step."""
    steps = [
        step for (step,) in session.execute(
            select(SequenceItem.step).where(SequenceItem.sequence_id == sequence_id)
            .distinct().order_by(SequenceItem.step)
        )
    ]
    if record_range is not None:
        low, high = record_range
        steps = [step for step in steps if step is not None and low <= step <= high]
    steps = [steps[rank - 1] for rank in sample_ranks(len(steps), record_density)] if steps else []
    if not steps:
        return []
    query = select(SequenceItem).where(
        SequenceItem.sequence_id == sequence_id, SequenceItem.step.in_(steps)
    )
    if index_range is not None:
        query = query.where(SequenceItem.idx.between(*index_range))
    rows = session.scalars(query.order_by(SequenceItem.step, SequenceItem.idx)).all()
    by_step: dict[int | None, list[SequenceItem]] = {}
    for row in rows:
        by_step.setdefault(row.step, []).append(row)
    out = []
    for step in steps:
        group = by_step.get(step, [])
        ranks = sample_ranks(len(group), index_density) if group else []
        picks = [group[rank - 1] for rank in ranks]
        out.extend(_item_out(item, blob_url) for item in picks)
    return out


def _item_out(item: SequenceItem, blob_url) -> dict[str, Any]:
    out: dict[str, Any] = {
        "step": item.step, "idx": item.idx, "epoch": item.epoch, "ts": item.ts,
        "caption": item.caption, "format": item.format, "width": item.width,
        "height": item.height,
    }
    if item.blob_key is not None:
        out["blob_uri"] = blob_url(item.blob_key) if blob_url else None
    if item.text is not None:
        out["text"] = item.text
    if item.data is not None:
        out["data"] = item.data
    return out


def run_info(session: Session, run: Run) -> dict[str, Any]:
    """The props and params of one run, the list of its metric series (without points), and the
    sequences of each kind (name and context, without items)."""
    series = session.execute(
        select(MetricSeries.name, MetricSeries.context)
        .where(MetricSeries.run_id == run.id)
        .order_by(MetricSeries.name, MetricSeries.id)
    ).all()
    traces: dict[str, list[dict[str, Any]]] = {
        "metric": [{"name": name, "context": context} for name, context in series],
    }
    sequences = session.execute(
        select(Sequence.kind, Sequence.name, Sequence.context)
        .where(Sequence.run_id == run.id)
        .order_by(Sequence.name, Sequence.id)
    ).all()
    for plural, singular in SEQUENCE_KINDS.items():
        traces[plural] = [
            {"name": name, "context": context} for kind, name, context in sequences
            if kind == singular
        ]
    return {
        "props": _props(session, [run])[run.id],
        "params": run.params,
        "traces": traces,
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
    listing: dict[str, Any] = {
        "params": sorted(paths),
        "metric": {name: sorted(keys) for name, keys in sorted(metric.items())},
    }
    for plural, singular in SEQUENCE_KINDS.items():
        names: dict[str, set[str]] = {}
        for name, context in session.execute(
            select(Sequence.name, Sequence.context)
            .join(Run, Run.id == Sequence.run_id)
            .where(Run.project_id == project_id, Sequence.kind == singular)
            .distinct()
        ):
            names.setdefault(name, set()).update(context.keys())
        listing[plural] = {name: sorted(keys) for name, keys in sorted(names.items())}
    return listing


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

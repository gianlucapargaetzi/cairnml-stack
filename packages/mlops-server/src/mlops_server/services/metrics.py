"""Metric series: one series per run, metric name and context. Points belong to a series."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mlops_server.models import MetricPoint, MetricSeries


def series_id(session: Session, run_id: str, name: str, context: dict[str, Any]) -> int:
    """The id of the series for this run, name and context, created when it does not exist."""
    found = session.scalar(
        select(MetricSeries.id).where(
            MetricSeries.run_id == run_id,
            MetricSeries.name == name,
            MetricSeries.context == context,
        )
    )
    if found is not None:
        return found
    # Two requests may create the same series at once; the unique key lets one of them win.
    created = session.execute(
        insert(MetricSeries)
        .values(run_id=run_id, name=name, context=context)
        .on_conflict_do_nothing(index_elements=["run_id", "name", "context"])
        .returning(MetricSeries.id)
    ).scalar()
    if created is not None:
        return created
    return session.scalar(
        select(MetricSeries.id).where(
            MetricSeries.run_id == run_id,
            MetricSeries.name == name,
            MetricSeries.context == context,
        )
    )


MAX_POINTS = 500


def sample_ranks(count: int, max_points: int = MAX_POINTS) -> list[int]:
    """1-based ranks of at most `max_points` evenly spaced points, first and last included."""
    if count <= max_points:
        return list(range(1, count + 1))
    if max_points <= 1:
        return [1]
    span = count - 1
    return sorted({round(i * span / (max_points - 1)) + 1 for i in range(max_points)})


def default_context_points(*columns):
    """Points of the default series (empty context). The legacy metric endpoints and the
    run summaries read only these, so context series do not change their numbers."""
    return (
        select(*columns)
        .select_from(MetricPoint)
        .join(MetricSeries, MetricSeries.id == MetricPoint.series_id)
        .where(MetricSeries.context == {})
    )

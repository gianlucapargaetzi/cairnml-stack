from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from mlops_server.models import Experiment, MetricPoint, MetricSeries, Run
from mlops_server.services.metrics import default_context_points


def last_values(session: Session, run_ids: list[str], metric: str) -> dict[str, float]:
    """The last logged value of `metric` for each run that has one."""
    if not run_ids:
        return {}
    rows = session.execute(
        default_context_points(MetricSeries.run_id, MetricPoint.value)
        .where(MetricSeries.run_id.in_(run_ids), MetricSeries.name == metric)
        .ext(distinct_on(MetricSeries.run_id))
        .order_by(
            MetricSeries.run_id,
            MetricPoint.step.desc().nulls_last(),
            MetricPoint.ts.desc(),
        )
    )
    return {run_id: value for run_id, value in rows}


def experiment_stats(session: Session, experiments: list[Experiment]) -> dict[str, dict]:
    """Run counts, last activity and the best run per experiment.

    `best` compares the last logged primary metric of every run, in the experiment's
    direction (min unless it is "max"). A experiment without a primary metric has no best.
    """
    ids = [t.id for t in experiments]
    counts = {
        experiment_id: (total, running, last)
        for experiment_id, total, running, last in session.execute(
            select(
                Run.experiment_id,
                func.count(),
                func.count().filter(Run.status == "running"),
                func.max(Run.created_at),
            )
            .where(Run.experiment_id.in_(ids))
            .group_by(Run.experiment_id)
        )
    }
    out: dict[str, dict] = {}
    for experiment in experiments:
        total, running, last = counts.get(experiment.id, (0, 0, None))
        best = None
        if experiment.primary_metric and total:
            runs = session.execute(
                select(Run.id, Run.name).where(Run.experiment_id == experiment.id)
            ).all()
            names = {run_id: name for run_id, name in runs}
            values = last_values(session, list(names), experiment.primary_metric)
            if values:
                pick = max if experiment.direction == "max" else min
                winner = pick(values, key=values.get)
                best = {"run_id": winner, "name": names[winner], "value": values[winner]}
        out[experiment.id] = {
            "runs": total,
            "running": running,
            "last_activity": last.isoformat() if last else None,
            "best": best,
        }
    return out

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from mlops_server.models import Experiment, MetricPoint, Task


def last_values(session: Session, experiment_ids: list[str], metric: str) -> dict[str, float]:
    """The last logged value of `metric` for each experiment that has one."""
    if not experiment_ids:
        return {}
    rows = session.execute(
        select(MetricPoint.experiment_id, MetricPoint.value)
        .where(MetricPoint.experiment_id.in_(experiment_ids), MetricPoint.name == metric)
        .ext(distinct_on(MetricPoint.experiment_id))
        .order_by(
            MetricPoint.experiment_id,
            MetricPoint.step.desc().nulls_last(),
            MetricPoint.ts.desc(),
        )
    )
    return {experiment_id: value for experiment_id, value in rows}


def task_stats(session: Session, tasks: list[Task]) -> dict[str, dict]:
    """Experiment counts, last activity and the best experiment per task.

    `best` compares the last logged primary metric of every experiment, in the task's
    direction (min unless it is "max"). A task without a primary metric has no best.
    """
    ids = [t.id for t in tasks]
    counts = {
        task_id: (total, running, last)
        for task_id, total, running, last in session.execute(
            select(
                Experiment.task_id,
                func.count(),
                func.count().filter(Experiment.status == "running"),
                func.max(Experiment.created_at),
            )
            .where(Experiment.task_id.in_(ids))
            .group_by(Experiment.task_id)
        )
    }
    out: dict[str, dict] = {}
    for task in tasks:
        total, running, last = counts.get(task.id, (0, 0, None))
        best = None
        if task.primary_metric and total:
            experiments = session.execute(
                select(Experiment.id, Experiment.name).where(Experiment.task_id == task.id)
            ).all()
            names = {exp_id: name for exp_id, name in experiments}
            values = last_values(session, list(names), task.primary_metric)
            if values:
                pick = max if task.direction == "max" else min
                winner = pick(values, key=values.get)
                best = {"experiment_id": winner, "name": names[winner], "value": values[winner]}
        out[task.id] = {
            "experiments": total,
            "running": running,
            "last_activity": last.isoformat() if last else None,
            "best": best,
        }
    return out

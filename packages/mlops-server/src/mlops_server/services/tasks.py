"""Tasks: one aspect of a project (training, augmentation, testing, ...)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Task

DEFAULT_TASK = "general"
# Checked in order: the first keyword found in the lower-cased name decides the kind.
_KINDS = [
    ("train", "training"), ("augment", "augmentation"), ("test", "testing"),
    ("eval", "evaluation"), ("compil", "compilation"), ("build", "compilation"),
    ("infer", "inference"), ("prep", "data-preparation"), ("data", "data-preparation"),
]


def guess_kind(name: str) -> str:
    lowered = name.lower()
    for needle, kind in _KINDS:
        if needle in lowered:
            return kind
    return "other"


def get_or_create_task(
    session: Session,
    project_id: str,
    name: str,
    primary_metric: str | None = None,
    direction: str | None = None,
) -> Task:
    query = select(Task).where(Task.project_id == project_id, Task.name == name)
    task = session.scalar(query)
    if task is None:
        try:
            with session.begin_nested():
                task = Task(
                    id=new_id("tsk"), project_id=project_id, name=name, kind=guess_kind(name),
                    primary_metric=primary_metric,
                    direction=direction if primary_metric else None,
                )
                session.add(task)
        except IntegrityError:  # another request created the same task at the same moment
            task = session.scalar(query)
    elif primary_metric and not task.primary_metric:
        task.primary_metric, task.direction = primary_metric, direction
    return task

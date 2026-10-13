"""Experiments: one aspect of a project (training, augmentation, testing, ...)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Experiment

DEFAULT_EXPERIMENT = "general"
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


def get_or_create_experiment(
    session: Session,
    project_id: str,
    name: str,
    primary_metric: str | None = None,
    direction: str | None = None,
) -> Experiment:
    query = select(Experiment).where(Experiment.project_id == project_id, Experiment.name == name)
    experiment = session.scalar(query)
    if experiment is None:
        try:
            with session.begin_nested():
                experiment = Experiment(
                    id=new_id("exp"), project_id=project_id, name=name, kind=guess_kind(name),
                    primary_metric=primary_metric,
                    direction=direction if primary_metric else None,
                )
                session.add(experiment)
        except IntegrityError:  # another request created the same experiment at the same moment
            experiment = session.scalar(query)
    elif primary_metric and not experiment.primary_metric:
        experiment.primary_metric, experiment.direction = primary_metric, direction
    return experiment

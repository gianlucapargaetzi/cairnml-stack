"""The explorer filter language: what it accepts, what it refuses, and that values stay bound."""

from __future__ import annotations

import pytest
from mlops_server.models import Run
from mlops_server.services.query import FilterError, compile_filter
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

ACCEPTED = [
    "run.name == 'baseline'",
    "run.name != 'x' and run.name.startswith('vis')",
    "run.hparams.lr > 0.01",
    "run.hparams.lr >= -1",
    "run.batch == 32",
    "run.hparams.flag == True",
    "run.hparams.flag",
    "run.hparams.model != None",
    "run.hparams.tag in ['a', 'b']",
    "run.lr not in [0.1, 0.2]",
    "run.archived == False",
    "run.archived",
    "run.active == True",
    "run.experiment == 'training'",
    "run.project in ['vision/seg']",
    "run.creation_time > 1700000000",
    "run.opt.name == 'adam' or run.opt.name == 'sgd'",
    "not run.archived",
    "any(t.name in ['vision'] for t in run.tags)",
    "any(t.name == 'fast' for t in run.tags) and run.name == 'x'",
    "metric.name == 'loss' and metric.context.subset == 'val'",
    "metric.name in ['loss', 'acc']",
    "",
]

REFUSED = {
    "run.name == 'x' or metric.name == 'loss'": "cannot be combined",
    "__import__('os').system('id')": "only startswith",
    "run.name == open('/etc/passwd')": "values must be",
    "lambda: 1": "not allowed",
    "run.name == 'a' if True else 'b'": "not allowed",
    "metric.last > 0.5": "not supported yet",
    "images.name == 'x'": "not supported yet",
    "run.tags == 'x'": "inside any",
    "any(t.name in 'x' for t in run.tags)": "list of strings",
    "1 < run.hparams.lr < 3": "chained",
    "run.name == run.hash": "values must be",
    "run.name.upper() == 'X'": "left side of a comparison",
    "run.hparams.lr ** 2 > 1": "left side of a comparison",
    "x.y == 1": "unknown name",
    "run.name == {'a': 1}": "values must be",
    "run.archived == 'yes'": "== True or == False",
    "run.creation_time == 'now'": "number of seconds",
    "run.name == 'a'; import os": "not a valid expression",
    "run.name.startswith(1)": "takes a string",
    "run.name": "not booleans",
    "run.name == True": "not booleans",
    "run.hparams.x > 1 and run.name": "not booleans",
    "run.name == 'x' " + "and run.name == 'x' " * 200: "longer than",
}


@pytest.mark.parametrize("text", ACCEPTED)
def test_valid_filters_compile(text):
    compiled = compile_filter(text)
    assert text == "" or compiled.run is not None or compiled.metric is not None


@pytest.mark.parametrize("text", list(REFUSED))
def test_invalid_filters_are_refused_with_a_reason(text):
    with pytest.raises(FilterError, match=REFUSED[text]):
        compile_filter(text)


def test_user_values_are_bound_parameters_never_sql_text():
    payload = "x'; DROP TABLE runs; --"
    compiled = compile_filter(f"run.name == \"{payload}\" and run.hparams.note == \"{payload}\"")
    sql = str(select(Run.id).where(compiled.run).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False}
    ))
    assert "DROP" not in sql and payload not in sql
    params = select(Run.id).where(compiled.run).compile(dialect=postgresql.dialect()).params
    assert payload in params.values()


def test_startswith_is_escaped_for_like():
    compiled = compile_filter("run.name.startswith('50%_')")
    sql = str(select(Run.id).where(compiled.run).compile(dialect=postgresql.dialect()))
    assert "ESCAPE" in sql


def test_run_and_metric_clauses_split_under_and():
    compiled = compile_filter("run.name == 'a' and metric.name == 'loss'")
    assert compiled.run is not None and compiled.metric is not None

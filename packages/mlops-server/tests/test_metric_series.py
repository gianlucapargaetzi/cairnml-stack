"""Metric series: points carry a context, and the legacy endpoints report the default series."""

from __future__ import annotations

import pytest
from mlops_server.models import MetricPoint, MetricSeries
from sqlalchemy import func, select


def _run(dev, make_project) -> str:
    make_project("vision/seg", members=["dev"])
    return dev.http.post("/api/v1/runs", json={"project": "vision/seg", "name": "n"}).json()["id"]


def _count(app, model, **where) -> int:
    with app.state.session_factory() as session:
        query = select(func.count()).select_from(model)
        for column, value in where.items():
            query = query.where(getattr(model, column) == value)
        return session.scalar(query)


def test_context_points_are_stored_apart_and_hidden_from_the_default_read(
    server, enroll_client, make_project, app
):
    dev = enroll_client("dev")
    run = _run(dev, make_project)
    points = [
        {"name": "loss", "value": 1.0, "step": 0, "ts": 1},
        {"name": "loss", "value": 2.0, "step": 0, "ts": 1, "context": {"subset": "val"}},
        {"name": "loss", "value": 3.0, "step": 1, "ts": 2, "context": {"subset": "val"}},
    ]
    posted = dev.http.post(f"/api/v1/runs/{run}/metrics", json={"points": points})
    assert posted.json() == {"accepted": 3}

    default = dev.http.get(f"/api/v1/runs/{run}/metrics").json()
    assert [p["value"] for p in default["loss"]] == [1.0]
    assert _count(app, MetricSeries, run_id=run) == 2
    assert _count(app, MetricPoint) == 3


def test_one_series_per_run_name_and_context(server, enroll_client, make_project, app):
    dev = enroll_client("dev")
    run = _run(dev, make_project)
    point = {"name": "acc", "value": 0.5, "step": 0, "ts": 1, "context": {"subset": "val"}}
    for _ in range(2):
        dev.http.post(f"/api/v1/runs/{run}/metrics", json={"points": [point]})
    assert _count(app, MetricSeries, run_id=run, name="acc") == 1
    assert _count(app, MetricPoint) == 2


def test_epoch_is_stored(server, enroll_client, make_project, app):
    dev = enroll_client("dev")
    run = _run(dev, make_project)
    point = {"name": "loss", "value": 0.1, "step": 4, "epoch": 2, "ts": 1}
    dev.http.post(f"/api/v1/runs/{run}/metrics", json={"points": [point]})
    with app.state.session_factory() as session:
        stored = session.scalar(select(MetricPoint))
        assert (stored.step, stored.epoch) == (4, 2)


@pytest.mark.parametrize(
    "context",
    [{"subset": [1, 2]}, {"nested": {"a": 1}}, {f"k{i}": 1 for i in range(9)}],
)
def test_context_must_be_a_few_simple_values(server, enroll_client, make_project, app, context):
    dev = enroll_client("dev")
    run = _run(dev, make_project)
    point = {"name": "loss", "value": 1.0, "ts": 1, "context": context}
    rejected = dev.http.post(f"/api/v1/runs/{run}/metrics", json={"points": [point]})
    assert rejected.status_code == 422
    assert _count(app, MetricSeries) == 0


def test_run_description_and_archived_flag_round_trip(server, enroll_client, make_project):
    dev = enroll_client("dev")
    run = _run(dev, make_project)
    patched = dev.http.patch(
        f"/api/v1/runs/{run}", json={"description": "baseline", "archived": True}
    )
    assert patched.status_code == 200
    body = dev.http.get(f"/api/v1/runs/{run}").json()
    assert body["description"] == "baseline" and body["archived"] is True

    cleared = dev.http.patch(f"/api/v1/runs/{run}", json={"description": None})
    assert cleared.json()["description"] is None
    assert cleared.json()["archived"] is True


def test_run_name_can_be_changed(server, enroll_client, make_project):
    dev = enroll_client("dev")
    run = _run(dev, make_project)
    assert dev.http.patch(f"/api/v1/runs/{run}", json={"name": "lr-0.1"}).json()["name"] == "lr-0.1"
    assert dev.http.patch(f"/api/v1/runs/{run}", json={"name": ""}).status_code == 422


@pytest.mark.parametrize(
    "context",
    [{"k" * 65: 1}, {"subset": "v" * 129}],
)
def test_oversized_context_keys_and_values_are_refused(
    server, enroll_client, make_project, app, context
):
    dev = enroll_client("dev")
    run = _run(dev, make_project)
    point = {"name": "loss", "value": 1.0, "ts": 1, "context": context}
    assert dev.http.post(f"/api/v1/runs/{run}/metrics", json={"points": [point]}).status_code == 422
    assert _count(app, MetricSeries) == 0

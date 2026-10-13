"""Explorer API v1: search, run actions, tags and bookmarks, with project scoping."""

from __future__ import annotations

import pytest
from mlops_server.testing import login_browser


def _run(client, project: str, name: str, experiment: str | None = None, params=None) -> str:
    body = {"project": project, "name": name}
    if experiment:
        body["experiment"] = experiment
    run = client.http.post("/api/v1/runs", json=body).json()["id"]
    if params:
        client.http.patch(f"/api/v1/runs/{run}", json={"params": params})
    return run


def _points(client, run: str, name: str, values, context=None):
    extra = {"context": context} if context else {}
    points = [
        {"name": name, "value": v, "step": i, "ts": 1.0, **extra}
        for i, v in enumerate(values)
    ]
    client.http.post(f"/api/v1/runs/{run}/metrics", json={"points": points})


def _project_id(client, slug: str) -> str:
    return next(p["id"] for p in client.http.get("/api/v1/projects").json() if p["slug"] == slug)


@pytest.fixture
def lab(server, enroll_client, make_project):
    """dev sees vision/seg; eve sees secret/lab only."""
    dev = enroll_client("dev")
    eve = enroll_client("eve")
    make_project("vision/seg", members=["dev"])
    make_project("secret/lab", members=["eve"])
    fast = _run(dev, "vision/seg", "fast", "training", {"lr": 0.1, "batch": 32, "note": "a"})
    slow = _run(dev, "vision/seg", "slow", "training", {"lr": 0.01, "batch": 8, "note": 3})
    _points(dev, fast, "loss", [1.0, 0.5, 0.25, 0.2, 0.1])
    _points(dev, fast, "loss", [1.1, 0.7], context={"subset": "val"})
    _points(dev, slow, "acc", [0.5, 0.6])
    private = _run(eve, "secret/lab", "hidden", "training", {"lr": 9.0})
    _points(eve, private, "loss", [42.0])
    return {"dev": dev, "eve": eve, "fast": fast, "slow": slow, "private": private}


def _search(client, path="/api/v1/explorer/runs/search", **params):
    return client.http.get(path, params=params)


def test_search_returns_props_params_and_traces(lab):
    response = _search(lab["dev"])
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "2"
    body = response.json()
    assert set(body) == {"runs", "progress"} and body["progress"] == [2, 2]
    fast = body["runs"][lab["fast"]]
    assert set(fast) == {"props", "params", "traces"}
    assert fast["props"]["name"] == "fast" and fast["props"]["experiment"]["name"] == "training"
    assert fast["props"]["project"] == "vision/seg" and fast["props"]["tags"] == []
    assert fast["params"]["lr"] == 0.1
    traces = {(t["name"], tuple(t["context"].items())): t for t in fast["traces"]}
    loss = traces[("loss", ())]
    assert loss["count"] == 5 and loss["last"] == 0.1
    assert traces[("loss", (("subset", "val"),))]["count"] == 2


def test_run_info_lists_the_metric_series_without_points(lab):
    info = lab["dev"].http.get(f"/api/v1/explorer/runs/{lab['fast']}/info").json()
    names = [(m["name"], m["context"]) for m in info["traces"]["metric"]]
    assert ("loss", {}) in names and ("loss", {"subset": "val"}) in names
    assert info["artifacts"] == [] and "points" not in str(info["traces"])


def test_runs_of_other_projects_are_not_searched(lab):
    eve_view = _search(lab["eve"]).json()["runs"]
    assert list(eve_view) == [lab["private"]]
    assert lab["fast"] not in eve_view
    assert lab["eve"].http.get(f"/api/v1/explorer/runs/{lab['fast']}/info").status_code == 404


def test_project_scope_filters_to_one_project(lab):
    listed = _search(lab["eve"], project="secret/lab").json()["runs"]
    assert list(listed) == [lab["private"]]
    assert _search(lab["eve"], project="vision/seg").json()["runs"] == {}


def test_param_and_field_filters(lab):
    dev = lab["dev"]
    assert list(_search(dev, q="run.lr > 0.05").json()["runs"]) == [lab["fast"]]
    assert list(_search(dev, q="run.hparams.lr > 0.05").json()["runs"]) == []  # nested path
    assert list(_search(dev, q="run.batch == 8").json()["runs"]) == [lab["slow"]]
    assert list(_search(dev, q="run.experiment == 'training'").json()["runs"]) != []
    assert list(_search(dev, q="run.name.startswith('sl')").json()["runs"]) == [lab["slow"]]
    # A string param next to a number comparison matches nothing and does not fail.
    assert _search(dev, q="run.note > 1").status_code == 200
    assert list(_search(dev, q="run.note == 'a'").json()["runs"]) == [lab["fast"]]


def test_tag_filter_uses_the_run_tags(lab):
    dev = lab["dev"]
    project = _project_id(dev, "vision/seg")
    tag = dev.http.post(f"/api/v1/explorer/projects/{project}/tags", json={"name": "fast"}).json()
    dev.http.post(f"/api/v1/explorer/runs/{lab['fast']}/tags/{tag['id']}")
    matched = _search(dev, q="any(t.name in ['fast'] for t in run.tags)").json()["runs"]
    assert list(matched) == [lab["fast"]]
    assert [t["name"] for t in matched[lab["fast"]]["props"]["tags"]] == ["fast"]


def test_metric_clauses_belong_to_the_metric_search(lab):
    refused = _search(lab["dev"], q="metric.name == 'loss'")
    assert refused.status_code == 400 and "search/metric" in refused.json()["detail"]

    metrics = _search(
        lab["dev"], path="/api/v1/explorer/runs/search/metric", q="metric.name == 'loss'"
    ).json()["runs"]
    assert list(metrics) == [lab["fast"]]
    assert {t["name"] for t in metrics[lab["fast"]]["traces"]} == {"loss"}
    assert len(metrics[lab["fast"]]["traces"]) == 2  # default and subset=val


def test_invalid_filters_are_refused_with_a_reason(lab):
    response = _search(lab["dev"], q="__import__('os').system('id')")
    assert response.status_code == 400
    assert "only startswith" in response.json()["detail"]


def test_density_limits_points_and_keeps_the_last(lab):
    body = _search(lab["dev"], points=3).json()["runs"][lab["fast"]]
    loss = next(t for t in body["traces"] if t["name"] == "loss" and not t["context"])
    assert len(loss["points"]) == 3
    assert loss["points"][0][1] == 1.0 and loss["points"][-1][1] == 0.1


def test_paging(lab):
    first = _search(lab["dev"], limit=1, offset=0)
    second = _search(lab["dev"], limit=1, offset=1)
    assert first.headers["X-Total-Count"] == second.headers["X-Total-Count"] == "2"
    assert len(first.json()["runs"]) == len(second.json()["runs"]) == 1
    assert set(first.json()["runs"]) != set(second.json()["runs"])


def test_active_runs_leave_out_finished_ones(lab):
    dev = lab["dev"]
    assert len(_search(dev, path="/api/v1/explorer/runs/active").json()["runs"]) == 2
    dev.http.patch(f"/api/v1/runs/{lab['fast']}", json={"status": "finished"})
    active = _search(dev, path="/api/v1/explorer/runs/active").json()["runs"]
    assert list(active) == [lab["slow"]]


def test_archive_is_all_or_nothing(lab):
    dev = lab["dev"]
    refused = dev.http.post(
        "/api/v1/explorer/runs/archive",
        json={"ids": [lab["fast"], lab["private"]]},
    )
    assert refused.status_code == 404
    assert dev.http.get(f"/api/v1/explorer/runs/{lab['fast']}/info").status_code == 200
    assert _search(dev).json()["runs"][lab["fast"]]["props"]["archived"] is False

    done = dev.http.post("/api/v1/explorer/runs/archive", json={"ids": [lab["fast"]]})
    assert done.json() == {"updated": 1, "archived": True}
    assert _search(dev).json()["runs"][lab["fast"]]["props"]["archived"] is True
    dev.http.post("/api/v1/explorer/runs/archive?archive=false", json={"ids": [lab["fast"]]})
    assert _search(dev).json()["runs"][lab["fast"]]["props"]["archived"] is False


def test_tags_are_created_attached_renamed_and_removed(lab):
    dev, eve = lab["dev"], lab["eve"]
    project = _project_id(dev, "vision/seg")
    base = f"/api/v1/explorer/projects/{project}/tags"
    tag = dev.http.post(base, json={"name": "baseline", "color": "#00aa00"}).json()
    assert tag["name"] == "baseline" and tag["color"] == "#00aa00"
    assert dev.http.post(base, json={"name": "baseline"}).status_code == 409
    assert [t["name"] for t in dev.http.get(base).json()] == ["baseline"]

    attached = dev.http.post(f"/api/v1/explorer/runs/{lab['slow']}/tags/{tag['id']}")
    assert attached.status_code == 200
    info = dev.http.get(f"/api/v1/explorer/runs/{lab['slow']}/info").json()
    assert [t["name"] for t in info["props"]["tags"]] == ["baseline"]

    renamed = dev.http.patch(f"/api/v1/explorer/tags/{tag['id']}", json={"name": "ref"})
    assert renamed.json()["name"] == "ref"

    other_project = _project_id(eve, "secret/lab")
    foreign = eve.http.post(
        f"/api/v1/explorer/projects/{other_project}/tags", json={"name": "x"}
    ).json()
    assert dev.http.post(
        f"/api/v1/explorer/runs/{lab['slow']}/tags/{foreign['id']}"
    ).status_code == 404
    assert dev.http.post(base, json={"name": "y"}).status_code == 200
    foreign_base = f"/api/v1/explorer/projects/{other_project}/tags"
    assert eve.http.post(foreign_base, json={"name": "y"}).status_code == 200

    dev.http.delete(f"/api/v1/explorer/tags/{tag['id']}")
    assert dev.http.get(f"/api/v1/explorer/runs/{lab['slow']}/info").json()["props"]["tags"] == []


def test_bookmarks_belong_to_their_owner(lab):
    dev, eve = lab["dev"], lab["eve"]
    created = dev.http.post(
        "/api/v1/explorer/bookmarks",
        json={"kind": "runs", "title": "Best", "state": {"filter": "run.batch == 8"}},
    ).json()
    assert created["id"].startswith("bmk_") and created["state"]["filter"] == "run.batch == 8"
    assert [b["id"] for b in dev.http.get("/api/v1/explorer/bookmarks").json()] == [created["id"]]
    assert eve.http.get("/api/v1/explorer/bookmarks").json() == []
    assert eve.http.get(f"/api/v1/explorer/bookmarks/{created['id']}").status_code == 404
    assert eve.http.delete(f"/api/v1/explorer/bookmarks/{created['id']}").status_code == 404

    renamed = dev.http.patch(
        f"/api/v1/explorer/bookmarks/{created['id']}", json={"title": None, "description": "d"}
    ).json()
    assert renamed["title"] == "Best" and renamed["description"] == "d"
    dev.http.delete(f"/api/v1/explorer/bookmarks/{created['id']}")
    assert dev.http.get("/api/v1/explorer/bookmarks").json() == []


def test_bookmark_kind_and_state_size_are_checked(lab):
    dev = lab["dev"]
    bad_kind = dev.http.post(
        "/api/v1/explorer/bookmarks", json={"kind": "boards", "title": "x"}
    )
    assert bad_kind.status_code == 422
    too_big = dev.http.post(
        "/api/v1/explorer/bookmarks",
        json={"kind": "runs", "title": "x", "state": {"blob": "a" * 70_000}},
    )
    assert too_big.status_code == 422


def test_project_params_lists_paths_and_metric_contexts(lab):
    project = _project_id(lab["dev"], "vision/seg")
    listed = lab["dev"].http.get(f"/api/v1/explorer/projects/{project}/params").json()
    assert listed["params"] == ["batch", "lr", "note"]
    assert listed["metric"] == {"acc": [], "loss": ["subset"]}
    assert lab["eve"].http.get(f"/api/v1/explorer/projects/{project}/params").status_code == 404


EXPLORER_ROUTES = {
    ("GET", "/api/v1/explorer/runs/search"),
    ("GET", "/api/v1/explorer/runs/search/metric"),
    ("GET", "/api/v1/explorer/runs/active"),
    ("GET", "/api/v1/explorer/runs/{run_id}/info"),
    ("POST", "/api/v1/explorer/runs/archive"),
    ("POST", "/api/v1/explorer/runs/{run_id}/tags/{tag_id}"),
    ("DELETE", "/api/v1/explorer/runs/{run_id}/tags/{tag_id}"),
    ("GET", "/api/v1/explorer/projects/{project_id}/params"),
    ("GET", "/api/v1/explorer/projects/{project_id}/tags"),
    ("POST", "/api/v1/explorer/projects/{project_id}/tags"),
    ("PATCH", "/api/v1/explorer/tags/{tag_id}"),
    ("DELETE", "/api/v1/explorer/tags/{tag_id}"),
    ("GET", "/api/v1/explorer/bookmarks"),
    ("POST", "/api/v1/explorer/bookmarks"),
    ("GET", "/api/v1/explorer/bookmarks/{bookmark_id}"),
    ("PATCH", "/api/v1/explorer/bookmarks/{bookmark_id}"),
    ("DELETE", "/api/v1/explorer/bookmarks/{bookmark_id}"),
}


def test_the_explorer_endpoint_set_is_the_documented_one(app):
    paths = app.openapi()["paths"]
    found = {
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith("/api/v1/explorer/")
        for method in operations
    }
    assert found == EXPLORER_ROUTES


def test_browser_bookmark_writes_need_the_csrf_token(browser, server):
    me = login_browser(browser)
    body = {"kind": "runs", "title": "from the browser", "state": {}}
    assert browser.post("/api/v1/explorer/bookmarks", json=body).status_code == 403
    done = browser.post(
        "/api/v1/explorer/bookmarks", json=body, headers={"X-CSRF-Token": me["csrf"]}
    )
    assert done.status_code == 200 and done.json()["title"] == "from the browser"


@pytest.mark.parametrize(
    "query",
    [
        "run.name == 'fast'", "run.name != 'fast'", "run.name.startswith('f%_')",
        "run.hash == 'run_missing'", "run.lr > 0.05", "run.lr <= 0.05", "run.lr in [0.1, 0.2]",
        "run.lr not in [0.1]", "run.note == 'a'", "run.note in ['a', 'b']", "run.note != None",
        "run.missing == None", "run.batch == 8", "run.batch != 8", "run.flag == True",
        "run.flag", "not run.archived", "run.archived == False", "run.active == True",
        "run.active", "run.experiment == 'training'", "run.experiment in ['general']",
        "run.project == 'vision/seg'", "run.project.startswith('vis')",
        "run.creation_time > 1", "run.creation_time <= 9999999999",
        "run.lr > 0.05 or run.batch == 8", "run.note > 1", "run.note == 3",
        "any(t.name in ['x'] for t in run.tags)",
        "any(t.name != 'x' for t in run.tags)",
        "run.lr > -1 and not (run.name == 'zzz')",
    ],
)
def test_every_accepted_form_runs_against_the_database(lab, query):
    response = _search(lab["dev"], q=query)
    assert response.status_code == 200, (query, response.text)


def test_metric_forms_run_against_the_database(lab):
    for query in ["metric.name == 'loss'", "metric.name in ['acc', 'loss']",
                  "metric.context.subset == 'val'", "metric.name.startswith('lo')"]:
        response = _search(lab["dev"], path="/api/v1/explorer/runs/search/metric", q=query)
        assert response.status_code == 200, (query, response.text)

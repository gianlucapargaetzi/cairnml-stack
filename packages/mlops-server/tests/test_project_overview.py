import pytest


@pytest.fixture
def lab(server, enroll_client, make_project, new_job):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    http = dev.http

    def run(name, experiment, final_loss=None, status=None, **extra):
        exp = http.post(
            "/api/v1/runs",
            json={"project": "vision/seg", "name": name, "experiment": experiment, **extra},
        ).json()
        if final_loss is not None:
            pts = [
                {"name": "val_loss", "value": v, "step": i, "ts": float(i)}
                for i, v in enumerate([final_loss * 2, final_loss])
            ]
            http.post(f"/api/v1/runs/{exp['id']}/metrics", json={"points": pts})
        if status:
            http.patch(f"/api/v1/runs/{exp['id']}", json={"status": status})
        return exp

    run("t1", "training", 0.5, "finished", primary_metric="val_loss", direction="min")
    run("t2", "training", 0.3, "finished")
    run("t3", "training", None, "running")
    run("e1", "evaluation")
    return dict(dev=dev, http=http, new_job=new_job)


def test_project_overview(lab):
    http = lab["http"]
    lab["new_job"](http, runtime={"type": "image", "image": "alpine:3.20"})
    lab["new_job"](http, runtime={"type": "image", "image": "alpine:3.20"})
    lab["new_job"](
        http, runtime={"type": "python", "python": "3.11", "command": ["python", "t.py"]}
    )
    body = http.get("/api/v1/projects/overview", params={"project": "vision/seg"}).json()
    experiments = {t["name"]: t for t in body["experiments"]}
    assert experiments["training"]["runs"] == 3 and experiments["training"]["running"] == 1
    best = experiments["training"]["best"]
    assert best["value"] == 0.3 and best["name"] == "t2"
    assert experiments["evaluation"]["best"] is None and experiments["evaluation"]["runs"] == 1
    assert body["counts"]["runs"] == 7 and body["counts"]["jobs"]["queued"] == 3
    containers = {c["name"]: c for c in body["containers"]}
    assert containers["alpine:3.20"]["jobs"] == 2 and containers["python:3.11"]["kind"] == "python"
    assert len(body["recent"]) == 7 and body["project"]["slug"] == "vision/seg"


def test_best_follows_the_direction(lab):
    http = lab["http"]
    experiment_id = next(
        t
        for t in http.get("/api/v1/experiments", params={"project": "vision/seg"}).json()
        if t["name"] == "training"
    )["id"]
    http.patch(f"/api/v1/experiments/{experiment_id}", json={"direction": "max"})
    best = http.get(f"/api/v1/experiments/{experiment_id}/summary").json()["stats"]["best"]
    assert best["value"] == 0.5 and best["name"] == "t1"


def test_experiment_summary_rows(lab):
    http = lab["http"]
    experiment_id = next(
        t
        for t in http.get("/api/v1/experiments", params={"project": "vision/seg"}).json()
        if t["name"] == "training"
    )["id"]
    body = http.get(f"/api/v1/experiments/{experiment_id}/summary").json()
    rows = {r["name"]: r for r in body["runs"]}
    assert rows["t2"]["primary_value"] == 0.3 and rows["t3"]["primary_value"] is None
    assert body["experiment"]["primary_metric"] == "val_loss" and body["stats"]["runs"] == 3


def test_run_list_filters_by_experiment(lab):
    rows = (
        lab["http"]
        .get("/api/v1/runs", params={"project": "vision/seg", "experiment": "evaluation"})
        .json()
    )
    assert [r["name"] for r in rows] == ["e1"]


def test_overview_access(lab, enroll_client):
    eve = enroll_client("eve")
    assert (
        eve.http.get("/api/v1/projects/overview", params={"project": "vision/seg"}).status_code
        == 404
    )
    assert eve.http.get("/api/v1/experiments/exp_missing/summary").status_code == 404

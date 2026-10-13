import pytest


@pytest.fixture
def lab(server, enroll_client, make_project, new_job):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    http = dev.http

    def experiment(name, task, final_loss=None, status=None, **extra):
        exp = http.post(
            "/api/v1/experiments",
            json={"project": "vision/seg", "name": name, "task": task, **extra},
        ).json()
        if final_loss is not None:
            pts = [
                {"name": "val_loss", "value": v, "step": i, "ts": float(i)}
                for i, v in enumerate([final_loss * 2, final_loss])
            ]
            http.post(f"/api/v1/experiments/{exp['id']}/metrics", json={"points": pts})
        if status:
            http.patch(f"/api/v1/experiments/{exp['id']}", json={"status": status})
        return exp

    experiment("t1", "training", 0.5, "finished", primary_metric="val_loss", direction="min")
    experiment("t2", "training", 0.3, "finished")
    experiment("t3", "training", None, "running")
    experiment("e1", "evaluation")
    return dict(dev=dev, http=http, new_job=new_job)


def test_project_overview(lab):
    http = lab["http"]
    lab["new_job"](http, runtime={"type": "image", "image": "alpine:3.20"})
    lab["new_job"](http, runtime={"type": "image", "image": "alpine:3.20"})
    lab["new_job"](
        http, runtime={"type": "python", "python": "3.11", "command": ["python", "t.py"]}
    )
    body = http.get("/api/v1/projects/overview", params={"project": "vision/seg"}).json()
    tasks = {t["name"]: t for t in body["tasks"]}
    assert tasks["training"]["experiments"] == 3 and tasks["training"]["running"] == 1
    assert tasks["training"]["best"]["value"] == 0.3 and tasks["training"]["best"]["name"] == "t2"
    assert tasks["evaluation"]["best"] is None and tasks["evaluation"]["experiments"] == 1
    assert body["counts"]["experiments"] == 7 and body["counts"]["jobs"]["queued"] == 3
    containers = {c["name"]: c for c in body["containers"]}
    assert containers["alpine:3.20"]["jobs"] == 2 and containers["python:3.11"]["kind"] == "python"
    assert len(body["recent"]) == 7 and body["project"]["slug"] == "vision/seg"


def test_best_follows_the_direction(lab):
    http = lab["http"]
    task_id = next(
        t
        for t in http.get("/api/v1/tasks", params={"project": "vision/seg"}).json()
        if t["name"] == "training"
    )["id"]
    http.patch(f"/api/v1/tasks/{task_id}", json={"direction": "max"})
    best = http.get(f"/api/v1/tasks/{task_id}/summary").json()["stats"]["best"]
    assert best["value"] == 0.5 and best["name"] == "t1"


def test_task_summary_rows(lab):
    http = lab["http"]
    task_id = next(
        t
        for t in http.get("/api/v1/tasks", params={"project": "vision/seg"}).json()
        if t["name"] == "training"
    )["id"]
    body = http.get(f"/api/v1/tasks/{task_id}/summary").json()
    rows = {r["name"]: r for r in body["experiments"]}
    assert rows["t2"]["primary_value"] == 0.3 and rows["t3"]["primary_value"] is None
    assert body["task"]["primary_metric"] == "val_loss" and body["stats"]["experiments"] == 3


def test_experiment_list_filters_by_task(lab):
    rows = (
        lab["http"]
        .get("/api/v1/experiments", params={"project": "vision/seg", "task": "evaluation"})
        .json()
    )
    assert [r["name"] for r in rows] == ["e1"]


def test_overview_access(lab, enroll_client):
    eve = enroll_client("eve")
    assert (
        eve.http.get("/api/v1/projects/overview", params={"project": "vision/seg"}).status_code
        == 404
    )
    assert eve.http.get("/api/v1/tasks/tsk_missing/summary").status_code == 404

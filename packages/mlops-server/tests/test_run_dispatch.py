import pytest


@pytest.fixture
def dev(enroll_client, make_project, stub_github):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    stub_github.commits.add(("org/repo", "a" * 40))
    return dev


def _recorded_run(http, **patch):
    """A local run as the client records it: created, then filled in with its code and params."""
    created = http.post("/api/v1/runs", json={"project": "vision/seg", "name": "run1"})
    assert created.status_code == 200, created.text
    exp = created.json()["id"]
    body = {
        "params": {"lr": 0.1}, "git": {"repo": "org/repo", "commit": "a" * 40, "cwd": "."},
        "script": "train.py", "argv": ["train.py", "--epochs", "3"],
        "python_version": "3.11.9", "requirements": [], **patch,
    }
    assert http.patch(f"/api/v1/runs/{exp}", json=body).status_code == 200
    return exp


def test_dispatch_runs_the_recorded_run_as_a_job(server, dev):
    exp = _recorded_run(dev.http)
    response = dev.http.post(f"/api/v1/runs/{exp}/dispatch", json={
        "queue": "gpu", "gpu": 1, "labels": ["lab-a"]})
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["queue"] == "gpu" and job["status"] == "queued" and job["run_id"] != exp
    spec = dev.http.get(f"/api/v1/jobs/{job['id']}/spec").json()
    assert spec["code"]["commit"] == "a" * 40 and spec["code"]["repo"] == "org/repo"
    assert spec["runtime"]["command"] == ["python", "train.py", "--epochs", "3"]
    assert spec["runtime"]["python"] == "3.11"
    assert spec["params"] == {"lr": 0.1}
    assert spec["resources"]["gpu"] == 1 and spec["resources"]["labels"] == ["lab-a"]
    new_exp = dev.http.get(f"/api/v1/runs/{job['run_id']}").json()
    assert new_exp["notes"] == f"dispatched from {exp}" and new_exp["source"] == "job"


def test_dispatch_refuses_a_run_that_cannot_be_reproduced(server, dev):
    exp = _recorded_run(dev.http, git=None, script=None, argv=[])
    response = dev.http.post(f"/api/v1/runs/{exp}/dispatch", json={})
    assert response.status_code == 422
    assert "no git commit and no script" in response.json()["detail"]


def test_dispatch_is_limited_to_project_members(server, dev, enroll_client):
    exp = _recorded_run(dev.http)
    outsider = enroll_client("eve")
    response = outsider.http.post(f"/api/v1/runs/{exp}/dispatch", json={})
    assert response.status_code in (403, 404)

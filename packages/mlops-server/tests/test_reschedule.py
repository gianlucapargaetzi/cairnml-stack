import pytest


@pytest.fixture
def dev(enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    return dev


def test_spec_of_a_job(server, dev, new_job):
    job = new_job(dev.http, params={"lr": 0.1}, experiment="training")
    spec = dev.http.get(f"/api/v1/jobs/{job['id']}/spec").json()
    assert spec["params"] == {"lr": 0.1} and spec["experiment"] == "training"
    assert spec["code"]["repo"] == "org/repo"


def test_reschedule_copies_and_applies_overrides(server, dev, new_job):
    job = new_job(dev.http, params={"lr": 0.1, "epochs": 3, "seed": 1}, queue="default",
                  resources={"cpu": 2, "memory_gb": 4})
    response = dev.http.post(f"/api/v1/jobs/{job['id']}/reschedule", json={
        "name": "lr sweep 0.5", "queue": "gpu", "resources": {"cpu": 8, "memory_gb": 16, "gpu": 1},
        "params": {"lr": 0.5, "seed": None, "batch": 64}, "env": {"FOO": "bar"}, "timeout_s": 3600})
    assert response.status_code == 200, response.text
    new = response.json()
    assert new["id"] != job["id"] and new["queue"] == "gpu" and new["status"] == "queued"
    spec = dev.http.get(f"/api/v1/jobs/{new['id']}/spec").json()
    assert spec["name"] == "lr sweep 0.5"
    assert spec["params"] == {"lr": 0.5, "epochs": 3, "batch": 64}      # merged, seed removed
    assert spec["resources"]["gpu"] == 1 and spec["env"] == {"FOO": "bar"}
    assert spec["timeout_s"] == 3600
    original = dev.http.get(f"/api/v1/jobs/{job['id']}/spec").json()
    assert spec["code"] == original["code"]  # same code
    exp = dev.http.get(f"/api/v1/runs/{new['run_id']}").json()
    assert exp["parent_id"] == job["run_id"] and exp["source"] == "job"
    assert "copied from" in exp["notes"]


def test_reschedule_without_overrides_is_an_exact_copy(server, dev, new_job, make_agent):
    # a finished job can be copied too
    agent = make_agent()
    job = new_job(dev.http, params={"a": 1})
    agent.http.post("/api/v1/agents/poll", json={"wait_s": 0})
    agent.http.post(f"/api/v1/jobs/{job['id']}/status", json={"status": "running"})
    agent.http.post(f"/api/v1/jobs/{job['id']}/status", json={"status": "finished", "exit_code": 0})
    copy = dev.http.post(f"/api/v1/jobs/{job['id']}/reschedule", json={}).json()
    assert dev.http.get(f"/api/v1/jobs/{copy['id']}/spec").json()["params"] == {"a": 1}


def test_reschedule_validation_and_access(server, dev, new_job, enroll_client, stub_github):
    job = new_job(dev.http)
    url = f"/api/v1/jobs/{job['id']}/reschedule"
    assert dev.http.post(url, json={"env": {"MLOPS_RUN_TOKEN": "x"}}).status_code == 422
    assert dev.http.post(url, json={"timeout_s": 5}).status_code == 422
    assert dev.http.post("/api/v1/jobs/job_missing/reschedule", json={}).status_code == 404
    eve = enroll_client("eve")
    assert eve.http.post(url, json={}).status_code == 404
    assert eve.http.get(f"/api/v1/jobs/{job['id']}/spec").status_code == 404
    stub_github.commits.clear()  # the commit vanished from GitHub (force push)
    assert "push it first" in dev.http.post(url, json={}).json()["detail"]


def test_job_list_has_experiment_and_cancel_flag(server, dev, new_job, make_agent):
    agent = make_agent()
    job = new_job(dev.http, experiment="training")
    agent.http.post("/api/v1/agents/poll", json={"wait_s": 0})
    dev.http.post(f"/api/v1/jobs/{job['id']}/cancel")
    row = dev.http.get("/api/v1/jobs").json()[0]
    assert row["experiment"] == "training" and row["cancel_requested"] is True

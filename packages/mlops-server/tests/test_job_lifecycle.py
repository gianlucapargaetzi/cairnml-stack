import pytest


@pytest.fixture
def dev(enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    return dev


def _assigned(dev, make_agent, new_job, **kw):
    agent = make_agent()
    job = new_job(dev.http, **kw)
    agent.http.post("/api/v1/agents/poll", json={"wait_s": 0})
    return agent, job


def _status(agent, job, status, **extra):
    return agent.http.post(f"/api/v1/jobs/{job['id']}/status", json={"status": status, **extra})


def test_status_transitions_update_the_experiment(server, make_agent, dev, new_job):
    agent, job = _assigned(dev, make_agent, new_job)
    assert _status(agent, job, "running").json()["status"] == "running"
    exp = dev.http.get(f"/api/v1/experiments/{job['experiment_id']}").json()
    assert exp["status"] == "running" and exp["started_at"]
    done = _status(agent, job, "finished", exit_code=0).json()
    assert done["status"] == "finished" and done["exit_code"] == 0
    final = dev.http.get(f"/api/v1/experiments/{job['experiment_id']}").json()
    assert final["status"] == "finished"


def test_invalid_transitions_are_conflicts(server, make_agent, dev, new_job):
    agent, job = _assigned(dev, make_agent, new_job)
    assert _status(agent, job, "finished").status_code == 409  # assigned -> finished not allowed
    _status(agent, job, "running")
    _status(agent, job, "failed", exit_code=3, message="boom")
    assert _status(agent, job, "running").status_code == 409


def test_other_agents_cannot_touch_the_job(server, make_agent, dev, new_job):
    agent, job = _assigned(dev, make_agent, new_job)
    intruder = make_agent()
    for path, body in [("status", {"status": "running"}), ("run-token", None), ("sts", None),
                       ("git-token", {"repo": "org/repo"}), ("artifact-url", {"key": "x"})]:
        r = intruder.http.post(f"/api/v1/jobs/{job['id']}/{path}", json=body)
        assert r.status_code == 404, path


def test_run_token_is_scoped_to_its_experiment(server, make_agent, dev, new_job, app):
    agent, job = _assigned(dev, make_agent, new_job)
    _status(agent, job, "running")
    token = agent.http.post(f"/api/v1/jobs/{job['id']}/run-token").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = server.get("/api/v1/me", headers=headers).json()
    assert me["kind"] == "run"
    exp = job["experiment_id"]
    ok = server.post(f"/api/v1/experiments/{exp}/metrics", headers=headers,
                     json={"points": [{"name": "x", "value": 1.0, "ts": 1.0}]})
    assert ok.status_code == 200
    other = dev.http.post(
        "/api/v1/experiments", json={"project": "vision/seg", "name": "other"}
    ).json()["id"]
    denied = server.post(f"/api/v1/experiments/{other}/metrics", headers=headers,
                         json={"points": [{"name": "x", "value": 1.0, "ts": 1.0}]})
    assert denied.status_code == 404
    created = server.post("/api/v1/projects", headers=headers, json={"slug": "a", "name": "a"})
    assert created.status_code == 403
    # once the job is over, the run token stops working
    _status(agent, job, "finished", exit_code=0)
    assert server.get("/api/v1/me", headers=headers).status_code == 401


def test_git_token_only_for_job_repos(server, make_agent, dev, new_job, stub_github):
    agent, job = _assigned(dev, make_agent, new_job)
    ok = agent.http.post(f"/api/v1/jobs/{job['id']}/git-token", json={"repo": "org/repo"})
    assert ok.status_code == 200 and ok.json()["token"] == "ghs_stub"
    other = agent.http.post(f"/api/v1/jobs/{job['id']}/git-token", json={"repo": "org/other"})
    assert other.status_code == 403


def test_sts_is_read_only_for_the_job_project(server, make_agent, dev, new_job, stub_storage):
    agent, job = _assigned(dev, make_agent, new_job)
    creds = agent.http.post(f"/api/v1/jobs/{job['id']}/sts").json()
    assert creds["prefix"] == "vision/seg/"
    assert stub_storage.sts_calls == [("vision/seg", False)]


def test_artifact_url_only_for_spec_keys(server, make_agent, dev, new_job, stub_github):
    exp = dev.http.post(
        "/api/v1/experiments", json={"project": "vision/seg", "name": "l"}
    ).json()["id"]
    key = f"vision/seg/{exp}/uncommitted.patch"
    dev.http.post(
        f"/api/v1/experiments/{exp}/artifacts",
        json={"name": "uncommitted.patch", "key": key, "kind": "patch"},
    )
    agent = make_agent()
    stub_github.commits.add(("org/repo", "a" * 40))
    job = dev.http.post("/api/v1/jobs", json={
        "name": "j", "project": "vision/seg",
        "code": {"repo": "org/repo", "commit": "a" * 40, "patch_key": key},
        "runtime": {"type": "python", "command": ["python", "t.py"]}}).json()
    agent.http.post("/api/v1/agents/poll", json={"wait_s": 0})
    ok = agent.http.post(f"/api/v1/jobs/{job['id']}/artifact-url", json={"key": key})
    assert ok.status_code == 200 and ok.json()["url"].endswith("op=get")
    secret = agent.http.post(
        f"/api/v1/jobs/{job['id']}/artifact-url", json={"key": "vision/seg/x/secret"}
    )
    assert secret.status_code == 403


def test_cancel_queued_and_running(server, make_agent, dev, new_job, app):
    queued = new_job(dev.http)
    cancelled = dev.http.post(f"/api/v1/jobs/{queued['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    exp = dev.http.get(f"/api/v1/experiments/{queued['experiment_id']}").json()
    assert exp["status"] == "cancelled"
    assert dev.http.post(f"/api/v1/jobs/{queued['id']}/cancel").status_code == 409

    agent, job = _assigned(dev, make_agent, new_job)
    _status(agent, job, "running")
    running = dev.http.post(f"/api/v1/jobs/{job['id']}/cancel").json()
    assert running["status"] == "running"
    hb = agent.http.post("/api/v1/agents/heartbeat", json={"running_job_ids": [job["id"]]}).json()
    assert hb["cancel_job_ids"] == [job["id"]]
    assert _status(agent, job, "cancelled").json()["status"] == "cancelled"


def test_non_members_cannot_see_or_cancel_jobs(server, make_agent, dev, new_job, enroll_client):
    job = new_job(dev.http)
    eve = enroll_client("eve")
    assert eve.http.get(f"/api/v1/jobs/{job['id']}").status_code == 404
    assert eve.http.post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 404


def test_client_cannot_set_status_of_a_job_experiment(server, make_agent, dev, new_job):
    agent, job = _assigned(dev, make_agent, new_job)
    _status(agent, job, "running")
    exp_id = job["experiment_id"]
    for status in ("finished", "cancelled"):
        r = dev.http.patch(f"/api/v1/experiments/{exp_id}", json={"status": status})
        assert r.status_code == 403
        assert r.json()["detail"] == "status of a job experiment is controlled by its job"
    assert dev.http.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "running"
    assert _status(agent, job, "finished", exit_code=0).status_code == 200


def test_run_token_is_refused_on_agent_routes(server, make_agent, dev, new_job):
    agent, job = _assigned(dev, make_agent, new_job)
    _status(agent, job, "running")
    token = agent.http.post(f"/api/v1/jobs/{job['id']}/run-token").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = server.post("/api/v1/agents/heartbeat", headers=headers, json={"running_job_ids": []})
    assert r.status_code == 403


def test_sts_is_503_when_storage_is_not_configured(server, make_agent, dev, new_job, app):
    agent, job = _assigned(dev, make_agent, new_job)
    app.state.storage = None  # per-test app: no S3 credentials configured
    r = agent.http.post(f"/api/v1/jobs/{job['id']}/sts")
    assert r.status_code == 503

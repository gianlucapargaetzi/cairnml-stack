def _create(http, project="vision/seg", name="baseline", **extra):
    return http.post("/api/v1/experiments", json={"project": project, "name": name, **extra})


def test_create_and_get(server, enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    created = _create(dev.http, config={"lr": 0.1}).json()
    assert created["status"] == "created" and created["owner"] == "dev"
    assert created["config"] == {"lr": 0.1}
    assert dev.http.get(f"/api/v1/experiments/{created['id']}").json()["id"] == created["id"]


def test_non_member_sees_404(server, enroll_client, make_project):
    enroll_client("dev"), enroll_client("eve")
    make_project("vision/seg", members=["dev"])
    eve = enroll_client("eve")
    assert _create(eve.http).status_code == 404
    exp = _create(enroll_client("dev").http).json()
    assert eve.http.get(f"/api/v1/experiments/{exp['id']}").status_code == 404
    assert eve.http.get("/api/v1/experiments").json() == []


def test_patch_merges_params_and_stores_reproduction_fields(server, enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    exp = _create(dev.http).json()
    url = f"/api/v1/experiments/{exp['id']}"
    dev.http.patch(url, json={"params": {"lr": 0.1}})
    body = dev.http.patch(url, json={
        "params": {"epochs": 3},
        "git": {"repo": "org/seg", "commit": "a" * 40, "dirty": True, "cwd": "src"},
        "datasets": [
            {"path": "data/train", "dvc_hash": "abc.dir", "repo": "org/seg", "commit": "a" * 40}
        ],
        "requirements": ["numpy==1.26.4"], "argv": ["train.py", "--lr", "0.1"],
        "python_version": "3.11.9", "script": "src/train.py",
    }).json()
    assert body["params"] == {"lr": 0.1, "epochs": 3}
    assert body["git"]["dirty"] is True and body["datasets"][0]["dvc_hash"] == "abc.dir"


def test_status_lifecycle(server, enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    url = f"/api/v1/experiments/{_create(dev.http).json()['id']}"
    running = dev.http.patch(url, json={"status": "running"}).json()
    assert running["started_at"] is not None and running["finished_at"] is None
    done = dev.http.patch(url, json={"status": "finished"}).json()
    assert done["finished_at"] is not None
    assert dev.http.patch(url, json={"status": "running"}).status_code == 409


def test_only_owner_or_admin_may_write(server, enroll_client, make_project):
    enroll_client("dev"), enroll_client("peer")
    make_project("vision/seg", members=["dev", "peer"])
    exp = _create(enroll_client("dev").http).json()
    peer = enroll_client("peer")
    assert peer.http.get(f"/api/v1/experiments/{exp['id']}").status_code == 200
    patched = peer.http.patch(f"/api/v1/experiments/{exp['id']}", json={"notes": "x"})
    assert patched.status_code == 404


def test_list_filters(server, enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    _create(dev.http, name="a")
    b = _create(dev.http, name="b").json()
    dev.http.patch(f"/api/v1/experiments/{b['id']}", json={"status": "running"})
    running = dev.http.get("/api/v1/experiments", params={"status": "running"}).json()
    assert [e["id"] for e in running] == [b["id"]]
    listed = dev.http.get("/api/v1/experiments", params={"project": "vision/seg"}).json()
    assert len(listed) == 2


def test_null_in_patch_does_not_clear_required_fields(server, enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    exp = _create(dev.http, config={"lr": 0.1}).json()
    url = f"/api/v1/experiments/{exp['id']}"
    dev.http.patch(url, json={"params": {"lr": 0.1}})
    response = dev.http.patch(url, json={"status": None, "params": None, "argv": None})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created" and body["params"] == {"lr": 0.1} and body["argv"] == []


def _attach_job(app, experiment_id: str, owner_id: str, agent_id: str, status="running") -> str:
    from mlops_server.ids import new_id
    from mlops_server.models import Experiment, Job
    from sqlalchemy import select

    with app.state.session_factory() as session:
        exp = session.get(Experiment, experiment_id)
        job = Job(
            id=new_id("job"), experiment_id=exp.id, project_id=exp.project_id,
            created_by=owner_id, spec={}, queue="default", agent_id=agent_id, status=status,
        )
        session.add(job)
        exp.job_id = job.id
        session.commit()
        assert session.scalar(select(Job).where(Job.id == job.id)) is not None
        return job.id


def test_agent_and_run_principals_cannot_set_status(
    app, server, enroll_client, make_project, make_agent
):
    from fastapi.testclient import TestClient

    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    agent = make_agent()
    exp = _create(dev.http).json()
    url = f"/api/v1/experiments/{exp['id']}"
    job_id = _attach_job(app, exp["id"], dev.user_id, agent.agent_id)
    assert agent.http.patch(url, json={"status": "running"}).status_code == 403
    token, _ = app.state.tokens.issue(
        sub=job_id, kind="run", uid=dev.user_id, experiment_id=exp["id"], job_id=job_id
    )
    run = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    response = run.patch(url, json={"status": "running"}, headers=headers)
    assert response.status_code == 403


def test_terminal_status_cannot_change_to_another_terminal(server, enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    url = f"/api/v1/experiments/{_create(dev.http).json()['id']}"
    assert dev.http.patch(url, json={"status": "finished"}).status_code == 200
    assert dev.http.patch(url, json={"status": "failed"}).status_code == 409
    assert dev.http.patch(url, json={"status": "cancelled"}).status_code == 409


def test_agent_cannot_write_after_experiment_finished(
    app, server, enroll_client, make_project, make_agent
):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    agent = make_agent()
    exp = _create(dev.http).json()
    url = f"/api/v1/experiments/{exp['id']}"
    job_id = _attach_job(app, exp["id"], dev.user_id, agent.agent_id)
    assert agent.http.patch(url, json={"params": {"lr": 0.1}}).status_code == 200
    # a job-linked experiment finishes through its job, not by a client PATCH
    done = agent.http.post(f"/api/v1/jobs/{job_id}/status", json={"status": "finished"})
    assert done.status_code == 200
    assert agent.http.patch(url, json={"notes": "late"}).status_code == 404
    assert agent.http.get(url).status_code == 200


def test_admin_lists_experiments_across_projects(server, enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    make_project("nlp/chat", members=["dev"])
    _create(dev.http, project="vision/seg")
    _create(dev.http, project="nlp/chat")
    admin = enroll_client("root", roles=["mlops-admin"])
    listed = admin.http.get("/api/v1/experiments").json()
    assert {e["project"] for e in listed} == {"vision/seg", "nlp/chat"}


def test_status_change_locks_the_experiment_row(app, server, enroll_client, make_project):
    from sqlalchemy import event

    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    url = f"/api/v1/experiments/{_create(dev.http).json()['id']}"
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", capture)
    try:
        assert dev.http.patch(url, json={"status": "running"}).status_code == 200
    finally:
        event.remove(app.state.engine, "before_cursor_execute", capture)
    assert any("FOR UPDATE" in s for s in statements)

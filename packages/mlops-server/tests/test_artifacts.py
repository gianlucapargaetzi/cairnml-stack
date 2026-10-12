import pytest


def _setup(enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    exp = dev.http.post("/api/v1/experiments", json={"project": "vision/seg", "name": "n"}).json()[
        "id"
    ]
    return dev, exp


def test_presign_register_list_download(server, enroll_client, make_project):
    dev, exp = _setup(enroll_client, make_project)
    pre = dev.http.post(
        f"/api/v1/experiments/{exp}/artifacts/presign", json={"name": "ckpt/e1.pt"}
    ).json()
    assert pre["key"] == f"vision/seg/{exp}/ckpt/e1.pt" and pre["upload_url"].endswith("op=put")
    reg = dev.http.post(
        f"/api/v1/experiments/{exp}/artifacts",
        json={
            "name": "ckpt/e1.pt",
            "key": pre["key"],
            "size": 12,
            "kind": "model",
            "meta": {"epoch": 1},
        },
    )
    assert reg.status_code == 200
    listed = dev.http.get(f"/api/v1/experiments/{exp}/artifacts").json()
    assert listed[0]["kind"] == "model" and listed[0]["size"] == 12
    url = dev.http.get(f"/api/v1/experiments/{exp}/artifacts/{listed[0]['id']}/download").json()[
        "url"
    ]
    assert url.endswith("op=get")


@pytest.mark.parametrize("name", ["../../etc/passwd", "/abs", "a/../../b", ""])
def test_path_traversal_names_are_rejected(server, enroll_client, make_project, name):
    dev, exp = _setup(enroll_client, make_project)
    assert (
        dev.http.post(
            f"/api/v1/experiments/{exp}/artifacts/presign", json={"name": name}
        ).status_code
        == 422
    )


def test_cannot_register_a_key_outside_the_experiment_prefix(server, enroll_client, make_project):
    dev, exp = _setup(enroll_client, make_project)
    for key in ["vision/seg/exp_other/x", "other/project/x", f"vision/seg/{exp}/../x"]:
        r = dev.http.post(f"/api/v1/experiments/{exp}/artifacts", json={"name": "x", "key": key})
        assert r.status_code == 422


def test_sts_requires_membership_and_returns_credentials(
    server, enroll_client, make_project, stub_storage
):
    dev, _ = _setup(enroll_client, make_project)
    ok = dev.http.post("/api/v1/storage/sts", json={"project": "vision/seg", "write": True})
    assert ok.status_code == 200 and ok.json()["prefix"] == "vision/seg/"
    assert stub_storage.sts_calls == [("vision/seg", True)]
    outsider = enroll_client("eve")
    assert (
        outsider.http.post("/api/v1/storage/sts", json={"project": "vision/seg"}).status_code == 404
    )


def _register(dev, exp, name="m.pt"):
    key = dev.http.post(f"/api/v1/experiments/{exp}/artifacts/presign", json={"name": name}).json()[
        "key"
    ]
    r = dev.http.post(f"/api/v1/experiments/{exp}/artifacts", json={"name": name, "key": key})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_download_of_another_experiments_artifact_is_404(server, enroll_client, make_project):
    dev, exp1 = _setup(enroll_client, make_project)
    exp2 = dev.http.post(
        "/api/v1/experiments", json={"project": "vision/seg", "name": "other"}
    ).json()["id"]
    art = _register(dev, exp1)
    assert dev.http.get(f"/api/v1/experiments/{exp2}/artifacts/{art}/download").status_code == 404
    assert dev.http.get(f"/api/v1/experiments/{exp1}/artifacts/{art}/download").status_code == 200


def test_non_owner_member_cannot_presign_or_register(server, enroll_client, make_project):
    dev = enroll_client("dev")
    bob = enroll_client("bob")
    make_project("vision/seg", members=["dev", "bob"])
    exp = dev.http.post("/api/v1/experiments", json={"project": "vision/seg", "name": "n"}).json()[
        "id"
    ]
    assert (
        bob.http.post(
            f"/api/v1/experiments/{exp}/artifacts/presign", json={"name": "x"}
        ).status_code
        == 404
    )
    key = f"vision/seg/{exp}/x"
    assert (
        bob.http.post(
            f"/api/v1/experiments/{exp}/artifacts", json={"name": "x", "key": key}
        ).status_code
        == 404
    )


def test_finished_run_token_cannot_presign(server, app, enroll_client, make_project):
    from mlops_server.ids import new_id
    from mlops_server.models import Agent, Experiment, Job

    dev, exp = _setup(enroll_client, make_project)
    with app.state.session_factory() as s:
        agent_id = new_id("agt")
        s.add(Agent(id=agent_id, name="a", public_key="x", queues=["default"], capabilities={}))
        e = s.get(Experiment, exp)
        job = Job(
            id=new_id("job"),
            experiment_id=exp,
            project_id=e.project_id,
            created_by=e.owner_id,
            spec={},
            queue="default",
            agent_id=agent_id,
            status="running",
        )
        s.add(job)
        e.job_id = job.id
        s.commit()
        job_id = job.id
    token, _ = app.state.tokens.issue(
        sub=job_id, kind="run", uid=dev.user_id, experiment_id=exp, job_id=job_id
    )
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        server.post(
            f"/api/v1/experiments/{exp}/artifacts/presign", json={"name": "x"}, headers=headers
        ).status_code
        == 200
    )
    # a job-linked experiment cannot be finished by a client PATCH, so set it directly
    with app.state.session_factory() as s:
        s.get(Experiment, exp).status = "finished"
        s.commit()
    assert (
        server.post(
            f"/api/v1/experiments/{exp}/artifacts/presign", json={"name": "x"}, headers=headers
        ).status_code
        == 404
    )


def test_presign_returns_503_when_storage_unconfigured(server, app, enroll_client, make_project):
    dev, exp = _setup(enroll_client, make_project)
    app.state.storage = None
    r = dev.http.post(f"/api/v1/experiments/{exp}/artifacts/presign", json={"name": "x"})
    assert r.status_code == 503

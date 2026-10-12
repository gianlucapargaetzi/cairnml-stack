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

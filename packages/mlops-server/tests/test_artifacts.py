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

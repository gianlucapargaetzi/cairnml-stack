import json
from datetime import UTC, datetime

import pytest
from mlops_server.services.storage import StorageService, dataset_policy, safe_artifact_name


@pytest.mark.parametrize("name", ["model.pt", "checkpoints/epoch-1.ckpt", "a_b.c-d/e.txt"])
def test_safe_names_accepted(name):
    assert safe_artifact_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../x",
        "a/../b",
        "/abs",
        "a//b",
        "a/./b",
        "x" * 256,
        "has space",
        "a\\b",
        "a\x00b",
        "model.pt\n",
    ],
)
def test_unsafe_names_rejected(name):
    with pytest.raises(ValueError):
        safe_artifact_name(name)


def test_dataset_policy_read_only_vs_write():
    ro = dataset_policy("datasets", "vision/seg/", write=False)
    rw = dataset_policy("datasets", "vision/seg/", write=True)

    def actions(p):
        return {
            a
            for s in p["Statement"]
            for a in (s["Action"] if isinstance(s["Action"], list) else [s["Action"]])
        }

    assert "s3:PutObject" not in actions(ro) and "s3:GetObject" in actions(ro)
    assert {"s3:PutObject", "s3:DeleteObject"} <= actions(rw)
    assert any(
        "arn:aws:s3:::datasets/vision/seg/*" in json.dumps(s["Resource"]) for s in ro["Statement"]
    )


class FakeSts:
    def __init__(self):
        self.calls = []

    def assume_role(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "Credentials": {
                "AccessKeyId": "AK",
                "SecretAccessKey": "SK",
                "SessionToken": "ST",
                "Expiration": datetime(2030, 1, 1, tzinfo=UTC),
            }
        }


def _service(sts=None):
    return StorageService(
        "http://mlops-nas:9000", "ak", "sk", "artifacts", "datasets", 3600, sts=sts
    )


def test_presigned_urls_target_the_public_endpoint():
    svc = _service()
    put, get = svc.presign_put("vision/seg/exp_1/m.pt"), svc.presign_get("vision/seg/exp_1/m.pt")
    assert put.startswith("http://mlops-nas:9000/artifacts/vision/seg/exp_1/m.pt?")
    assert "X-Amz-Signature=" in put and "X-Amz-Signature=" in get


def test_sts_scopes_policy_to_project_prefix():
    sts = FakeSts()
    creds = _service(sts).sts_credentials("vision/seg", write=False)
    call = sts.calls[0]
    assert call["DurationSeconds"] == 3600 and "/" not in call["RoleSessionName"]
    assert "vision/seg/" in call["Policy"] and "PutObject" not in call["Policy"]
    assert (creds.access_key, creds.session_token) == ("AK", "ST")
    assert creds.prefix == "vision/seg/" and creds.endpoint_url == "http://mlops-nas:9000"

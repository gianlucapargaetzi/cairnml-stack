import subprocess
from datetime import UTC, datetime

import pytest
from mlops_agent.dvc import DvcError, UnsupportedDataset, dataset_targets, dvc_pull
from mlops_common.schemas import DatasetRef, StsResponse

STS = StsResponse(access_key="AK1", secret_key="SECRET-KEY", session_token="SESSION-TOKEN",
                  expires_at=datetime(2030, 1, 1, tzinfo=UTC), endpoint_url="http://mlops-nas:9000",
                  bucket="datasets", prefix="p/")


def test_targets_for_code_repo_datasets():
    refs = [
        DatasetRef(path="data/train"),
        DatasetRef(path="data/val", repo="org/repo", commit="a" * 40),
    ]
    assert dataset_targets(refs, "org/repo", "a" * 40) == ["data/train", "data/val"]


@pytest.mark.parametrize("ref", [
    DatasetRef(path="d", repo="org/other"),
    DatasetRef(path="d", repo="org/repo", commit="b" * 40),
])
def test_unsupported_datasets_fail_fast(ref):
    with pytest.raises(UnsupportedDataset):
        dataset_targets([ref], "org/repo", "a" * 40)
    with pytest.raises(UnsupportedDataset):
        dataset_targets([DatasetRef(path="d")], None, None)


def test_pull_passes_credentials_through_the_environment_only(tmp_path):
    seen = {}

    def run(cmd, **kwargs):
        seen.update(cmd=cmd, env=kwargs["env"], cwd=kwargs["cwd"])
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    dvc_pull(tmp_path, ["data/train"], STS, run=run, which=lambda name: "/usr/bin/dvc")
    assert seen["cmd"] == ["dvc", "pull", "--force", "data/train"]
    assert seen["env"]["AWS_ACCESS_KEY_ID"] == "AK1"
    assert seen["env"]["AWS_SESSION_TOKEN"] == "SESSION-TOKEN"
    assert "SECRET-KEY" not in " ".join(seen["cmd"])


def test_failure_message_is_scrubbed(tmp_path):
    def run(cmd, **kwargs):
        stderr = "auth failed for SECRET-KEY / SESSION-TOKEN"
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=stderr)

    with pytest.raises(DvcError) as err:
        dvc_pull(tmp_path, ["x"], STS, run=run, which=lambda name: "/usr/bin/dvc")
    assert "SECRET-KEY" not in str(err.value) and "SESSION-TOKEN" not in str(err.value)


def test_missing_dvc_binary_and_no_targets(tmp_path):
    dvc_pull(tmp_path, [], STS, which=lambda name: None)  # nothing to do, no error
    with pytest.raises(DvcError, match="not installed"):
        dvc_pull(tmp_path, ["x"], STS, which=lambda name: None)

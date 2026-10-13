from types import SimpleNamespace

import pytest
from mlops import runtime
from mlops.api import ApiClient

_RUN_ENV = (
    "MLOPS_RUN_TOKEN",
    "MLOPS_RUN_ID",
    "MLOPS_SERVER_URL",
    "MLOPS_PARAMS",
    "MLOPS_JOB_ID",
)


@pytest.fixture
def cfg_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MLOPS_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("MLOPS_DATA_DIR", str(tmp_path / "data"))
    for name in _RUN_ENV:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def sdk(cfg_env, monkeypatch, enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    uploads = []

    def fake_put(url, source, http=None):
        data = source if isinstance(source, bytes) else source.read_bytes()
        uploads.append((url, data))

    monkeypatch.setattr("mlops.transfer.put_file", fake_put)
    api = ApiClient(dev.http)
    runtime.set_api_override(lambda token, url: api)
    yield SimpleNamespace(dev=dev, api=api, uploads=uploads)
    runtime.set_api_override(None)

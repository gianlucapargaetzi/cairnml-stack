import pytest
from fastapi.testclient import TestClient
from mlops_agent.api import AgentApi
from mlops_agent.config import AgentPaths
from mlops_common.http import KeyAuth
from mlops_common.keys import read_private_key


@pytest.fixture
def agent_home(tmp_path):
    return AgentPaths(tmp_path / "agent-home")


@pytest.fixture
def api_for(app, settings):
    def _make(paths: AgentPaths, agent_id: str) -> AgentApi:
        http = TestClient(app)
        http.auth = KeyAuth(
            settings.public_url, agent_id, read_private_key(paths.key), token_client=TestClient(app)
        )
        return AgentApi(http)

    return _make

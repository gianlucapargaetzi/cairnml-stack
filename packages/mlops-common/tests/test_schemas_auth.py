import pytest
from mlops_common.schemas import AgentTokenRequest, Capabilities, TokenResponse
from pydantic import ValidationError


def test_capabilities_defaults_and_validation():
    caps = Capabilities(cpu=4, memory_gb=16)
    assert caps.gpus == 0 and caps.runtimes == ["python", "image", "compose"]
    with pytest.raises(ValidationError):
        Capabilities(cpu=0, memory_gb=16)
    with pytest.raises(ValidationError):
        Capabilities(cpu=1, memory_gb=1, runtimes=["lua"])


def test_agent_token_ttl_bounds():
    assert AgentTokenRequest().ttl == 900
    with pytest.raises(ValidationError):
        AgentTokenRequest(ttl=10)
    with pytest.raises(ValidationError):
        AgentTokenRequest(ttl=10**6)


def test_token_response_default_type():
    assert TokenResponse(access_token="x", expires_in=3600).token_type == "bearer"

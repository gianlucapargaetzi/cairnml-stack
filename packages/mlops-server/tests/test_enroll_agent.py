from datetime import timedelta

import httpx
import pytest
from mlops_common.keys import generate_private_key, public_key_pem
from mlops_server.db import utcnow
from mlops_server.models import Agent, EnrollmentToken
from sqlalchemy import select

CAPS = {"cpu": 4, "memory_gb": 8}


def _enroll_agent(server, token, key=None):
    key = key or generate_private_key()
    return server.post(
        "/api/v1/enroll/agent",
        json={
            "token": token,
            "name": "a1",
            "public_key": public_key_pem(key),
            "capabilities": CAPS,
        },
    )


def _assert_refused(http):
    # KeyAuth raises when its token exchange is refused, so the 401 arrives as an exception.
    with pytest.raises(httpx.HTTPStatusError) as refused:
        http.get("/api/v1/me")
    assert refused.value.response.status_code == 401


def test_only_admins_can_create_agent_tokens(server, enroll_client):
    user = enroll_client("dev")
    assert user.http.post("/api/v1/admin/agent-tokens", json={}).status_code == 403
    admin = enroll_client("root", roles=["mlops-admin"])
    response = admin.http.post("/api/v1/admin/agent-tokens", json={"queues": ["gpu"]})
    assert response.status_code == 200
    assert response.json()["token"].startswith("mlops_at_")


def test_agent_tokens_require_authentication(server):
    assert server.post("/api/v1/admin/agent-tokens", json={}).status_code == 401


def test_agent_enrollment_is_single_use(server, enroll_client):
    admin = enroll_client("root", roles=["mlops-admin"])
    token = admin.http.post("/api/v1/admin/agent-tokens", json={"queues": ["gpu"]}).json()["token"]
    first = _enroll_agent(server, token)
    assert first.status_code == 200 and first.json()["queues"] == ["gpu"]
    assert _enroll_agent(server, token).status_code == 401


def test_unknown_and_expired_tokens_look_the_same(server, enroll_client, app):
    admin = enroll_client("root", roles=["mlops-admin"])
    token = admin.http.post("/api/v1/admin/agent-tokens", json={}).json()["token"]
    with app.state.session_factory() as s:
        row = s.scalar(select(EnrollmentToken))
        row.expires_at = utcnow() - timedelta(seconds=1)
        s.commit()
    expired, unknown = _enroll_agent(server, token), _enroll_agent(server, "mlops_at_nope")
    assert expired.status_code == unknown.status_code == 401
    assert expired.json() == unknown.json()


def test_enrolled_agent_gets_tokens_and_capabilities_are_stored(server, make_agent, app):
    agent = make_agent(queues=["gpu"], cpu=16, gpus=2, labels=["a100"])
    assert agent.http.get("/api/v1/me").json()["kind"] == "agent"
    with app.state.session_factory() as s:
        row = s.get(Agent, agent.agent_id)
        assert row.queues == ["gpu"] and row.capabilities["gpus"] == 2


def test_agent_token_cannot_call_admin_endpoints(server, make_agent):
    agent = make_agent()
    assert agent.http.post("/api/v1/admin/agent-tokens", json={}).status_code == 403


def test_revocation_is_immediate(server, make_agent, enroll_client):
    agent = make_agent()
    assert agent.http.get("/api/v1/me").status_code == 200
    admin = enroll_client("root2", roles=["mlops-admin"])
    revoke = admin.http.post(f"/api/v1/admin/agents/{agent.agent_id}/revoke")
    assert revoke.json() == {"revoked": True}
    _assert_refused(agent.http)

    victim = enroll_client("victim")
    assert victim.http.get("/api/v1/me").status_code == 200
    admin.http.post(f"/api/v1/admin/clients/{victim.client_id}/revoke")
    _assert_refused(victim.http)


def test_admin_listings_and_non_admin_denied(server, make_agent, enroll_client):
    agent = make_agent()
    admin = enroll_client("root3", roles=["mlops-admin"])
    listed = admin.http.get("/api/v1/admin/agents").json()
    assert any(a["id"] == agent.agent_id for a in listed)
    assert admin.http.get("/api/v1/admin/clients").status_code == 200
    assert enroll_client("dev2").http.get("/api/v1/admin/agents").status_code == 403

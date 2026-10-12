import httpx
import pytest

pytestmark = pytest.mark.e2e


def test_every_protected_endpoint_rejects_anonymous_and_forged_callers(stack, server_url):
    for method, path in [
        ("get", "/api/v1/me"),
        ("get", "/api/v1/projects"),
        ("post", "/api/v1/jobs"),
        ("post", "/api/v1/agents/poll"),
        ("post", "/api/v1/admin/agent-tokens"),
    ]:
        assert getattr(httpx, method)(server_url + path).status_code in (401, 422), path
    forged = {"Authorization": "Bearer eyJhbGciOiJFZERTQSJ9.e30.AAAA"}
    assert httpx.get(server_url + "/api/v1/me", headers=forged).status_code == 401


def test_enrollment_needs_a_real_idp_login(stack, server_url):
    body = {
        "name": "x",
        "public_key": "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----",
    }
    assert httpx.post(server_url + "/api/v1/enroll/client", json=body).status_code == 401
    assert (
        httpx.post(
            server_url + "/api/v1/enroll/client",
            json=body,
            headers={"Authorization": "Bearer not-a-jwt"},
        ).status_code
        == 401
    )


def test_agent_enrollment_needs_a_valid_admin_token(stack, server_url):
    body = {
        "token": "mlops_at_made_up",
        "name": "evil",
        "public_key": "x",
        "capabilities": {"cpu": 1, "memory_gb": 1},
    }
    assert httpx.post(server_url + "/api/v1/enroll/agent", json=body).status_code in (401, 422)


def test_only_admins_can_create_agent_tokens(dev, admin):
    denied = dev.api()._http.post("/api/v1/admin/agent-tokens", json={"queues": ["default"]})
    assert denied.status_code == 403 and "admin role required" in denied.text
    token = admin.api()._http.post("/api/v1/admin/agent-tokens", json={"queues": ["default"]})
    assert token.status_code == 200 and token.json()["token"].startswith("mlops_at_")


def test_a_client_key_works_without_any_login_and_a_revoked_one_stops(make_cli, admin):
    victim = make_cli("dev")
    whoami = victim.run("whoami").stdout
    assert whoami.startswith("client cli_")
    client_id = whoami.split()[1]
    revoked = admin.api()._http.post(f"/api/v1/admin/clients/{client_id}/revoke")
    assert revoked.status_code == 200
    assert victim.run("whoami", check=False).returncode != 0


def test_a_client_token_does_not_work_on_agent_endpoints(dev, stack):
    api = dev.api()
    assert api._http.post("/api/v1/agents/poll", json={"wait_s": 0}).status_code == 403

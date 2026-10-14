from fastapi.testclient import TestClient
from mlops_server.testing import login_browser


def test_my_clients_lists_only_the_signed_in_users_machines(browser, enroll_client):
    enroll_client("alice", name="alice-laptop")
    enroll_client("bob", name="bob-laptop")
    login_browser(browser)  # signs in as alice, the browser fixture's default user
    clients = browser.get("/api/v1/me/clients").json()
    assert [c["name"] for c in clients] == ["alice-laptop"]
    assert clients[0]["revoked_at"] is None and clients[0]["created_at"]


def test_my_clients_needs_a_web_session(app, enroll_client):
    enroll_client("alice")
    assert TestClient(app).get("/api/v1/me/clients").status_code == 401

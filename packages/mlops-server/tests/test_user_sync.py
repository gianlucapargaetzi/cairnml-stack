import httpx
import pytest
from mlops_server.models import Client, Job, Run, User
from mlops_server.services.user_sync import sync_users


@pytest.fixture
def world(server, enroll_client, make_project, make_agent, new_job, stub_directory):
    admin = enroll_client("root", roles=["mlops-admin"])
    carol = enroll_client("carol")
    bob = enroll_client("bob")
    make_project("vision/seg", members=["carol", "bob"])
    agent = make_agent()
    running = new_job(carol.http)
    agent.http.post("/api/v1/agents/poll", json={"wait_s": 0})
    agent.http.post(f"/api/v1/jobs/{running['id']}/status", json={"status": "running"})
    run_token = agent.http.post(f"/api/v1/jobs/{running['id']}/run-token").json()["access_token"]
    queued = new_job(carol.http)
    bobs = new_job(bob.http)
    return dict(admin=admin, carol=carol, bob=bob, agent=agent, running=running, queued=queued,
                bobs=bobs, run_token=run_token)


def _refused(http):
    # A revoked client fails at the key exchange (KeyAuth raises on the 401), not at /me.
    with pytest.raises(httpx.HTTPStatusError) as refused:
        http.get("/api/v1/me")
    assert refused.value.response.status_code == 401


def _sync(admin):
    response = admin.http.post("/api/v1/admin/sync-users")
    assert response.status_code == 200, response.text
    return response.json()


def test_nothing_changes_while_the_idp_agrees(world, stub_directory):
    report = _sync(world["admin"])
    assert report["disabled"] == [] and report["errors"] == 0 and report["checked"] >= 3
    assert world["carol"].http.get("/api/v1/me").status_code == 200


def test_disabling_a_user_in_the_idp_revokes_everything(world, stub_directory, app, server):
    stub_directory.disable("sub-carol")
    report = _sync(world["admin"])
    assert report["disabled"] == [world["carol"].user_id]
    # 1) the client key stops working immediately
    _refused(world["carol"].http)
    # 2) the client rows are revoked (not just the user flag)
    with app.state.session_factory() as s:
        carol_clients = s.query(Client).filter(Client.user_id == world["carol"].user_id)
        assert all(c.revoked_at for c in carol_clients)
        # 3) queued jobs are cancelled, running ones are asked to stop
        assert s.get(Job, world["queued"]["id"]).status == "cancelled"
        assert s.get(Run, world["queued"]["run_id"]).status == "cancelled"
        assert s.get(Job, world["running"]["id"]).cancel_requested is True
        assert s.get(Job, world["bobs"]["id"]).status == "queued"  # other users untouched
    hb = world["agent"].http.post("/api/v1/agents/heartbeat",
                                  json={"running_job_ids": [world["running"]["id"]]}).json()
    assert hb["cancel_job_ids"] == [world["running"]["id"]]
    # 4) the run token of the user's running job is dead as well
    assert world["bob"].http.get("/api/v1/me").status_code == 200
    bearer = {"Authorization": f"Bearer {world['run_token']}"}
    # The bearer header is used as is; the run token is refused because its owner is disabled.
    assert server.get("/api/v1/me", headers=bearer).status_code == 401


def test_a_deleted_user_is_treated_as_disabled(world, stub_directory):
    stub_directory.remove("sub-bob")
    assert _sync(world["admin"])["disabled"] == [world["bob"].user_id]
    _refused(world["bob"].http)


def test_reenabling_unblocks_the_account_but_old_keys_stay_revoked(
    world, stub_directory, enroll_client
):
    stub_directory.disable("sub-carol")
    _sync(world["admin"])
    stub_directory.enable("sub-carol")
    report = _sync(world["admin"])
    assert report["reenabled"] == [world["carol"].user_id]
    _refused(world["carol"].http)  # the old key is gone for good
    fresh = enroll_client("carol")  # enrolling a new key works again
    assert fresh.http.get("/api/v1/me").status_code == 200


def test_enrollment_is_refused_for_a_user_the_sync_has_disabled(world, stub_directory, server, idp):
    stub_directory.disable("sub-carol")
    _sync(world["admin"])
    from mlops_common.keys import generate_private_key, public_key_pem

    token = idp.token(sub="sub-carol", username="carol")
    denied = server.post(
        "/api/v1/enroll/client",
        json={"name": "x", "public_key": public_key_pem(generate_private_key())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 403


def test_losing_the_admin_role_takes_effect_after_sync(server, enroll_client, stub_directory):
    boss = enroll_client("boss", roles=["mlops-admin"])
    other = enroll_client("other", roles=["mlops-admin"])
    stub_directory.set_roles("sub-boss", [])
    assert other.http.post("/api/v1/admin/sync-users").json()["roles_changed"]
    assert boss.http.post("/api/v1/admin/agent-tokens", json={}).status_code == 403


def test_an_idp_outage_changes_nothing(world, stub_directory):
    stub_directory.fail_for("sub-carol")
    report = _sync(world["admin"])
    assert report["errors"] == 1 and report["disabled"] == []
    assert world["carol"].http.get("/api/v1/me").status_code == 200


def test_sync_users_function_directly(server, app, enroll_client, stub_directory):
    enroll_client("dave")
    with app.state.session_factory() as s:
        assert sync_users(s, stub_directory).disabled == []


def test_only_admins_can_trigger_a_sync_and_missing_directory_is_503(server, enroll_client, app):
    assert enroll_client("dev").http.post("/api/v1/admin/sync-users").status_code == 403
    admin = enroll_client("root", roles=["mlops-admin"])
    saved, app.state.directory = app.state.directory, None
    try:
        assert admin.http.post("/api/v1/admin/sync-users").status_code == 503
    finally:
        app.state.directory = saved


class _GoneDirectory:
    """Every user is missing from the IdP, as if the directory URL were wrong."""

    def get_user(self, subject):
        return None


def test_a_directory_that_reports_every_user_gone_disables_nobody(world, app):
    with app.state.session_factory() as s:
        report = sync_users(s, _GoneDirectory())
        assert report.disabled == [] and report.checked >= 3
        assert report.errors == report.checked  # every would-be disable is held back
    with app.state.session_factory() as s:
        assert not any(u.disabled for u in s.query(User).all())
    assert world["carol"].http.get("/api/v1/me").status_code == 200


def test_a_200_reply_without_enabled_is_an_error_and_disables_nobody(world, app):
    import httpx
    from mlops_server.services.directory import KeycloakDirectory

    issuer = "http://idp.test/realms/mlops"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 300})
        if path.endswith("/composite"):
            return httpx.Response(200, json=[])
        if path.endswith("/users/sub-carol"):
            return httpx.Response(200, json={"id": "sub-carol"})  # proxy-style reply: no "enabled"
        return httpx.Response(200, json={"enabled": True})

    directory = KeycloakDirectory(issuer, "mlops-server", "secret",
                                  http=httpx.Client(transport=httpx.MockTransport(handler)))
    with app.state.session_factory() as s:
        report = sync_users(s, directory)
        assert report.errors == 1 and report.disabled == []
    with app.state.session_factory() as s:
        assert s.get(User, world["carol"].user_id).disabled is False
    assert world["carol"].http.get("/api/v1/me").status_code == 200


def test_one_missing_user_among_several_is_disabled(world, stub_directory):
    stub_directory.remove("sub-bob")
    report = _sync(world["admin"])
    assert report["disabled"] == [world["bob"].user_id]
    assert report["errors"] == 0
    assert world["carol"].http.get("/api/v1/me").status_code == 200

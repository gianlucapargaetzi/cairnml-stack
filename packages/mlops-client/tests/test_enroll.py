import stat

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from mlops.api import ApiClient
from mlops.cli import app as cli_app
from mlops.config import key_path, load_config
from mlops.enroll import enroll, whoami
from mlops.idp import LoginFailed, device_login
from mlops_common.http import KeyAuth
from mlops_common.keys import read_private_key

ISSUER = "http://mlops-idp:8080/realms/mlops"


def _mock_idp(router, token_responses):
    router.get(f"{ISSUER}/.well-known/openid-configuration").respond(
        200,
        json={
            "device_authorization_endpoint": f"{ISSUER}/device",
            "token_endpoint": f"{ISSUER}/token",
        },
    )
    router.post(f"{ISSUER}/device").respond(
        200,
        json={
            "device_code": "dc",
            "user_code": "ABCD",
            "interval": 1,
            "expires_in": 600,
            "verification_uri_complete": f"{ISSUER}/device?user_code=ABCD",
        },
    )
    return router.post(f"{ISSUER}/token").mock(side_effect=token_responses)


@respx.mock
def test_device_login_polls_until_approved():
    route = _mock_idp(
        respx.mock,
        [
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(400, json={"error": "slow_down"}),
            httpx.Response(200, json={"access_token": "idp-token"}),
        ],
    )
    printed, opened, slept = [], [], []
    token = device_login(
        ISSUER, "mlops-cli", sleep=slept.append, out=printed.append, open_browser=opened.append
    )
    assert token == "idp-token" and route.call_count == 3
    assert any("ABCD" in line for line in printed) and opened == [f"{ISSUER}/device?user_code=ABCD"]
    assert slept == [1, 1, 6]  # slow_down adds 5 seconds


@respx.mock
def test_device_login_reports_denial():
    _mock_idp(
        respx.mock,
        [httpx.Response(400, json={"error": "access_denied", "error_description": "no"})],
    )
    with pytest.raises(LoginFailed, match="no"):
        device_login(
            ISSUER,
            "mlops-cli",
            sleep=lambda s: None,
            out=lambda s: None,
            open_browser=lambda u: None,
        )


def test_enroll_writes_config_and_a_private_key(cfg_env, server, idp, settings):
    cfg = enroll(server, "laptop", idp_token=idp.token(username="dev"))
    assert cfg.server_url == settings.public_url and cfg.client_id.startswith("cli_")
    assert stat.S_IMODE(key_path().stat().st_mode) == 0o600 and load_config() == cfg


def test_enrolled_key_works_without_the_idp(cfg_env, server, idp, app, settings):
    cfg = enroll(server, "laptop", idp_token=idp.token(username="dev"))
    http = TestClient(app)
    http.auth = KeyAuth(
        cfg.server_url, cfg.client_id, read_private_key(key_path()), token_client=TestClient(app)
    )
    me = whoami(ApiClient(http))
    assert me["kind"] == "client"


def test_login_is_used_when_no_idp_token_is_given(cfg_env, server, idp):
    cfg = enroll(server, "laptop", login=lambda issuer, client_id: idp.token(username="dev"))
    assert load_config() == cfg


def test_enroll_twice_needs_force(cfg_env, server, idp):
    enroll(server, "a", idp_token=idp.token())
    with pytest.raises(RuntimeError, match="already enrolled"):
        enroll(server, "b", idp_token=idp.token())
    assert (
        enroll(server, "b", idp_token=idp.token(), force=True).client_id == load_config().client_id
    )


def test_rejected_idp_token_leaves_nothing_behind(cfg_env, server, idp):
    with pytest.raises(httpx.HTTPStatusError):
        enroll(server, "a", idp_token=idp.token(azp="other-client"))
    assert load_config() is None and not key_path().exists()


def test_cli_whoami_without_enrollment(cfg_env):
    from typer.testing import CliRunner

    result = CliRunner().invoke(cli_app, ["whoami"])
    assert result.exit_code == 1 and "mlops enroll" in result.output


@respx.mock
def test_browser_failure_does_not_abort_login():
    _mock_idp(respx.mock, [httpx.Response(200, json={"access_token": "idp-token"})])

    def broken_browser(url):
        raise RuntimeError("no browser here")

    printed = []
    token = device_login(
        ISSUER, "mlops-cli", sleep=lambda s: None, out=printed.append, open_browser=broken_browser
    )
    assert token == "idp-token"
    assert any(f"{ISSUER}/device?user_code=ABCD" in line for line in printed)


def test_force_write_failure_keeps_the_old_key(cfg_env, server, idp, monkeypatch):
    enroll(server, "a", idp_token=idp.token())
    old_key = key_path().read_bytes()
    old_cfg = load_config()

    def failing_write(path, key):
        raise OSError("disk full")

    monkeypatch.setattr("mlops.enroll.write_private_key", failing_write)
    with pytest.raises(OSError, match="disk full"):
        enroll(server, "b", idp_token=idp.token(), force=True)
    assert key_path().read_bytes() == old_key and load_config() == old_cfg


def test_save_config_failure_leaves_no_key_without_earlier_enrollment(
    cfg_env, server, idp, monkeypatch
):
    def failing_save(cfg):
        raise OSError("read-only config dir")

    monkeypatch.setattr("mlops.enroll.save_config", failing_save)
    with pytest.raises(OSError, match="read-only"):
        enroll(server, "a", idp_token=idp.token())
    assert not key_path().exists() and load_config() is None


def test_save_config_failure_restores_the_previous_key(cfg_env, server, idp, monkeypatch):
    enroll(server, "a", idp_token=idp.token())
    old_key = key_path().read_bytes()
    old_cfg = load_config()

    def failing_save(cfg):
        raise OSError("read-only config dir")

    monkeypatch.setattr("mlops.enroll.save_config", failing_save)
    with pytest.raises(OSError):
        enroll(server, "b", idp_token=idp.token(), force=True)
    assert key_path().read_bytes() == old_key and load_config() == old_cfg


def test_cli_whoami_reports_an_unreachable_server(cfg_env, monkeypatch):
    from mlops.api import ApiClient as Api
    from typer.testing import CliRunner

    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    api = Api(
        httpx.Client(base_url="http://mlops.example:8000", transport=httpx.MockTransport(refuse))
    )
    monkeypatch.setattr("mlops.runtime.make_api", lambda *args, **kwargs: api)
    result = CliRunner().invoke(cli_app, ["whoami"])
    assert result.exit_code == 1
    assert "cannot reach http://mlops.example:8000" in result.output
    assert "Traceback" not in result.output


def test_forced_browser_enrollment_logs_the_old_session_out_first(cfg_env, server, idp):
    enroll(server, "a", idp_token=idp.token(username="alice"))
    calls = []

    def logout(issuer, client_id):
        calls.append(("logout", issuer))

    def login(issuer, client_id):
        calls.append(("login", issuer))
        return idp.token(username="bob")

    enroll(server, "b", login=login, logout=logout, force=True)
    assert [step for step, _ in calls] == ["logout", "login"]


def test_first_enrollment_and_token_enrollment_do_not_log_out(cfg_env, server, idp):
    def logout(issuer, client_id):
        raise AssertionError("no logout expected")

    enroll(server, "a", login=lambda i, c: idp.token(), logout=logout)
    enroll(server, "b", idp_token=idp.token(), logout=logout, force=True)


def _visit_redirect():
    # urllib, not httpx: respx mocks every httpx request in these tests.
    from urllib.request import urlopen

    urlopen("http://127.0.0.1:8799/logged-out", timeout=5).read()


@respx.mock
def test_end_idp_session_waits_for_the_idp_redirect():
    import threading

    from mlops.idp import end_idp_session

    respx.get(f"{ISSUER}/.well-known/openid-configuration").respond(
        200, json={"end_session_endpoint": f"{ISSUER}/logout"}
    )
    opened = []

    def browser(url):
        opened.append(url)
        # The IdP sends the browser back to the local redirect once the logout is done.
        threading.Thread(target=_visit_redirect, daemon=True).start()

    end_idp_session(ISSUER, "mlops-cli", open_browser=browser, port=8799, timeout=10)
    assert opened and opened[0].startswith(f"{ISSUER}/logout?")
    assert "client_id=mlops-cli" in opened[0] and "8799%2Flogged-out" in opened[0]


@respx.mock
def test_end_idp_session_fails_when_no_redirect_comes():
    from mlops.idp import LoginFailed, end_idp_session

    respx.get(f"{ISSUER}/.well-known/openid-configuration").respond(
        200, json={"end_session_endpoint": f"{ISSUER}/logout"}
    )
    with pytest.raises(LoginFailed, match="not confirmed"):
        end_idp_session(ISSUER, "mlops-cli", open_browser=lambda url: None, port=8798, timeout=1)


@respx.mock
def test_end_idp_session_without_endpoint_opens_nothing():
    from mlops.idp import end_idp_session

    respx.get(f"{ISSUER}/.well-known/openid-configuration").respond(200, json={})
    opened = []
    end_idp_session(ISSUER, "mlops-cli", open_browser=opened.append)
    assert opened == []

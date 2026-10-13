import hashlib

import pytest
from mlops_server.db import utcnow
from mlops_server.models import WebLogin, WebSession
from mlops_server.testing import login_browser, start_login
from sqlalchemy import select


def test_login_redirects_to_the_idp_with_pkce_state_and_nonce(browser, settings):
    response, query = start_login(browser)
    authorize = f"{settings.oidc_issuer}/protocol/openid-connect/auth?"
    assert response.headers["location"].startswith(authorize)
    assert query["client_id"] == ["mlops-web"] and query["response_type"] == ["code"]
    assert query["redirect_uri"] == [f"{settings.public_url}/ui/auth/callback"]
    assert query["code_challenge_method"] == ["S256"] and query["scope"] == ["openid"]
    cookie = response.headers["set-cookie"].lower()
    assert "mlops_login=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_callback_creates_a_session_and_me_works_with_the_cookie(browser, app):
    _, query = start_login(browser)
    done = browser.get("/ui/auth/callback", params={"code": "abc", "state": query["state"][0]})
    assert done.status_code == 302 and done.headers["location"] == "/ui-next/"
    cookie = done.headers["set-cookie"].lower()
    assert "mlops_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie
    sent = browser.idp["calls"][0]
    assert sent["grant_type"] == "authorization_code" and sent["client_id"] == "mlops-web"
    assert sent["code"] == "abc"
    assert sent["code_verifier"] and sent["redirect_uri"].endswith("/ui/auth/callback")
    me = browser.get("/api/v1/me").json()
    assert me["kind"] == "web" and me["username"] == "alice" and me["csrf"]
    with app.state.session_factory() as s:
        row = s.scalar(select(WebSession))
        cookie = browser.cookies["mlops_session"].encode()
        assert row.token_hash == hashlib.sha256(cookie).hexdigest()
        assert s.scalar(select(WebLogin)) is None  # the login transaction is single use


@pytest.mark.parametrize(
    "mutate", ["state", "cookie", "replay", "code", "idp_fail", "wrong_client", "nonce"]
)
def test_callback_rejections_leave_no_session(browser, app, mutate):
    _, query = start_login(browser)
    state = query["state"][0]
    params = {"code": "abc", "state": state}
    if mutate == "state":
        params["state"] = "forged"
    headers = {}
    if mutate == "cookie":
        # an explicit header replaces the cookie jar
        headers = {"Cookie": "mlops_login=another-state"}
    if mutate == "code":
        params.pop("code")
    if mutate == "idp_fail":
        browser.idp["status"] = 400
    if mutate == "wrong_client":
        browser.idp["azp"] = "mlops-cli"
    if mutate == "nonce":
        browser.idp["nonce_override"] = "not-the-nonce"
    if mutate == "replay":
        assert browser.get("/ui/auth/callback", params=params).status_code == 302
        # a perfect replay of the same cookie and code
        headers = {"Cookie": f"mlops_login={state}"}
    response = browser.get("/ui/auth/callback", params=params, headers=headers)
    assert response.status_code == 400
    assert "mlops_session" not in response.headers.get("set-cookie", "")
    assert "forged" not in response.text and state not in response.text
    with app.state.session_factory() as s:
        expected = 1 if mutate == "replay" else 0
        assert len(s.scalars(select(WebSession)).all()) == expected


def test_disabled_users_cannot_log_in(browser, app, enroll_client):
    enroll_client("alice")
    from mlops_server.models import User

    with app.state.session_factory() as s:
        s.scalar(select(User).where(User.username == "alice")).disabled = True
        s.commit()
    _, query = start_login(browser)
    done = browser.get("/ui/auth/callback", params={"code": "c", "state": query["state"][0]})
    assert done.status_code == 403


def test_session_dies_when_expired_or_the_user_is_disabled(browser, app):
    login_browser(browser)
    assert browser.get("/api/v1/me").status_code == 200
    from datetime import timedelta

    from mlops_server.models import User

    with app.state.session_factory() as s:
        s.scalar(select(User)).disabled = True
        s.commit()
    assert browser.get("/api/v1/me").status_code == 401
    with app.state.session_factory() as s:
        s.scalar(select(User)).disabled = False
        s.scalar(select(WebSession)).expires_at = utcnow() - timedelta(seconds=1)
        s.commit()
    assert browser.get("/api/v1/me").status_code == 401


def test_logout_needs_the_csrf_token_and_ends_the_session(browser):
    me = login_browser(browser)
    assert browser.post("/ui/auth/logout").status_code == 403
    assert browser.post("/ui/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    response = browser.post("/ui/auth/logout", headers={"X-CSRF-Token": me["csrf"]})
    assert response.status_code == 200
    assert "protocol/openid-connect/logout" in response.json()["logout_url"]
    assert browser.get("/api/v1/me").status_code == 401


def test_an_authorization_header_wins_over_the_cookie_and_web_tokens_cannot_enroll(
    browser, idp, server
):
    login_browser(browser)
    from mlops_common.keys import generate_private_key, public_key_pem

    web_token = idp.token(azp="mlops-web")
    body = {"name": "x", "public_key": public_key_pem(generate_private_key())}
    denied = server.post("/api/v1/enroll/client", json=body,
                         headers={"Authorization": f"Bearer {web_token}"})
    assert denied.status_code == 401  # the CLI enrollment only takes tokens issued to mlops-cli
    assert browser.get("/api/v1/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_secure_cookie_over_https(browser, app):
    app.state.settings.public_url = "https://mlops.example"
    response = browser.get("/ui/auth/login")
    assert "secure" in response.headers["set-cookie"].lower()


@pytest.mark.parametrize(
    "requested, expected",
    [
        ("/ui-next/runs?q=x", "/ui-next/runs?q=x"),
        ("/ui/", "/ui/"),
        ("https://evil.example/", "/ui-next/"),
        ("//evil.example/", "/ui-next/"),
        ("/api/v1/me", "/ui-next/"),
        (None, "/ui-next/"),
    ],
)
def test_login_returns_the_browser_to_an_allowed_ui_path_only(browser, requested, expected):
    _, query = start_login(browser, {"next": requested} if requested else None)
    done = browser.get("/ui/auth/callback", params={"code": "abc", "state": query["state"][0]})
    assert done.status_code == 302 and done.headers["location"] == expected

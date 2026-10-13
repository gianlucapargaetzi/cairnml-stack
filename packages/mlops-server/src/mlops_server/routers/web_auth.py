"""Browser login: authorization code flow with PKCE, handled entirely on the server."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import WebLogin, WebSession
from mlops_server.security.deps import Principal, check_csrf, get_session, require
from mlops_server.services import audit
from mlops_server.services.users import upsert_user

router = APIRouter(prefix="/ui/auth")
SESSION_COOKIE, LOGIN_COOKIE = "mlops_session", "mlops_login"

_PAGE = ("<!doctype html><meta charset=utf-8><title>Login failed</title>"
         "<p>The login could not be completed.</p>"
         "<p><a href=\"/ui/auth/login\">Try again</a></p>")


def endpoints(settings) -> tuple[str, str, str]:
    base = settings.oidc_issuer.rstrip("/") + "/protocol/openid-connect"
    return (settings.oidc_authorization_endpoint or f"{base}/auth",
            settings.oidc_token_endpoint or f"{base}/token",
            settings.oidc_logout_endpoint or f"{base}/logout")


def _secure(settings) -> bool:
    return settings.public_url.startswith("https://")


def _fail(status: int = 400) -> HTMLResponse:
    return HTMLResponse(_PAGE, status_code=status)


NEXT_COOKIE = "mlops_next"
ALLOWED_NEXT = ("/ui/", "/ui-next/")


def _safe_next(value: str | None) -> str:
    """Where to send the browser after sign-in. Only paths of this server's UIs are allowed."""
    if value and value.startswith(ALLOWED_NEXT) and not value.startswith("//"):
        return value
    return "/ui-next/"


@router.get("/login")
def login(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    next: str | None = None,
):
    settings = request.app.state.settings
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    now = datetime.now(UTC)
    session.execute(delete(WebLogin).where(WebLogin.expires_at < now))
    session.add(WebLogin(state=state, verifier=verifier, nonce=nonce,
                         expires_at=now + timedelta(minutes=10)))
    session.commit()
    query = urlencode({
        "response_type": "code", "client_id": settings.web_client_id, "scope": "openid",
        "redirect_uri": f"{settings.public_url.rstrip('/')}/ui/auth/callback",
        "state": state, "nonce": nonce, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    authorize_url = endpoints(settings)[0]
    response = RedirectResponse(f"{authorize_url}?{query}", status_code=302)
    response.set_cookie(LOGIN_COOKIE, state, max_age=600, httponly=True, samesite="lax",
                        secure=_secure(settings), path="/ui/auth")
    response.set_cookie(NEXT_COOKIE, _safe_next(next), max_age=600, httponly=True,
                        samesite="lax", secure=_secure(settings), path="/ui/auth")
    return response


@router.get("/callback")
def callback(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    settings = request.app.state.settings
    cookie = request.cookies.get(LOGIN_COOKIE)
    if error or not code or not state or not cookie:
        return _fail()
    if not hmac.compare_digest(cookie, state):
        return _fail()
    pending = session.get(WebLogin, state)
    if pending is None or pending.expires_at < datetime.now(UTC):
        return _fail()
    verifier, nonce = pending.verifier, pending.nonce
    session.delete(pending)
    session.commit()  # single use, even if the rest fails

    try:
        reply = request.app.state.idp_http.post(endpoints(settings)[1], data={
            "grant_type": "authorization_code", "code": code,
            "client_id": settings.web_client_id, "code_verifier": verifier,
            "redirect_uri": f"{settings.public_url.rstrip('/')}/ui/auth/callback",
        })
        if reply.status_code != 200:
            return _fail()
        body = reply.json()
        oidc = request.app.state.oidc
        identity = oidc.verify(body["access_token"], clients=[settings.web_client_id])
        oidc.verify_nonce(body["id_token"], nonce, clients=[settings.web_client_id])
    except Exception:  # any IdP or token problem: same fixed page, nothing echoed
        return _fail()

    user = upsert_user(session, identity)
    if user.disabled:
        session.commit()
        return _fail(403)
    token = secrets.token_urlsafe(32)
    session.add(WebSession(
        id=new_id("ws"), token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
        csrf=secrets.token_urlsafe(16),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.web_session_ttl),
    ))
    audit.record(session, user.id, "web.login", request)
    session.commit()
    response = RedirectResponse(_safe_next(request.cookies.get(NEXT_COOKIE)), status_code=302)
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.web_session_ttl,
                        httponly=True, samesite="lax", secure=_secure(settings), path="/")
    response.delete_cookie(LOGIN_COOKIE, path="/ui/auth")
    response.delete_cookie(NEXT_COOKIE, path="/ui/auth")
    return response


@router.post("/logout")
def logout(
    request: Request,
    principal: Annotated[Principal, Depends(require("web"))],
    session: Annotated[Session, Depends(get_session)],
    x_csrf_token: Annotated[str, Header()] = "",
):
    check_csrf(principal, x_csrf_token)
    row = session.get(WebSession, principal.id)
    if row is not None:
        session.delete(row)
    audit.record(session, principal.user_id, "web.logout", request)
    session.commit()
    settings = request.app.state.settings
    query = urlencode({"client_id": settings.web_client_id,
                       "post_logout_redirect_uri": f"{settings.public_url.rstrip('/')}/ui-next/"})
    logout_url = endpoints(settings)[2]
    response = JSONResponse({"logout_url": f"{logout_url}?{query}"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response

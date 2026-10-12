"""Request-level authentication: resolves a bearer token to a live Principal."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Agent, Client, Job, User, WebSession
from mlops_server.security.tokens import TokenInvalid


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


@dataclass(frozen=True)
class Principal:
    id: str
    kind: str  # "client" | "agent" | "run"
    user_id: str | None
    roles: frozenset[str]
    is_admin: bool
    experiment_id: str | None = None
    job_id: str | None = None
    csrf: str | None = None  # set for web sessions only


def _unauthorized(detail: str = "invalid credentials") -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def principal_dep(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        cookie = request.cookies.get("mlops_session")
        if header or not cookie:
            raise _unauthorized("missing bearer token")
        return _web_principal(request, session, cookie)
    try:
        claims = request.app.state.tokens.verify(header[7:].strip())
    except TokenInvalid:
        raise _unauthorized() from None
    admin_role = request.app.state.settings.oidc_admin_role

    if claims.kind == "client":
        row = session.get(Client, claims.sub)
        user = session.get(User, row.user_id) if row else None
        if row is None or row.revoked_at is not None or user is None or user.disabled:
            raise _unauthorized()
        roles = frozenset(user.roles or [])
        return Principal(row.id, "client", user.id, roles, admin_role in roles)

    if claims.kind == "agent":
        agent = session.get(Agent, claims.sub)
        if agent is None or agent.revoked_at is not None:
            raise _unauthorized()
        return Principal(agent.id, "agent", None, frozenset(), False)

    job = session.get(Job, claims.job_id) if claims.job_id else None
    owner = session.get(User, job.created_by) if job else None
    if (
        job is None
        or claims.sub != job.id
        or owner is None
        or owner.disabled
        or job.status not in ("assigned", "running")
        or job.experiment_id != claims.experiment_id
    ):
        raise _unauthorized()
    return Principal(
        job.id, "run", job.created_by, frozenset(), False, job.experiment_id, job.id
    )


def _web_principal(request: Request, session: Session, cookie: str) -> Principal:
    token_hash = hashlib.sha256(cookie.encode()).hexdigest()
    row = session.scalar(select(WebSession).where(WebSession.token_hash == token_hash))
    user = session.get(User, row.user_id) if row else None
    if row is None or row.expires_at < datetime.now(UTC) or user is None or user.disabled:
        raise _unauthorized()
    roles = frozenset(user.roles or [])
    admin_role = request.app.state.settings.oidc_admin_role
    return Principal(row.id, "web", user.id, roles, admin_role in roles, csrf=row.csrf)


def check_csrf(principal: Principal, presented: str) -> None:
    """State-changing requests made with a session cookie must echo its CSRF token."""
    if principal.kind != "web":
        return
    if not principal.csrf or not hmac.compare_digest(principal.csrf, presented or ""):
        raise HTTPException(403, "missing or wrong CSRF token")


READERS = ("client", "web")
READ_ANY = ("client", "agent", "run", "web")


def require(*kinds: str, admin: bool = False) -> Callable[..., Principal]:
    def dependency(principal: Annotated[Principal, Depends(principal_dep)]) -> Principal:
        if kinds and principal.kind not in kinds:
            raise HTTPException(403, "this token type is not allowed here")
        if admin and not principal.is_admin:
            raise HTTPException(403, "admin role required")
        return principal

    return dependency


def public_origin(settings) -> str:
    parsed = urlparse(settings.public_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def require_writer(*kinds: str, admin: bool = False) -> Callable[..., Principal]:
    """Like `require(*kinds, "web")`, but a browser session must also echo its CSRF token
    and, when an Origin header is sent, come from the public origin of this server."""
    base = require(*kinds, "web", admin=admin)

    def dependency(
        request: Request,
        principal: Principal = Depends(base),  # noqa: B008 (closure dependency)
        x_csrf_token: str = Header(default=""),
    ) -> Principal:
        if principal.kind == "web":
            if not principal.csrf or not hmac.compare_digest(principal.csrf, x_csrf_token):
                raise HTTPException(403, "missing or wrong CSRF token")
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != public_origin(request.app.state.settings):
                raise HTTPException(403, "cross-origin request refused")
        return principal

    return dependency

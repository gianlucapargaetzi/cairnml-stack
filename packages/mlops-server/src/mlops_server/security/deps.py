"""Request-level authentication: resolves a bearer token to a live Principal."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from mlops_server.models import Agent, Client, Job, User
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


def _unauthorized(detail: str = "invalid credentials") -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def principal_dep(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> Principal:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise _unauthorized("missing bearer token")
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
    if (
        job is None
        or job.status not in ("assigned", "running")
        or job.experiment_id != claims.experiment_id
    ):
        raise _unauthorized()
    return Principal(
        claims.sub, "run", job.created_by, frozenset(), False, job.experiment_id, job.id
    )


def require(*kinds: str, admin: bool = False) -> Callable[..., Principal]:
    def dependency(principal: Annotated[Principal, Depends(principal_dep)]) -> Principal:
        if kinds and principal.kind not in kinds:
            raise HTTPException(403, "this token type is not allowed here")
        if admin and not principal.is_admin:
            raise HTTPException(403, "admin role required")
        return principal

    return dependency

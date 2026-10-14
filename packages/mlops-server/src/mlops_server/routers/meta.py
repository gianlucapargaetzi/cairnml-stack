from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from mlops_common.schemas import PublicConfig
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Client, User
from mlops_server.security.deps import Principal, get_session, principal_dep, require

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config", response_model=PublicConfig)
def public_config(request: Request) -> PublicConfig:
    settings = request.app.state.settings
    return PublicConfig(
        server_url=settings.public_url,
        oidc_issuer=settings.oidc_issuer,
        oidc_client_id=settings.oidc_client_id,
    )


@router.get("/me/clients")
def my_clients(
    principal: Annotated[Principal, Depends(require("web"))],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    """The machines enrolled for the signed-in user. Read-only: revocation stays with the CLI."""
    rows = session.scalars(
        select(Client).where(Client.user_id == principal.user_id).order_by(Client.created_at)
    ).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "created_at": c.created_at.isoformat(),
            "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
        }
        for c in rows
    ]


@router.get("/me")
def me(
    principal: Annotated[Principal, Depends(principal_dep)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    user = session.get(User, principal.user_id) if principal.user_id else None
    return {
        "id": principal.id,
        "kind": principal.kind,
        "user_id": principal.user_id,
        "username": user.username if user else None,
        "roles": sorted(principal.roles),
        "is_admin": principal.is_admin,
        "csrf": principal.csrf,
    }

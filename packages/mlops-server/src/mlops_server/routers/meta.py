from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from mlops_common.schemas import PublicConfig
from sqlalchemy.orm import Session

from mlops_server.models import User
from mlops_server.security.deps import Principal, get_session, principal_dep

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

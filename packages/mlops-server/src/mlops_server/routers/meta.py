from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from mlops_common.schemas import PublicConfig

from mlops_server.security.deps import Principal, principal_dep

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
def me(principal: Annotated[Principal, Depends(principal_dep)]) -> dict:
    return {
        "id": principal.id,
        "kind": principal.kind,
        "user_id": principal.user_id,
        "roles": sorted(principal.roles),
        "is_admin": principal.is_admin,
    }

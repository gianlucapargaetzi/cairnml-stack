from __future__ import annotations

from fastapi import APIRouter, Request
from mlops_common.schemas import PublicConfig

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

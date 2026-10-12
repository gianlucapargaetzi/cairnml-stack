from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from mlops_server import models  # noqa: F401  (register tables)
from mlops_server.db import Base, make_engine
from mlops_server.routers import auth, enroll, meta
from mlops_server.settings import Settings


def create_app(
    settings: Settings | None = None, *, oidc=None, storage=None, github=None
) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="mlops-server", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    if oidc is None:
        from mlops_server.security.oidc import OidcVerifier

        oidc = OidcVerifier(
            settings.oidc_issuer,
            settings.oidc_client_id,
            jwks_url=settings.oidc_jwks_url
            or f"{settings.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs",
        )
    app.state.oidc = oidc
    app.state.storage = storage
    app.state.github = github
    from mlops_common.keys import read_private_key

    from mlops_server.security.tokens import TokenService

    app.state.tokens = TokenService(
        read_private_key(settings.signing_key_path), settings.public_url, settings.access_token_ttl
    )
    for module in (meta, enroll, auth):
        app.include_router(module.router, prefix="/api/v1")
    return app

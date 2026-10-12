from __future__ import annotations

import math
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from mlops_server import models  # noqa: F401  (register tables)
from mlops_server.db import Base, make_engine
from mlops_server.routers import (
    admin,
    agents,
    artifacts,
    auth,
    dashboard,
    enroll,
    experiments,
    jobs,
    meta,
    projects,
    repos,
    telemetry,
    web_auth,
)
from mlops_server.routers import storage as storage_api
from mlops_server.settings import Settings


def _json_safe(value: Any) -> Any:
    """Replace non-finite floats, which strict JSON cannot encode, with their string form."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


async def _validation_error_handler(_request: Request, exc: RequestValidationError):
    # Python's json accepts NaN/Infinity, so a bad body can carry them into the error detail.
    content = {"detail": jsonable_encoder(_json_safe(exc.errors()))}
    return JSONResponse(status_code=422, content=content)


def create_app(
    settings: Settings | None = None, *, oidc=None, storage=None, github=None, directory=None
) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if settings.auto_migrate:
            from mlops_server.migrate import upgrade

            upgrade(settings.database_url)
        else:
            Base.metadata.create_all(engine)
        reaper = None
        if settings.reaper_interval > 0:
            from mlops_server.services.reaper import ReaperThread

            reaper = ReaperThread(
                app.state.session_factory, settings.agent_timeout, settings.reaper_interval
            )
            reaper.start()
        user_sync = None
        if app.state.directory is not None and settings.idp_sync_interval > 0:
            from mlops_server.services.user_sync import UserSyncThread

            user_sync = UserSyncThread(
                app.state.session_factory, app.state.directory, settings.idp_sync_interval
            )
            user_sync.start()
        yield
        if user_sync is not None:
            user_sync.stop()
        if reaper is not None:
            reaper.stop()
        engine.dispose()

    app = FastAPI(title="mlops-server", lifespan=lifespan)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    if oidc is None:
        from mlops_server.security.oidc import OidcVerifier

        oidc = OidcVerifier(
            settings.oidc_issuer,
            [settings.oidc_client_id, settings.web_client_id],
            jwks_url=settings.oidc_jwks_url
            or f"{settings.oidc_issuer.rstrip('/')}/protocol/openid-connect/certs",
        )
    app.state.oidc = oidc
    app.state.idp_http = httpx.Client(timeout=10.0)
    if storage is None:
        from mlops_server.services.storage import build_storage

        storage = build_storage(settings)
    app.state.storage = storage
    if github is None:
        from mlops_server.services.github import build_github

        github = build_github(settings)
    app.state.github = github
    if directory is None:
        from mlops_server.services.directory import build_directory

        directory = build_directory(settings)
    app.state.directory = directory
    from mlops_common.keys import read_private_key

    from mlops_server.security.tokens import TokenService

    app.state.tokens = TokenService(
        read_private_key(settings.signing_key_path), settings.public_url, settings.access_token_ttl
    )
    for module in (
        meta, enroll, auth, admin, projects, experiments, telemetry, artifacts, storage_api, repos,
        jobs, agents, dashboard,
    ):
        app.include_router(module.router, prefix="/api/v1")
    app.include_router(web_auth.router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if path.startswith("/api") or path.startswith("/ui/auth") or path in ("/ui", "/ui/"):
            response.headers["Cache-Control"] = "no-store"
        if path.startswith("/ui"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'self'"
            )
        return response

    return app

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from mlops_server import models  # noqa: F401  (register tables)
from mlops_server.db import Base, make_engine
from mlops_server.routers import meta
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
    app.state.oidc = oidc
    app.state.storage = storage
    app.state.github = github
    app.state.tokens = None  # set in Task 8
    for module in (meta,):
        app.include_router(module.router, prefix="/api/v1")
    return app

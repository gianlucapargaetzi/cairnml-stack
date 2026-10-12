"""pytest plugin: Postgres container, fake IdP and enrollment helpers for every test."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from mlops_common.http import KeyAuth
from mlops_common.keys import generate_private_key, public_key_pem, write_private_key
from mlops_common.schemas import StsResponse

from mlops_server.app import create_app
from mlops_server.db import Base
from mlops_server.services.github import InstallationToken, RepoNotAccessible
from mlops_server.settings import Settings


class FakeIdp:
    ISSUER = "http://idp.test/realms/mlops"

    def __init__(self) -> None:
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "test-key"

    def jwks(self) -> dict:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key()))
        jwk.update(kid=self.kid, alg="RS256", use="sig")
        return {"keys": [jwk]}

    def token(
        self,
        sub: str = "sub-dev",
        username: str = "dev",
        roles: tuple[str, ...] | list[str] = (),
        azp: str = "mlops-cli",
        iss: str | None = None,
        exp_in: int = 300,
        key=None,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": iss or self.ISSUER,
            "sub": sub,
            "preferred_username": username,
            "azp": azp,
            "iat": now,
            "exp": now + exp_in,
            "realm_access": {"roles": list(roles)},
        }
        return jwt.encode(claims, key or self._key, algorithm="RS256", headers={"kid": self.kid})

    def verifier(self):
        from mlops_server.security.oidc import OidcVerifier

        return OidcVerifier(self.ISSUER, "mlops-cli", jwks=self.jwks())


@pytest.fixture(scope="session")
def pg_url():
    url = os.environ.get("MLOPS_TEST_DATABASE_URL")
    if url:
        yield url
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16", driver="psycopg") as pg:
        yield pg.get_connection_url()


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp()


@pytest.fixture
def settings(tmp_path, pg_url) -> Settings:
    key_path = tmp_path / "signing.pem"
    write_private_key(key_path, generate_private_key())
    return Settings(
        database_url=pg_url,
        public_url="http://testserver",
        signing_key_path=key_path,
        oidc_issuer=FakeIdp.ISSUER,
        oidc_client_id="mlops-cli",
    )


class StubStorage:
    def __init__(self) -> None:
        self.sts_calls: list[tuple[str, bool]] = []

    def presign_put(self, key: str, expires: int = 3600) -> str:
        return f"https://nas.test/artifacts/{key}?op=put"

    def presign_get(self, key: str, expires: int = 3600) -> str:
        return f"https://nas.test/artifacts/{key}?op=get"

    def sts_credentials(self, project_slug: str, write: bool) -> StsResponse:
        self.sts_calls.append((project_slug, write))
        return StsResponse(
            access_key="AK", secret_key="SK", session_token="ST",
            expires_at=datetime(2030, 1, 1, tzinfo=UTC), endpoint_url="https://nas.test",
            bucket="datasets", prefix=f"{project_slug}/",
        )


@pytest.fixture
def stub_storage() -> StubStorage:
    return StubStorage()


@pytest.fixture
def app(settings, idp, stub_storage, stub_github):
    application = create_app(
        settings, oidc=idp.verifier(), storage=stub_storage, github=stub_github
    )
    Base.metadata.drop_all(application.state.engine)
    return application


@pytest.fixture
def server(app):
    with TestClient(app) as client:
        yield client


@dataclass
class EnrolledClient:
    client_id: str
    user_id: str
    key: object
    http: TestClient


@pytest.fixture
def enroll_client(app, server, idp, settings):
    def _enroll(username: str = "dev", roles=(), name: str = "laptop") -> EnrolledClient:
        key = generate_private_key()
        response = server.post(
            "/api/v1/enroll/client",
            json={"name": name, "public_key": public_key_pem(key)},
            headers={
                "Authorization": "Bearer "
                + idp.token(sub=f"sub-{username}", username=username, roles=roles)
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        http = TestClient(app)
        http.auth = KeyAuth(
            settings.public_url, body["client_id"], key, token_client=TestClient(app)
        )
        return EnrolledClient(body["client_id"], body["user_id"], key, http)

    return _enroll


@dataclass
class EnrolledAgent:
    agent_id: str
    key: object
    http: TestClient


@pytest.fixture
def make_agent(app, server, enroll_client, settings):
    admin = enroll_client("root", roles=("mlops-admin",), name="admin-box")

    def _make(
        queues=("default",), cpu=8, memory_gb=32.0, gpus=0, labels=(),
        runtimes=("python", "image", "compose"),
    ) -> EnrolledAgent:
        token = admin.http.post("/api/v1/admin/agent-tokens", json={"queues": list(queues)})
        assert token.status_code == 200, token.text
        key = generate_private_key()
        response = server.post(
            "/api/v1/enroll/agent",
            json={
                "token": token.json()["token"],
                "name": "agent",
                "public_key": public_key_pem(key),
                "capabilities": {
                    "cpu": cpu, "memory_gb": memory_gb, "gpus": gpus,
                    "labels": list(labels), "runtimes": list(runtimes),
                },
            },
        )
        assert response.status_code == 200, response.text
        agent_id = response.json()["agent_id"]
        http = TestClient(app)
        http.auth = KeyAuth(settings.public_url, agent_id, key, token_client=TestClient(app))
        return EnrolledAgent(agent_id, key, http)

    return _make


@pytest.fixture
def make_project(enroll_client):
    admin = enroll_client("padmin", roles=("mlops-admin",), name="proj-admin")

    def _make(slug: str = "vision/seg", members=()) -> str:
        response = admin.http.post("/api/v1/projects", json={"slug": slug, "name": slug})
        assert response.status_code in (200, 409), response.text
        for username in members:
            added = admin.http.post(
                "/api/v1/project-members", json={"project": slug, "username": username}
            )
            assert added.status_code == 200, added.text
        return slug

    return _make


class StubGitHub:
    def __init__(self) -> None:
        self.commits: set[tuple[str, str]] = set()
        self.heads: dict[tuple[str, str], str] = {}
        self.inaccessible: set[str] = set()
        self.token_calls: list[str] = []

    def _check(self, repo: str) -> None:
        if repo in self.inaccessible:
            raise RepoNotAccessible(repo)

    def installation_token(self, repo: str) -> InstallationToken:
        self._check(repo)
        self.token_calls.append(repo)
        return InstallationToken("ghs_stub", datetime(2030, 1, 1, tzinfo=UTC))

    def commit_exists(self, repo: str, sha: str) -> bool:
        self._check(repo)
        return (repo, sha) in self.commits

    def head_commit(self, repo: str, ref: str) -> str | None:
        self._check(repo)
        return self.heads.get((repo, ref))


@pytest.fixture
def stub_github() -> StubGitHub:
    return StubGitHub()


@pytest.fixture
def new_job(stub_github):
    def _new(http, project="vision/seg", queue="default", runtime=None, resources=None, **extra):
        stub_github.commits.add(("org/repo", "a" * 40))
        spec = {
            "name": "job", "project": project, "queue": queue,
            "code": {"repo": "org/repo", "commit": "a" * 40},
            "runtime": runtime
            or {"type": "python", "python": "3.11", "command": ["python", "train.py"]},
            "resources": resources or {},
            **extra,
        }
        response = http.post("/api/v1/jobs", json=spec)
        assert response.status_code == 200, response.text
        return response.json()

    return _new

"""pytest plugin: Postgres container, fake IdP and enrollment helpers for every test."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from mlops_common.http import KeyAuth
from mlops_common.keys import generate_private_key, public_key_pem, write_private_key

from mlops_server.app import create_app
from mlops_server.db import Base
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


@pytest.fixture
def app(settings, idp):
    application = create_app(settings, oidc=idp.verifier())
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

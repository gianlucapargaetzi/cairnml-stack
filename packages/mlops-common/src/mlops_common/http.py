"""httpx helpers: key-based token exchange and static tokens."""

from __future__ import annotations

import threading
import time
from collections.abc import Generator

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mlops_common.assertion import make_assertion
from mlops_common.schemas import TokenResponse


class KeyAuth(httpx.Auth):
    """Signs an assertion with the machine key and exchanges it for a short-lived token."""

    requires_response_body = False

    def __init__(
        self,
        server_url: str,
        principal_id: str,
        key: Ed25519PrivateKey,
        token_client: httpx.Client | None = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._principal_id = principal_id
        self._key = key
        self._token_client = token_client
        self._token: str | None = None
        self._refresh_at = 0.0
        self._lock = threading.Lock()

    def _fetch(self) -> str:
        body = {"assertion": make_assertion(self._key, self._principal_id, self._server_url)}
        if self._token_client is not None:
            response = self._token_client.post("/api/v1/auth/token", json=body)
        else:
            with httpx.Client(base_url=self._server_url, timeout=30.0) as client:
                response = client.post("/api/v1/auth/token", json=body)
        response.raise_for_status()
        parsed = TokenResponse.model_validate(response.json())
        self._token = parsed.access_token
        self._refresh_at = time.time() + parsed.expires_in - 60
        return self._token

    def _current(self, force: bool = False) -> str:
        with self._lock:
            if force or self._token is None or time.time() >= self._refresh_at:
                return self._fetch()
            return self._token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._current()}"
        response = yield request
        if response.status_code == 401:
            request.headers["Authorization"] = f"Bearer {self._current(force=True)}"
            yield request


class StaticTokenAuth(httpx.Auth):
    def __init__(self, token: str) -> None:
        self._token = token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._token}"
        yield request


def make_client(
    server_url: str,
    auth: httpx.Auth | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 30.0,
) -> httpx.Client:
    return httpx.Client(
        base_url=server_url.rstrip("/"), auth=auth, transport=transport, timeout=timeout
    )

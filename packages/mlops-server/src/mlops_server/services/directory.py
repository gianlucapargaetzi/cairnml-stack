"""Asks the IdP whether a user still exists, is enabled and which roles they hold."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx


class DirectoryError(Exception):
    pass


@dataclass(frozen=True)
class DirectoryUser:
    enabled: bool
    roles: tuple[str, ...]


class Directory(Protocol):
    def get_user(self, subject: str) -> DirectoryUser | None: ...


def _json(response: httpx.Response, what: str) -> Any:
    try:
        return response.json()
    except ValueError:
        raise DirectoryError(f"malformed {what} response") from None


class KeycloakDirectory:
    def __init__(self, issuer: str, client_id: str, client_secret: str,
                 http: httpx.Client | None = None, clock=time.time) -> None:
        self._issuer = issuer.rstrip("/")
        self._admin = self._issuer.replace("/realms/", "/admin/realms/", 1)
        self._client_id, self._secret = client_id, client_secret
        self._http = http or httpx.Client(timeout=10.0)
        self._clock = clock
        self._lock = threading.Lock()  # guards _token and _expires_at only
        self._token: str | None = None
        self._expires_at = 0.0

    def _fetch_token(self) -> tuple[str, float]:
        try:
            response = self._http.post(
                f"{self._issuer}/protocol/openid-connect/token",
                data={"grant_type": "client_credentials", "client_id": self._client_id,
                      "client_secret": self._secret},
            )
        except httpx.HTTPError:
            raise DirectoryError("IdP unreachable") from None
        if response.status_code != 200:
            raise DirectoryError(f"IdP token request failed: {response.status_code}")
        body = _json(response, "token")
        if not isinstance(body, dict) or not isinstance(body.get("access_token"), str):
            raise DirectoryError("malformed token response")
        try:
            lifetime = float(body.get("expires_in", 60))
        except (TypeError, ValueError):
            raise DirectoryError("malformed token response") from None
        return body["access_token"], self._clock() + lifetime

    def _access_token(self) -> str:
        with self._lock:
            if self._token and self._clock() < self._expires_at - 30:
                return self._token
        token, expires_at = self._fetch_token()
        with self._lock:
            self._token, self._expires_at = token, expires_at
        return token

    def _forget(self, token: str) -> None:
        with self._lock:
            if self._token == token:
                self._token = None

    def _get(self, path: str) -> httpx.Response:
        for attempt in (1, 2):
            token = self._access_token()
            try:
                response = self._http.get(
                    self._admin + path, headers={"Authorization": f"Bearer {token}"})
            except httpx.HTTPError:
                raise DirectoryError("IdP unreachable") from None
            if response.status_code == 401 and attempt == 1:
                self._forget(token)
                continue
            return response
        raise DirectoryError("unreachable")

    def get_user(self, subject: str) -> DirectoryUser | None:
        # httpx normalizes dot segments, so "." and ".." would address other endpoints.
        # A valid IdP token never carries such a subject.
        if subject in (".", ".."):
            raise DirectoryError("subject is not a valid user id")
        quoted = quote(subject, safe="")
        response = self._get(f"/users/{quoted}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DirectoryError(f"user lookup failed: {response.status_code}")
        body = _json(response, "user")
        if not isinstance(body, dict):
            raise DirectoryError("malformed user response")
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            # A reply without a boolean must never read as "disabled" (that would revoke the user).
            raise DirectoryError("malformed user response")
        roles_response = self._get(f"/users/{quoted}/role-mappings/realm/composite")
        if roles_response.status_code != 200:
            raise DirectoryError(f"role lookup failed: {roles_response.status_code}")
        items = _json(roles_response, "roles")
        if not isinstance(items, list):
            raise DirectoryError("malformed roles response")
        names = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise DirectoryError("malformed roles response")
            names.append(item["name"])
        return DirectoryUser(enabled=enabled, roles=tuple(sorted(names)))


def build_directory(settings) -> Directory | None:
    if not settings.idp_sync_client_secret:
        return None
    return KeycloakDirectory(
        settings.oidc_issuer, settings.idp_sync_client_id, settings.idp_sync_client_secret
    )

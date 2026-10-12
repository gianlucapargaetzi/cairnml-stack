"""Asks the IdP whether a user still exists, is enabled and which roles they hold."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol
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


class KeycloakDirectory:
    def __init__(self, issuer: str, client_id: str, client_secret: str,
                 http: httpx.Client | None = None, clock=time.time) -> None:
        self._issuer = issuer.rstrip("/")
        self._admin = self._issuer.replace("/realms/", "/admin/realms/", 1)
        self._client_id, self._secret = client_id, client_secret
        self._http = http or httpx.Client(timeout=10.0)
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0

    def _refresh(self) -> str:
        try:
            response = self._http.post(
                f"{self._issuer}/protocol/openid-connect/token",
                data={"grant_type": "client_credentials", "client_id": self._client_id,
                      "client_secret": self._secret},
            )
        except httpx.HTTPError as exc:
            raise DirectoryError("IdP unreachable") from exc
        if response.status_code != 200:
            raise DirectoryError(f"IdP token request failed: {response.status_code}")
        body = response.json()
        self._token = body["access_token"]
        self._expires_at = self._clock() + body.get("expires_in", 60)
        return self._token

    def _get(self, path: str) -> httpx.Response:
        for attempt in (1, 2):
            token = (self._token if self._token and self._clock() < self._expires_at - 30
                     else self._refresh())
            try:
                response = self._http.get(
                    self._admin + path, headers={"Authorization": f"Bearer {token}"})
            except httpx.HTTPError as exc:
                raise DirectoryError("IdP unreachable") from exc
            if response.status_code == 401 and attempt == 1:
                self._token = None
                continue
            return response
        raise DirectoryError("unreachable")

    def get_user(self, subject: str) -> DirectoryUser | None:
        quoted = quote(subject, safe="")
        response = self._get(f"/users/{quoted}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DirectoryError(f"user lookup failed: {response.status_code}")
        enabled = bool(response.json().get("enabled"))
        roles_response = self._get(f"/users/{quoted}/role-mappings/realm/composite")
        if roles_response.status_code != 200:
            raise DirectoryError(f"role lookup failed: {roles_response.status_code}")
        roles = tuple(sorted(item["name"] for item in roles_response.json()))
        return DirectoryUser(enabled=enabled, roles=roles)


def build_directory(settings) -> Directory | None:
    if not settings.idp_sync_client_secret:
        return None
    return KeycloakDirectory(
        settings.oidc_issuer, settings.idp_sync_client_id, settings.idp_sync_client_secret
    )

"""Read-only GitHub App client: installation tokens and commit lookups."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
import jwt

_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_REFRESH_MARGIN = 300


def valid_repo(repo: str) -> bool:
    return bool(_REPO_RE.match(repo)) and ".." not in repo


class GitHubError(Exception):
    pass


class RepoNotAccessible(GitHubError):
    pass


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: datetime


class GitHubApp:
    def __init__(
        self,
        app_id: str,
        private_key_pem: str,
        api_url: str,
        http: httpx.Client | None = None,
        clock=time.time,
    ) -> None:
        self._app_id = app_id
        self._key = private_key_pem
        self._api = api_url.rstrip("/")
        self._http = http or httpx.Client(timeout=20.0)
        self._clock = clock
        self._installations: dict[str, int] = {}
        self._tokens: dict[str, InstallationToken] = {}

    def _app_jwt(self) -> str:
        now = int(self._clock())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self._app_id}, self._key, algorithm="RS256"
        )

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _installation_id(self, repo: str) -> int:
        if repo not in self._installations:
            response = self._http.get(
                f"{self._api}/repos/{repo}/installation", headers=self._headers(self._app_jwt())
            )
            if response.status_code == 404:
                raise RepoNotAccessible(repo)
            if response.status_code != 200:
                raise GitHubError(f"installation lookup failed: {response.status_code}")
            self._installations[repo] = response.json()["id"]
        return self._installations[repo]

    def installation_token(self, repo: str) -> InstallationToken:
        cached = self._tokens.get(repo)
        if cached and cached.expires_at.timestamp() - self._clock() > _REFRESH_MARGIN:
            return cached
        response = self._http.post(
            f"{self._api}/app/installations/{self._installation_id(repo)}/access_tokens",
            headers=self._headers(self._app_jwt()),
            json={"repositories": [repo.split("/", 1)[1]], "permissions": {"contents": "read"}},
        )
        if response.status_code != 201:
            raise GitHubError(f"token request failed: {response.status_code}")
        body = response.json()
        token = InstallationToken(
            body["token"], datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
        )
        self._tokens[repo] = token
        return token

    def _commit(self, repo: str, ref: str) -> dict | None:
        token = self.installation_token(repo).token
        response = self._http.get(
            f"{self._api}/repos/{repo}/commits/{ref}", headers=self._headers(token)
        )
        if response.status_code in (404, 422):
            return None
        if response.status_code != 200:
            raise GitHubError(f"commit lookup failed: {response.status_code}")
        return response.json()

    def commit_exists(self, repo: str, sha: str) -> bool:
        return self._commit(repo, sha) is not None

    def head_commit(self, repo: str, ref: str) -> str | None:
        found = self._commit(repo, ref)
        return found["sha"] if found else None


def build_github(settings) -> GitHubApp | None:
    if not (settings.github_app_id and settings.github_app_private_key_path):
        return None
    return GitHubApp(
        settings.github_app_id,
        settings.github_app_private_key_path.read_text(),
        settings.github_api_url,
    )

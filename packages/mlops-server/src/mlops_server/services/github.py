"""Read-only GitHub App client: installation tokens and commit lookups."""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

import httpx
import jwt

_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_REFRESH_MARGIN = 300


def valid_repo(repo: str) -> bool:
    return bool(_REPO_RE.fullmatch(repo)) and ".." not in repo


def _segment(value: str) -> str:
    """Percent-encode one path segment, including dot-only ones that httpx would normalize."""
    encoded = quote(value, safe="")
    return encoded.replace(".", "%2E") if encoded in (".", "..") else encoded


class GitHubError(Exception):
    pass


class RepoNotAccessible(GitHubError):
    pass


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class BranchInfo:
    name: str
    sha: str


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    parents: tuple[str, ...]
    message: str
    author: str
    date: str


def _commit_info(item: dict) -> CommitInfo:
    detail = item.get("commit") or {}
    author = detail.get("author") or {}
    return CommitInfo(
        sha=item["sha"],
        parents=tuple(parent["sha"] for parent in item.get("parents", [])),
        message=(detail.get("message") or "").split("\n", 1)[0],
        author=author.get("name", ""),
        date=author.get("date", ""),
    )


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

    def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            return self._http.request(method, url, **kwargs)
        except httpx.HTTPError:
            raise GitHubError("GitHub transport error") from None

    @staticmethod
    def _json(response: httpx.Response) -> dict:
        try:
            body = response.json()
        except ValueError:
            raise GitHubError("GitHub returned a non-JSON body") from None
        if not isinstance(body, dict):
            raise GitHubError("GitHub returned an unexpected body")
        return body

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
            response = self._send(
                "GET",
                f"{self._api}/repos/{repo}/installation",
                headers=self._headers(self._app_jwt()),
            )
            if response.status_code == 404:
                raise RepoNotAccessible(repo)
            if response.status_code != 200:
                raise GitHubError(f"installation lookup failed: {response.status_code}")
            installation_id = self._json(response).get("id")
            if not isinstance(installation_id, int):
                raise GitHubError("installation lookup returned no id")
            self._installations[repo] = installation_id
        return self._installations[repo]

    def installation_token(self, repo: str) -> InstallationToken:
        cached = self._tokens.get(repo)
        if cached and cached.expires_at.timestamp() - self._clock() > _REFRESH_MARGIN:
            return cached
        response = self._send(
            "POST",
            f"{self._api}/app/installations/{self._installation_id(repo)}/access_tokens",
            headers=self._headers(self._app_jwt()),
            json={"repositories": [repo.split("/", 1)[1]], "permissions": {"contents": "read"}},
        )
        if response.status_code != 201:
            raise GitHubError(f"token request failed: {response.status_code}")
        body = self._json(response)
        try:
            token = InstallationToken(
                body["token"], datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
            )
        except (KeyError, TypeError, ValueError):
            raise GitHubError("token response is malformed") from None
        self._tokens[repo] = token
        return token

    def _get(self, repo: str, path: str, params: dict | None = None) -> httpx.Response | None:
        """GET under /repos/{repo}: None for a missing path or ref, else GitHubError on failure."""
        token = self.installation_token(repo).token
        response = self._send(
            "GET", f"{self._api}/repos/{repo}{path}", headers=self._headers(token), params=params
        )
        if response.status_code in (404, 422):
            return None
        if response.status_code != 200:
            raise GitHubError(f"GitHub request failed: {response.status_code}")
        return response

    def _list(self, response: httpx.Response | None) -> list:
        if response is None:
            return []
        try:
            body = response.json()
        except ValueError:
            raise GitHubError("GitHub returned a non-JSON body") from None
        if not isinstance(body, list):
            raise GitHubError("GitHub returned an unexpected body")
        return body

    def _commit(self, repo: str, ref: str) -> dict | None:
        response = self._get(repo, f"/commits/{_segment(ref)}")
        return None if response is None else self._json(response)

    def commit_exists(self, repo: str, sha: str) -> bool:
        return self._commit(repo, sha) is not None

    def head_commit(self, repo: str, ref: str) -> str | None:
        found = self._commit(repo, ref)
        if found is None:
            return None
        sha = found.get("sha")
        if not isinstance(sha, str):
            raise GitHubError("commit response has no sha")
        return sha

    def get_default_branch(self, repo: str) -> str:
        response = self._get(repo, "")
        if response is None:
            raise RepoNotAccessible(repo)
        branch = self._json(response).get("default_branch")
        if not isinstance(branch, str):
            raise GitHubError("repository response has no default branch")
        return branch

    def list_branches(self, repo: str, limit: int = 20) -> list[BranchInfo]:
        items = self._list(self._get(repo, "/branches", {"per_page": limit}))
        return [BranchInfo(item["name"], item["commit"]["sha"]) for item in items]

    def list_commits(self, repo: str, ref: str, limit: int = 50) -> list[CommitInfo]:
        items = self._list(self._get(repo, "/commits", {"sha": ref, "per_page": limit}))
        return [_commit_info(item) for item in items]

    def list_path_commits(
        self, repo: str, path: str, ref: str, limit: int = 10
    ) -> list[CommitInfo]:
        params = {"sha": ref, "path": path, "per_page": limit}
        return [_commit_info(item) for item in self._list(self._get(repo, "/commits", params))]

    def list_tree(self, repo: str, ref: str) -> tuple[list[str], bool]:
        response = self._get(repo, f"/git/trees/{_segment(ref)}", {"recursive": 1})
        if response is None:
            return [], False
        body = self._json(response)
        blobs = [item["path"] for item in body.get("tree", []) if item.get("type") == "blob"]
        return blobs, bool(body.get("truncated"))

    def read_file(self, repo: str, path: str, ref: str, max_bytes: int = 200_000) -> str | None:
        encoded = "/".join(_segment(part) for part in path.split("/"))
        response = self._get(repo, f"/contents/{encoded}", {"ref": ref})
        if response is None:
            return None
        body = self._json(response)
        if body.get("encoding") != "base64" or body.get("size", 0) > max_bytes:
            return None
        try:
            return base64.b64decode(body["content"]).decode("utf-8", errors="replace")
        except (KeyError, TypeError, ValueError):
            raise GitHubError("file response is malformed") from None


def build_github(settings) -> GitHubApp | None:
    if not (settings.github_app_id and settings.github_app_private_key_path):
        return None
    return GitHubApp(
        settings.github_app_id,
        settings.github_app_private_key_path.read_text(),
        settings.github_api_url,
    )

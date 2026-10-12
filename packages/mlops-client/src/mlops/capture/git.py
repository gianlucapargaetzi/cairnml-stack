"""Reading git state and building a reproducible patch of local changes."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

_SCP_LIKE = re.compile(r"^[\w.-]+@[\w.-]+:(?P<path>.+)$")
_COMMIT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class GitState:
    root: Path
    remote_url: str | None
    repo: str | None
    commit: str
    branch: str | None
    dirty: bool


def _redact(url: str) -> str:
    """Remove user:password@ userinfo from a URL with a scheme.

    urlsplit cannot be used for the split itself: it ends the netloc at the first
    "/", so a password containing "/" would survive. The scheme is validated with
    urlsplit, and the userinfo ends at the last "@" of the remainder, so an
    unencoded "/" or "@" in a password is removed as well. A "@" in a repository
    path is over-redacted, which is the safe direction.
    """
    if not url or "://" not in url:
        return url
    scheme, _, rest = url.partition("://")
    if not urlsplit(f"{scheme}://x").scheme:
        return url
    _, at, tail = rest.rpartition("@")
    return f"{scheme}://{tail}" if at else url


def parse_repo_slug(url: str) -> str | None:
    if not url:
        return None
    url = _redact(url)
    match = _SCP_LIKE.match(url)
    path = match.group("path") if match else re.sub(r"^[A-Za-z+]+://[^/]*", "", url)
    path = path.removesuffix(".git").strip("/")
    parts = [p for p in path.split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else None


def _run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, env={**os.environ, **(env or {})}
    )


def _out(args: list[str], cwd: Path, env: dict | None = None) -> str | None:
    result = _run(args, cwd, env)
    return result.stdout.decode().strip() if result.returncode == 0 else None


def capture_git(start: Path | None = None) -> GitState | None:
    start = Path(start or Path.cwd())
    if not start.is_dir():
        return None
    top = _out(["rev-parse", "--show-toplevel"], start)
    if not top:
        return None
    root = Path(top)
    commit = _out(["rev-parse", "HEAD"], root)
    if not commit:
        return None
    remote = _out(["remote", "get-url", "origin"], root)
    remote = _redact(remote) if remote else None
    branch = _out(["branch", "--show-current"], root) or None
    dirty = bool(_out(["--no-optional-locks", "status", "--porcelain"], root))
    return GitState(root.resolve(), remote, parse_repo_slug(remote or ""), commit, branch, dirty)


def build_patch(root: Path) -> bytes:
    # A temporary index seeded from HEAD carries no stat data, so every path is
    # compared by content. Copying the real index can keep stale stat data and miss
    # edits made within the same timestamp tick as the last index write.
    with tempfile.TemporaryDirectory() as tmp:
        env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        seeded = _run(["read-tree", "HEAD"], root, env)
        if seeded.returncode != 0:
            raise RuntimeError(f"git read-tree failed: {seeded.stderr.decode().strip()}")
        added = _run(["add", "-A"], root, env)
        if added.returncode != 0:
            raise RuntimeError(f"git add failed: {added.stderr.decode().strip()}")
        diff = _run(
            ["diff", "--cached", "--binary", "--full-index", "--no-color", "--no-ext-diff", "HEAD"],
            root,
            env,
        )
        if diff.returncode != 0:
            raise RuntimeError(f"git diff failed: {diff.stderr.decode().strip()}")
        return diff.stdout


def is_pushed(root: Path, commit: str) -> bool:
    if not _COMMIT.fullmatch(commit):
        return False
    return bool(_out(["branch", "-r", "--contains", commit], root))

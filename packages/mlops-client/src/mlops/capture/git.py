"""Reading git state and building a reproducible patch of local changes."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SCP_LIKE = re.compile(r"^[\w.-]+@[\w.-]+:(?P<path>.+)$")
_USERINFO = re.compile(r"^(?P<scheme>[a-z+]+://)[^/@]*@")


@dataclass(frozen=True)
class GitState:
    root: Path
    remote_url: str | None
    repo: str | None
    commit: str
    branch: str | None
    dirty: bool


def parse_repo_slug(url: str) -> str | None:
    if not url:
        return None
    match = _SCP_LIKE.match(url)
    path = match.group("path") if match else re.sub(r"^[a-z+]+://[^/]*", "", url)
    path = path.removesuffix(".git").strip("/")
    parts = [p for p in path.split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else None


def _redact(url: str) -> str:
    """Drop any user:password@ userinfo so credentials never enter the state."""
    return _USERINFO.sub(lambda m: m.group("scheme"), url)


def _run(args: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, env={**os.environ, **(env or {})}
    )


def _out(args: list[str], cwd: Path, env: dict | None = None) -> str | None:
    result = _run(args, cwd, env)
    return result.stdout.decode().strip() if result.returncode == 0 else None


def capture_git(start: Path | None = None) -> GitState | None:
    start = Path(start or Path.cwd())
    if not start.exists():
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
    dirty = bool(_out(["status", "--porcelain"], root))
    return GitState(root.resolve(), remote, parse_repo_slug(remote or ""), commit, branch, dirty)


def build_patch(root: Path) -> bytes:
    git_dir = _out(["rev-parse", "--absolute-git-dir"], root)
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "index"
        real_index = Path(git_dir) / "index"
        if real_index.exists():
            shutil.copy(real_index, index)
        env = {"GIT_INDEX_FILE": str(index)}
        added = _run(["add", "-A"], root, env)
        if added.returncode != 0:
            raise RuntimeError(f"git add failed: {added.stderr.decode().strip()}")
        diff = _run(["diff", "--cached", "--binary", "--full-index", "HEAD"], root, env)
        if diff.returncode != 0:
            raise RuntimeError(f"git diff failed: {diff.stderr.decode().strip()}")
        return diff.stdout


def is_pushed(root: Path, commit: str) -> bool:
    return bool(_out(["branch", "-r", "--contains", commit], root))

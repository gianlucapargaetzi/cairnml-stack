"""Preparing a job's working directory: git checkout, patches, downloaded inputs."""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

import httpx


class GitError(Exception):
    pass


def _auth_header(token: str) -> str:
    raw = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return f"AUTHORIZATION: basic {raw}"


def _scrub(text: str, token: str | None) -> str:
    """Remove the token in every form it can take in git output (raw, base64, header)."""
    if not token:
        return text
    secrets = [
        _auth_header(token),
        base64.b64encode(f"x-access-token:{token}".encode()).decode(),
        base64.b64encode(token.encode()).decode(),
        token,
    ]
    for secret in secrets:
        text = text.replace(secret, "***")
    return text


def _git(args: list[str], cwd: Path, token: str | None = None, stdin: bytes | None = None) -> None:
    command = ["git"]
    if token:
        command += ["-c", f"http.extraheader={_auth_header(token)}"]
    command += args
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_GLOBAL": os.devnull}
    result = subprocess.run(command, cwd=cwd, input=stdin, capture_output=True, env=env)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise GitError(_scrub(f"git {args[0]} failed: {stderr}", token))


def clone_at(
    repo: str, commit: str, dest: Path, token: str, web_url: str = "https://github.com"
) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], dest)
    _git(["remote", "add", "origin", f"{web_url.rstrip('/')}/{repo}.git"], dest)
    _git(["fetch", "-q", "--depth", "1", "origin", commit], dest, token)
    _git(["checkout", "-q", "--detach", "FETCH_HEAD"], dest)


def apply_patch(dest: Path, patch: bytes) -> None:
    _git(["apply", "--binary", "--whitespace=nowarn", "-"], dest, stdin=patch)


def safe_join(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes the workspace: {relative}")
    return target


def download(
    url: str, dest: Path, http: httpx.Client | None = None, max_bytes: int = 2 * 1024**3
) -> None:
    client = http or httpx.Client(timeout=120.0)
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes():
                    written += len(chunk)
                    if written > max_bytes:
                        raise ValueError("download too large")
                    handle.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

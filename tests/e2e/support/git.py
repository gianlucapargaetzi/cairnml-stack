"""Local git repositories for the git tests: a bare repository stands in for the remote, and a clone of it is the
checkout a person works in. No network and no GitHub are involved."""

import os
import subprocess
from pathlib import Path

IDENTITY = {
    "GIT_AUTHOR_NAME": "E2E Test", "GIT_AUTHOR_EMAIL": "e2e@example.test",
    "GIT_COMMITTER_NAME": "E2E Test", "GIT_COMMITTER_EMAIL": "e2e@example.test",
}


def git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                         env={**os.environ, **IDENTITY}, timeout=120)
    assert out.returncode == 0, f"git {' '.join(args)} failed: {out.stderr}"
    return out.stdout.strip()


def make_remote_and_checkout(root: Path, branch: str = "main"):
    """A bare remote with one commit on the branch, and a clone of it. Returns (remote path, checkout path)."""
    remote = root / "remote.git"
    checkout = root / "checkout"
    remote.mkdir(parents=True)
    git(remote, "init", "--bare", "-b", branch)
    seed = root / "seed"
    seed.mkdir()
    git(seed, "init", "-b", branch)
    (seed / "README.md").write_text("e2e repository\n")
    git(seed, "add", ".")
    git(seed, "commit", "-m", "initial commit")
    git(seed, "remote", "add", "origin", remote.as_posix())
    git(seed, "push", "origin", branch)
    git(root, "clone", remote.as_posix(), checkout.as_posix())
    return remote, checkout


def commit_all(checkout: Path, message: str) -> str:
    git(checkout, "add", "-A")
    git(checkout, "commit", "-m", message)
    return git(checkout, "rev-parse", "HEAD")

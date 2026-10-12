"""Helpers shared by tests (kept in the package so tests need no relative imports)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def make_repo(tmp_path: Path, files: dict[str, str] | None = None, name: str = "owner/name"):
    files = files or {"train.py": "print('train')\n"}
    bare = tmp_path / "origin" / f"{name}.git"
    bare.mkdir(parents=True)
    git("init", "-q", "--bare", "-b", "main", cwd=bare)
    work = tmp_path / "work" / name.split("/")[-1]
    work.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=work)
    git("config", "user.email", "t@example.test", cwd=work)
    git("config", "user.name", "t", cwd=work)
    for relative, content in files.items():
        path = work / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "init", cwd=work)
    git("remote", "add", "origin", str(bare), cwd=work)
    git("push", "-q", "origin", "main", cwd=work)
    return work, bare

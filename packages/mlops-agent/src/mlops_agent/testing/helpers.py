import subprocess
from pathlib import Path


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def make_origin(tmp_path: Path, repo="owner/name", files=None):
    files = files or {"train.py": "print(1)\n"}
    bare = tmp_path / "origin" / f"{repo}.git"
    bare.mkdir(parents=True)
    git("init", "-q", "--bare", cwd=bare)
    git("config", "uploadpack.allowAnySHA1InWant", "true", cwd=bare)
    work = tmp_path / "seed"
    work.mkdir()
    git("init", "-q", cwd=work)
    git("config", "user.email", "t@example.test", cwd=work)
    git("config", "user.name", "t", cwd=work)
    for name, content in files.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "seed", cwd=work)
    git("remote", "add", "origin", str(bare), cwd=work)
    git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=work)
    return f"file://{tmp_path / 'origin'}", git("rev-parse", "HEAD", cwd=work)

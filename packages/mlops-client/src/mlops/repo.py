"""One-time setup of a project repository."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import yaml

from mlops.capture.git import capture_git


def _dvc(run, path: Path, *args: str) -> None:
    result = run(["dvc", *args], cwd=path, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"dvc {' '.join(args[:2])} failed: {(result.stderr or result.stdout).strip()}"
        )


def find_project(start: Path) -> str:
    current = Path(start).resolve()
    for folder in [current, *current.parents]:
        candidate = folder / ".mlops" / "project.yaml"
        if candidate.exists():
            return yaml.safe_load(candidate.read_text())["project"]
    raise ValueError("not an mlops repo: run `mlops repo init --project <slug>`")


def init_repo(path: Path, project: str, api, run=subprocess.run, which=None) -> dict:
    which = which or shutil.which
    git = capture_git(path)
    if git is None:
        raise ValueError("this is not a git repository with at least one commit")
    if which("dvc") is None:
        raise RuntimeError("dvc is not installed (pip install 'mlops-client[dvc]')")
    sts = api.sts(project, write=False)
    remote_url = f"s3://{sts.bucket}/{sts.prefix.rstrip('/')}"

    (path / ".mlops").mkdir(exist_ok=True)
    (path / ".mlops" / "project.yaml").write_text(
        yaml.safe_dump({"project": project, "server": api.server_url})
    )
    if not (path / ".dvc").exists():
        _dvc(run, path, "init", "-q")
    _dvc(run, path, "remote", "add", "-f", "-d", "storage", remote_url)
    # Only the URL and the endpoint go into .dvc/config. Credentials are never stored.
    _dvc(run, path, "remote", "modify", "storage", "endpointurl", sts.endpoint_url)

    app_state = "unknown"
    if git.repo:
        try:
            api.repo_status(git.repo, "HEAD")
            app_state = "installed"
        except httpx.HTTPStatusError as exc:
            app_state = "not installed" if exc.response.status_code == 404 else "unknown"
        try:
            api.link_repo(project, git.repo, "code")
        except httpx.HTTPStatusError:
            pass  # not fatal: the GitHub App may not be installed yet; the summary shows its state
    return {
        "project": project,
        "remote_url": remote_url,
        "endpoint": sts.endpoint_url,
        "github_app": app_state,
    }

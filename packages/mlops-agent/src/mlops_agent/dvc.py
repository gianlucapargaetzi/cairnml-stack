"""Pulling DVC-tracked datasets with short-lived S3 credentials."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from mlops_common.schemas import DatasetRef, StsResponse, _safe_relative

_ENV_PASSTHROUGH = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")


class DvcError(Exception):
    pass


class UnsupportedDataset(Exception):
    pass


def _check_path(path: str) -> None:
    # A leading "-" would be read by dvc as an option; the rest is the shared relative-path rule.
    if path.startswith("-"):
        raise UnsupportedDataset(f"dataset path {path!r} must not start with '-'")
    try:
        _safe_relative(path)
    except ValueError as err:
        raise UnsupportedDataset(f"dataset path {path!r} {err}") from None


def dataset_targets(
    datasets: list[DatasetRef], code_repo: str | None, code_commit: str | None
) -> list[str]:
    targets = []
    for ref in datasets:
        if code_repo is None:
            raise UnsupportedDataset("datasets need a code repository that holds the DVC metadata")
        if ref.repo not in (None, code_repo):
            raise UnsupportedDataset(
                f"dataset {ref.path!r} lives in {ref.repo}; "
                "only datasets in the code repository are supported"
            )
        if ref.commit not in (None, code_commit):
            raise UnsupportedDataset(
                f"dataset {ref.path!r} is pinned to a different commit than the code"
            )
        _check_path(ref.path)
        targets.append(ref.path)
    return targets


def _scrub(text: str, sts: StsResponse) -> str:
    for secret in (sts.secret_key, sts.session_token, sts.access_key):
        if secret:  # an empty secret would match everywhere
            text = text.replace(secret, "***")
    return text


def dvc_pull(
    workdir: Path,
    targets: list[str],
    sts: StsResponse,
    run=subprocess.run,
    which=shutil.which,
) -> None:
    if not targets:
        return
    if which("dvc") is None:
        raise DvcError("dvc is not installed on this agent")
    # Credentials travel in the environment only, never on argv. The rest of the
    # environment is an allowlist so unrelated agent secrets stay out of dvc.
    env = {key: os.environ[key] for key in _ENV_PASSTHROUGH if key in os.environ}
    env = {
        **env,
        "AWS_ACCESS_KEY_ID": sts.access_key,
        "AWS_SECRET_ACCESS_KEY": sts.secret_key,
        "AWS_SESSION_TOKEN": sts.session_token,
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    # "--" ends option parsing so a target can never be read as a dvc flag.
    result = run(
        ["dvc", "pull", "--force", "--", *targets],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DvcError(_scrub(f"dvc pull failed: {(result.stderr or result.stdout).strip()}", sts))

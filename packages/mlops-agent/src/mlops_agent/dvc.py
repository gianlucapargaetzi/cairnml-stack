"""Pulling DVC-tracked datasets with short-lived S3 credentials."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from mlops_common.schemas import DatasetRef, StsResponse


class DvcError(Exception):
    pass


class UnsupportedDataset(Exception):
    pass


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
    # Credentials travel in the environment only, never on argv.
    env = {
        **os.environ,
        "AWS_ACCESS_KEY_ID": sts.access_key,
        "AWS_SECRET_ACCESS_KEY": sts.secret_key,
        "AWS_SESSION_TOKEN": sts.session_token,
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    result = run(
        ["dvc", "pull", "--force", *targets], cwd=workdir, env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise DvcError(_scrub(f"dvc pull failed: {(result.stderr or result.stdout).strip()}", sts))

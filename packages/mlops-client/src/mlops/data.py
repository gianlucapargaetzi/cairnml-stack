"""DVC pull and push, with short-lived storage credentials passed only in the environment."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def dvc_command(
    api,
    project: str,
    action: str,
    targets: list[str],
    cwd: Path,
    run=subprocess.run,
    which=None,
) -> None:
    which = which or shutil.which
    if action not in ("pull", "push"):
        raise ValueError("action must be pull or push")
    if which("dvc") is None:
        raise RuntimeError("dvc is not installed (pip install 'mlops-client[dvc]')")
    sts = api.sts(project, write=(action == "push"))
    env = {
        **os.environ,
        "AWS_ACCESS_KEY_ID": sts.access_key,
        "AWS_SECRET_ACCESS_KEY": sts.secret_key,
        "AWS_SESSION_TOKEN": sts.session_token,
        "AWS_EC2_METADATA_DISABLED": "true",
    }
    result = run(["dvc", action, *targets], cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        for secret in (sts.secret_key, sts.session_token, sts.access_key):
            if secret:
                message = message.replace(secret, "***")
        raise RuntimeError(f"dvc {action} failed: {message}")

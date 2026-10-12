"""Runs a command in a cached virtualenv inside a python container."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from mlops_agent.executors.base import BaseExecutor, RunContext
from mlops_agent.executors.docker_run import container_dir, run_container

_SETUP_LOCKS: dict[str, threading.Lock] = {}
_SETUP_LOCKS_GUARD = threading.Lock()
_JOB_PATH = "/venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def wheels_digest(wheels_dir: Path | None) -> str:
    if wheels_dir is None or not Path(wheels_dir).is_dir():
        return ""
    entries = sorted((p.name, p.stat().st_size) for p in Path(wheels_dir).iterdir() if p.is_file())
    return hashlib.sha256(repr(entries).encode()).hexdigest()[:12]


def venv_volume_name(python: str, requirements_text: str, client_spec: str, extra: str = "") -> str:
    digest = hashlib.sha256(
        f"{python}\n{requirements_text}\n{client_spec}\n{extra}".encode()
    ).hexdigest()[:16]
    return f"mlops-venv-{python}-{digest}"


def _setup_lock(volume: str) -> threading.Lock:
    with _SETUP_LOCKS_GUARD:
        return _SETUP_LOCKS.setdefault(volume, threading.Lock())


def _read_in_workdir(ctx: RunContext, relative: str) -> str:
    base = ctx.workdir.resolve()
    target = (base / relative).resolve()  # follows symlinks, so escapes are visible here
    if not target.is_relative_to(base):
        raise ValueError(f"requirements file {relative!r} is outside the job workdir")
    return target.read_text()


def _requirements_text(ctx: RunContext) -> str:
    runtime = ctx.spec.runtime
    if runtime.requirements:
        return "\n".join(runtime.requirements)
    if runtime.requirements_file:
        return _read_in_workdir(ctx, runtime.requirements_file)
    if (ctx.workdir / "requirements.txt").exists():
        return _read_in_workdir(ctx, "requirements.txt")
    return ""


class PythonExecutor(BaseExecutor):
    def __init__(self, client) -> None:
        super().__init__()
        self._client = client

    def _setup_script(self, ctx: RunContext) -> str:
        find_links = "--find-links /wheels " if ctx.settings.wheels_dir else ""
        return (
            "set -e\n"
            "if [ ! -f /venv/.ready ]; then\n"
            "  python -m venv /venv\n"
            "  /venv/bin/pip install --no-cache-dir --upgrade pip\n"
            "  if [ -s /work/.mlops/requirements.txt ]; then\n"
            "    /venv/bin/pip install --no-cache-dir -r /work/.mlops/requirements.txt\n"
            "  fi\n"
            f"  /venv/bin/pip install --no-cache-dir {find_links}{ctx.settings.client_pip_spec}\n"
            "  touch /venv/.ready\n"
            "fi\n"
        )

    def run(self, ctx: RunContext) -> int:
        runtime = ctx.spec.runtime
        try:
            text = _requirements_text(ctx)
        except (OSError, ValueError) as exc:  # missing or escaping file: a failed run, not a crash
            ctx.stderr(f"cannot read requirements: {exc}")
            return 1
        requirements_path = ctx.root / ".mlops" / "requirements.txt"
        requirements_path.parent.mkdir(parents=True, exist_ok=True)
        requirements_path.write_text(text)

        image = f"python:{runtime.python}-slim"
        volume = venv_volume_name(
            runtime.python,
            text,
            ctx.settings.client_pip_spec,
            wheels_digest(ctx.settings.wheels_dir),
        )
        mounts = {
            str(ctx.root): {"bind": "/work", "mode": "rw"},
            volume: {"bind": "/venv", "mode": "rw"},
        }

        setup_mounts = dict(mounts)
        if ctx.settings.wheels_dir:
            setup_mounts[str(ctx.settings.wheels_dir)] = {"bind": "/wheels", "mode": "ro"}
        with _setup_lock(volume):  # two jobs must not build the same venv concurrently
            code = run_container(
                self._client,
                image,
                ["sh", "-c", self._setup_script(ctx)],
                ctx=ctx,
                volumes=setup_mounts,
                environment={},
                executor=self,
                limits=False,
            )
        if code != 0 or self.cancelled:
            return code

        environment = {
            **ctx.env,
            "PATH": _JOB_PATH,
            "VIRTUAL_ENV": "/venv",
            "PYTHONUNBUFFERED": "1",
        }
        # the cached venv is shared by every job with the same requirements: jobs get it read-only
        job_mounts = {**mounts, volume: {"bind": "/venv", "mode": "ro"}}
        return run_container(
            self._client,
            image,
            list(runtime.command),
            ctx=ctx,
            volumes=job_mounts,
            environment=environment,
            executor=self,
            working_dir=container_dir(ctx),
            network=ctx.settings.job_network,
        )

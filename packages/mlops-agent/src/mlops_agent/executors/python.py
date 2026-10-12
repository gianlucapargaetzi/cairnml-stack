"""Runs a command in a cached virtualenv inside a python container."""

from __future__ import annotations

import hashlib
import threading
from collections import defaultdict

from mlops_agent.executors.base import BaseExecutor, RunContext
from mlops_agent.executors.docker_run import run_container

_SETUP_LOCKS: dict[str, threading.Lock] = defaultdict(threading.Lock)
_JOB_PATH = "/venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def venv_volume_name(python: str, requirements_text: str, client_spec: str) -> str:
    digest = hashlib.sha256(f"{python}\n{requirements_text}\n{client_spec}".encode()).hexdigest()[
        :16
    ]
    return f"mlops-venv-{python}-{digest}"


def _requirements_text(ctx: RunContext) -> str:
    runtime = ctx.spec.runtime
    if runtime.requirements:
        return "\n".join(runtime.requirements)
    if runtime.requirements_file:
        return (ctx.workdir / runtime.requirements_file).read_text()
    default = ctx.workdir / "requirements.txt"
    return default.read_text() if default.exists() else ""


def _container_dir(ctx: RunContext) -> str:
    relative = ctx.workdir.resolve().relative_to(ctx.root.resolve())
    return "/work" if str(relative) == "." else f"/work/{relative}"


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
        text = _requirements_text(ctx)
        requirements_path = ctx.root / ".mlops" / "requirements.txt"
        requirements_path.parent.mkdir(parents=True, exist_ok=True)
        requirements_path.write_text(text)

        image = f"python:{runtime.python}-slim"
        volume = venv_volume_name(runtime.python, text, ctx.settings.client_pip_spec)
        mounts = {
            str(ctx.root): {"bind": "/work", "mode": "rw"},
            volume: {"bind": "/venv", "mode": "rw"},
        }

        setup_mounts = dict(mounts)
        if ctx.settings.wheels_dir:
            setup_mounts[str(ctx.settings.wheels_dir)] = {"bind": "/wheels", "mode": "ro"}
        with _SETUP_LOCKS[volume]:  # two jobs must not build the same venv concurrently
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
        return run_container(
            self._client,
            image,
            list(runtime.command),
            ctx=ctx,
            volumes=mounts,
            environment=environment,
            executor=self,
            working_dir=_container_dir(ctx),
            network=ctx.settings.job_network,
        )

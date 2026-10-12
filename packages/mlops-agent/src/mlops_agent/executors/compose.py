"""Runs a docker compose project and reports the exit code of one service."""

from __future__ import annotations

import os
import subprocess
import threading

from mlops_agent.executors.base import BaseExecutor, RunContext
from mlops_agent.workspace import safe_join

# Host variables docker compose needs. Everything else stays out of the environment,
# so unrelated agent secrets (enrollment or registry tokens) never reach compose.
_ENV_PASSTHROUGH = (
    "PATH",
    "HOME",
    "DOCKER_HOST",
    "DOCKER_CONFIG",
    "DOCKER_CONTEXT",
    "XDG_RUNTIME_DIR",
    "LANG",
    "LC_ALL",
    "TMPDIR",
)


def _pump(stream, sink) -> None:
    for line in stream:
        sink(line.rstrip("\r\n"))


def _compose_env(ctx: RunContext) -> dict[str, str]:
    host = {key: os.environ[key] for key in _ENV_PASSTHROUGH if key in os.environ}
    return {**host, **ctx.env}


class ComposeExecutor(BaseExecutor):
    def __init__(self, popen=subprocess.Popen, run=subprocess.run) -> None:
        super().__init__()
        self._popen = popen
        self._run = run
        self._proc = None

    def _kill(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:  # already exited
                pass

    def _attach(self, proc) -> None:
        """Register the compose process; terminate it at once if cancel() already ran."""
        with self._lock:
            self._proc = proc
            cancelled = self._cancelled.is_set()
        if cancelled:
            self._kill()

    def run(self, ctx: RunContext) -> int:
        runtime = ctx.spec.runtime
        compose_file = safe_join(ctx.workdir, runtime.file)
        base = ["docker", "compose", "-p", f"mlops-{ctx.job_id}", "-f", str(compose_file)]
        up = ["up", "--build", "--abort-on-container-exit", "--exit-code-from", runtime.service]
        env = _compose_env(ctx)
        try:
            proc = self._popen(
                base + up,
                cwd=ctx.workdir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._attach(proc)
            threads = [
                threading.Thread(target=_pump, args=(proc.stdout, ctx.stdout), daemon=True),
                threading.Thread(target=_pump, args=(proc.stderr, ctx.stderr), daemon=True),
            ]
            for thread in threads:
                thread.start()
            code = proc.wait()
            for thread in threads:
                thread.join(timeout=10)
            return code
        finally:
            with self._lock:
                self._proc = None
            self._run(
                base + ["down", "-v", "--remove-orphans"],
                cwd=ctx.workdir,
                env=env,
                capture_output=True,
            )

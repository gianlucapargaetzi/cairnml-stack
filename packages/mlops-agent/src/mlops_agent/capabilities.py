"""Detect what this machine can offer to the scheduler."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterable

from mlops_common.schemas import Capabilities


def _mem_bytes() -> int:
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def _docker_ok() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


def _gpus(run: Callable) -> list[str]:
    try:
        result = run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _compose_ok(run: Callable) -> bool:
    try:
        result = run(["docker", "compose", "version"], capture_output=True, text=True, timeout=15)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def detect(
    labels: Iterable[str] = (),
    *,
    run: Callable = subprocess.run,
    docker_ok: Callable[[], bool] = _docker_ok,
    cpu_count: Callable[[], int | None] = os.cpu_count,
    mem_bytes: Callable[[], int] = _mem_bytes,
) -> Capabilities:
    gpus = _gpus(run)
    has_docker = docker_ok()
    runtimes = []
    if has_docker:
        runtimes = ["python", "image"] + (["compose"] if _compose_ok(run) else [])
    return Capabilities(
        cpu=cpu_count() or 1,
        memory_gb=round(mem_bytes() / 1024**3, 1),
        gpus=len(gpus),
        gpu_models=gpus,
        labels=list(labels),
        runtimes=runtimes,
        docker=has_docker,
    )

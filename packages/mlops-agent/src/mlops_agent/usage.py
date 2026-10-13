"""Samples what the machine is actually using right now."""

from __future__ import annotations

import subprocess

from mlops_common.schemas import AgentUsage, GpuUsage

_GB = 1024**3
_NVIDIA_QUERY = [
    "nvidia-smi",
    "--query-gpu=index,utilization.gpu,memory.used,memory.total",
    "--format=csv,noheader,nounits",
]


def _gpus(run) -> list[GpuUsage]:
    try:
        result = run(_NVIDIA_QUERY, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    gpus = []
    for line in result.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        try:
            index = int(parts[0])
            util, used, total = float(parts[1]), float(parts[2]), float(parts[3])
        except (ValueError, IndexError):
            continue
        gpus.append(
            GpuUsage(
                index=index,
                util_percent=util,
                mem_used_gb=round(used / 1024, 1),
                mem_total_gb=round(total / 1024, 1),
            )
        )
    return gpus


def sample_usage(run=subprocess.run, psutil_module=None) -> AgentUsage:
    if psutil_module is None:
        import psutil as psutil_module
    memory = psutil_module.virtual_memory()
    return AgentUsage(
        cpu_percent=float(psutil_module.cpu_percent(interval=None)),
        mem_used_gb=round(memory.used / _GB, 1),
        mem_total_gb=round(memory.total / _GB, 1),
        gpus=_gpus(run),
    )

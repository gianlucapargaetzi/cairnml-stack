"""Queueing jobs and following them. Status is read over REST, so the reading does not depend on the SDK's
API level (see scripts/enqueue.py for why enqueueing must be the first SDK call of its process)."""

import time
from pathlib import Path

from . import workspace

FINAL = ("completed", "failed", "stopped", "aborted", "closed")


def enqueue(home: Path, task_id: str, *, cpus=1, ram_gb=1.0, gpus=0, gpu_memory_gb=0.0, disk_gb=1.0,
            priority=50, force=True) -> dict:
    args = ["--task-id", task_id, "--cpus", str(cpus), "--ram-gb", str(ram_gb), "--gpus", str(gpus),
            "--gpu-memory-gb", str(gpu_memory_gb), "--disk-gb", str(disk_gb), "--priority", str(priority)]
    if force:
        args.append("--force")
    return workspace.run_json(home, "enqueue.py", args, timeout=300)


def task_record(api, task_id: str) -> dict:
    return api.authed("tasks.get_by_id", {"task": task_id})["task"]


def wait_for(api, task_id: str, states, timeout: float = 900, poll: float = 5.0) -> dict:
    """Polls the task until its status is one of states; returns the record. Raises after the timeout."""
    deadline = time.monotonic() + timeout
    record = {}
    while time.monotonic() < deadline:
        record = task_record(api, task_id)
        if record.get("status") in states:
            return record
        time.sleep(poll)
    raise TimeoutError(f"task {task_id} is '{record.get('status')}' after {timeout}s, wanted one of {states}")

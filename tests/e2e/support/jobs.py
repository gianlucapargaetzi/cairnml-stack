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


def wait_for(api, task_id: str, states, timeout: float = 60, poll: float = 1.0) -> dict:
    """Polls the task until its status is one of states; returns the record. Raises after the timeout."""
    deadline = time.monotonic() + timeout
    record = {}
    while time.monotonic() < deadline:
        record = task_record(api, task_id)
        if record.get("status") in states:
            return record
        time.sleep(poll)
    raise TimeoutError(f"task {task_id} is '{record.get('status')}' after {timeout}s, wanted one of {states}")


def wait_until(api, task_id: str, condition, timeout: float = 60, poll: float = 1.0):
    """Waits until condition(record) is true. Stops early, returning None, when the job reaches a final status:
    a job that has ended will not reach the condition later, so waiting on is time lost."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = task_record(api, task_id)
        if condition(record):
            return record
        if record.get("status") in FINAL:
            return None
        time.sleep(poll)
    return None


def wait_for_start(api, task_id: str, timeout: float = 60) -> dict:
    """Waits until the job body has started (its first scalar is logged). A job that never starts fails here with its
    status and message, instead of timing out in the test that needed it. A job whose container never starts ends
    with a final status, which ends this wait at once (wait_until); the ceiling only covers a job that is still in
    progress without logging anything (E2E.md, speed section, item 8)."""
    record = wait_until(api, task_id, lambda r: r.get("last_metrics"), timeout=timeout)
    if record:
        return record
    last = task_record(api, task_id)
    raise AssertionError(
        "the job never started: after {:.0f} s its status is '{}' ({!r}); its job body did not run".format(
            timeout, last.get("status"), last.get("status_message")))

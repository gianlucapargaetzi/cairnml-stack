"""Gets a task, then enqueues it, in one process. Used to show the order-dependence of the enqueue check (KNOWN
DEFECT D6): enqueueing as the first SDK call works, after a service call it is refused."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import report  # noqa: E402

from clearml import Task  # noqa: E402
from clearml.backend_interface.task.requirements import build_requirements  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="get a task, then enqueue it")
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()

    Task.get_task(task_id=args.task_id)
    requirements = build_requirements(cpus=1, ram_gb=1.0, gpus=0, disk_gb=1.0)
    result = Task.enqueue(args.task_id, force=True, requirements=requirements)
    report({"queued": result["data"]["queued"]})


if __name__ == "__main__":
    main()

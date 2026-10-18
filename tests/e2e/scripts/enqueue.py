"""Puts a recorded task in the queue with what it needs from a machine. Must be the first SDK call of its process:
the SDK learns the server's API level from its first session, and enqueue depends on it."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import report  # noqa: E402

from clearml import Task  # noqa: E402
from clearml.backend_interface.task.requirements import build_requirements  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="enqueue a task")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--ram-gb", type=float, default=1.0)
    parser.add_argument("--gpus", type=int, default=0)
    parser.add_argument("--gpu-memory-gb", type=float, default=0.0)
    parser.add_argument("--disk-gb", type=float, default=1.0)
    parser.add_argument("--priority", type=int, default=50)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    requirements = build_requirements(cpus=args.cpus, ram_gb=args.ram_gb, gpus=args.gpus,
                                      gpu_memory_gb=args.gpu_memory_gb, disk_gb=args.disk_gb)
    result = Task.enqueue(args.task_id, force=args.force, requirements=requirements, priority=args.priority)
    report({"queued": result["data"]["queued"], "status": result["data"]["fields"]["status"]})


if __name__ == "__main__":
    main()

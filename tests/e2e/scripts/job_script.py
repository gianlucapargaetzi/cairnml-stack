"""The body of a job: what runs on an agent when a task is enqueued.

Options let the tests shape a run: how many scalars it logs, how long it sleeps, whether it fails after a set
number of scalars, and whether it reports the git commit of the checkout it runs in. It always writes one small
artifact, and prints a JSON line at the end.
"""

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import report  # noqa: E402

from clearml import Task  # noqa: E402

# A small image that is on the host already, so a job does not depend on a registry pull.
BASE_IMAGE = "python:3.12-slim"


def git_commit(folder: Path):
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=folder, capture_output=True, text=True, timeout=30)
    except OSError:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def main() -> None:
    parser = argparse.ArgumentParser(description="a job body")
    parser.add_argument("--scalars", type=int, default=10)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--fail-after", type=int, default=0, help="raise after this many scalars (0: never)")
    parser.add_argument("--git", action="store_true", help="report the commit of the checkout")
    parser.add_argument("--base-image", default=BASE_IMAGE, help="the container image the job runs in")
    parser.add_argument("--project", default="e2e-jobs")
    parser.add_argument("--name", default="job")
    args = parser.parse_args()

    task = Task.init(project_name=args.project, task_name=args.name, reuse_last_task_id=False)
    task.set_base_docker(args.base_image)
    logger = task.get_logger()
    for step in range(args.scalars):
        logger.report_scalar(title="job", series="progress", value=step, iteration=step)
        if args.fail_after and step + 1 == args.fail_after:
            raise RuntimeError("deliberate failure in the job script")
        time.sleep(args.sleep / max(args.scalars, 1))
    print("job body finished")

    commit = git_commit(Path(__file__).resolve().parent) if args.git else None
    marker = Path(tempfile.mkstemp(prefix="job-result-", suffix=".txt")[1])
    marker.write_text("result of the job\n")
    task.upload_artifact("result", artifact_object=str(marker), wait_on_upload=True)
    report({"task_id": task.id, "commit": commit})
    task.close()


if __name__ == "__main__":
    main()

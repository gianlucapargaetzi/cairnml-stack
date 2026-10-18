"""A training script that records a run: two scalar series, parameters, a single value, a text line, a debug
image and a console line. It is the "first run" of README section 2, with more of the logger in it.

Run it on a machine that has been enrolled with clearml-init. The last line it prints is JSON with the task id.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import report  # noqa: E402

from clearml import Task  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="record a run")
    parser.add_argument("--project", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--steps", type=int, default=100)
    args = parser.parse_args()

    task = Task.init(project_name=args.project, task_name=args.name, reuse_last_task_id=False)
    # set_parameters replaces the whole parameter set, so it comes first; set_parameter then adds to it.
    task.set_parameters({"General/epochs": 3})
    task.set_parameter("General/lr", 0.01)

    logger = task.get_logger()
    for step in range(args.steps):
        logger.report_scalar(title="loss", series="train", value=1.0 / (step + 1), iteration=step)
        logger.report_scalar(title="loss", series="val", value=2.0 / (step + 1), iteration=step)
    logger.report_single_value(name="accuracy", value=0.93)
    logger.report_text("text line from the example run")
    logger.report_image(title="debug", series="gradient", iteration=0,
                        image=np.tile(np.arange(16, dtype=np.uint8), (16, 1)))
    print("console line from the example run")

    report({"task_id": task.id, "steps": args.steps})
    task.close()


if __name__ == "__main__":
    main()

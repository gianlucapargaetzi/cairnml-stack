"""Gets a dataset by id on another machine, copies it out, and prints the digest of each file it finds."""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import file_digest, report  # noqa: E402

from clearml import Dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="get a dataset and check its files")
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    local = Path(Dataset.get(dataset_id=args.dataset_id).get_local_copy())
    out = Path(args.out)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(local, out)
    files = {}
    for path in sorted(out.rglob("*")):
        if path.is_file():
            files[path.relative_to(out).as_posix()] = file_digest(path)
    report({"files": files})


if __name__ == "__main__":
    main()

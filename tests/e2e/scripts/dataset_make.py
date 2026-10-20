"""Creates a dataset from a folder: add the files, finalize, upload. Prints the dataset id and the digest of each
file, so a second machine can check what it gets back (see dataset_fetch.py)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import deterministic_bytes, file_digest, report  # noqa: E402

from clearml import Dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="create and upload a dataset")
    parser.add_argument("--project", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--work", required=True)
    args = parser.parse_args()

    source = Path(args.work)
    (source / "images").mkdir(parents=True, exist_ok=True)
    for index in range(3):
        (source / "images" / f"sample-{index}.bin").write_bytes(deterministic_bytes(50_000 + index, seed=index))
    (source / "labels.csv").write_text("id,label\n0,cat\n1,dog\n2,cat\n")

    dataset = Dataset.create(dataset_name=args.name, dataset_project=args.project)
    dataset.add_files(path=str(source))
    dataset.upload()
    dataset.finalize()
    refused_after_finalize = False
    try:
        dataset.add_files(path=str(source / "labels.csv"))
    except Exception:
        refused_after_finalize = True
    files = {}
    for path in sorted(source.rglob("*")):
        if path.is_file():
            files[path.relative_to(source).as_posix()] = file_digest(path)
    report({"dataset_id": dataset.id, "files": files, "refused_after_finalize": refused_after_finalize})


if __name__ == "__main__":
    main()

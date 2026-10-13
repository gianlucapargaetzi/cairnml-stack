"""Resolve a local path to the DVC hash recorded in git."""

from __future__ import annotations

from pathlib import Path

import yaml
from mlops_common.schemas import DatasetRef

from mlops.capture.git import GitState


def _dvc_file_hash(dvc_file: Path) -> str | None:
    outs = (yaml.safe_load(dvc_file.read_text()) or {}).get("outs") or []
    return outs[0].get("md5") if outs else None


def _lock_hash(lock_file: Path, relative: str) -> str | None:
    stages = (yaml.safe_load(lock_file.read_text()) or {}).get("stages") or {}
    for stage in stages.values():
        for out in stage.get("outs") or []:
            if out.get("path") == relative:
                return out.get("md5")
    return None


def resolve_dataset(path: str | Path, git: GitState | None, base: Path | None = None) -> DatasetRef:
    if git is None:
        raise ValueError("datasets need a git repository that holds the DVC metadata")
    absolute = (Path(base or Path.cwd()) / path).resolve()
    if git.root != absolute and git.root not in absolute.parents:
        raise ValueError(f"{path} is outside the git repository {git.root}")
    relative = absolute.relative_to(git.root).as_posix()
    digest = None
    dvc_file = absolute.parent / (absolute.name + ".dvc")
    if dvc_file.exists():
        digest = _dvc_file_hash(dvc_file)
    if digest is None:
        # dvc.lock paths are relative to the directory holding the lock file.
        candidates = [absolute.parent / "dvc.lock"]
        if git.root / "dvc.lock" not in candidates:
            candidates.append(git.root / "dvc.lock")
        for lock in candidates:
            inside = lock.parent == absolute.parent or lock.parent in absolute.parents
            if lock.exists() and inside:
                digest = _lock_hash(lock, absolute.relative_to(lock.parent).as_posix())
                if digest:
                    break
    if digest is None:
        raise ValueError(f"{path} is not tracked by DVC (no .dvc file or dvc.lock entry)")
    return DatasetRef(path=relative, dvc_hash=digest, repo=git.repo, commit=git.commit)

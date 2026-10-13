"""Locate the running script and the working directory relative to the repo."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from mlops.capture.git import GitState


@dataclass(frozen=True)
class ScriptInfo:
    path: Path
    in_repo: bool
    rel: str | None  # posix path relative to the repo root when in_repo


def find_script(
    explicit: str | Path | None = None, git: GitState | None = None
) -> ScriptInfo | None:
    candidate = explicit
    if candidate is None:
        main = sys.modules.get("__main__")
        candidate = getattr(main, "__file__", None) or (sys.argv[0] if sys.argv else None)
    if not candidate or candidate in ("-c", "-m"):
        return None
    path = Path(candidate).resolve()
    if not path.is_file():
        return None
    if git is not None and git.root in path.parents:
        return ScriptInfo(path, True, path.relative_to(git.root).as_posix())
    return ScriptInfo(path, False, None)


def relative_cwd(git: GitState | None, start: Path | None = None) -> str:
    if git is None:
        return "."
    here = Path(start or Path.cwd()).resolve()
    if here == git.root:
        return "."
    return here.relative_to(git.root).as_posix() if git.root in here.parents else "."

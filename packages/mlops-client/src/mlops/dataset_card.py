"""Dataset card scaffolding: writes a Markdown card next to a .dvc file. Uploads nothing."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def parse_dvc_file(text: str) -> dict:
    """The hash, size and file count of the single output in a .dvc file (None when absent)."""
    empty = {"dvc_hash": None, "size_bytes": None, "nfiles": None}
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return empty
    outs = doc.get("outs") if isinstance(doc, dict) else None
    if not isinstance(outs, list) or not outs or not isinstance(outs[0], dict):
        return empty
    return {
        "dvc_hash": outs[0].get("md5"),
        "size_bytes": outs[0].get("size"),
        "nfiles": outs[0].get("nfiles"),
    }


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def check_dataset_path(path: str | Path) -> str:
    """A repository-relative dataset path without '..', empty or absolute segments."""
    text = str(path)
    if not text or text.startswith("/") or any(p in ("", "..") for p in text.split("/")):
        raise ValueError(f"unsafe dataset path {text!r}")
    return text


def scaffold_card(
    path: str | Path,
    dvc_info: dict,
    *,
    title: str | None = None,
    license: str | None = None,
    type: str = "other",
    description: str | None = None,
) -> str:
    path = check_dataset_path(path)
    title = title or path.rsplit("/", 1)[-1]
    meta: dict = {
        "title": title,
        "type": type,
        "license": license or "unspecified",
        "version": "1",
        "tags": [],
        "owners": [],
    }
    if dvc_info.get("size_bytes") is not None:
        meta["size_bytes"] = dvc_info["size_bytes"]
    front = yaml.safe_dump(meta, sort_keys=False).strip()
    nfiles = f"{dvc_info['nfiles']} files, " if dvc_info.get("nfiles") else ""
    summary = description or (
        "Describe what this dataset contains, how it was collected, and known limitations."
    )
    return (
        f"---\n{front}\n---\n# {title}\n\n{summary}\n\n"
        f"## Contents\n\n- {nfiles}DVC hash `{dvc_info.get('dvc_hash') or 'n/a'}` "
        "(recorded when this card was created).\n\n"
        "## Intended use\n\n## Known issues\n"
    )


def write_card(path: str | Path, dvc_info: dict, **fields) -> Path:
    """Create PATH.card.md exclusively (mode "x"); FileExistsError when it is already there."""
    text = scaffold_card(path, dvc_info, **fields)
    target = Path(str(path) + ".card.md")
    with open(target, "x", encoding="utf-8") as handle:
        handle.write(text)
    return target


def printable(text: object) -> str:
    """Card text safe for a terminal: control characters removed, newlines and tabs kept."""
    return _CONTROL.sub("", str(text))

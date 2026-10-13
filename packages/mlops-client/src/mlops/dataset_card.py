"""Dataset card scaffolding: writes a Markdown card next to a .dvc file. Uploads nothing."""

from __future__ import annotations

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


def scaffold_card(
    path: str | Path,
    dvc_info: dict,
    *,
    title: str | None = None,
    license: str | None = None,
    type: str = "other",
    description: str | None = None,
) -> str:
    path = str(path)
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

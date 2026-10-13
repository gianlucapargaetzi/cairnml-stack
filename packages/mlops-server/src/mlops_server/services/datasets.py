"""Dataset catalog and cards, read from Git. The framework stores no dataset metadata of its own."""

from __future__ import annotations

import datetime
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from mlops_server.services.github import CommitInfo

CARD_SUFFIX = ".card.md"
MAX_DATASETS = 200
MAX_VERSIONS = 10
DatasetType = Literal["tabular", "images", "text", "audio", "video", "timeseries", "other"]


class Column(BaseModel):
    name: str
    type: str | None = None
    description: str | None = None


class DatasetCardOut(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    title: str | None = None
    type: DatasetType = "other"
    license: str | None = None
    source: str | None = None
    version: str | None = None
    created: str | None = None
    owners: list[str] = []
    tags: list[str] = []
    size_bytes: int | None = Field(default=None, ge=0)
    rows: int | None = Field(default=None, ge=0)
    columns: list[Column] = []
    splits: dict[str, int] = {}
    extra: dict[str, Any] = {}
    warnings: list[str] = []
    error: str | None = None
    body: str = ""

    @field_validator("created", mode="before")
    @classmethod
    def _date_as_text(cls, value: Any) -> Any:
        # YAML reads an unquoted 2026-01-01 as a date object; keep the author's spelling.
        if isinstance(value, datetime.date):
            return value.isoformat()
        return value


def front_matter(text: str) -> tuple[dict, str, str | None]:
    if not text.startswith("---"):
        return {}, text, None
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text, "front matter is not closed"
    body = text[end + 4 :].lstrip("\n")
    try:
        meta = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as exc:
        return {}, body, f"invalid YAML ({exc.__class__.__name__})"
    if not isinstance(meta, dict):
        return {}, body, "front matter must be a mapping"
    return meta, body, None


_KNOWN = set(DatasetCardOut.model_fields) - {"extra", "warnings", "error", "body"}


def parse_card(text: str) -> DatasetCardOut:
    meta, body, error = front_matter(text)
    if error:
        return DatasetCardOut(error=error, body=body)
    # YAML null means "not set": treat it like an absent key so it is not reported as invalid.
    known = {k: v for k, v in meta.items() if k in _KNOWN and v is not None}
    extra = {k: v for k, v in meta.items() if k not in _KNOWN}
    warnings: list[str] = []
    while True:
        try:
            return DatasetCardOut(**known, extra=extra, warnings=warnings, body=body)
        except ValidationError as exc:
            bad = {str(e["loc"][0]) for e in exc.errors() if e["loc"]} & set(known)
            if not bad:
                return DatasetCardOut(
                    extra=extra, warnings=warnings + ["card could not be read"], body=body
                )
            for key in sorted(bad):
                warnings.append(f"ignored invalid field {key!r}")
                known.pop(key)


def _dvc_outs(text: str | None) -> list | None:
    if not text:
        return None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    outs = doc.get("outs") if isinstance(doc, dict) else None
    return outs if isinstance(outs, list) else None


def parse_dvc(text: str | None) -> dict:
    empty: dict[str, Any] = {"dvc_hash": None, "size_bytes": None, "nfiles": None}
    outs = _dvc_outs(text)
    if not outs or not isinstance(outs[0], dict):
        return empty
    return {
        "dvc_hash": outs[0].get("md5"),
        "size_bytes": outs[0].get("size"),
        "nfiles": outs[0].get("nfiles"),
    }


def list_datasets(github, repo: str, ref: str) -> list[dict]:
    paths, _truncated = github.list_tree(repo, ref)
    present = set(paths)
    entries = []
    dvc_paths = sorted(p for p in paths if p.endswith(".dvc") and not p.startswith(".dvc/"))
    for dvc_path in dvc_paths[:MAX_DATASETS]:
        path = dvc_path[: -len(".dvc")]
        entry: dict[str, Any] = {
            "path": path,
            **parse_dvc(github.read_file(repo, dvc_path, ref)),
            "has_card": path + CARD_SUFFIX in present,
            "type": None,
            "license": None,
            "title": None,
            "tags": [],
        }
        if entry["has_card"]:
            card = parse_card(github.read_file(repo, path + CARD_SUFFIX, ref) or "")
            entry.update(type=card.type, license=card.license, title=card.title, tags=card.tags)
        entries.append(entry)
    return entries


def _version(github, repo: str, dvc_path: str, commit: CommitInfo) -> dict:
    return {
        "commit": commit.sha,
        "date": commit.date,
        "message": commit.message,
        "author": commit.author,
        "dvc_hash": parse_dvc(github.read_file(repo, dvc_path, commit.sha))["dvc_hash"],
    }


def dataset_detail(github, repo: str, path: str, ref: str) -> dict | None:
    dvc_path = path + ".dvc"
    dvc_text = github.read_file(repo, dvc_path, ref)
    if dvc_text is None:
        return None
    card_text = github.read_file(repo, path + CARD_SUFFIX, ref)
    commits = github.list_path_commits(repo, dvc_path, ref, limit=MAX_VERSIONS)
    return {
        "repo": repo,
        "path": path,
        "ref": ref,
        "dvc": parse_dvc(dvc_text),
        "card": parse_card(card_text).model_dump() if card_text is not None else None,
        "versions": [_version(github, repo, dvc_path, c) for c in commits],
    }

"""Sequences: storage keys for binary items, validation of registered items, and their writes.

A binary item (image, audio) is stored in S3 under a key derived from its own fields, so the
server can check that a registration points at the object its item describes. Text, figure and
distribution items carry their value inline. A batch is validated in full before anything is
written, so a refused item never leaves the rest of its batch half stored."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException
from mlops_common.schemas import MAX_SEQUENCE_DATA, SequenceItemIn
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Run, Sequence, SequenceItem
from mlops_server.services.storage import safe_artifact_name

BINARY_KINDS = {"image", "audio"}
MAX_DISTRIBUTION_BINS = 10_000


def context_segment(context: dict[str, Any]) -> str:
    """A path segment that keeps two contexts with the same name and step apart, or ""."""
    if not context:
        return ""
    digest = hashlib.sha1(json.dumps(context, sort_keys=True).encode()).hexdigest()[:10]
    return f"ctx-{digest}/"


def blob_key(
    project_slug: str, run_id: str, kind: str, name: str, context: dict[str, Any],
    step: int | None, idx: int, fmt: str,
) -> str:
    """<project>/<run>/<kind>/<name>/[ctx-<hash>/]<step>_<idx>.<format>. Raises ValueError on a
    name that is not a safe path."""
    name = safe_artifact_name(name)
    step_part = "none" if step is None else str(step)
    return (
        f"{project_slug}/{run_id}/{kind}/{name}/{context_segment(context)}"
        f"{step_part}_{idx}.{fmt}"
    )


def _refuse(message: str) -> HTTPException:
    return HTTPException(422, message)


def validate_item(item: SequenceItemIn, project_slug: str, run_id: str) -> None:
    """Checks that the item has the value its kind needs. Raises HTTPException(422)."""
    try:
        safe_artifact_name(item.name)
    except ValueError:
        raise _refuse("invalid sequence name") from None
    if item.kind in BINARY_KINDS:
        if not item.format or not item.blob_key:
            raise _refuse(f"a {item.kind} item needs a format and an uploaded blob_key")
        expected = blob_key(
            project_slug, run_id, item.kind, item.name, item.context, item.step, item.idx,
            item.format,
        )
        if item.blob_key != expected:
            raise _refuse("blob_key must be the key the presign call returned for this item")
        if item.text is not None or item.data is not None:
            raise _refuse(f"a {item.kind} item carries its value in the blob, not in text or data")
    elif item.kind == "text":
        if item.text is None:
            raise _refuse("a text item needs text")
        if item.blob_key or item.data is not None:
            raise _refuse("a text item carries only text")
    else:
        _validate_inline_data(item)


def _validate_inline_data(item: SequenceItemIn) -> None:
    if item.data is None:
        raise _refuse(f"a {item.kind} item needs data")
    if item.blob_key or item.text is not None:
        raise _refuse(f"a {item.kind} item carries only data")
    try:
        size = len(json.dumps(item.data, allow_nan=False))
    except (TypeError, ValueError):
        raise _refuse(f"{item.kind} data must be JSON") from None
    if size > MAX_SEQUENCE_DATA:
        raise _refuse(f"{item.kind} data is larger than {MAX_SEQUENCE_DATA} bytes")
    if item.kind == "distribution":
        _validate_distribution(item.data)


def _validate_distribution(data: Any) -> None:
    if not isinstance(data, dict):
        raise _refuse("distribution data is {bin_counts, bin_range}")
    counts, bounds = data.get("bin_counts"), data.get("bin_range")
    if not isinstance(counts, list) or not counts or len(counts) > MAX_DISTRIBUTION_BINS:
        raise _refuse(f"bin_counts is a list of 1 to {MAX_DISTRIBUTION_BINS} numbers")
    if not all(isinstance(c, int | float) and not isinstance(c, bool) for c in counts):
        raise _refuse("bin_counts holds numbers only")
    if (
        not isinstance(bounds, list) or len(bounds) != 2
        or not all(isinstance(b, int | float) and not isinstance(b, bool) for b in bounds)
    ):
        raise _refuse("bin_range is [low, high]")


def write_items(
    session: Session, run: Run, project_slug: str, items: list[SequenceItemIn]
) -> int:
    """Stores the items, skipping any whose (sequence, step, index) is already stored. Returns
    the number stored. Validation of the whole batch happens first."""
    for item in items:
        validate_item(item, project_slug, run.id)
    sequences: dict[tuple[str, str, str], Sequence] = {}
    stored = 0
    for item in items:
        key = (item.kind, item.name, json.dumps(item.context, sort_keys=True))
        sequence = sequences.get(key)
        if sequence is None:
            sequence = session.scalar(
                select(Sequence).where(
                    Sequence.run_id == run.id, Sequence.kind == item.kind,
                    Sequence.name == item.name, Sequence.context == item.context,
                )
            )
            if sequence is None:
                sequence = Sequence(run_id=run.id, kind=item.kind, name=item.name,
                                    context=item.context)
                session.add(sequence)
                session.flush()
            sequences[key] = sequence
        if item.step is not None and _exists(session, sequence.id, item.step, item.idx):
            continue
        session.add(SequenceItem(
            sequence_id=sequence.id, step=item.step, idx=item.idx, epoch=item.epoch,
            ts=item.ts, caption=item.caption, format=item.format, width=item.width,
            height=item.height, blob_key=item.blob_key, text=item.text,
            data=item.data if item.kind in {"figure", "distribution"} else None,
        ))
        session.flush()
        stored += 1
    session.commit()
    return stored


def _exists(session: Session, sequence_id: int, step: int, idx: int) -> bool:
    return session.scalar(
        select(SequenceItem.id).where(
            SequenceItem.sequence_id == sequence_id, SequenceItem.step == step,
            SequenceItem.idx == idx,
        )
    ) is not None

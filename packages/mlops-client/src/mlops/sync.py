"""Upload runs that were recorded while the server was unreachable (`mlops sync`).

Exactly-once rules:
- The experiment is created once and its id is written to the spool meta before any
  event is replayed, so a retry reuses it.
- Log lines carry a seq, so the server ignores a replayed batch it already has.
- Each artifact's ordinal is written to the meta once it is registered, so a retry does
  not register it twice.
- Metrics have no server idempotency key. A crash between a metrics POST and the spool
  rewrite can repeat that batch on the next sync (known residual risk).

The spool is removed only when every event and artifact succeeded.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

import httpx

from mlops import transfer
from mlops.config import spool_root
from mlops.spool import Spool
from mlops.uplink import replay

log = logging.getLogger("mlops")


def _write_meta(directory: Path, meta: dict) -> None:
    tmp = directory / "meta.json.tmp"
    with tmp.open("w") as handle:
        handle.write(json.dumps(meta))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, directory / "meta.json")


def _artifact_error(exc: Exception) -> str:
    # Never include str(exc): httpx puts the presigned URL (a one-hour write capability)
    # into HTTP error messages.
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def _sync_artifacts(
    api, spool: Spool, directory: Path, meta: dict, experiment_id: str, put
) -> None:
    done = set(meta.get("artifacts_registered", []))
    errors: list[str] = []
    ordinal = -1
    for event in spool.events():
        if event["kind"] != "artifact":
            continue
        ordinal += 1
        if ordinal in done:
            continue
        payload = event["payload"]
        try:
            presigned = api.presign(experiment_id, payload["name"])
            put(presigned["upload_url"], spool.file_path(payload["name"]))
            api.register_artifact(
                experiment_id,
                payload["name"],
                presigned["key"],
                payload["size"],
                payload["kind"],
                payload["meta"],
            )
        except Exception as exc:
            errors.append(f"artifact {payload['name']}: {_artifact_error(exc)}")
            continue
        done.add(ordinal)
        meta = {**meta, "artifacts_registered": sorted(done)}
        _write_meta(directory, meta)
    if errors:
        raise RuntimeError("; ".join(errors))


def _sync_one(api, directory: Path, put) -> str:
    spool = Spool(directory)
    meta = spool.meta()
    experiment_id = meta.get("experiment_id")
    if experiment_id is None:
        created = api.create_experiment(
            meta["project"], meta["name"], meta.get("config") or {},
            task=meta.get("task") or "general",
            primary_metric=meta.get("primary_metric"),
            direction=meta.get("direction"),
        )
        experiment_id = created["id"]
        meta = {**meta, "experiment_id": experiment_id}
        _write_meta(directory, meta)  # before any replay, so a retry reuses this experiment

    replay(spool, api, experiment_id, keep_rejected=True)
    undelivered = sum(1 for event in spool.events() if event["kind"] != "artifact")
    if undelivered:
        raise RuntimeError(f"{undelivered} event(s) not delivered; the spool is kept")
    _sync_artifacts(api, spool, directory, meta, experiment_id, put)
    return experiment_id


def sync_all(api, root: Path | None = None, put=None, failed: list[str] | None = None) -> list[str]:
    """Replay every spooled run. Returns the experiment ids that were fully synced.

    A run that fails keeps its spool; its error is appended to `failed` when given.
    """
    put = put or transfer.put_file
    root = Path(root or spool_root())
    synced: list[str] = []
    if not root.exists():
        return synced
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            experiment_id = _sync_one(api, directory, put)
        except Exception as exc:
            log.warning("could not sync %s, keeping its spool: %s", directory.name, exc)
            if failed is not None:
                failed.append(f"{directory.name}: {exc}")
            continue
        try:
            # replay() already removes the directory when no events or artifacts remain.
            if directory.exists():
                shutil.rmtree(directory)
        except OSError as exc:
            # The run is on the server, but a leftover spool must not pass as a clean sync.
            log.warning("synced %s but could not remove its spool: %s", directory.name, exc)
            if failed is not None:
                failed.append(f"{directory.name}: could not remove the spool: {exc}")
            continue
        synced.append(experiment_id)
    return synced

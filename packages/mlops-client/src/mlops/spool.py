"""On-disk queue for events that could not reach the server."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


class Spool:
    def __init__(self, directory: Path, meta: dict | None = None) -> None:
        self.dir = Path(directory)
        self._meta = meta or {}

    @property
    def _events_file(self) -> Path:
        return self.dir / "events.jsonl"

    def exists(self) -> bool:
        return self.dir.exists()

    def meta(self) -> dict:
        path = self.dir / "meta.json"
        return json.loads(path.read_text()) if path.exists() else dict(self._meta)

    def _ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        meta_path = self.dir / "meta.json"
        if not meta_path.exists():
            meta_path.write_text(json.dumps(self._meta))

    def append(self, kind: str, payload: dict) -> None:
        self._ensure()
        with self._events_file.open("a") as handle:
            handle.write(json.dumps({"kind": kind, "payload": payload}) + "\n")

    def events(self) -> list[dict]:
        if not self._events_file.exists():
            return []
        return [json.loads(line) for line in self._events_file.read_text().splitlines() if line]

    def rewrite(self, events: list[dict]) -> None:
        if not events:
            shutil.rmtree(self.dir, ignore_errors=True)
            return
        self._events_file.write_text("".join(json.dumps(e) + "\n" for e in events))

    def file_path(self, name: str) -> Path:
        self._ensure()
        root = (self.dir / "files").resolve()
        target = (root / name).resolve()
        if root not in target.parents:
            raise ValueError(f"invalid spool file name: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

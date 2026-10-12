from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx

_CHUNK = 1024 * 1024


def _chunks(path: Path) -> Iterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            yield chunk


def put_file(url: str, source: Path | bytes, http: httpx.Client | None = None) -> None:
    client = http or httpx.Client(
        timeout=httpx.Timeout(60.0, connect=10.0, read=600.0, write=600.0)
    )
    if isinstance(source, bytes):
        response = client.put(url, content=source)
    else:
        response = client.put(
            url, content=_chunks(source), headers={"Content-Length": str(source.stat().st_size)}
        )
    response.raise_for_status()

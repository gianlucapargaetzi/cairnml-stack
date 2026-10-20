"""Helpers shared by the example scripts: the one JSON line a script prints at the end, and the digests the
artifact scripts compare (the upload side writes them, the check side recomputes them from what came back)."""

import hashlib
import io
import json
import os
from pathlib import Path


def report(result: dict) -> None:
    """The last line of every script: what it did, as JSON, for the test that ran it."""
    print(json.dumps(result, sort_keys=True))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path) -> str:
    return sha256(Path(path).read_bytes())


def folder_digest(path) -> str:
    """Digest of a folder: its relative file names and their contents, in a stable order."""
    root = Path(path)
    entries = []
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            full = Path(dirpath) / filename
            entries.append((full.relative_to(root).as_posix(), file_digest(full)))
    return sha256(json.dumps(sorted(entries)).encode())


def json_digest(obj) -> str:
    return sha256(json.dumps(obj, sort_keys=True).encode())


def frame_digest(frame) -> str:
    return sha256(frame.to_csv(index=False).encode())


def array_digest(array) -> str:
    import numpy as np

    array = np.asarray(array)
    return sha256(str(array.dtype).encode() + str(array.shape).encode() + array.tobytes())


def image_digest(image) -> str:
    """The pixels of an image (PIL or array), so the digest does not depend on the file format."""
    import numpy as np

    if hasattr(image, "convert"):
        image = np.asarray(image.convert("RGB"))
    return array_digest(image)


def pickled_digest(obj) -> str:
    """The canonical form of a plain object (dicts, lists, tuples, sets, numbers, strings)."""
    return sha256(repr(_canonical(obj)).encode())


def _canonical(obj):
    if isinstance(obj, dict):
        return sorted((repr(k), _canonical(v)) for k, v in obj.items())
    if isinstance(obj, (set, frozenset)):
        return sorted(repr(_canonical(v)) for v in obj)
    if isinstance(obj, (list, tuple)):
        return [type(obj).__name__, [_canonical(v) for v in obj]]
    return obj


def deterministic_bytes(size: int, seed: int) -> bytes:
    """Bytes that are the same on every run for the same seed, so a re-run can be compared."""
    out = io.BytesIO()
    block = hashlib.sha256(str(seed).encode()).digest()
    while out.tell() < size:
        block = hashlib.sha256(block).digest()
        out.write(block)
    return out.getvalue()[:size]

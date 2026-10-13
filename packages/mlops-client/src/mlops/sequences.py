"""Turns the values of log_image, log_audio, log_text, log_figure and log_distribution into what
the server stores. Each encoder raises ValueError with the reason when a value cannot be stored,
before anything is sent or spooled."""

from __future__ import annotations

import io
import json
import math
import re
import struct
from pathlib import Path
from typing import Any

from mlops_common.schemas import MAX_SEQUENCE_TEXT

DISTRIBUTION_BINS = 64
_NAME_RE = re.compile(r"[A-Za-z0-9._/-]+")


def checked_name(name: str) -> str:
    """A sequence name is a path-like label: letters, digits, '.', '_', '-' and '/' between
    non-empty parts. The storage key is built from it."""
    if not isinstance(name, str) or not name or len(name) > 200 or not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid sequence name {name!r}")
    if name.startswith("/") or any(part in ("", ".", "..") for part in name.split("/")):
        raise ValueError(f"invalid sequence name {name!r}")
    return name


def _read(value: Any) -> bytes:
    if isinstance(value, bytes | bytearray):
        return bytes(value)
    if isinstance(value, str | Path):
        path = Path(value)
        if not path.is_file():
            raise ValueError(f"{value!r} is not an existing file")
        return path.read_bytes()
    raise ValueError("pass bytes, the path of a file, or a PIL image")


def _image_format(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    raise ValueError("images must be PNG, JPEG, GIF or WEBP bytes, a file of one of those, "
                     "or a PIL image")


def _image_size(data: bytes, fmt: str) -> tuple[int | None, int | None]:
    """Width and height from the header, when the format keeps them where we can read them."""
    try:
        if fmt == "png":
            width, height = struct.unpack(">II", data[16:24])
            return width, height
        if fmt == "gif":
            width, height = struct.unpack("<HH", data[6:10])
            return width, height
        if fmt == "jpeg":
            i = 2
            while i + 9 <= len(data) and data[i] == 0xFF:
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):  # start of frame
                    height, width = struct.unpack(">HH", data[i + 5:i + 9])
                    return width, height
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except struct.error:
        pass
    return None, None


def encode_image(value: Any) -> tuple[bytes, str, int | None, int | None]:
    """(bytes, format, width, height) of an image."""
    if hasattr(value, "save") and hasattr(value, "size"):  # a PIL image, without importing PIL
        buffer = io.BytesIO()
        value.save(buffer, format="PNG")
        width, height = value.size
        return buffer.getvalue(), "png", int(width), int(height)
    data = _read(value)
    fmt = _image_format(data)
    width, height = _image_size(data, fmt)
    return data, fmt, width, height


def encode_audio(value: Any) -> tuple[bytes, str]:
    """(bytes, format) of an encoded audio file. Raw sample arrays are not accepted."""
    data = _read(value)
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return data, "wav"
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return data, "mp3"
    if data[:4] == b"OggS":
        return data, "ogg"
    if data[:4] == b"fLaC":
        return data, "flac"
    raise ValueError("audio must be WAV, MP3, OGG or FLAC bytes, or a file of one of those")


def encode_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("text must be a string")
    if len(value) > MAX_SEQUENCE_TEXT:
        raise ValueError(f"text is longer than {MAX_SEQUENCE_TEXT} characters")
    return value


def encode_figure(value: Any) -> dict:
    """A Plotly figure, as its JSON dict."""
    if hasattr(value, "to_plotly_json"):
        value = value.to_plotly_json()
    if not isinstance(value, dict):
        raise ValueError("figures are Plotly figures or dicts of Plotly JSON")
    _check_json(value, "figure")
    return value


def encode_distribution(values: Any) -> dict:
    """{bin_counts, bin_range} of a distribution. A dict already in that form is kept; a sequence
    of numbers is counted into DISTRIBUTION_BINS equal-width bins."""
    if isinstance(values, dict):
        _check_json(values, "distribution")
        return values
    try:
        numbers = [float(v) for v in values]
    except (TypeError, ValueError):
        raise ValueError("a distribution is a dict {bin_counts, bin_range} or numbers") from None
    if not numbers or not all(math.isfinite(v) for v in numbers):
        raise ValueError("a distribution needs at least one finite number")
    low, high = min(numbers), max(numbers)
    if low == high:
        low, high = low - 0.5, high + 0.5
    width = (high - low) / DISTRIBUTION_BINS
    counts = [0] * DISTRIBUTION_BINS
    for v in numbers:
        counts[min(int((v - low) / width), DISTRIBUTION_BINS - 1)] += 1
    return {"bin_counts": counts, "bin_range": [low, high]}


def _check_json(value: Any, what: str) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be JSON with finite numbers") from None

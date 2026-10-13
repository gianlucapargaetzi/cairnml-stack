"""Environment capture with secret redaction."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import subprocess

_SECRET_KEY = re.compile(
    r"(token|secret|passw|pwd|cookie|credential|auth|private[-_]?key|access[-_]?key|api[-_]?key|key)",
    re.I,
)
_TOKENISH = re.compile(
    r"^(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.)"
)
# scheme://user:password@host, the password part is masked (the user part is kept).
_URL_PASSWORD = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*://[^:/@\s]*):([^@\s]*)@")


def _mask_url_password(value: str) -> str:
    return _URL_PASSWORD.sub(r"\1:***@", value)


def redact_mapping(values: dict) -> dict:
    out = {}
    for key, value in values.items():
        if _SECRET_KEY.search(str(key)):
            out[key] = "***"
        elif isinstance(value, str):
            out[key] = _mask_url_password(value)
        else:
            out[key] = value
    return out


def redact_argv(argv: list[str]) -> list[str]:
    out: list[str] = []
    hide_next = False
    for item in argv:
        if hide_next:
            out.append("***")
            hide_next = False
        elif item.startswith("--") and "=" in item:
            flag, _, value = item.partition("=")
            if _SECRET_KEY.search(flag) or _TOKENISH.match(value):
                out.append(f"{flag}=***")
            else:
                out.append(f"{flag}={_mask_url_password(value)}")
        elif item.startswith("-") and _SECRET_KEY.search(item):
            out.append(item)
            hide_next = True
        elif _TOKENISH.match(item):
            out.append("***")
        else:
            out.append(_mask_url_password(item))
    return out


def _is_local_install(dist) -> bool:
    raw = dist.read_text("direct_url.json")
    if not raw:
        return False
    try:
        info = json.loads(raw)
    except ValueError:
        return False
    editable = bool(info.get("dir_info", {}).get("editable"))
    return editable or str(info.get("url", "")).startswith("file:")


def capture_requirements() -> list[str]:
    found: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = (dist.metadata["Name"] or "").strip()
        if not name or re.match(r"^mlops[-_]", name, re.I) or _is_local_install(dist):
            continue
        found[name.lower().replace("_", "-")] = dist.version
    return [f"{name}=={version}" for name, version in sorted(found.items())]


def _gpus() -> list[str]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def capture_environment() -> dict:
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count() or 1,
        "gpus": _gpus(),
    }

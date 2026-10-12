"""Capture (and optionally override) argparse results of the top-level parser."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable

_original = None
_depth = 0
_state: dict = {"callback": None, "overrides": None}


def _jsonable(values: dict) -> dict:
    return json.loads(json.dumps(values, default=str))


def _cast(value, current):
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("1", "true", "yes", "on")
    if isinstance(current, (int, float, str)) and not isinstance(value, (list, dict)):
        try:
            return type(current)(value)
        except (TypeError, ValueError):
            return value
    return value


def apply_overrides(ns: argparse.Namespace, overrides: dict) -> None:
    for key, value in overrides.items():
        if hasattr(ns, key):
            setattr(ns, key, _cast(value, getattr(ns, key)))


def install(callback: Callable[[dict], None], overrides: dict | None = None) -> None:
    global _original
    _state.update(callback=callback, overrides=overrides)
    if _original is not None:
        return
    _original = argparse.ArgumentParser.parse_known_args

    def patched(self, args=None, namespace=None):
        global _depth
        _depth += 1
        try:
            ns, extras = _original(self, args, namespace)
        finally:
            _depth -= 1
        if _depth == 0:
            if _state["overrides"]:
                apply_overrides(ns, _state["overrides"])
            if _state["callback"]:
                _state["callback"](_jsonable(vars(ns)))
        return ns, extras

    argparse.ArgumentParser.parse_known_args = patched


def uninstall() -> None:
    global _original
    if _original is not None:
        argparse.ArgumentParser.parse_known_args = _original
        _original = None
    _state.update(callback=None, overrides=None)

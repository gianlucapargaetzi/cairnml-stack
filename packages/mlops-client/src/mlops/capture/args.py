"""Capture (and optionally override) argparse results of the top-level parser."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Callable

_log = logging.getLogger(__name__)
_original = None
_depth = 0
_state: dict = {"callback": None, "overrides": None}


def _jsonable(values: dict) -> dict:
    return json.loads(json.dumps(values, default=str))


_SKIP = object()
_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")


def _cast(value, current):
    """Convert an override to the type of the parsed value, or return _SKIP.

    An override that cannot be converted, or whose parsed value is None or a
    list (no reliable type to cast to), is skipped so the parsed value stays.
    """
    if current is None or isinstance(current, (list, dict)):
        return _SKIP
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
        return _SKIP
    if isinstance(value, (list, dict)):
        return _SKIP
    try:
        return type(current)(value)
    except Exception:
        return _SKIP


def apply_overrides(target, overrides: dict) -> None:
    """Apply overrides to a parsed namespace, or to a dict in place.

    Only keys the target already has are considered. An override that cannot be
    converted to the type of the current value leaves that value unchanged.
    """
    is_dict = isinstance(target, dict)
    for key, value in overrides.items():
        if is_dict:
            if key not in target:
                continue
            current = target[key]
        elif hasattr(target, key):
            current = getattr(target, key)
        else:
            continue
        cast = _cast(value, current)
        if cast is _SKIP:
            continue
        if is_dict:
            target[key] = cast
        else:
            setattr(target, key, cast)


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
            # Capture must never break the user's program: a failing override
            # or callback is logged and the parsed namespace is returned as is.
            try:
                if _state["overrides"]:
                    apply_overrides(ns, _state["overrides"])
                if _state["callback"]:
                    _state["callback"](_jsonable(vars(ns)))
            except Exception:
                _log.debug("argument capture failed", exc_info=True)
        return ns, extras

    argparse.ArgumentParser.parse_known_args = patched


def uninstall() -> None:
    global _original
    if _original is not None:
        argparse.ArgumentParser.parse_known_args = _original
        _original = None
    _state.update(callback=None, overrides=None)

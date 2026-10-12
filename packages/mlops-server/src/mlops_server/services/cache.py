"""Small in-process TTL cache for read-only GitHub lookups."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class TtlCache:
    def __init__(self, ttl_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl, self._clock = ttl_s, clock
        self._items: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: Any, factory: Callable[[], Any]) -> Any:
        now = self._clock()
        with self._lock:
            hit = self._items.get(key)
            if hit and hit[0] > now:
                return hit[1]
        value = factory()
        with self._lock:
            self._items[key] = (now + self._ttl, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

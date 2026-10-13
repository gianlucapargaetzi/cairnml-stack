"""Small in-process TTL cache for read-only GitHub lookups."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class TtlCache:
    def __init__(
        self,
        ttl_s: float,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = 512,
    ) -> None:
        self._ttl, self._clock, self._max = ttl_s, clock, max_entries
        self._items: dict[Any, tuple[float, Any]] = {}  # insertion order: oldest first
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def _store(self, key: Any, value: Any, now: float) -> None:
        """Insert under the lock: drop expired entries, then the oldest beyond the cap."""
        with self._lock:
            for old_key in [k for k, (expires, _) in self._items.items() if expires <= now]:
                del self._items[old_key]
            self._items.pop(key, None)
            while len(self._items) >= self._max:
                del self._items[next(iter(self._items))]
            self._items[key] = (now + self._ttl, value)

    def get_or_set(
        self,
        key: Any,
        factory: Callable[[], Any],
        *,
        store_if: Callable[[Any], bool] = lambda value: True,
    ) -> Any:
        now = self._clock()
        with self._lock:
            hit = self._items.get(key)
            if hit and hit[0] > now:
                return hit[1]
        value = factory()
        if store_if(value):
            self._store(key, value, self._clock())
        return value

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

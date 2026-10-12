"""A write-through stream proxy that reports complete lines."""

from __future__ import annotations

import threading
from collections.abc import Callable


class TeeStream:
    def __init__(self, original, on_line: Callable[[str], None]) -> None:
        self._original = original
        self._on_line = on_line
        self._buffer = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> int:
        written = self._original.write(text)
        with self._lock:
            self._buffer += text
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                self._emit(line)
        return written if written is not None else len(text)

    def _emit(self, line: str) -> None:
        if line.endswith("\r"):  # CRLF line endings: the \r belongs to the terminator
            line = line[:-1]
        line = line.split("\r")[-1]  # progress updates: keep the last segment
        try:
            self._on_line(line)
        except Exception:  # logging must never break the user's program
            pass

    def flush_partial(self) -> None:
        with self._lock:
            if self._buffer:
                self._emit(self._buffer)
                self._buffer = ""

    def flush(self) -> None:
        self._original.flush()

    def __getattr__(self, name: str):
        return getattr(self._original, name)

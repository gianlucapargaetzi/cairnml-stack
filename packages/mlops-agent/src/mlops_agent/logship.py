"""Batches log lines and ships them to the server idempotently."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class LogShipper:
    def __init__(
        self,
        post: Callable[[str, int, list[dict]], None],
        stream: str,
        *,
        flush_s: float = 1.0,
        max_lines: int = 500,
        max_buffer: int = 100_000,
        sleep: Callable[[float], None] = time.sleep,
        scrub: Callable[[str], str] = lambda text: text,
    ) -> None:
        self._post = post
        self._stream = stream
        self._flush_s = flush_s
        self._max_lines = max_lines
        self._max_buffer = max_buffer
        self._sleep = sleep
        self._scrub = scrub
        self._buffer: deque[dict] = deque()
        self._dropped = 0  # lines dropped from the buffer and not yet reported
        self._seq = 0
        # A batch whose post has been attempted but not confirmed. It is resent
        # unchanged, with the same seq, until it succeeds; new lines never join it.
        self._inflight: tuple[int, list[dict]] | None = None
        self._inflight_reported = 0
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def write(self, line: str) -> None:
        entry = {"ts": time.time(), "text": self._scrub(line)}
        with self._lock:
            self._buffer.append(entry)
            while len(self._buffer) > self._max_buffer:
                self._buffer.popleft()
                self._dropped += 1

    def _take(self) -> tuple[list[dict], int]:
        """Return the next batch and the number of drops it reports.

        The drop note is prepended to the batch only, never to the buffer, so the
        buffer holds log lines alone and removal after a send stays exact.
        """
        with self._lock:
            reported = self._dropped
            items = list(self._buffer)
        if reported:
            note = {"ts": time.time(), "text": f"[mlops-agent: {reported} log lines dropped]"}
            return [note] + items[: self._max_lines - 1], reported
        return items[: self._max_lines], 0

    def _send(self, seq: int, batch: list[dict]) -> bool:
        for delay in (0.0, 0.5, 1.0, 2.0):
            if delay:
                self._sleep(delay)
            try:
                self._post(self._stream, seq, batch)
            except Exception:
                continue
            return True
        return False

    def _commit(self, batch: list[dict], reported: int) -> None:
        """Remove sent lines and the reported drop count after a successful post."""
        sent = {id(entry) for entry in batch}
        with self._lock:
            # Overflow may already have popped some sent lines from the front;
            # only remove entries that are still at the front and were sent.
            while self._buffer and id(self._buffer[0]) in sent:
                self._buffer.popleft()
            self._dropped -= reported

    def flush(self) -> None:
        with self._flush_lock:
            while True:
                if self._inflight is None:
                    batch, reported = self._take()
                    if not batch:
                        return
                    self._inflight = (self._seq, batch)
                    self._inflight_reported = reported
                seq, batch = self._inflight
                if not self._send(seq, batch):
                    return
                self._commit(batch, self._inflight_reported)
                self._inflight = None
                self._seq = seq + 1

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self._flush_s):
                self.flush()

        self._thread = threading.Thread(target=loop, name=f"logship-{self._stream}", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.flush()

"""Never-blocking delivery of metrics and log lines, with an on-disk fallback."""

from __future__ import annotations

import logging
import threading
import time

import httpx

from mlops.spool import Spool

log = logging.getLogger("mlops")
_TRANSIENT = (httpx.TransportError, OSError)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, _TRANSIENT)


def _send_event(api, experiment_id: str, kind: str, payload: dict) -> None:
    if kind == "metrics":
        api.post_metrics(experiment_id, payload["points"])
    elif kind == "logs":
        api.post_logs(experiment_id, payload["stream"], payload["seq"], payload["lines"])
    elif kind == "patch":
        api.patch_experiment(experiment_id, **payload["fields"])
    else:
        raise ValueError(f"unknown event kind {kind!r}")


def replay(spool: Spool, api, experiment_id: str) -> int:
    """Send spooled events in order. Returns the number the server accepted.

    Stops at the first transient failure and keeps the unsent tail. Artifact events
    are kept for `mlops sync`, in their original position.
    """
    pending = spool.events()
    sent = 0
    kept: list[dict] = []
    for index, event in enumerate(pending):
        if event["kind"] == "artifact":
            kept.append(event)  # handled by `mlops sync`
            continue
        try:
            _send_event(api, experiment_id, event["kind"], event["payload"])
        except Exception as exc:
            if _is_transient(exc):
                spool.rewrite(kept + pending[index:])
                return sent
            log.warning("dropping %s event that the server rejected: %s", event["kind"], exc)
            continue
        sent += 1
    spool.rewrite(kept)
    return sent


class Uplink:
    def __init__(
        self,
        api,
        experiment_id: str | None,
        spool: Spool,
        *,
        flush_s: float = 2.0,
        max_batch: int = 500,
    ) -> None:
        self._api = api
        self._exp = experiment_id
        self._spool = spool
        self._flush_s = flush_s
        self._max_batch = max_batch
        self._metrics: list[dict] = []
        self._lines: dict[str, list[dict]] = {"stdout": [], "stderr": []}
        self._seq = {"stdout": 0, "stderr": 0}
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.degraded = False

    def metric(
        self, name: str, value: float, step: int | None = None, ts: float | None = None
    ) -> None:
        with self._lock:
            self._metrics.append(
                {"name": name, "value": float(value), "step": step, "ts": ts or time.time()}
            )

    def log(self, stream: str, text: str) -> None:
        with self._lock:
            self._lines[stream].append({"ts": time.time(), "text": text})

    def _deliver(self, kind: str, payload: dict, *, direct: bool) -> None:
        if not direct or self._api is None or self._exp is None:
            self._spool.append(kind, payload)
            return
        try:
            _send_event(self._api, self._exp, kind, payload)
        except Exception as exc:
            if _is_transient(exc):
                self._spool.append(kind, payload)
                self.degraded = True
            else:
                log.warning("server rejected %s batch: %s", kind, exc)

    def _drain(self) -> bool:
        """Replay spooled events before any new ones. Returns True when nothing is left to send."""
        if self._api is None or self._exp is None or not self._spool.exists():
            return True
        if not self._spool.events():
            return True
        replay(self._spool, self._api, self._exp)
        drained = not any(e["kind"] != "artifact" for e in self._spool.events())
        if not drained:
            self.degraded = True
        return drained

    def flush(self) -> None:
        with self._flush_lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        # Must hold _flush_lock. Spooled events go first so they are never overtaken.
        direct = self._drain()
        with self._lock:
            metrics, self._metrics = self._metrics, []
            lines = {s: v for s, v in self._lines.items() if v}
            for stream in lines:
                self._lines[stream] = []
        for start in range(0, len(metrics), self._max_batch):
            self._deliver(
                "metrics", {"points": metrics[start : start + self._max_batch]}, direct=direct
            )
        for stream, items in lines.items():
            for start in range(0, len(items), self._max_batch):
                seq = self._seq[stream]
                self._seq[stream] += 1
                self._deliver(
                    "logs",
                    {
                        "stream": stream,
                        "seq": seq,
                        "lines": items[start : start + self._max_batch],
                    },
                    direct=direct,
                )

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(self._flush_s):
                try:
                    self.flush()
                except Exception:  # keep the thread alive; the next tick retries
                    log.warning("telemetry flush failed; retrying", exc_info=True)

        self._thread = threading.Thread(target=loop, name="mlops-uplink", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        with self._flush_lock:
            self._flush_locked()
            if self._api is not None and self._exp is not None and self._spool.events():
                replay(self._spool, self._api, self._exp)

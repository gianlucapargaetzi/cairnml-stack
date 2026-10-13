"""Polls for jobs, runs them concurrently, sends heartbeats."""

from __future__ import annotations

import logging
import threading
import time

from mlops_agent.api import AgentApi
from mlops_agent.config import AgentSettings
from mlops_agent.runner import JobRunner
from mlops_agent.usage import sample_usage

log = logging.getLogger("mlops_agent")

# Seconds to wait for running jobs to finish after a stop request.
_SHUTDOWN_GRACE_S = 30


def _backoff(failures: int) -> float:
    return min(30, 2**failures)


class AgentLoop:
    def __init__(
        self,
        api: AgentApi,
        runner: JobRunner,
        settings: AgentSettings,
        usage_fn=sample_usage,
    ) -> None:
        self._api = api
        self._runner = runner
        self._settings = settings
        self._usage_fn = usage_fn
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._sleep = time.sleep

    def running_ids(self) -> list[str]:
        with self._lock:
            return [job_id for job_id, t in self._threads.items() if t.is_alive()]

    def poll_once(self, wait_s: int | None = None) -> bool:
        wait = self._settings.poll_wait_s if wait_s is None else wait_s
        assignment = self._api.poll(self.running_ids(), wait)
        if assignment is None:
            return False

        def work() -> None:
            try:
                self._runner.run(assignment)
            except Exception:
                log.exception("job %s crashed the runner", assignment.job_id)

        thread = threading.Thread(target=work, name=f"job-{assignment.job_id}", daemon=True)
        with self._lock:
            self._threads[assignment.job_id] = thread
        thread.start()
        return True

    def heartbeat_once(self) -> None:
        try:
            usage = self._usage_fn()
        except Exception:
            log.warning("could not sample usage", exc_info=True)
            usage = None
        for job_id in self._api.heartbeat(self.running_ids(), None, usage):
            self._runner.cancel(job_id)

    def run_forever(self, stop: threading.Event) -> None:
        def beat() -> None:
            failures = 0
            while not stop.wait(
                self._settings.heartbeat_s if failures == 0 else _backoff(failures)
            ):
                try:
                    self.heartbeat_once()
                    failures = 0
                except Exception:
                    failures += 1
                    log.warning("heartbeat failed (%s in a row)", failures, exc_info=True)

        threading.Thread(target=beat, name="heartbeat", daemon=True).start()
        failures = 0
        while not stop.is_set():
            try:
                self.poll_once()
                failures = 0
            except Exception:
                failures += 1
                log.warning("poll failed (%s in a row)", failures, exc_info=True)
                self._sleep(_backoff(failures))
        for job_id in self.running_ids():
            self._runner.cancel(job_id)
        deadline = time.monotonic() + _SHUTDOWN_GRACE_S
        with self._lock:
            threads = list(self._threads.values())
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from mlops_common.schemas import JobSpec

from mlops_agent.config import AgentSettings

LogSink = Callable[[str], None]


@dataclass
class RunContext:
    job_id: str
    experiment_id: str
    spec: JobSpec
    root: Path  # job workspace root (mounted at /work)
    workdir: Path  # directory the command runs in
    env: dict[str, str]
    stdout: LogSink
    stderr: LogSink
    settings: AgentSettings


class BaseExecutor(ABC):
    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._lock = threading.Lock()  # guards _cancelled and _container together
        self._container = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled.set()
        self._kill()

    def _attach(self, container) -> None:
        """Register a started container; kill it at once if cancel() already ran."""
        with self._lock:
            self._container = container
            cancelled = self._cancelled.is_set()
        if cancelled:
            self._kill()

    def _detach(self) -> None:
        with self._lock:
            self._container = None

    def _kill(self) -> None:
        with self._lock:
            container = self._container
        if container is not None:
            try:
                container.kill()
            except Exception:  # already stopped or removed
                pass

    @abstractmethod
    def run(self, ctx: RunContext) -> int: ...

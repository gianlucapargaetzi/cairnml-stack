"""Fail jobs whose agent stopped sending heartbeats."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from mlops_server.db import utcnow
from mlops_server.models import Agent, Experiment, Job
from mlops_server.services.audit import record

log = logging.getLogger(__name__)


def reap_lost_agents(session: Session, now: datetime, timeout_s: int) -> list[str]:
    cutoff = now - timedelta(seconds=timeout_s)
    jobs = session.scalars(
        select(Job)
        .join(Agent, Agent.id == Job.agent_id)
        .where(
            Job.status.in_(("assigned", "running")),
            or_(Agent.last_seen.is_(None), Agent.last_seen < cutoff),
        )
    ).all()
    reaped = []
    for job in jobs:
        job.status = "failed"
        job.message = "agent lost contact"
        job.finished_at = now
        experiment = session.get(Experiment, job.experiment_id)
        if experiment.status not in ("finished", "failed", "cancelled"):
            experiment.status = "failed"
            experiment.finished_at = now
        record(session, "reaper", "job.reaped", None, job_id=job.id, agent_id=job.agent_id)
        reaped.append(job.id)
    return reaped


class ReaperThread:
    def __init__(self, session_factory, timeout_s: int, interval_s: int) -> None:
        self._factory = session_factory
        self._timeout = timeout_s
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="reaper", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                with self._factory() as session:
                    reaped = reap_lost_agents(session, utcnow(), self._timeout)
                    session.commit()
                if reaped:
                    log.warning("reaped jobs of lost agents: %s", reaped)
            except Exception:  # keep the loop alive
                log.exception("reaper iteration failed")

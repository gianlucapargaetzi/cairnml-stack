"""Fail jobs whose agent stopped sending heartbeats."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from mlops_server.db import utcnow
from mlops_server.models import Agent, Job, Run
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
        .with_for_update(of=Job, skip_locked=True)
    ).all()
    reaped = []
    for job in jobs:
        # Same lock order as set_status: job first, then run. A job whose agent
        # holds the row is skipped and picked up on the next pass.
        if job.status not in ("assigned", "running"):
            continue
        run = session.get(
            Run, job.run_id, with_for_update=True, populate_existing=True
        )
        job.status = "failed"
        job.message = "agent lost contact"
        job.finished_at = now
        if run.status not in ("finished", "failed", "cancelled"):
            run.status = "failed"
            run.finished_at = now
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

"""Resource-matching job assignment on top of the jobs table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from mlops_server.models import Agent, Job

ACTIVE = ("assigned", "running")
PAGE_SIZE = 50


@dataclass(frozen=True)
class Free:
    cpu: int
    memory_gb: float
    gpu: int


def free_resources(session: Session, agent: Agent) -> Free:
    used = session.execute(
        select(
            func.coalesce(func.sum(Job.cpu), 0),
            func.coalesce(func.sum(Job.memory_gb), 0.0),
            func.coalesce(func.sum(Job.gpu), 0),
        ).where(Job.agent_id == agent.id, Job.status.in_(ACTIVE))
    ).one()
    caps = agent.capabilities
    return Free(
        cpu=caps["cpu"] - int(used[0]),
        memory_gb=caps["memory_gb"] - float(used[1]),
        gpu=caps.get("gpus", 0) - int(used[2]),
    )


def fits(job: Job, free: Free, capabilities: dict) -> bool:
    return (
        job.cpu <= free.cpu
        and job.memory_gb <= free.memory_gb
        and job.gpu <= free.gpu
        and set(job.labels) <= set(capabilities.get("labels", []))
        and job.spec["runtime"]["type"] in capabilities.get("runtimes", [])
    )


def claim_next(session: Session, agent: Agent) -> Job | None:
    # Lock the agent row first so overlapping polls from one agent serialise, then read its
    # free capacity under that lock.
    locked = session.scalar(
        select(Agent)
        .where(Agent.id == agent.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        return None
    free = free_resources(session, locked)
    cursor: tuple[datetime, str] | None = None
    while True:
        query = select(Job).where(Job.status == "queued", Job.queue.in_(locked.queues))
        if cursor is not None:
            query = query.where(
                or_(
                    Job.created_at > cursor[0],
                    and_(Job.created_at == cursor[0], Job.id > cursor[1]),
                )
            )
        page = session.scalars(query.order_by(Job.created_at, Job.id).limit(PAGE_SIZE)).all()
        if not page:
            return None
        for candidate in page:
            if not fits(candidate, free, locked.capabilities):
                continue
            # Lock only the chosen row; scanned rows stay unlocked for other agents.
            job = session.scalar(
                select(Job)
                .where(Job.id == candidate.id, Job.status == "queued")
                .with_for_update(skip_locked=True)
            )
            if job is None:
                continue  # taken by another poll since the scan
            job.status = "assigned"
            job.agent_id = locked.id
            job.assigned_at = datetime.now(UTC)
            return job
        if len(page) < PAGE_SIZE:
            return None
        cursor = (page[-1].created_at, page[-1].id)


def cancellations(session: Session, agent: Agent, running_job_ids: list[str]) -> list[str]:
    out = []
    for job_id in running_job_ids:
        job = session.get(Job, job_id)
        if (
            job is None
            or job.agent_id != agent.id
            or job.status not in ACTIVE
            or job.cancel_requested
        ):
            out.append(job_id)
    return out

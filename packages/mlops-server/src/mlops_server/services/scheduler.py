"""Resource-matching job assignment on top of the jobs table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mlops_server.models import Agent, Job

ACTIVE = ("assigned", "running")


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
    free = free_resources(session, agent)
    candidates = session.scalars(
        select(Job)
        .where(Job.status == "queued", Job.queue.in_(agent.queues))
        .order_by(Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(50)
    ).all()
    for job in candidates:
        if fits(job, free, agent.capabilities):
            job.status = "assigned"
            job.agent_id = agent.id
            job.assigned_at = datetime.now(UTC)
            return job
    return None


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

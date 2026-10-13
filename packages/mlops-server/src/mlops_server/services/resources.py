"""Agent capacity, usage and queue statistics for the resources view."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Agent, Job, Project, Run
from mlops_server.services import scheduler


def _online(agent: Agent, now: datetime, timeout_s: int) -> bool:
    return bool(agent.last_seen and agent.last_seen >= now - timedelta(seconds=timeout_s))


def agents_status(
    session: Session,
    timeout_s: int,
    now: datetime | None = None,
    visible_projects: set[str] | None = None,
) -> list[dict]:
    """Every active agent. `visible_projects` limits the running jobs listed (None: all)."""
    now = now or datetime.now(UTC)
    out = []
    for agent in session.scalars(
        select(Agent).where(Agent.revoked_at.is_(None)).order_by(Agent.name)
    ):
        free = scheduler.free_resources(session, agent)
        running = session.execute(
            select(Job.id, Job.project_id, Run.name, Project.slug)
            .join(Run, Run.id == Job.run_id)
            .join(Project, Project.id == Job.project_id)
            .where(Job.agent_id == agent.id, Job.status.in_(scheduler.ACTIVE))
            .order_by(Job.created_at, Job.id)
        ).all()
        listed = [
            {"id": job_id, "run_name": name, "project": slug}
            for job_id, project_id, name, slug in running
            if visible_projects is None or project_id in visible_projects
        ]
        out.append({
            "id": agent.id,
            "name": agent.name,
            "queues": agent.queues,
            "capabilities": agent.capabilities,
            "online": _online(agent, now, timeout_s),
            "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
            "free": {"cpu": free.cpu, "memory_gb": free.memory_gb, "gpu": free.gpu},
            "usage": agent.usage,
            "usage_at": agent.usage_at.isoformat() if agent.usage_at else None,
            "running_jobs": listed,
            # Jobs in projects the caller cannot see, as a count only (no names or slugs).
            "other_running_jobs": len(running) - len(listed),
        })
    return out


def queue_stats(session: Session, agents: list[dict], now: datetime | None = None) -> list[dict]:
    """Per queue: queued and running jobs, online agents serving it, oldest queued wait."""
    now = now or datetime.now(UTC)
    jobs = session.scalars(
        select(Job).where(Job.status.in_(("queued", *scheduler.ACTIVE)))
    ).all()
    names = {q for a in agents for q in a["queues"]} | {j.queue for j in jobs}
    stats = []
    for name in sorted(names):
        in_queue = [j for j in jobs if j.queue == name]
        queued = [j for j in in_queue if j.status == "queued"]
        stats.append({
            "name": name,
            "queued": len(queued),
            "running": len(in_queue) - len(queued),
            "agents": sum(1 for a in agents if a["online"] and name in a["queues"]),
            "oldest_wait_s": (
                int((now - min(j.created_at for j in queued)).total_seconds()) if queued else None
            ),
        })
    return stats

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mlops_server.models import Agent, Experiment, Job, Project
from mlops_server.routers.experiments import experiment_out
from mlops_server.security.deps import READERS, Principal, get_session, require
from mlops_server.services import access

router = APIRouter()


@router.get("/overview")
def overview(
    request: Request,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    projects = [
        p
        for p in session.scalars(select(Project).order_by(Project.slug))
        if access.is_member(session, principal, p)
    ]
    ids = [p.id for p in projects]
    jobs = dict(
        session.execute(
            select(Job.status, func.count()).where(Job.project_id.in_(ids)).group_by(Job.status)
        ).all()
    )
    per_project = {
        project_id: (count, running, last)
        for project_id, count, running, last in session.execute(
            select(
                Experiment.project_id,
                func.count(),
                func.count().filter(Experiment.status == "running"),
                func.max(Experiment.created_at),
            )
            .where(Experiment.project_id.in_(ids))
            .group_by(Experiment.project_id)
        )
    }
    cutoff = datetime.now(UTC) - timedelta(seconds=request.app.state.settings.agent_timeout)
    agents = session.scalars(select(Agent).where(Agent.revoked_at.is_(None))).all()
    recent = session.scalars(
        select(Experiment)
        .where(Experiment.project_id.in_(ids))
        .order_by(Experiment.created_at.desc(), Experiment.id.desc())
        .limit(10)
    )
    return {
        "jobs": jobs,
        "experiments_running": sum(running for _, running, _ in per_project.values()),
        "agents": {
            "online": sum(1 for a in agents if a.last_seen and a.last_seen >= cutoff),
            "total": len(agents),
        },
        "projects": [
            {
                "slug": p.slug,
                "name": p.name,
                "experiments": per_project.get(p.id, (0, 0, None))[0],
                "running": per_project.get(p.id, (0, 0, None))[1],
                "last_activity": (
                    per_project[p.id][2].isoformat() if p.id in per_project else None
                ),
            }
            for p in projects
        ],
        "recent": [experiment_out(session, e).model_dump(mode="json") for e in recent],
    }

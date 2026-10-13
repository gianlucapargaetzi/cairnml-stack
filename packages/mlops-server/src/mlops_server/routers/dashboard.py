from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from mlops_server.models import Agent, Experiment, Job, Project, ProjectRepo, Task, User
from mlops_server.routers.experiments import experiment_out
from mlops_server.routers.tasks import load_task, task_out
from mlops_server.security.deps import READERS, Principal, get_session, require
from mlops_server.services import access, resources
from mlops_server.services.task_stats import last_values, task_stats

router = APIRouter()
JOB_WINDOW = 2000  # the overview derives job counts and containers from the newest jobs only
SUMMARY_WINDOW = 200  # a task summary lists its newest experiments only


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


def _container_name(runtime: dict) -> tuple[str, str]:
    kind = runtime["type"]
    if kind == "image":
        return kind, runtime["image"]
    if kind == "python":
        return kind, f"python:{runtime.get('python')}"
    return kind, runtime.get("file", "compose.yaml")


def _containers(jobs: list[Job]) -> list[dict]:
    """Distinct images, Python versions and compose files used by `jobs` (newest first)."""
    found: dict[tuple[str, str], dict] = {}
    for job in jobs:
        kind, name = _container_name(job.spec["runtime"])
        entry = found.setdefault(
            (kind, name),
            {
                "kind": kind,
                "name": name,
                "jobs": 0,
                "last_used": job.created_at,
                "last_status": job.status,
            },
        )
        entry["jobs"] += 1
    rows = sorted(found.values(), key=lambda e: e["last_used"], reverse=True)
    for row in rows:
        row["last_used"] = row["last_used"].isoformat()
    return rows


@router.get("/projects/overview")
def project_overview(
    project: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    proj = access.ensure_member(session, principal, project)
    tasks = session.scalars(
        select(Task).where(Task.project_id == proj.id).order_by(Task.name)
    ).all()
    stats = task_stats(session, tasks)
    jobs = list(
        session.scalars(
            select(Job)
            .where(Job.project_id == proj.id)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(JOB_WINDOW)
        )
    )
    total, running = session.execute(
        select(func.count(), func.count().filter(Experiment.status == "running")).where(
            Experiment.project_id == proj.id
        )
    ).one()
    recent = session.scalars(
        select(Experiment)
        .where(Experiment.project_id == proj.id)
        .order_by(Experiment.created_at.desc(), Experiment.id.desc())
        .limit(8)
    )
    repos = session.scalars(
        select(ProjectRepo).where(ProjectRepo.project_id == proj.id).order_by(ProjectRepo.repo)
    )
    return {
        "project": {
            "slug": proj.slug,
            "name": proj.name,
            "created_at": proj.created_at.isoformat(),
        },
        "repos": [{"repo": r.repo, "role": r.role} for r in repos],
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "kind": t.kind,
                "description": t.description,
                "primary_metric": t.primary_metric,
                "direction": t.direction,
                **stats[t.id],
            }
            for t in tasks
        ],
        "containers": _containers(jobs),
        "counts": {
            "experiments": total,
            "running": running,
            "jobs": dict(Counter(job.status for job in jobs)),
        },
        "recent": [experiment_out(session, e).model_dump(mode="json") for e in recent],
    }


@router.get("/tasks/{task_id}/summary")
def task_summary(
    task_id: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    task = load_task(session, principal, task_id)
    stats = task_stats(session, [task])[task.id]
    experiments = session.scalars(
        select(Experiment)
        .where(Experiment.task_id == task.id)
        .order_by(Experiment.created_at.desc(), Experiment.id.desc())
        .limit(SUMMARY_WINDOW)
    ).all()
    values = (
        last_values(session, [e.id for e in experiments], task.primary_metric)
        if task.primary_metric
        else {}
    )
    owner_ids = list({e.owner_id for e in experiments})
    owners = (
        {u.id: u.username for u in session.scalars(select(User).where(User.id.in_(owner_ids)))}
        if owner_ids
        else {}
    )
    rows = []
    for e in experiments:
        git = e.git or {}
        args = (e.params or {}).get("args") or {}
        params = {k: v for k, v in (e.params or {}).items() if k != "args"}
        rows.append(
            {
                "id": e.id,
                "name": e.name,
                "status": e.status,
                "owner": owners.get(e.owner_id),
                "created_at": e.created_at.isoformat(),
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "finished_at": e.finished_at.isoformat() if e.finished_at else None,
                "commit": git.get("commit"),
                "dirty": bool(git.get("dirty")),
                "primary_value": values.get(e.id),
                "params": {**(e.config or {}), **params, **args},
            }
        )
    return {
        "task": task_out(session, task).model_dump(mode="json"),
        "stats": stats,
        "experiments": rows,
    }


@router.get("/resources")
def get_resources(
    request: Request,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    # Visible to every authenticated reader. Running jobs are named only for projects the caller
    # belongs to (admins: all); other projects appear as anonymous counts. Never key material.
    visible = {
        p.id for p in session.scalars(select(Project))
        if access.is_member(session, principal, p)
    }
    agents = resources.agents_status(
        session, request.app.state.settings.agent_timeout, visible_projects=visible
    )
    return {"agents": agents, "queues": resources.queue_stats(session, agents)}

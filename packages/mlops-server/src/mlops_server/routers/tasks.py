from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from mlops_common.schemas import TaskCreate, TaskOut, TaskPatch
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Project, Task
from mlops_server.security.deps import READERS, Principal, get_session, require
from mlops_server.services import access

router = APIRouter()


def task_out(session: Session, task: Task) -> TaskOut:
    return TaskOut(
        id=task.id, project=session.get(Project, task.project_id).slug, name=task.name,
        kind=task.kind, description=task.description, primary_metric=task.primary_metric,
        direction=task.direction, created_at=task.created_at,
    )


def load_task(session: Session, principal: Principal, task_id: str) -> Task:
    task = session.get(Task, task_id)
    project = session.get(Project, task.project_id) if task else None
    if task is None or not access.is_member(session, principal, project):
        raise HTTPException(404, "task not found")
    return task


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
    project: str | None = None,
):
    if project:
        ids = [access.ensure_member(session, principal, project).id]
    else:
        projects = session.scalars(select(Project))
        ids = [p.id for p in projects if access.is_member(session, principal, p)]
    rows = session.scalars(select(Task).where(Task.project_id.in_(ids)).order_by(Task.name))
    return [task_out(session, t) for t in rows]


@router.post("/tasks", response_model=TaskOut)
def create_task(
    body: TaskCreate,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
):
    project = access.ensure_member(session, principal, body.project)
    task = Task(
        id=new_id("tsk"), project_id=project.id, name=body.name, kind=body.kind,
        description=body.description, primary_metric=body.primary_metric,
        direction=body.direction,
    )
    session.add(task)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "task already exists") from None
    return task_out(session, task)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
):
    return task_out(session, load_task(session, principal, task_id))


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def patch_task(
    task_id: str,
    body: TaskPatch,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
):
    task = load_task(session, principal, task_id)
    for name, value in body.model_dump(exclude_unset=True).items():
        if name == "kind" and value is None:
            continue  # the kind is required; an explicit null leaves it as it is
        setattr(task, name, value)
    session.commit()
    return task_out(session, task)

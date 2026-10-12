from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from mlops_common.schemas import MemberAdd, ProjectCreate, ProjectOut
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Project, ProjectMember, User
from mlops_server.security.deps import Principal, get_session, require
from mlops_server.services import access, audit

router = APIRouter()


@router.post("/projects", response_model=ProjectOut)
def create_project(
    body: ProjectCreate,
    request: Request,
    principal: Annotated[Principal, Depends(require("client", admin=True))],
    session: Annotated[Session, Depends(get_session)],
) -> ProjectOut:
    session.add(Project(id=new_id("prj"), slug=body.slug, name=body.name))
    audit.record(session, principal.id, "project.created", request, slug=body.slug)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "project already exists") from None
    return ProjectOut(slug=body.slug, name=body.name)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
) -> list[ProjectOut]:
    projects = session.scalars(select(Project).order_by(Project.slug)).all()
    return [
        ProjectOut(slug=p.slug, name=p.name)
        for p in projects
        if access.is_member(session, principal, p)
    ]


@router.post("/project-members")
def add_member(
    body: MemberAdd,
    request: Request,
    principal: Annotated[Principal, Depends(require("client", admin=True))],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, bool]:
    project = access.get_project(session, body.project)
    user = session.scalar(select(User).where(User.username == body.username))
    if user is None:
        raise HTTPException(404, "user not found")
    if session.get(ProjectMember, (project.id, user.id)) is None:
        session.add(ProjectMember(project_id=project.id, user_id=user.id))
        audit.record(
            session, principal.id, "project.member_added", request,
            project=project.slug, user=user.id,
        )
        session.commit()
    return {"added": True}

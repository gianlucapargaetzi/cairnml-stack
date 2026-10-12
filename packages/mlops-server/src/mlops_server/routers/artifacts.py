from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from mlops_common.schemas import ArtifactOut, ArtifactRegister, PresignRequest, PresignResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Artifact, Project
from mlops_server.security.deps import Principal, get_session, require
from mlops_server.services import access
from mlops_server.services.storage import safe_artifact_name

router = APIRouter()
any_principal = require("client", "agent", "run")
PRESIGN_EXPIRES = 3600


def _storage(request: Request):
    if request.app.state.storage is None:
        raise HTTPException(503, "storage is not configured")
    return request.app.state.storage


def _prefix(session: Session, exp) -> str:
    return f"{session.get(Project, exp.project_id).slug}/{exp.id}/"


def _checked_name(name: str) -> str:
    try:
        return safe_artifact_name(name)
    except ValueError:
        raise HTTPException(422, "invalid artifact name") from None


@router.post("/experiments/{experiment_id}/artifacts/presign", response_model=PresignResponse)
def presign(
    experiment_id: str,
    body: PresignRequest,
    request: Request,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    exp = access.load_experiment(session, principal, experiment_id, True)
    key = _prefix(session, exp) + _checked_name(body.name)
    return PresignResponse(
        upload_url=_storage(request).presign_put(key, PRESIGN_EXPIRES),
        key=key,
        expires_in=PRESIGN_EXPIRES,
    )


@router.post("/experiments/{experiment_id}/artifacts", response_model=ArtifactOut)
def register(
    experiment_id: str,
    body: ArtifactRegister,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    exp = access.load_experiment(session, principal, experiment_id, True)
    name = _checked_name(body.name)
    if body.key != _prefix(session, exp) + name:
        raise HTTPException(422, "artifact key must be <project>/<experiment>/<name>")
    artifact = Artifact(
        id=new_id("art"),
        experiment_id=exp.id,
        name=name,
        key=body.key,
        size=body.size,
        kind=body.kind,
        meta=body.meta,
    )
    session.add(artifact)
    session.commit()
    return ArtifactOut(
        id=artifact.id,
        name=name,
        key=artifact.key,
        size=artifact.size,
        kind=artifact.kind,
        meta=artifact.meta,
    )


@router.get("/experiments/{experiment_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(
    experiment_id: str,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    access.load_experiment(session, principal, experiment_id, False)
    rows = session.scalars(
        select(Artifact)
        .where(Artifact.experiment_id == experiment_id)
        .order_by(Artifact.created_at)
    )
    return [
        ArtifactOut(id=a.id, name=a.name, key=a.key, size=a.size, kind=a.kind, meta=a.meta)
        for a in rows
    ]


@router.get("/experiments/{experiment_id}/artifacts/{artifact_id}/download")
def download(
    experiment_id: str,
    artifact_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    access.load_experiment(session, principal, experiment_id, False)
    artifact = session.get(Artifact, artifact_id)
    if artifact is None or artifact.experiment_id != experiment_id:
        raise HTTPException(404, "artifact not found")
    return {"url": _storage(request).presign_get(artifact.key, PRESIGN_EXPIRES)}

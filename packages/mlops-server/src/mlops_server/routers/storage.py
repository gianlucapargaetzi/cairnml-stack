from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from mlops_common.schemas import StsRequest, StsResponse
from sqlalchemy.orm import Session

from mlops_server.security.deps import Principal, get_session, require
from mlops_server.services import access, audit

router = APIRouter()


@router.post("/storage/sts", response_model=StsResponse)
def client_sts(
    body: StsRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
):
    project = access.ensure_member(session, principal, body.project)
    storage = request.app.state.storage
    if storage is None:
        raise HTTPException(503, "storage is not configured")
    creds = storage.sts_credentials(project.slug, body.write)
    audit.record(
        session, principal.id, "sts.issued", request, project=project.slug, write=body.write
    )
    session.commit()
    return creds

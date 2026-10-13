"""Sequence ingestion: presigned uploads for image and audio blobs, and registration of items.

Runs, clients and agents may write; a run token may write its own run (access.load_run decides).
Text, figure and distribution items are registered with their value and need no upload."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from mlops_common.schemas import SequenceBatch, SequencePresignRequest, SequencePresignResponse
from sqlalchemy.orm import Session

from mlops_server.models import Project
from mlops_server.security.deps import Principal, get_session, require
from mlops_server.services import access
from mlops_server.services.sequences import blob_key, write_items

router = APIRouter()
any_principal = require("client", "agent", "run")
PRESIGN_EXPIRES = 3600


def _storage(request: Request):
    if request.app.state.storage is None:
        raise HTTPException(503, "storage is not configured")
    return request.app.state.storage


@router.post("/runs/{run_id}/sequences/presign", response_model=SequencePresignResponse)
def presign(
    run_id: str,
    body: SequencePresignRequest,
    request: Request,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    run = access.load_run(session, principal, run_id, True)
    project = session.get(Project, run.project_id)
    try:
        key = blob_key(project.slug, run.id, body.kind, body.name, body.context, body.step,
                       body.idx, body.format)
    except ValueError:
        raise HTTPException(422, "invalid sequence name") from None
    return SequencePresignResponse(
        upload_url=_storage(request).presign_put(key, PRESIGN_EXPIRES),
        key=key,
        expires_in=PRESIGN_EXPIRES,
    )


@router.post("/runs/{run_id}/sequences")
def register(
    run_id: str,
    body: SequenceBatch,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    run = access.load_run(session, principal, run_id, True)
    project = session.get(Project, run.project_id)
    return {"accepted": write_items(session, run, project.slug, body.items)}

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from mlops_common.schemas import AgentTokenRequest, AgentTokenResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Agent, Client, EnrollmentToken
from mlops_server.security.deps import READERS, Principal, get_session, require
from mlops_server.services import audit
from mlops_server.services.user_sync import sync_users

router = APIRouter(prefix="/admin")
admin_only = require("client", admin=True)
admin_reader = require(*READERS, admin=True)


@router.post("/agent-tokens", response_model=AgentTokenResponse)
def create_agent_token(
    body: AgentTokenRequest,
    request: Request,
    principal: Annotated[Principal, Depends(admin_only)],
    session: Annotated[Session, Depends(get_session)],
) -> AgentTokenResponse:
    token = "mlops_at_" + secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(seconds=body.ttl)
    row = EnrollmentToken(
        id=new_id("tok"),
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        queues=list(body.queues),
        created_by=principal.user_id,
        expires_at=expires_at,
    )
    session.add(row)
    audit.record(
        session, principal.id, "agent_token.created", request, token_id=row.id, queues=body.queues
    )
    session.commit()
    return AgentTokenResponse(token=token, expires_at=expires_at)


@router.get("/clients")
def list_clients(
    _: Annotated[Principal, Depends(admin_reader)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    rows = session.scalars(select(Client).order_by(Client.created_at)).all()
    return [
        {"id": r.id, "name": r.name, "user_id": r.user_id, "revoked": r.revoked_at is not None}
        for r in rows
    ]


@router.get("/agents")
def list_agents(
    _: Annotated[Principal, Depends(admin_reader)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    rows = session.scalars(select(Agent).order_by(Agent.created_at)).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "queues": r.queues,
            "capabilities": r.capabilities,
            "revoked": r.revoked_at is not None,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
        }
        for r in rows
    ]


def _revoke(model, row_id: str, principal: Principal, request: Request, session: Session) -> dict:
    row = session.get(model, row_id)
    if row is None:
        raise HTTPException(404, "not found")
    row.revoked_at = datetime.now(UTC)
    audit.record(session, principal.id, f"{model.__tablename__}.revoked", request, target=row_id)
    session.commit()
    return {"revoked": True}


@router.post("/clients/{client_id}/revoke")
def revoke_client(
    client_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(admin_only)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    return _revoke(Client, client_id, principal, request, session)


@router.post("/agents/{agent_id}/revoke")
def revoke_agent(
    agent_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(admin_only)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    return _revoke(Agent, agent_id, principal, request, session)


@router.post("/sync-users")
def trigger_user_sync(
    request: Request,
    principal: Annotated[Principal, Depends(admin_only)],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    directory = request.app.state.directory
    if directory is None:
        raise HTTPException(503, "no IdP directory configured (set MLOPS_IDP_SYNC_CLIENT_SECRET)")
    report = sync_users(session, directory)
    audit.record(session, principal.id, "user_sync.triggered", request,
                 disabled=len(report.disabled))
    session.commit()
    return report.as_dict()

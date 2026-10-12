from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from mlops_common.keys import load_public_key
from mlops_common.schemas import (
    AgentEnrollRequest,
    AgentEnrollResponse,
    ClientEnrollRequest,
    ClientEnrollResponse,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Agent, Client, EnrollmentToken
from mlops_server.security.deps import get_session
from mlops_server.security.oidc import OidcError
from mlops_server.services import audit
from mlops_server.services.users import upsert_user

router = APIRouter(prefix="/enroll")


@router.post("/client", response_model=ClientEnrollResponse)
def enroll_client(
    body: ClientEnrollRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    authorization: str = Header(default=""),
) -> ClientEnrollResponse:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "IdP login required")
    try:
        identity = request.app.state.oidc.verify(
            authorization[7:].strip(), clients=[request.app.state.settings.oidc_client_id]
        )
    except OidcError:
        raise HTTPException(401, "invalid IdP token") from None
    try:
        load_public_key(body.public_key)
    except ValueError:
        raise HTTPException(422, "public_key must be an Ed25519 PEM public key") from None

    user = upsert_user(session, identity)
    if user.disabled:
        raise HTTPException(403, "user is disabled")
    # Client has no relationship() to User, so flush the user row before the FK insert.
    session.flush()
    client = Client(id=new_id("cli"), user_id=user.id, name=body.name, public_key=body.public_key)
    session.add(client)
    audit.record(session, user.id, "client.enrolled", request, client_id=client.id, name=body.name)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "this public key is already enrolled") from None
    return ClientEnrollResponse(client_id=client.id, user_id=user.id, username=user.username)


@router.post("/agent", response_model=AgentEnrollResponse)
def enroll_agent(
    body: AgentEnrollRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> AgentEnrollResponse:
    digest = hashlib.sha256(body.token.encode()).hexdigest()
    token = session.scalar(
        select(EnrollmentToken).where(EnrollmentToken.token_hash == digest).with_for_update()
    )
    now = datetime.now(UTC)
    if token is None or token.used_at is not None or token.expires_at < now:
        raise HTTPException(401, "invalid or expired enrollment token")
    try:
        load_public_key(body.public_key)
    except ValueError:
        raise HTTPException(422, "public_key must be an Ed25519 PEM public key") from None
    agent = Agent(
        id=new_id("agt"),
        name=body.name,
        public_key=body.public_key,
        capabilities=body.capabilities.model_dump(),
        queues=list(token.queues),
    )
    token.used_at = now
    session.add(agent)
    audit.record(session, agent.id, "agent.enrolled", request, token_id=token.id, name=body.name)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "this public key is already enrolled") from None
    return AgentEnrollResponse(agent_id=agent.id, queues=agent.queues)

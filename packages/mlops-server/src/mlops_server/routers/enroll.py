from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from mlops_common.keys import load_public_key
from mlops_common.schemas import ClientEnrollRequest, ClientEnrollResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import Client, User
from mlops_server.security.deps import get_session
from mlops_server.security.oidc import OidcError
from mlops_server.services import audit

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
        identity = request.app.state.oidc.verify(authorization[7:].strip())
    except OidcError:
        raise HTTPException(401, "invalid IdP token") from None
    try:
        load_public_key(body.public_key)
    except ValueError:
        raise HTTPException(422, "public_key must be an Ed25519 PEM public key") from None

    user = session.scalar(select(User).where(User.idp_subject == identity.subject))
    if user is not None and user.disabled:
        raise HTTPException(403, "user is disabled")
    if user is None:
        user = User(
            id=new_id("usr"),
            idp_subject=identity.subject,
            username=identity.username,
            roles=list(identity.roles),
        )
        session.add(user)
    else:
        user.username = identity.username
        user.roles = list(identity.roles)
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

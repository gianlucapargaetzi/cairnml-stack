from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from mlops_common.assertion import AssertionInvalid, unverified_issuer, verify_assertion
from mlops_common.keys import load_public_key
from mlops_common.schemas import TokenRequest, TokenResponse
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.models import Agent, Client, UsedJti
from mlops_server.security.deps import get_session
from mlops_server.services import audit

router = APIRouter()


def _deny() -> HTTPException:
    return HTTPException(401, "invalid credentials")


@router.post("/auth/token", response_model=TokenResponse)
def exchange(
    body: TokenRequest, request: Request, session: Annotated[Session, Depends(get_session)]
) -> TokenResponse:
    settings = request.app.state.settings
    try:
        issuer = unverified_issuer(body.assertion)
    except AssertionInvalid:
        raise _deny() from None
    if issuer.startswith("cli_"):
        row, kind = session.get(Client, issuer), "client"
    elif issuer.startswith("agt_"):
        row, kind = session.get(Agent, issuer), "agent"
    else:
        raise _deny()
    if row is None or row.revoked_at is not None:
        raise _deny()
    try:
        claims = verify_assertion(
            body.assertion, load_public_key(row.public_key), audience=settings.public_url
        )
    except (AssertionInvalid, ValueError):
        raise _deny() from None

    now = datetime.now(UTC)
    session.execute(delete(UsedJti).where(UsedJti.expires_at < now))
    session.add(
        UsedJti(jti=claims["jti"], expires_at=datetime.fromtimestamp(claims["exp"] + 60, UTC))
    )
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise _deny() from None

    uid = row.user_id if kind == "client" else None
    token, expires_in = request.app.state.tokens.issue(row.id, kind, uid=uid)
    audit.record(session, row.id, "token.issued", request, kind=kind)
    session.commit()
    return TokenResponse(access_token=token, expires_in=expires_in)

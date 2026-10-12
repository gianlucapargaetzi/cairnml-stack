from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from mlops_server.models import AuditEvent


def record(
    session: Session,
    actor: str,
    action: str,
    request: Request | None = None,
    **detail,
) -> None:
    ip = request.client.host if request is not None and request.client else None
    session.add(AuditEvent(actor=actor, action=action, detail=detail, ip=ip))

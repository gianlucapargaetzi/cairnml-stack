from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from mlops_common.schemas import (
    HeartbeatRequest,
    HeartbeatResponse,
    JobAssignment,
    JobSpec,
    PollRequest,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Agent, Project
from mlops_server.security.deps import READERS, Principal, get_session, require
from mlops_server.services import access, resources, scheduler

router = APIRouter(prefix="/agents")
agent_only = require("agent")


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    body: HeartbeatRequest,
    principal: Annotated[Principal, Depends(agent_only)],
    session: Annotated[Session, Depends(get_session)],
):
    agent = session.get(Agent, principal.id)
    now = datetime.now(UTC)
    agent.last_seen = now
    if body.capabilities is not None:
        agent.capabilities = body.capabilities.model_dump()
    if body.usage is not None:
        agent.usage, agent.usage_at = body.usage.model_dump(), now
    cancel = scheduler.cancellations(session, agent, body.running_job_ids)
    session.commit()
    return HeartbeatResponse(cancel_job_ids=cancel)


@router.post("/poll", response_model=JobAssignment, responses={204: {"description": "no job"}})
def poll(
    body: PollRequest,
    request: Request,
    principal: Annotated[Principal, Depends(agent_only)],
    session: Annotated[Session, Depends(get_session)],
):
    session.close()  # do not hold a connection while long-polling
    deadline = time.monotonic() + body.wait_s
    while True:
        with request.app.state.session_factory() as s:
            agent = s.get(Agent, principal.id)
            agent.last_seen = datetime.now(UTC)
            job = scheduler.claim_next(s, agent)
            if job is not None:
                s.commit()
                return JobAssignment(
                    job_id=job.id,
                    experiment_id=job.experiment_id,
                    spec=JobSpec.model_validate(job.spec),
                )
            s.commit()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return Response(status_code=204)
        time.sleep(min(1.0, remaining))


@router.get("/status")
def agent_status(
    request: Request,
    principal: Annotated[Principal, Depends(require(*READERS))],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict]:
    visible = {
        p.id for p in session.scalars(select(Project))
        if access.is_member(session, principal, p)
    }
    return resources.agents_status(
        session, request.app.state.settings.agent_timeout, visible_projects=visible
    )

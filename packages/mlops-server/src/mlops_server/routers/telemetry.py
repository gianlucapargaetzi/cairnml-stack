from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from mlops_common.schemas import LogBatch, MetricBatch
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mlops_server.models import LogChunk, MetricPoint
from mlops_server.security.deps import Principal, get_session, require
from mlops_server.services import access

router = APIRouter()
any_principal = require("client", "agent", "run")
MAX_LINE = 16_384
MAX_BATCH_CHARS = 2_000_000
TRUNCATED_SUFFIX = "... [truncated]"


@router.post("/experiments/{experiment_id}/metrics")
def post_metrics(
    experiment_id: str,
    body: MetricBatch,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    access.load_experiment(session, principal, experiment_id, True)
    session.add_all(
        MetricPoint(experiment_id=experiment_id, name=p.name, step=p.step, value=p.value, ts=p.ts)
        for p in body.points
    )
    session.commit()
    return {"accepted": len(body.points)}


@router.post("/experiments/{experiment_id}/logs")
def post_logs(
    experiment_id: str,
    body: LogBatch,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    access.load_experiment(session, principal, experiment_id, True)
    if sum(len(line.text) for line in body.lines) > MAX_BATCH_CHARS:
        raise HTTPException(413, "log batch too large")
    lines = [
        {
            "ts": line.ts,
            "text": line.text
            if len(line.text) <= MAX_LINE
            else line.text[:MAX_LINE] + TRUNCATED_SUFFIX,
        }
        for line in body.lines
    ]
    statement = (
        insert(LogChunk)
        .values(
            experiment_id=experiment_id,
            stream=body.stream,
            seq=body.seq,
            lines=lines,
            ts=body.lines[0].ts,
        )
        .on_conflict_do_nothing(index_elements=["experiment_id", "stream", "seq"])
        # rowcount is unreliable for ORM-enabled inserts (-1 on psycopg); RETURNING yields a
        # row only when the insert actually happened.
        .returning(LogChunk.id)
    )
    inserted = session.execute(statement).first()
    session.commit()
    if inserted is None:
        return {"duplicate": True}
    return {"accepted": len(lines)}


@router.get("/experiments/{experiment_id}/metrics")
def get_metrics(
    experiment_id: str,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
    name: str | None = None,
):
    access.load_experiment(session, principal, experiment_id, False)
    query = select(MetricPoint).where(MetricPoint.experiment_id == experiment_id)
    if name:
        query = query.where(MetricPoint.name == name)
    series: dict[str, list[dict]] = {}
    for p in session.scalars(query.order_by(MetricPoint.step, MetricPoint.ts)):
        series.setdefault(p.name, []).append({"step": p.step, "value": p.value, "ts": p.ts})
    return series


@router.get("/experiments/{experiment_id}/logs")
def get_logs(
    experiment_id: str,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
    stream: str | None = None,
    after_seq: int = -1,
):
    access.load_experiment(session, principal, experiment_id, False)
    query = select(LogChunk).where(
        LogChunk.experiment_id == experiment_id, LogChunk.seq > after_seq
    )
    if stream:
        query = query.where(LogChunk.stream == stream)
    chunks = session.scalars(query.order_by(LogChunk.stream, LogChunk.seq))
    return [{"stream": c.stream, "seq": c.seq, "lines": c.lines} for c in chunks]

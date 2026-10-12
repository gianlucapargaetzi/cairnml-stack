from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from mlops_common.schemas import LogBatch, MetricBatch
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mlops_server.models import LogChunk, MetricPoint
from mlops_server.security.deps import READ_ANY, Principal, get_session, require
from mlops_server.services import access

router = APIRouter()
any_principal = require("client", "agent", "run")
read_any = require(*READ_ANY)
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
    principal: Annotated[Principal, Depends(read_any)],
    session: Annotated[Session, Depends(get_session)],
    name: str | None = None,
    since_id: int | None = Query(None, ge=0),
):
    """Every point, ordered by step. With since_id, only points stored after that id, in
    insertion order, so a live page can fetch just what is new (ids grow with each insert)."""
    access.load_experiment(session, principal, experiment_id, False)
    query = select(MetricPoint).where(MetricPoint.experiment_id == experiment_id)
    if name:
        query = query.where(MetricPoint.name == name)
    if since_id is None:
        ordered = query.order_by(MetricPoint.step, MetricPoint.ts, MetricPoint.id)
    else:
        ordered = query.where(MetricPoint.id > since_id).order_by(MetricPoint.id)
    series: dict[str, list[dict]] = {}
    for p in session.scalars(ordered):
        series.setdefault(p.name, []).append(
            {"id": p.id, "step": p.step, "value": p.value, "ts": p.ts}
        )
    return series


@router.get("/experiments/{experiment_id}/logs")
def get_logs(
    experiment_id: str,
    principal: Annotated[Principal, Depends(read_any)],
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

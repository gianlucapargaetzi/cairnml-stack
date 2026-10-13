from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from mlops_common.schemas import LogBatch, MetricBatch
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mlops_server.models import LogChunk, MetricPoint, MetricSeries
from mlops_server.security.deps import READ_ANY, Principal, get_session, require
from mlops_server.services import access
from mlops_server.services.metrics import default_context_points, series_id

router = APIRouter()
any_principal = require("client", "agent", "run")
read_any = require(*READ_ANY)
MAX_LINE = 16_384
MAX_BATCH_CHARS = 2_000_000
TRUNCATED_SUFFIX = "... [truncated]"


@router.post("/runs/{run_id}/metrics")
def post_metrics(
    run_id: str,
    body: MetricBatch,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    access.load_run(session, principal, run_id, True)
    series: dict[tuple[str, str], int] = {}
    for p in body.points:
        key = (p.name, json.dumps(p.context, sort_keys=True))
        if key not in series:
            series[key] = series_id(session, run_id, p.name, p.context)
    session.add_all(
        MetricPoint(
            series_id=series[(p.name, json.dumps(p.context, sort_keys=True))],
            step=p.step, epoch=p.epoch, value=p.value, ts=p.ts,
        )
        for p in body.points
    )
    session.commit()
    return {"accepted": len(body.points)}


@router.post("/runs/{run_id}/logs")
def post_logs(
    run_id: str,
    body: LogBatch,
    principal: Annotated[Principal, Depends(any_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    access.load_run(session, principal, run_id, True)
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
            run_id=run_id,
            stream=body.stream,
            seq=body.seq,
            lines=lines,
            ts=body.lines[0].ts,
        )
        .on_conflict_do_nothing(index_elements=["run_id", "stream", "seq"])
        # rowcount is unreliable for ORM-enabled inserts (-1 on psycopg); RETURNING yields a
        # row only when the insert actually happened.
        .returning(LogChunk.id)
    )
    inserted = session.execute(statement).first()
    session.commit()
    if inserted is None:
        return {"duplicate": True}
    return {"accepted": len(lines)}


@router.get("/runs/{run_id}/metrics")
def get_metrics(
    run_id: str,
    principal: Annotated[Principal, Depends(read_any)],
    session: Annotated[Session, Depends(get_session)],
    name: str | None = None,
    since_id: int | None = Query(None, ge=0),
):
    """Every point, ordered by step. With since_id, only points stored after that id, in
    insertion order, so a live page can fetch just what is new (ids grow with each insert)."""
    access.load_run(session, principal, run_id, False)
    query = default_context_points(MetricPoint, MetricSeries.name).where(
        MetricSeries.run_id == run_id
    )
    if name:
        query = query.where(MetricSeries.name == name)
    if since_id is None:
        ordered = query.order_by(MetricPoint.step, MetricPoint.ts, MetricPoint.id)
    else:
        ordered = query.where(MetricPoint.id > since_id).order_by(MetricPoint.id)
    series: dict[str, list[dict]] = {}
    for p, metric in session.execute(ordered).all():
        series.setdefault(metric, []).append(
            {"id": p.id, "step": p.step, "value": p.value, "ts": p.ts}
        )
    return series


@router.get("/runs/{run_id}/logs")
def get_logs(
    run_id: str,
    principal: Annotated[Principal, Depends(read_any)],
    session: Annotated[Session, Depends(get_session)],
    stream: str | None = None,
    after_seq: int = -1,
):
    access.load_run(session, principal, run_id, False)
    query = select(LogChunk).where(
        LogChunk.run_id == run_id, LogChunk.seq > after_seq
    )
    if stream:
        query = query.where(LogChunk.stream == stream)
    chunks = session.scalars(query.order_by(LogChunk.stream, LogChunk.seq))
    return [{"stream": c.stream, "seq": c.seq, "lines": c.lines} for c in chunks]

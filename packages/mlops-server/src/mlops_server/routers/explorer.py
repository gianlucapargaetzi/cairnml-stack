"""Explorer API v1: search over runs and metrics, run actions, tags and bookmarks.

Endpoints mirror the calls of the Aim UI that the MLOps Flow fork keeps; the audit is in
docs/explorer_api.md. Reads need a client or browser session. Writes need the same, plus the CSRF
token for browser sessions.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import ExplorerState, Project, RunTag, Tag
from mlops_server.security.deps import READERS, Principal, get_session, require, require_writer
from mlops_server.services import access
from mlops_server.services.explorer import (
    project_params,
    run_info,
    search,
    search_sequences,
)
from mlops_server.services.query import SEQUENCE_KINDS, FilterError

router = APIRouter(prefix="/explorer")
read_principal = require(*READERS)
write_principal = require_writer("client")
MAX_BATCH = 500
PRESIGN_EXPIRES = 3600
SequencePlural = Literal["images", "audios", "texts", "figures", "distributions"]
MAX_BOOKMARK_STATE = 64_000  # bytes of JSON
BookmarkKind = Literal[
    "runs", "metrics", "params", "scatters", "images", "audios", "texts", "figures", "distributions"
]


def _bad_filter(error: FilterError) -> HTTPException:
    return HTTPException(400, str(error))


def _search(
    session: Session, principal: Principal, response: Response, *, query, project, limit,
    offset, points, metric_search: bool,
):
    try:
        body, total = search(
            session, principal, query=query, project=project, limit=limit, offset=offset,
            density=points, metric_search=metric_search,
        )
    except FilterError as error:
        raise _bad_filter(error) from None
    response.headers["X-Total-Count"] = str(total)
    return body


@router.get("/runs/search")
def search_runs(
    response: Response,
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
    q: str | None = None,
    project: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    points: int = Query(50, ge=1, le=500),
):
    """Runs that match `q`, with props, params and sampled traces. `X-Total-Count` is the total."""
    return _search(
        session, principal, response, query=q, project=project, limit=limit, offset=offset,
        points=points, metric_search=False,
    )


@router.get("/runs/search/metric")
def search_metrics(
    response: Response,
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
    q: str | None = None,
    project: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    points: int = Query(50, ge=1, le=500),
):
    """Like search/run, but `metric.*` clauses choose the traces and runs with no match are left
    out."""
    return _search(
        session, principal, response, query=q, project=project, limit=limit, offset=offset,
        points=points, metric_search=True,
    )


def _range(value: str | None, name: str) -> tuple[int, int] | None:
    """A closed range such as "2:10"; None when absent."""
    if value is None:
        return None
    try:
        low, high = (int(part) for part in value.split(":"))
    except ValueError:
        raise HTTPException(422, f"{name} is two integers, low:high") from None
    if low > high:
        raise HTTPException(422, f"{name} must not be reversed")
    return low, high


@router.get("/runs/search/{kind}")
def search_sequence_runs(
    kind: SequencePlural,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
    q: str | None = None,
    project: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    record_range: str | None = None,
    record_density: int = Query(50, ge=1, le=500),
    index_range: str | None = None,
    index_density: int = Query(5, ge=1, le=50),
):
    """Runs with a sequence of this kind that match `q`. Each run lists its sequences with
    sampled items. Image and audio items carry `blob_uri`, a presigned GET valid for an hour."""
    storage = request.app.state.storage
    blob_url = (lambda key: storage.presign_get(key, PRESIGN_EXPIRES)) if storage else None
    try:
        body, total = search_sequences(
            session, principal, kind=SEQUENCE_KINDS[kind], query=q, project=project,
            limit=limit, offset=offset, record_range=_range(record_range, "record_range"),
            record_density=record_density, index_range=_range(index_range, "index_range"),
            index_density=index_density, blob_url=blob_url,
        )
    except FilterError as error:
        raise _bad_filter(error) from None
    response.headers["X-Total-Count"] = str(total)
    return body


@router.get("/runs/active")
def active_runs(
    response: Response,
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
    q: str | None = None,
    project: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    points: int = Query(50, ge=1, le=500),
):
    """Runs that have not finished yet (created, queued or running)."""
    query = "run.active == True" if not q else f"run.active == True and ({q})"
    return _search(
        session, principal, response, query=query, project=project, limit=limit, offset=offset,
        points=points, metric_search=False,
    )


@router.get("/runs/{run_id}/info")
def get_run_info(
    run_id: str,
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    return run_info(session, access.load_run(session, principal, run_id, False))


class ArchiveBody(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=MAX_BATCH)


@router.post("/runs/archive")
def archive_runs(
    body: ArchiveBody,
    principal: Annotated[Principal, Depends(write_principal)],
    session: Annotated[Session, Depends(get_session)],
    archive: bool = True,
):
    """Archive or unarchive several runs. All of them must be writable, or none change."""
    runs = [access.load_run(session, principal, run_id, True) for run_id in dict.fromkeys(body.ids)]
    for run in runs:
        run.archived = archive
    session.commit()
    return {"updated": len(runs), "archived": archive}


def _run_and_tag(session: Session, principal: Principal, run_id: str, tag_id: str):
    run = access.load_run(session, principal, run_id, True)
    tag = session.get(Tag, tag_id)
    if tag is None or tag.project_id != run.project_id:
        raise HTTPException(404, "tag not found in this run's project")
    return run, tag


@router.post("/runs/{run_id}/tags/{tag_id}")
def attach_tag(
    run_id: str,
    tag_id: str,
    principal: Annotated[Principal, Depends(write_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    run, tag = _run_and_tag(session, principal, run_id, tag_id)
    if session.get(RunTag, (run.id, tag.id)) is None:
        session.add(RunTag(run_id=run.id, tag_id=tag.id))
        session.commit()
    return {"run_id": run.id, "tag_id": tag.id}


@router.delete("/runs/{run_id}/tags/{tag_id}")
def detach_tag(
    run_id: str,
    tag_id: str,
    principal: Annotated[Principal, Depends(write_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    run, tag = _run_and_tag(session, principal, run_id, tag_id)
    link = session.get(RunTag, (run.id, tag.id))
    if link is not None:
        session.delete(link)
        session.commit()
    return {"run_id": run.id, "tag_id": tag.id}


def _project_for_reading(session: Session, principal: Principal, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or not access.is_member(session, principal, project):
        raise HTTPException(404, "project not found")
    return project


@router.get("/projects/{project_id}/params")
def get_project_params(
    project_id: str,
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    """Autocomplete data: parameter paths, and metric names with their context keys."""
    project = _project_for_reading(session, principal, project_id)
    return project_params(session, project.id)


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: str | None = Field(default=None, max_length=2000)


class TagPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: str | None = Field(default=None, max_length=2000)


def _tag_out(tag: Tag) -> dict:
    return {"id": tag.id, "project_id": tag.project_id, "name": tag.name, "color": tag.color,
            "description": tag.description}


@router.get("/projects/{project_id}/tags")
def list_tags(
    project_id: str,
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    project = _project_for_reading(session, principal, project_id)
    tags = session.scalars(select(Tag).where(Tag.project_id == project.id).order_by(Tag.name))
    return [_tag_out(tag) for tag in tags]


@router.post("/projects/{project_id}/tags")
def create_tag(
    project_id: str,
    body: TagIn,
    principal: Annotated[Principal, Depends(write_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    project = _project_for_reading(session, principal, project_id)
    tag = Tag(id=new_id("tag"), project_id=project.id, name=body.name, color=body.color,
              description=body.description)
    session.add(tag)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "a tag with this name already exists") from None
    return _tag_out(tag)


def _writable_tag(session: Session, principal: Principal, tag_id: str) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(404, "tag not found")
    _project_for_reading(session, principal, tag.project_id)
    return tag


@router.patch("/tags/{tag_id}")
def patch_tag(
    tag_id: str,
    body: TagPatch,
    principal: Annotated[Principal, Depends(write_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    tag = _writable_tag(session, principal, tag_id)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("name") is None:
        fields.pop("name", None)  # a name cannot be cleared
    for name, value in fields.items():
        setattr(tag, name, value)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "a tag with this name already exists") from None
    return _tag_out(tag)


@router.delete("/tags/{tag_id}")
def delete_tag(
    tag_id: str,
    principal: Annotated[Principal, Depends(write_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    tag = _writable_tag(session, principal, tag_id)
    session.execute(delete(RunTag).where(RunTag.tag_id == tag.id))
    session.delete(tag)
    session.commit()
    return {"deleted": tag_id}


class BookmarkIn(BaseModel):
    kind: BookmarkKind
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    state: dict = Field(default_factory=dict)


class BookmarkPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    state: dict | None = None


def _bookmark_out(bookmark: ExplorerState) -> dict:
    return {
        "id": bookmark.id, "kind": bookmark.kind, "title": bookmark.title,
        "description": bookmark.description, "state": bookmark.state,
        "created_at": bookmark.created_at.isoformat(),
    }


def _check_state(state: dict) -> dict:
    if len(json.dumps(state)) > MAX_BOOKMARK_STATE:
        raise HTTPException(422, f"a bookmark's state is at most {MAX_BOOKMARK_STATE} bytes")
    return state


def _own_bookmark(session: Session, principal: Principal, bookmark_id: str) -> ExplorerState:
    bookmark = session.get(ExplorerState, bookmark_id)
    if bookmark is None or bookmark.user_id != principal.user_id:
        raise HTTPException(404, "bookmark not found")
    return bookmark


@router.get("/bookmarks")
def list_bookmarks(
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
    kind: BookmarkKind | None = None,
):
    """The caller's own bookmarks. Bookmarks are private to their owner."""
    query = select(ExplorerState).where(ExplorerState.user_id == principal.user_id)
    if kind:
        query = query.where(ExplorerState.kind == kind)
    return [_bookmark_out(b) for b in session.scalars(query.order_by(ExplorerState.created_at))]


@router.post("/bookmarks")
def create_bookmark(
    body: BookmarkIn,
    principal: Annotated[Principal, Depends(write_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    bookmark = ExplorerState(
        id=new_id("bmk"), user_id=principal.user_id, kind=body.kind, title=body.title,
        description=body.description, state=_check_state(body.state),
    )
    session.add(bookmark)
    session.commit()
    return _bookmark_out(bookmark)


@router.get("/bookmarks/{bookmark_id}")
def get_bookmark(
    bookmark_id: str,
    principal: Annotated[Principal, Depends(read_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    return _bookmark_out(_own_bookmark(session, principal, bookmark_id))


@router.patch("/bookmarks/{bookmark_id}")
def patch_bookmark(
    bookmark_id: str,
    body: BookmarkPatch,
    principal: Annotated[Principal, Depends(write_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    bookmark = _own_bookmark(session, principal, bookmark_id)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("title") is None:
        fields.pop("title", None)  # a title cannot be cleared
    if "state" in fields:
        fields["state"] = _check_state(fields["state"] or {})
    for name, value in fields.items():
        setattr(bookmark, name, value)
    session.commit()
    return _bookmark_out(bookmark)


@router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(
    bookmark_id: str,
    principal: Annotated[Principal, Depends(write_principal)],
    session: Annotated[Session, Depends(get_session)],
):
    session.delete(_own_bookmark(session, principal, bookmark_id))
    session.commit()
    return {"deleted": bookmark_id}


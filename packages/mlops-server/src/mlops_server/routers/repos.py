from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from mlops_server.security.deps import Principal, get_session, require
from mlops_server.services import access
from mlops_server.services.github import GitHubError, RepoNotAccessible, valid_repo

router = APIRouter()


def _github(request: Request):
    if request.app.state.github is None:
        raise HTTPException(503, "GitHub is not configured")
    return request.app.state.github


@router.get("/repos/status")
def repo_status(
    repo: str,
    ref: str,
    request: Request,
    principal: Annotated[Principal, Depends(require("client"))],
    session: Annotated[Session, Depends(get_session)],
):
    if not valid_repo(repo):
        raise HTTPException(422, "repo must be owner/name")
    # Only a repo linked to one of the caller's projects (or any repo for an admin) is visible.
    if not access.repo_visible(session, principal, repo):
        raise HTTPException(404, "GitHub App is not installed on this repository")
    try:
        head = _github(request).head_commit(repo, ref)
    except RepoNotAccessible:
        raise HTTPException(404, "GitHub App is not installed on this repository") from None
    except GitHubError:
        raise HTTPException(502, "GitHub request failed") from None
    return {"repo": repo, "ref": ref, "head": head}

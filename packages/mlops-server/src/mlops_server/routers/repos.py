from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from mlops_server.security.deps import Principal, require
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
    _: Annotated[Principal, Depends(require("client"))],
):
    if not valid_repo(repo):
        raise HTTPException(422, "repo must be owner/name")
    try:
        head = _github(request).head_commit(repo, ref)
    except RepoNotAccessible:
        raise HTTPException(404, "GitHub App is not installed on this repository") from None
    except GitHubError:
        raise HTTPException(502, "GitHub request failed") from None
    return {"repo": repo, "ref": ref, "head": head}

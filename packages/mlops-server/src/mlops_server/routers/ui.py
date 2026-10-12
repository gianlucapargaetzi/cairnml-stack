from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

STATIC = Path(__file__).resolve().parent.parent / "ui" / "static"
router = APIRouter()


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/ui/", status_code=302)


@router.get("/ui", include_in_schema=False)
def ui_no_slash() -> RedirectResponse:
    return RedirectResponse("/ui/", status_code=302)


@router.get("/ui/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", media_type="text/html")

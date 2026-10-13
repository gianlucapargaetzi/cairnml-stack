from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

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


# The MLOps Flow explorer (the Aim UI fork, built by packages/mlops-ui). It runs next to the old
# dashboard until the fork reaches parity. Its files are copied into NEXT by `npm run build:server`.
NEXT = Path(__file__).resolve().parent.parent / "ui" / "next"
NEXT_UNBUILT = "The explorer is not built. Run `npm run build:server` in packages/mlops-ui."


def _inside(base: Path, relative: str) -> Path | None:
    """The file `relative` names under `base`, or None when it would leave `base`."""
    root = base.resolve()
    target = (root / relative).resolve()
    return target if target.is_relative_to(root) else None


def _next_index() -> HTMLResponse:
    index = NEXT / "index.html"
    if not index.is_file():
        return HTMLResponse(NEXT_UNBUILT, status_code=503)
    return FileResponse(index, media_type="text/html")


@router.get("/ui-next", include_in_schema=False)
def next_no_slash() -> RedirectResponse:
    return RedirectResponse("/ui-next/", status_code=302)


@router.get("/ui-next/", include_in_schema=False)
def next_index() -> HTMLResponse:
    return _next_index()


@router.get("/ui-next/{path:path}", include_in_schema=False)
def next_file(path: str) -> HTMLResponse:
    """A built file when one exists, else the app shell (the browser router takes the path)."""
    target = _inside(NEXT, path)
    if target is not None and target.is_file():
        return FileResponse(target)
    return _next_index()

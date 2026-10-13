"""The explorer build is served under /ui-next with its own CSP; the old dashboard stays at /ui/."""

from __future__ import annotations

import pytest
from mlops_server.routers import ui


@pytest.fixture
def built(tmp_path, monkeypatch):
    root = tmp_path / "next"
    (root / "static" / "js").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>MLOps Flow</title>")
    (root / "static" / "js" / "main.js").write_text("console.log('fork')")
    secret = tmp_path / "secret.txt"
    secret.write_text("not for the web")
    monkeypatch.setattr(ui, "NEXT", root)
    return root


def test_the_index_is_served_with_the_explorer_csp(server, built):
    response = server.get("/ui-next/", follow_redirects=False)
    assert response.status_code == 200 and "MLOps Flow" in response.text
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "unsafe-eval" not in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert response.headers["Cache-Control"] == "no-store"


def test_the_explorer_csp_admits_the_storage_origin_for_blobs(server, built):
    """Images and audio are read from their presigned URLs, which live on the storage origin."""
    csp = server.get("/ui-next/").headers["Content-Security-Policy"]
    assert "img-src 'self' data: blob: http://mlops-nas:9000" in csp
    assert "connect-src 'self' http://mlops-nas:9000" in csp


def test_unknown_paths_get_the_app_shell_for_the_browser_router(server, built):
    response = server.get("/ui-next/runs/abc/detail")
    assert response.status_code == 200 and "MLOps Flow" in response.text


def test_built_files_are_served_and_cacheable_by_name(server, built):
    response = server.get("/ui-next/static/js/main.js")
    assert response.status_code == 200 and "console.log" in response.text
    assert response.headers.get("Cache-Control") != "no-store"


def test_paths_cannot_leave_the_build_folder(server, built):
    response = server.get("/ui-next/../secret.txt")
    assert "not for the web" not in response.text
    traversal = server.get("/ui-next/%2e%2e/secret.txt")
    assert "not for the web" not in traversal.text


def test_the_bare_prefix_redirects_to_the_slash(server, built):
    response = server.get("/ui-next", follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"] == "/ui-next/"


def test_a_missing_build_says_how_to_build_it(server, monkeypatch, tmp_path):
    monkeypatch.setattr(ui, "NEXT", tmp_path / "absent")
    response = server.get("/ui-next/")
    assert response.status_code == 503 and "build:server" in response.text


def test_the_old_dashboard_still_answers_at_ui(server, built):
    assert server.get("/ui/", follow_redirects=False).status_code == 200
    assert "default-src 'self'; img-src" in server.get("/ui/").headers["Content-Security-Policy"]

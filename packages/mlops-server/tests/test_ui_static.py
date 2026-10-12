import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src" / "mlops_server" / "ui" / "static"


def test_root_redirects_to_the_ui_and_the_ui_serves_html(server):
    assert server.get("/", follow_redirects=False).headers["location"] == "/ui/"
    assert server.get("/ui", follow_redirects=False).headers["location"] == "/ui/"
    page = server.get("/ui/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "<script src=\"/ui/static/vendor/chart.umd.js\"></script>" in page.text
    assert "<script type=\"module\" src=\"/ui/static/app.js\"></script>" in page.text
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page.text)  # no inline scripts
    assert "style=" not in page.text


def test_static_files_are_served_without_traversal(server):
    js = server.get("/ui/static/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert server.get("/ui/static/..%2f..%2fsettings.py").status_code == 404
    assert server.get("/ui/static/../../settings.py").status_code in (404, 400)


def test_vendored_chart_library_matches_its_recorded_hash():
    recorded = (STATIC / "vendor" / "chart.umd.js.sha256").read_text().split()[0]
    assert hashlib.sha256((STATIC / "vendor" / "chart.umd.js").read_bytes()).hexdigest() == recorded


FORBIDDEN = re.compile(
    r"\binnerHTML\b|\bouterHTML\b|\binsertAdjacentHTML\b|document\.write"
    r"|\beval\s*\(|new Function\s*\("
)


def test_ui_code_never_builds_html_from_strings():
    for path in STATIC.rglob("*.js"):
        if "vendor" in path.parts:
            continue
        assert not FORBIDDEN.search(path.read_text()), path


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_pure_ui_helpers_pass_their_node_tests():
    tests = Path(__file__).resolve().parents[1] / "ui-tests" / "lib.test.mjs"
    result = subprocess.run(["node", "--test", str(tests)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_route_has_a_view_module():
    app_js = (STATIC / "app.js").read_text()
    for name in re.findall(r'import\("\./views/([a-z]+)\.js"\)', app_js):
        assert (STATIC / "views" / f"{name}.js").exists(), name

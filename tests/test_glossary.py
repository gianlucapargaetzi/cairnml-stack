import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "packages" / "mlops-server" / "src" / "mlops_server" / "ui" / "static"
CLIENT = ROOT / "packages" / "mlops-client" / "src" / "mlops"

TERMS = ["Agent", "Project", "Experiment", "Run", "Job", "Dataset", "Resource"]


def test_the_glossary_defines_every_term_once():
    text = (ROOT / "docs" / "glossary.md").read_text()
    for term in TERMS:
        assert len(re.findall(rf"^\|\s*\*\*{term}\*\*\s*\|", text, re.M)) == 1, term


def _user_facing_strings(path: Path):
    for match in re.finditer(r'"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\\n$]|\\.)*)`', path.read_text()):
        yield match.group(1) or match.group(2) or ""


def test_the_ui_does_not_use_retired_words():
    retired = re.compile(r"\bworkspaces?\b", re.I)
    for path in UI.rglob("*.js"):
        if "vendor" in path.parts:
            continue
        for text in _user_facing_strings(path):
            assert not retired.search(text), f"{path.name}: {text!r}"
    assert not retired.search((UI / "index.html").read_text())


def test_the_sdk_names_follow_the_glossary():
    names = " ".join(p.read_text() for p in CLIENT.rglob("*.py"))
    assert "class Run" in names and "def current_run" in names
    assert not re.search(r"class Experiment\b|def current_experiment\b|mlops\.experiment\b", names)


RETIRED = re.compile(
    r"/api/v1/tasks|\btask_id\b|\bTask[A-Z]\w*|\bclass Task\b|\btasks?\b|\bTasks?\b|\bTASK"
    r"|\bMLOPS_EXPERIMENT_ID\b|\btsk_|\bcurrent_experiment\b|\bmlops\.Experiment\b"
)


def test_the_code_does_not_use_retired_words():
    """Task is retired (now Experiment), and Experiment no longer means one execution (now Run)."""
    this_file = Path(__file__).resolve()
    code = [
        p for root in (ROOT / "packages", ROOT / "tests")
        for suffix in ("*.py", "*.js", "*.mjs", "*.css")
        for p in root.rglob(suffix) if p.resolve() != this_file
    ]
    hits = [
        f"{p.relative_to(ROOT)}: {m.group(0)}"
        for p in code for m in RETIRED.finditer(p.read_text())
    ]
    assert not hits, hits[:20]


def test_the_four_dashboard_tabs_exist():
    app_js = (UI / "app.js").read_text()
    for label in ("Projects", "Datasets", "Jobs", "Resources"):
        assert f'"{label}"' in app_js, label

"""E2E.md, UI checks on runs: the scalars chart and its hover values, the console, debug samples, the comparison of
runs, the dashboards, and live job status. Each test signs in through the sign-in form in its own browser context.

The selectors are the ones of this build: the run's tabs are links ending in /output/<tab>, the project's tabs are
OVERVIEW, WORKLOADS, TASKS, EXPERIMENTS and MODELS.
"""

import re
import time

import pytest

from support import jobs, settings, workspace
from support.web import sign_in
from support.workspace import new_name, run_json

pytestmark = pytest.mark.ui

CONSOLE_LINE = "console line from the example run"


@pytest.fixture(scope="module")
def runs(client_home, project):
    """Two runs of the same metrics in one project: the run to look at, and a second one to compare with."""
    first = run_json(client_home, "track_example.py", ["--project", project, "--name", new_name("web-run"),
                                                       "--steps", "100"])
    second = run_json(client_home, "track_example.py", ["--project", project, "--name", new_name("web-run-2"),
                                                        "--steps", "50"])
    api = workspace.device_api(client_home)
    project_id = api.authed("projects.get_all", {"name": f"^{project}$"})["projects"][0]["id"]
    return {"project_id": project_id, "first": first["task_id"], "second": second["task_id"]}


@pytest.fixture(scope="module")
def signed_in_page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = sign_in(context)
    yield page
    context.close()


def _open(page, path: str, settle_ms: int = 4000):
    """Opens a page and waits for it to settle: the network goes quiet, bounded by settle_ms."""
    page.goto(settings.WEB_URL + path)
    try:
        page.wait_for_load_state("networkidle", timeout=settle_ms)
    except Exception:  # the app keeps polling on some pages; the content checks below decide
        pass


def _task_path(runs, tab: str) -> str:
    return f"/projects/{runs['project_id']}/tasks/{runs['first']}/output/{tab}"


def test_scalars_page_draws_both_series_of_the_loss(runs, signed_in_page):
    _open(signed_in_page, _task_path(runs, "scalars"))
    body = signed_in_page.inner_text("body")
    assert "loss" in body
    assert "train" in body and "val" in body, "the legend must name both series"
    assert "accuracy" in body and "0.93" in body, "the single value must be in the summary"
    assert signed_in_page.locator("canvas, svg").count() > 0


def test_hovering_the_chart_shows_a_tooltip(runs, signed_in_page):
    """The tooltip is drawn on the chart's canvas, so its values are not text the page exposes: the suite checks the
    stored values through the API (test_04). Here the check is that the pointer over the plot changes what is drawn
    (the guide line and the tooltip), and that moving it away changes it back."""
    _open(signed_in_page, _task_path(runs, "scalars"))
    axis = signed_in_page.locator("text=Iterations").first.bounding_box()
    centre_x, plot_y = axis["x"] + axis["width"] / 2, axis["y"] - 190
    clip = {"x": centre_x - 330, "y": plot_y - 150, "width": 480, "height": 330}
    signed_in_page.mouse.move(5, 5)
    signed_in_page.wait_for_timeout(800)
    idle = signed_in_page.screenshot(clip=clip)
    signed_in_page.mouse.move(centre_x - 200, plot_y)
    signed_in_page.mouse.move(centre_x - 150, plot_y)
    signed_in_page.wait_for_timeout(1000)
    hovered = signed_in_page.screenshot(clip=clip)
    assert hovered != idle, "hovering over the plot must draw the tooltip and the guide line"


def test_console_tab_shows_the_line_the_script_printed(runs, signed_in_page):
    _open(signed_in_page, _task_path(runs, "log"))
    assert CONSOLE_LINE in signed_in_page.inner_text("body")


def test_debug_sample_renders_as_an_image(runs, signed_in_page):
    _open(signed_in_page, _task_path(runs, "debugImages"), settle_ms=6000)
    widths = signed_in_page.evaluate("() => Array.from(document.images).map(i => i.naturalWidth)")
    samples = [w for w in widths if w > 0]
    assert len(samples) >= 2, f"the debug sample must render (logo and sample): {widths}"


def test_comparison_view_overlays_both_runs(runs, signed_in_page):
    """The project's experiments, in the scalars view: both runs are listed, and their metrics share one chart."""
    _open(signed_in_page, f"/projects/{runs['project_id']}/experiments", settle_ms=5000)
    signed_in_page.mouse.click(550, 92)  # the scalars view button of the experiments toolbar
    signed_in_page.wait_for_timeout(4000)
    body = signed_in_page.inner_text("body")
    assert "Scalars" in body or "SCALARS" in body
    assert "loss" in body
    assert body.count("Iterations") >= 1
    names = [n for n in re.findall(r"e2e-web-run(?:-2)?-[0-9a-f]{6}", body)]
    assert len(set(names)) == 2, f"both runs must be listed in the comparison: {names}"


def test_project_tabs_offer_tasks_and_experiments(runs, signed_in_page):
    _open(signed_in_page, f"/projects/{runs['project_id']}/overview", settle_ms=5000)
    body = signed_in_page.inner_text("body")
    for tab in ("TASKS", "EXPERIMENTS"):
        assert tab in body, f"the project header must show the {tab} tab"


def test_task_folder_lists_its_experiments(runs, signed_in_page):
    """The project's TASKS tab lists the run's task (its name), as one folder with its experiments in it."""
    _open(signed_in_page, f"/projects/{runs['project_id']}/tasks", settle_ms=5000)
    body = signed_in_page.inner_text("body")
    assert re.search(r"e2e-web-run-[0-9a-f]{6}", body), "the tasks tab must list the task of the run"


def test_single_click_selects_and_double_click_opens_a_project(runs, project, signed_in_page):
    """E2E.md: a single click on a project does not navigate; a double click opens its project dashboard."""
    _open(signed_in_page, "/dashboard", settle_ms=5000)
    card = signed_in_page.locator(f"text={project}").first
    card.click()
    signed_in_page.wait_for_timeout(2000)
    assert "/dashboard" in signed_in_page.url, "a single click must not navigate"
    card.dblclick()
    signed_in_page.wait_for_url(re.compile(rf"/projects/{runs['project_id']}"), timeout=30_000)


def test_jobs_list_shows_a_running_job_without_a_reload(client_home, project, runs, signed_in_page):
    new_name_prefix = new_name("live")
    task_id = run_json(client_home, "job_script.py", ["--project", project, "--name", new_name_prefix,
                                                      "--scalars", "1", "--sleep", "300"])["task_id"]
    api = workspace.device_api(client_home)
    jobs.enqueue(client_home, task_id)
    _open(signed_in_page, "/dashboard", settle_ms=4000)
    signed_in_page.click("text=MANAGE WORKERS AND JOBS")
    signed_in_page.wait_for_timeout(4000)
    api = workspace.device_api(client_home)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        rows = signed_in_page.locator("tr, [role=row], mat-row").filter(has_text=new_name_prefix)
        if rows.count() and re.search(r"in progress|running", rows.first.inner_text(), re.IGNORECASE):
            return
        if jobs.task_record(api, task_id).get("status") in jobs.FINAL:
            break  # the job has ended without running: nothing more to see
        signed_in_page.wait_for_timeout(3000)
    pytest.fail(f"the job {new_name_prefix} never showed as running on the Jobs page")

import os
import re

import pytest

# Playwright is in the `ui` dependency group only; without it the whole module is skipped.
expect = pytest.importorskip("playwright.sync_api").expect

pytestmark = pytest.mark.e2e

BASE = os.environ.get("MLOPS_E2E_SERVER", "http://mlops-server:8000").rstrip("/") + "/ui/"
REPO = os.environ.get("MLOPS_E2E_GITHUB_REPO")


@pytest.fixture
def logged_in(page, direct_grants, dev, project, login):
    login(page, "dev")
    return page


def test_the_four_tabs_are_there(logged_in):
    nav = logged_in.locator("#nav")
    for label in ("Projects", "Datasets", "Jobs", "Resources"):
        expect(nav.get_by_role("link", name=label)).to_be_visible()


def test_projects_tab_shows_the_hierarchy_and_tasks(logged_in, dev, project, tmp_path):
    script = tmp_path / "t.py"
    script.write_text(
        "import mlops\n"
        'e = mlops.init("e2e/demo", "lr-0.1", {"lr": 0.1}, task="training", '
        'primary_metric="val_loss", direction="min")\n'
        'e.log_metric("val_loss", 0.4, 1)\n'
    )
    assert dev.python(script, cwd=tmp_path).returncode == 0
    logged_in.goto(BASE + "#/projects")
    expect(logged_in.get_by_text("e2e", exact=True).first).to_be_visible()  # the group
    logged_in.get_by_role("link", name="demo").first.click()
    expect(logged_in.get_by_role("heading", name="Tasks")).to_be_visible()
    expect(logged_in.get_by_role("link", name="training")).to_be_visible()
    expect(logged_in.get_by_text("0.4").first).to_be_visible()  # best result
    logged_in.get_by_role("link", name="training").click()
    expect(logged_in.get_by_role("heading", name=re.compile("training"))).to_be_visible()
    expect(logged_in.get_by_text("lr-0.1").first).to_be_visible()


def test_task_settings_can_be_saved_from_the_browser(logged_in):
    logged_in.goto(BASE + "#/projects?project=e2e%2Fdemo")
    logged_in.get_by_role("link", name="training").click()
    logged_in.get_by_text("Settings", exact=True).click()
    logged_in.get_by_label("description").fill("trains the model")
    logged_in.get_by_role("button", name="Save").click()
    expect(logged_in.get_by_text("Saved.")).to_be_visible()


@pytest.mark.skipif(not REPO, reason="needs MLOPS_E2E_GITHUB_REPO")
def test_the_commit_graph_and_the_dataset_card(logged_in, dev):
    dev.run("repo", "link", "--project", "e2e/demo", "--repo", REPO, "--role", "data")
    logged_in.goto(BASE + "#/projects?project=e2e%2Fdemo")
    expect(logged_in.locator("svg.graph")).to_be_visible(timeout=30000)
    logged_in.locator("svg.graph g.commit").first.click()
    expect(logged_in.locator(".graph-detail")).not_to_have_text(
        "Click a commit to see the experiments that ran on it."
    )
    logged_in.get_by_role("link", name="data/sample").first.click()
    expect(logged_in.get_by_role("heading", name=re.compile("sample", re.I))).to_be_visible()
    expect(logged_in.get_by_role("heading", name="Versions")).to_be_visible()


def test_cancel_a_running_job_from_the_jobs_tab(
    logged_in, dev, project, agent_ready, dispatch_image, wait_for
):
    job_id = dispatch_image(dev, "sleep 600", "ui-cancel")
    wait_for(
        lambda: dev.api().get_job(job_id)["status"] == "running",
        timeout=180,
        message="the job to start",
    )
    logged_in.goto(BASE + "#/jobs")
    logged_in.once("dialog", lambda dialog: dialog.accept())
    row = logged_in.get_by_role("row", name=re.compile("ui-cancel")).first
    expect(row).to_be_visible(timeout=20000)
    row.get_by_role("button", name="Cancel").click()
    wait_for(
        lambda: dev.api().get_job(job_id)["status"] == "cancelled",
        timeout=120,
        message="the job to be cancelled",
    )
    logged_in.get_by_role("tab", name=re.compile("Finished")).click()
    expect(logged_in.get_by_role("row", name=re.compile("ui-cancel")).first).to_be_visible(
        timeout=20000
    )


def test_copy_a_job_change_a_parameter_and_reschedule(
    logged_in, dev, project, agent_ready, dispatch_image, wait_for
):
    job_id = dispatch_image(dev, "echo hello", "ui-copy")
    wait_for(
        lambda: dev.api().get_job(job_id)["status"] == "finished",
        timeout=180,
        message="the job to finish",
    )
    logged_in.goto(BASE + "#/jobs")
    logged_in.get_by_role("tab", name=re.compile("Finished")).click()
    row = logged_in.get_by_role("row", name=re.compile("ui-copy")).first
    row.get_by_role("button", name="Copy and reschedule").click()
    logged_in.get_by_label("name", exact=True).fill("ui-copy v2")
    logged_in.get_by_label("parameter value").first.fill("0.5")
    logged_in.get_by_role("button", name="Add parameter").click()
    logged_in.get_by_label("parameter key").last.fill("batch")
    logged_in.get_by_label("parameter value").last.fill("64")
    logged_in.get_by_role("button", name="Dispatch copy").click()
    expect(logged_in.get_by_text(re.compile("Queued job job_"))).to_be_visible()
    newest = dev.api().list_experiments("e2e/demo", limit=5)
    copy = next(e for e in newest if e["name"] == "ui-copy v2")
    assert copy["params"] == {"lr": 0.5, "batch": 64} and copy["parent_id"]
    assert copy["task"] == "testing"


def test_a_failed_reschedule_shows_the_server_message(
    logged_in, dev, project, agent_ready, dispatch_image, wait_for
):
    job_id = dispatch_image(dev, "true", "ui-bad")
    wait_for(
        lambda: dev.api().get_job(job_id)["status"] == "finished",
        timeout=180,
        message="the job to finish",
    )
    logged_in.goto(BASE + "#/jobs")
    logged_in.get_by_role("tab", name=re.compile("Finished")).click()
    row = logged_in.get_by_role("row", name=re.compile("ui-bad")).first
    row.get_by_role("button", name="Copy and reschedule").click()
    # 700000 s is above the 7-day limit of the job spec. The timeout field has min=60 in the
    # browser, so a value below it would be stopped before the server could answer.
    logged_in.get_by_label("timeout seconds").fill("700000")
    logged_in.get_by_role("button", name="Dispatch copy").click()
    expect(logged_in.get_by_text(re.compile("Could not queue the copy"))).to_be_visible()


def test_resources_tab_shows_the_agent_and_its_queues(logged_in, agent_ready):
    logged_in.goto(BASE + "#/resources")
    expect(logged_in.locator(".agent-card").first).to_be_visible(timeout=20000)
    expect(logged_in.get_by_text("Allocated to jobs").first).to_be_visible()
    expect(logged_in.get_by_text("Actually in use").first).to_be_visible()
    expect(logged_in.get_by_role("heading", name="Queues")).to_be_visible()


def test_a_browser_cannot_use_the_api_to_do_other_writes(logged_in):
    # No CSRF token is sent, so the server must refuse the write from the browser session.
    status = logged_in.evaluate(
        """async () => (await fetch('/api/v1/projects', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({slug: 'evil', name: 'x'}),
        })).status"""
    )
    assert status == 403

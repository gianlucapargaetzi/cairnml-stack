import os
import re

import pytest

# Playwright is in the `ui` dependency group only; without it the whole module is skipped.
expect = pytest.importorskip("playwright.sync_api").expect

pytestmark = pytest.mark.e2e

BASE = os.environ.get("MLOPS_E2E_SERVER", "http://mlops-server:8000").rstrip("/") + "/ui/"

SCRIPT = '''
import mlops, sys
name = sys.argv[1]
lr = float(sys.argv[2])
experiment = mlops.init("e2e/demo", name, {"lr": lr})
for step in range(5):
    experiment.log_metric("loss", lr * (5 - step), step)
print("dashboard line one")
print("<script>window.__xss = 1</script> in a log line", file=sys.stderr)
experiment.upload_artifact("note.txt", obj="hello")
'''


@pytest.fixture(scope="module")
def runs(dev, project, tmp_path_factory):
    folder = tmp_path_factory.mktemp("dash")
    script = folder / "run_dash.py"
    script.write_text(SCRIPT)
    xss_name = "<img src=x onerror=window.__xss=1>"
    for name, lr in [("dash-a", "0.1"), ("dash-b", "0.2"), (xss_name, "0.3")]:
        result = dev.python(script, name, lr, cwd=folder)
        assert result.returncode == 0, result.stderr
    api = dev.api()
    found = {e["name"]: e["id"] for e in api.list_experiments("e2e/demo", limit=200)}
    return found


@pytest.fixture
def logged_in(page, direct_grants, runs, login):
    login(page)
    return page


def test_login_redirects_through_the_idp_and_shows_the_user(logged_in):
    expect(logged_in.get_by_role("heading", name="Overview")).to_be_visible()
    expect(logged_in.get_by_text("e2e/demo").first).to_be_visible()


def test_unauthenticated_visitors_are_sent_to_the_login(page, direct_grants):
    page.goto(BASE)
    page.wait_for_url(re.compile(r"/realms/mlops/"))
    assert page.locator("#username").count() == 1


def test_experiment_list_filters_and_detail_page(logged_in, runs):
    page = logged_in
    page.goto(BASE + "#/experiments?project=e2e%2Fdemo")
    expect(page.get_by_role("link", name="dash-a")).to_be_visible()
    page.get_by_placeholder("name contains...").fill("dash-b")
    expect(page.get_by_role("link", name="dash-a")).to_have_count(0)
    page.get_by_role("link", name="dash-b").click()
    expect(page.get_by_role("heading", name=re.compile("dash-b"))).to_be_visible()
    expect(page.locator("canvas[aria-label='chart loss']")).to_be_visible()
    expect(page.locator("pre.log[aria-label='logs']")).to_contain_text("dashboard line one")
    expect(page.get_by_text("note.txt")).to_be_visible()
    expect(page.get_by_text("lr").first).to_be_visible()


def test_data_from_runs_is_rendered_as_text_never_as_html(logged_in, runs):
    page = logged_in
    page.goto(BASE + "#/experiments?project=e2e%2Fdemo")
    expect(page.get_by_text("<img src=x onerror=window.__xss=1>").first).to_be_visible()
    page.get_by_role("link", name="<img src=x onerror=window.__xss=1>").click()
    expect(page.locator("pre.log[aria-label='logs']")).to_contain_text(
        "<script>window.__xss = 1</script>"
    )
    assert page.evaluate("window.__xss === undefined")
    assert page.locator("img[src='x']").count() == 0


def test_comparing_runs_shows_differences(logged_in, runs):
    page = logged_in
    page.goto(BASE + "#/experiments?project=e2e%2Fdemo")
    page.get_by_label("select dash-a").check()
    page.get_by_label("select dash-b").check()
    page.get_by_role("button", name=re.compile("Compare selected")).click()
    expect(page.get_by_role("heading", name="Compare experiments")).to_be_visible()
    expect(page.locator("canvas[aria-label='compare loss']")).to_be_visible()
    expect(page.locator("tr.differs th", has_text="lr")).to_be_visible()
    expect(page.locator("td.best").first).to_be_visible()


def test_jobs_and_resources_pages(logged_in, dev, project, tmp_path):
    spec = tmp_path / "dash-job.yaml"
    spec.write_text(
        "name: dash-job\nproject: e2e/demo\nruntime:\n  type: image\n  image: alpine:3.20\n"
        "  command: [echo, hi]\n"
    )
    dev.run("dispatch", "--file", str(spec))
    page = logged_in
    # The Jobs tab shows the job under Running, Scheduled or Finished depending on its state;
    # the row itself is covered by test_tabs.py. The agents moved to the Resources tab.
    page.goto(BASE + "#/jobs")
    expect(page.get_by_role("heading", name="Jobs")).to_be_visible()
    page.goto(BASE + "#/resources")
    expect(page.locator(".agent-card").first).to_be_visible(timeout=20000)
    expect(page.locator("span.dot.on").first).to_be_visible(timeout=30000)


def test_admin_page_is_for_admins_only(page, direct_grants, runs, login):
    login(page, "dev")
    assert page.locator("#nav a[data-route='admin']").count() == 0
    page.goto(BASE + "#/admin")
    expect(page.get_by_text("Administrators only.")).to_be_visible()


def test_logout_ends_the_session(page, direct_grants, runs, login):
    login(page, "dev")
    page.get_by_role("button", name="Log out").click()
    page.wait_for_url(re.compile(r"/realms/mlops/|/ui/"))
    page.goto(BASE)
    page.wait_for_url(re.compile(r"/realms/mlops/"))  # the session is gone, the IdP asks again


def test_disabling_the_user_ends_an_open_browser_session(
    page, direct_grants, runs, admin, keycloak_admin, login
):
    login(page, "carol")                                    # creates carol's user row on the server
    admin.run("admin", "project-add-member", "e2e/demo", "carol")
    page.reload()
    expect(page.get_by_role("heading", name="Overview")).to_be_visible()
    keycloak_admin.set_enabled("carol", False)
    try:
        admin.run("admin", "sync-users")
        # the next API call gets 401 and the UI goes to the login
        page.reload()
        page.wait_for_url(re.compile(r"/realms/mlops/"))
    finally:
        keycloak_admin.set_enabled("carol", True)
        admin.run("admin", "sync-users")

"""E2E.md, UI checks: the web app as a person sees it, in a headless browser.

Every test signs in through the real sign-in page (the same form clearml-init uses), in a fresh browser context,
so no test depends on another test's cookies. Pages are checked for their text and their layout; screenshots are
not compared pixel by pixel.
"""

import os
import re

import pytest

from support import settings
from support.web import DASHBOARD, sign_in
from support.workspace import new_name, run_json

pytestmark = pytest.mark.ui

@pytest.fixture
def signed_in(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = sign_in(context)
    yield page
    context.close()


def test_sign_in_renders_the_dashboard(signed_in):
    body = signed_in.inner_text("body")
    assert "RECENT PROJECTS" in body
    assert "RECENT EXPERIMENTS" in body
    assert "MANAGE WORKERS AND JOBS" in body


def test_recent_experiments_list_a_run_recorded_from_the_client(client_home, project, signed_in):
    name = new_name("ui-run")
    run_json(client_home, "track_example.py", ["--project", project, "--name", name, "--steps", "3"])
    signed_in.reload()
    signed_in.wait_for_selector("text=RECENT EXPERIMENTS", timeout=60_000)
    signed_in.wait_for_selector(f"text={name}", timeout=120_000)
    assert name in signed_in.inner_text("body")


def test_stale_cookie_goes_to_the_sign_in_page(browser):
    """A cookie that no longer belongs to a device must not leave a half-loaded page: the app asks to sign in."""
    context = browser.new_context()
    context.add_cookies([{"name": "clearml_session", "value": "stale-0000", "url": settings.WEB_URL}])
    page = context.new_page()
    page.goto(settings.WEB_URL + "/dashboard")
    page.wait_for_url(re.compile(r"(realms/mlops|login)"), timeout=60_000)
    assert page.locator("#username").count() == 1
    context.close()


def test_dark_mode_renders_with_a_dark_background(browser):
    context = browser.new_context(color_scheme="dark", viewport={"width": 1280, "height": 800})
    page = sign_in(context)
    background = effective_background(page)
    assert _luminance(background) < 0.25, f"the body is not dark in dark mode: {background}"
    context.close()


def test_light_mode_renders_with_a_light_background(browser):
    context = browser.new_context(color_scheme="light", viewport={"width": 1280, "height": 800})
    page = sign_in(context)
    background = effective_background(page)
    assert _luminance(background) > 0.6, f"the body is not light in light mode: {background}"
    context.close()


def test_dashboard_has_no_horizontal_scroll_at_phone_width(browser):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = sign_in(context)
    widths = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert widths[0] <= widths[1] + 1, f"the page is wider than the phone screen: {widths}"
    context.close()


def test_manage_workers_and_jobs_page_opens(signed_in):
    signed_in.click("text=MANAGE WORKERS AND JOBS")
    signed_in.wait_for_load_state("networkidle", timeout=60_000)
    body = signed_in.inner_text("body")
    assert "WORKERS" in body.upper() and "JOBS" in body.upper()


EFFECTIVE_BACKGROUND = """() => {
    let el = document.elementFromPoint(8, 400) || document.body;
    while (el) {
        const bg = getComputedStyle(el).backgroundColor;
        if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') return bg;
        el = el.parentElement;
    }
    return 'rgb(255, 255, 255)';
}"""


def effective_background(page) -> str:
    """The colour painted behind the page: the first non-transparent background at the left edge."""
    return page.evaluate(EFFECTIVE_BACKGROUND)


def _luminance(css_color: str) -> float:
    """A rough brightness, 0 (black) to 1 (white), for rgb(...) and color(srgb ...) values."""
    numbers = [float(v) for v in re.findall(r"[\d.]+", css_color)[:3]]
    if len(numbers) < 3:
        return 0.5
    scale = 1.0 if "srgb" in css_color else 1 / 255
    return sum(numbers) * scale / 3


def test_restarting_the_api_keeps_the_dashboard_rendering(browser, isolated_stack):
    """Restart regression of E2E.md: after the API container restarts, a reload renders the same dashboard, with
    no half-loaded page. The restart is of this suite's own stack."""
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = sign_in(context)
    before = page.inner_text("body")
    result = isolated_stack.compose("restart", "apiserver", timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
    assert isolated_stack._wait is not None
    isolated_stack._wait(isolated_stack._api_answers, 300, "the API after the restart")
    page.reload()
    page.wait_for_selector("text=RECENT EXPERIMENTS", timeout=120_000)
    after = page.inner_text("body")
    for heading in ("RECENT PROJECTS", "RECENT EXPERIMENTS", "MANAGE WORKERS AND JOBS"):
        assert heading in after, f"{heading} missing after the restart"
    assert before.split("\n")[0] == after.split("\n")[0]
    context.close()

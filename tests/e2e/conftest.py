"""Shared fixtures for the end-to-end suite.

The suite starts its own stack for the session (support/stack.py): a separate compose project, with its own
state, accounts and ports. Nothing here touches deploy/ or the stack it runs. Every session gets its own HOME,
so the machine's real ~/.clearml is never touched, and the test devices are enrolled through the real sign-in
page.

Set MLOPS_E2E_KEEP_STACK=1 to leave the stack running after the session, for debugging.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
import requests

from support import devices, settings, workspace
from support.keycloak import Keycloak
from support.stack import IsolatedStack, StackError

# The browsers are installed in the real home; the SDK and the CLI run with a throwaway one.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", settings.BROWSERS_PATH)


def pytest_collection_modifyitems(config, items):
    """Tests marked github need a GitHub repository this machine can reach. They are skipped unless
    MLOPS_E2E_GITHUB_REPO names one (see E2E.md)."""
    if settings.github_tests_enabled():
        return
    skip = pytest.mark.skip(reason="needs a reachable GitHub repository: set MLOPS_E2E_GITHUB_REPO (E2E.md)")
    for item in items:
        if "github" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def isolated_stack():
    """Starts the suite's own stack, and removes it (containers, volumes, state folder) when the session ends."""
    stack = IsolatedStack(keep=bool(os.environ.get("MLOPS_E2E_KEEP_STACK")))
    try:
        stack.start()
    except StackError as exc:
        stack.stop()
        pytest.exit(f"The test stack could not start:\n{exc}", returncode=2)
    except BaseException:
        stack.stop()  # any other failure still removes what was started
        raise
    try:
        yield stack
    finally:
        stack.stop()


def _health_problems() -> list:
    problems = []
    checks = {
        "ClearML API": (f"{settings.API_URL}/v2.8/login.supported_modes", "post"),
        "web app": (settings.WEB_URL + "/", "get"),
        "sign-in service": (f"{settings.ISSUER}/.well-known/openid-configuration", "get"),
        "object storage": (settings.STORAGE_URL + "/health", "get"),
    }
    for name, (url, method) in checks.items():
        try:
            reply = requests.request(method, url, timeout=10, json={} if method == "post" else None)
            if reply.status_code != 200:
                problems.append(f"{name} answered {reply.status_code} at {url}")
        except requests.RequestException as exc:
            problems.append(f"{name} is not reachable at {url} ({exc.__class__.__name__})")
    return problems


@pytest.fixture(scope="session", autouse=True)
def stack(isolated_stack):
    """Every test needs the stack. If it is not answering, the suite stops here, with the reason."""
    problems = _health_problems()
    if problems:
        pytest.exit("The test stack is not ready:\n  - " + "\n  - ".join(problems), returncode=2)
    return settings


@pytest.fixture(scope="session")
def browser():
    """One headless Chromium for the session; each test signs in in a context of its own."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="session")
def session_home():
    """A throwaway HOME for this session. The SDK, the CLI and the device key all live here."""
    home = Path(tempfile.mkdtemp(prefix="mlops-e2e-home-"))
    yield home
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="session")
def keycloak(stack):
    return Keycloak()


@pytest.fixture(scope="session")
def admin_account(stack):
    return settings.ADMIN_USER, settings.ADMIN_PASSWORD


@pytest.fixture(scope="session")
def member_account(keycloak):
    """A plain user (not an admin), created for this session and removed afterwards."""
    username = f"{settings.PREFIX}-member-{os.urandom(3).hex()}"
    password = os.urandom(12).hex()
    keycloak.create_user(username, password)
    yield username, password
    keycloak.delete_user(username)


@pytest.fixture(scope="session")
def client_home(session_home, admin_account):
    """This session's client machine, enrolled as the admin through the sign-in page."""
    user, password = admin_account
    result = devices.init(session_home, user=user, password=password, name="e2e-client")
    assert result.returncode == 0, result.output
    yield session_home
    devices.logout(session_home)


@pytest.fixture(scope="session")
def project(client_home):
    """The project this session's tasks, datasets and models are created in. Deleted, with its contents, at the end."""
    api = workspace.device_api(client_home)
    name = workspace.new_name("project")
    project_id = workspace.create_project(api, name)
    yield name
    try:
        workspace.delete_project(api, project_id)
    except Exception:  # cleanup must not hide the failures of the tests themselves
        pass

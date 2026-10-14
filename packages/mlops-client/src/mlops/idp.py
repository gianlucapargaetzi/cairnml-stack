from __future__ import annotations

import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlsplit

import httpx


class LoginFailed(Exception):
    pass


# The CLI listens here for Keycloak's post-logout redirect. The URI must be registered on the
# mlops-cli client (deploy/idp/realm-mlops.json), so the port is fixed.
LOGOUT_PORT = 8765
LOGOUT_PATH = "/logged-out"


def end_idp_session(
    issuer: str,
    client_id: str,
    *,
    http: httpx.Client | None = None,
    open_browser=webbrowser.open,
    port: int = LOGOUT_PORT,
    timeout: float = 300.0,
) -> None:
    """Log the browser out of the IdP and wait until Keycloak confirms it.

    Only returns once the IdP redirected back to this process, so the device login that follows
    asks for credentials instead of approving as the previous user.
    """
    client = http or httpx.Client(timeout=30.0)
    meta = client.get(issuer.rstrip("/") + "/.well-known/openid-configuration").json()
    url = meta.get("end_session_endpoint")
    if not url:
        return
    redirect = f"http://127.0.0.1:{port}{LOGOUT_PATH}"
    confirmed = []

    class _Callback(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - the name http.server requires
            if urlsplit(self.path).path == LOGOUT_PATH:
                confirmed.append(True)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Logged out. You can close this tab.")

        def log_message(self, *args):  # keep the terminal quiet
            pass

    try:
        listener = HTTPServer(("127.0.0.1", port), _Callback)
    except OSError as exc:
        raise LoginFailed(f"cannot listen on 127.0.0.1:{port} for the logout: {exc}") from None
    query = urlencode({"client_id": client_id, "post_logout_redirect_uri": redirect})
    with listener:
        try:
            open_browser(f"{url}?{query}")
        except Exception:  # best effort: the logout URL is printed below
            print(f"Open {url}?{query} to log out")
        deadline = time.monotonic() + timeout
        listener.timeout = 1.0
        while not confirmed and time.monotonic() < deadline:
            listener.handle_request()
    if not confirmed:
        raise LoginFailed("the IdP logout was not confirmed in time")


def device_login(
    issuer: str,
    client_id: str,
    *,
    http: httpx.Client | None = None,
    sleep=time.sleep,
    out=print,
    open_browser=webbrowser.open,
) -> str:
    client = http or httpx.Client(timeout=30.0)
    meta = client.get(issuer.rstrip("/") + "/.well-known/openid-configuration").json()
    started = client.post(
        meta["device_authorization_endpoint"], data={"client_id": client_id, "scope": "openid"}
    )
    started.raise_for_status()
    device = started.json()
    url = device.get("verification_uri_complete") or device["verification_uri"]
    out(f"Open {url} and confirm the code {device['user_code']}")
    try:
        open_browser(url)
    except Exception:  # best effort: the URL is already printed
        pass
    interval = device.get("interval", 5)
    deadline = time.monotonic() + device["expires_in"]
    while time.monotonic() < deadline:
        sleep(interval)
        response = client.post(
            meta["token_endpoint"],
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device["device_code"],
                "client_id": client_id,
            },
        )
        body = response.json()
        if response.status_code == 200:
            return body["access_token"]
        error = body.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise LoginFailed(body.get("error_description") or error or "login failed")
    raise LoginFailed("login timed out")

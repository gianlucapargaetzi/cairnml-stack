from __future__ import annotations

import time
import webbrowser

import httpx


class LoginFailed(Exception):
    pass


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

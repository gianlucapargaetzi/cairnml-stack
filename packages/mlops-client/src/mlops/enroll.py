from __future__ import annotations

import os

import httpx
from mlops_common.keys import generate_private_key, public_key_pem, write_private_key
from mlops_common.schemas import ClientEnrollRequest, ClientEnrollResponse, PublicConfig

from mlops.api import ApiClient
from mlops.config import ClientConfig, key_path, load_config, save_config
from mlops.idp import device_login, end_idp_session


def enroll(
    http: httpx.Client,
    name: str,
    idp_token: str | None = None,
    *,
    login=device_login,
    logout=end_idp_session,
    force: bool = False,
) -> ClientConfig:
    already_enrolled = bool(load_config() or key_path().exists())
    if already_enrolled and not force:
        raise RuntimeError("already enrolled; use --force to enroll again")
    meta = PublicConfig.model_validate(http.get("/api/v1/config").raise_for_status().json())
    if idp_token is None and already_enrolled:
        # The browser may still hold the previous user's IdP session, which would approve the
        # login silently as that user. Log it out first so the next login asks for credentials.
        logout(meta.oidc_issuer, meta.oidc_client_id)
    token = idp_token or login(meta.oidc_issuer, meta.oidc_client_id)
    key = generate_private_key()
    response = http.post(
        "/api/v1/enroll/client",
        json=ClientEnrollRequest(name=name, public_key=public_key_pem(key)).model_dump(),
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    client_id = ClientEnrollResponse.model_validate(response.json()).client_id
    # The key is written only after the server accepted it. It goes to a temporary file first and
    # replaces the old key atomically, so the old key is never removed before the new one exists.
    previous_key = key_path().read_bytes() if key_path().exists() else None
    _replace_key(key)
    cfg = ClientConfig(server_url=meta.server_url.rstrip("/"), client_id=client_id)
    try:
        save_config(cfg)
    except BaseException:
        _restore_key(previous_key)
        raise
    return cfg


def _tmp_key_path():
    return key_path().with_name(key_path().name + ".tmp")


def _replace_key(key) -> None:
    tmp = _tmp_key_path()
    tmp.unlink(missing_ok=True)
    write_private_key(tmp, key)
    os.replace(tmp, key_path())


def _restore_key(previous: bytes | None) -> None:
    if previous is None:
        key_path().unlink(missing_ok=True)
        return
    tmp = _tmp_key_path()
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(previous)
    os.replace(tmp, key_path())


def whoami(api: ApiClient) -> dict:
    return api.me()

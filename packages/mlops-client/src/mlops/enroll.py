from __future__ import annotations

import httpx
from mlops_common.keys import generate_private_key, public_key_pem, write_private_key
from mlops_common.schemas import ClientEnrollRequest, ClientEnrollResponse, PublicConfig

from mlops.api import ApiClient
from mlops.config import ClientConfig, key_path, load_config, save_config
from mlops.idp import device_login


def enroll(
    http: httpx.Client,
    name: str,
    idp_token: str | None = None,
    *,
    login=device_login,
    force: bool = False,
) -> ClientConfig:
    if (load_config() or key_path().exists()) and not force:
        raise RuntimeError("already enrolled; use --force to enroll again")
    meta = PublicConfig.model_validate(http.get("/api/v1/config").raise_for_status().json())
    token = idp_token or login(meta.oidc_issuer, meta.oidc_client_id)
    key = generate_private_key()
    response = http.post(
        "/api/v1/enroll/client",
        json=ClientEnrollRequest(name=name, public_key=public_key_pem(key)).model_dump(),
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    client_id = ClientEnrollResponse.model_validate(response.json()).client_id
    # The key is written only after the server accepted it, so a failed enrollment leaves nothing.
    key_path().unlink(missing_ok=True)
    write_private_key(key_path(), key)
    cfg = ClientConfig(server_url=meta.server_url.rstrip("/"), client_id=client_id)
    save_config(cfg)
    return cfg


def whoami(api: ApiClient) -> dict:
    return api.me()

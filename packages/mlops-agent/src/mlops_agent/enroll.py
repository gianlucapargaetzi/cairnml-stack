from __future__ import annotations

import httpx
from mlops_common.keys import generate_private_key, public_key_pem, write_private_key
from mlops_common.schemas import AgentEnrollRequest, AgentEnrollResponse, Capabilities

from mlops_agent.config import AgentPaths
from mlops_agent.identity import Identity, load_identity, save_identity


def enroll(
    paths: AgentPaths,
    server_url: str,
    token: str,
    name: str,
    capabilities: Capabilities,
    http: httpx.Client | None = None,
) -> Identity:
    if load_identity(paths) is not None or paths.key.exists():
        raise RuntimeError(f"already enrolled (state in {paths.home})")
    key = generate_private_key()
    body = AgentEnrollRequest(
        token=token, name=name, public_key=public_key_pem(key), capabilities=capabilities
    )
    client = http or httpx.Client(base_url=server_url.rstrip("/"), timeout=30.0)
    response = client.post("/api/v1/enroll/agent", json=body.model_dump(mode="json"))
    response.raise_for_status()
    agent_id = AgentEnrollResponse.model_validate(response.json()).agent_id
    write_private_key(paths.key, key)
    identity = Identity(agent_id=agent_id, server_url=server_url.rstrip("/"))
    save_identity(paths, identity)
    return identity

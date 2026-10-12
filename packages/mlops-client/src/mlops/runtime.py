from __future__ import annotations

import os
from collections.abc import Callable

from mlops.api import ApiClient

_override: Callable[[str | None, str | None], ApiClient] | None = None


def set_api_override(fn: Callable[[str | None, str | None], ApiClient] | None) -> None:
    """Tests inject an in-process API here. Arguments are (run_token, server_url)."""
    global _override
    _override = fn


def make_api(run_token: str | None = None, server_url: str | None = None) -> ApiClient:
    if _override is not None:
        return _override(run_token, server_url)
    if run_token:
        return ApiClient.from_run_token(server_url or os.environ["MLOPS_SERVER_URL"], run_token)
    return ApiClient.from_config()

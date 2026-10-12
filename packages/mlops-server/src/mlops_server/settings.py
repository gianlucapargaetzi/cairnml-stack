from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MLOPS_")

    database_url: str
    public_url: str = "http://mlops-server:8000"
    signing_key_path: Path
    access_token_ttl: int = 3600
    run_token_ttl: int = 86400
    agent_timeout: int = 90
    reaper_interval: int = 30

    oidc_issuer: str
    oidc_client_id: str = "mlops-cli"
    oidc_jwks_url: str | None = None
    oidc_admin_role: str = "mlops-admin"

    github_app_id: str | None = None
    github_app_private_key_path: Path | None = None
    github_api_url: str = "https://api.github.com"

    s3_endpoint: str = "http://mlops-nas:9000"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    artifacts_bucket: str = "artifacts"
    datasets_bucket: str = "datasets"
    sts_ttl: int = 3600

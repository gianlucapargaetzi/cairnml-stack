import httpx
import pytest
from mlops import runtime
from mlops.api import ApiClient
from mlops.cli import app as cli
from typer.testing import CliRunner


def _as(api_http):
    runtime.set_api_override(lambda token, url: ApiClient(api_http))


def test_admin_commands_end_to_end(cfg_env, server, enroll_client):
    admin = enroll_client("root", roles=["mlops-admin"])
    enroll_client("alice")
    _as(admin.http)
    try:
        runner = CliRunner()
        assert (
            runner.invoke(cli, ["admin", "project-create", "vision/seg", "--name", "Seg"]).exit_code
            == 0
        )
        assert (
            runner.invoke(cli, ["admin", "project-add-member", "vision/seg", "alice"]).exit_code
            == 0
        )
        token = runner.invoke(
            cli, ["admin", "agent-token", "--queue", "gpu", "--queue", "cpu", "--ttl", "600"]
        )
        assert token.exit_code == 0 and token.output.strip().startswith("mlops_at_")
        clients = runner.invoke(cli, ["admin", "clients"])
        assert "cli_" in clients.output
        assert runner.invoke(cli, ["admin", "agents"]).exit_code == 0
        victim = enroll_client("victim")
        revoke = runner.invoke(cli, ["admin", "revoke-client", victim.client_id])
        assert revoke.exit_code == 0
        # A revoked client cannot even exchange its key for a token, so the request fails in auth.
        with pytest.raises(httpx.HTTPStatusError) as refused:
            victim.http.get("/api/v1/me")
        assert refused.value.response.status_code == 401
    finally:
        runtime.set_api_override(None)


def test_non_admins_get_a_clear_error(cfg_env, server, enroll_client):
    dev = enroll_client("dev")
    _as(dev.http)
    try:
        result = CliRunner().invoke(cli, ["admin", "agent-token"])
        assert result.exit_code == 1 and "admin role required" in result.output
    finally:
        runtime.set_api_override(None)

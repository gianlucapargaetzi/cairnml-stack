from __future__ import annotations

import logging
import signal
import threading
from typing import Annotated

import httpx
import typer
from mlops_common.keys import read_private_key

from mlops_agent.api import AgentApi
from mlops_agent.capabilities import detect
from mlops_agent.config import AgentSettings
from mlops_agent.enroll import enroll as do_enroll
from mlops_agent.identity import load_identity

app = typer.Typer(help="mlops agent: runs jobs from the mlops server")


@app.command()
def enroll(
    server: Annotated[
        str | None, typer.Option(help="Server URL (default: MLOPS_AGENT_SERVER_URL)")
    ] = None,
    token: Annotated[
        str | None,
        typer.Option(
            help="One-time enrollment token from an admin (default: MLOPS_AGENT_ENROLL_TOKEN)"
        ),
    ] = None,
    name: Annotated[str | None, typer.Option(help="Agent name (default: MLOPS_AGENT_NAME)")] = None,
    label: Annotated[list[str] | None, typer.Option(help="Capability label, repeatable")] = None,
) -> None:
    settings = AgentSettings()
    server = server or settings.server_url
    token = token or settings.enroll_token
    if not (server and token):
        raise typer.BadParameter("--server and --token are required")
    try:
        identity = do_enroll(
            settings.paths,
            server,
            token,
            name or settings.name,
            detect(label or settings.labels),
        )
    except RuntimeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        # Report the status only: the response body or request may echo the token.
        typer.echo(f"error: server rejected enrollment (HTTP {exc.response.status_code})", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"enrolled as {identity.agent_id}")
    typer.echo(f"identity written to {settings.paths.identity}")


@app.command()
def run() -> None:
    import docker

    from mlops_agent.executors import make_executor
    from mlops_agent.loop import AgentLoop
    from mlops_agent.runner import JobRunner

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = AgentSettings()
    identity = load_identity(settings.paths)
    if identity is None:
        typer.echo("not enrolled: run `mlops-agent enroll` first", err=True)
        raise typer.Exit(1)
    settings.server_url = settings.server_url or identity.server_url
    try:
        key = read_private_key(settings.paths.key)
    except (OSError, PermissionError) as exc:
        typer.echo(f"error: cannot load agent key: {exc}", err=True)
        raise typer.Exit(1) from None
    api = AgentApi.from_identity(identity, key)
    client = docker.from_env()
    runner = JobRunner(api, settings, lambda kind: make_executor(kind, client, settings))
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    AgentLoop(api, runner, settings).run_forever(stop)


if __name__ == "__main__":
    app()

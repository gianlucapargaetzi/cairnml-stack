from __future__ import annotations

import platform

import httpx
import typer

from mlops import runtime
from mlops.config import NotEnrolled
from mlops.enroll import enroll as do_enroll
from mlops.enroll import whoami as do_whoami
from mlops.idp import LoginFailed

app = typer.Typer(help="mlops client", no_args_is_help=True)


@app.command()
def enroll(
    server: str = typer.Option(..., help="Server URL, e.g. http://mlops-server:8000"),
    name: str = typer.Option(platform.node() or "client", help="Name for this machine"),
    idp_token: str | None = typer.Option(
        None, help="Use an existing IdP token instead of the browser login"
    ),
    force: bool = typer.Option(False, help="Replace an existing enrollment"),
) -> None:
    """Log in once and register this machine's key."""
    try:
        with httpx.Client(base_url=server.rstrip("/"), timeout=30.0) as http:
            cfg = do_enroll(http, name, idp_token, force=force)
    except RuntimeError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    except LoginFailed as exc:
        typer.echo(f"error: login failed: {exc}", err=True)
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        # Report the status only: the response body may echo the token.
        typer.echo(f"error: server rejected enrollment (HTTP {exc.response.status_code})", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"enrolled as {cfg.client_id} on {cfg.server_url}")


@app.command()
def whoami() -> None:
    """Show who this machine is enrolled as (uses the key, no login)."""
    try:
        me = do_whoami(runtime.make_api())
    except NotEnrolled as exc:
        typer.echo(f"{exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"{me['kind']} {me['id']} (admin={me['is_admin']})")

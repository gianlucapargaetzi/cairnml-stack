from __future__ import annotations

import platform
import time
from pathlib import Path

import httpx
import typer
import yaml
from mlops_common.schemas import TERMINAL_STATUSES

from mlops import runtime
from mlops.config import NotEnrolled
from mlops.dispatch import DispatchError, dispatch_experiment, server_detail
from mlops.enroll import enroll as do_enroll
from mlops.enroll import whoami as do_whoami
from mlops.idp import LoginFailed

app = typer.Typer(help="mlops client", no_args_is_help=True)
job_app = typer.Typer(help="inspect and cancel jobs", no_args_is_help=True)
app.add_typer(job_app, name="job")


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(1)


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
    except httpx.TransportError:
        typer.echo(f"error: cannot reach {server}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"enrolled as {cfg.client_id} on {cfg.server_url}")


@app.command()
def whoami() -> None:
    """Show who this machine is enrolled as (uses the key, no login)."""
    try:
        api = runtime.make_api()
        me = do_whoami(api)
    except NotEnrolled as exc:
        typer.echo(f"{exc}", err=True)
        raise typer.Exit(1) from None
    except httpx.TransportError:
        typer.echo(f"error: cannot reach {api.server_url}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"{me['kind']} {me['id']} (admin={me['is_admin']})")


@app.command()
def dispatch(
    experiment_id: str = typer.Argument(None, help="Experiment to re-run on an agent"),
    queue: str = typer.Option("default", help="Queue to submit to"),
    cpu: int = typer.Option(None, help="CPU cores to request"),
    memory_gb: float = typer.Option(None, help="Memory in GB to request"),
    gpu: int = typer.Option(None, help="GPUs to request"),
    label: list[str] | None = typer.Option(None, help="Agent label the job needs (repeatable)"),  # noqa: B008
    file: Path | None = typer.Option(None, help="Dispatch an explicit job spec (YAML) instead"),  # noqa: B008
) -> None:
    """Run a recorded experiment, or a job spec file, on an agent."""
    api = runtime.make_api()
    try:
        if file is not None:
            try:
                spec = yaml.safe_load(file.read_text())
            except (OSError, yaml.YAMLError) as exc:
                _fail(f"cannot read job spec {file}: {exc}")
            job = api.create_job(spec)
        elif experiment_id:
            requested = {"cpu": cpu, "memory_gb": memory_gb, "gpu": gpu}
            resources = {k: v for k, v in requested.items() if v is not None}
            if label:
                resources["labels"] = label
            job = dispatch_experiment(api, experiment_id, queue=queue, resources=resources)
        else:
            _fail("give an experiment id or --file")
    except DispatchError as exc:
        _fail(str(exc))
    except httpx.HTTPStatusError as exc:
        _fail(server_detail(exc))
    typer.echo(f"dispatched {job['id']} (experiment {job['experiment_id']}) status={job['status']}")


@app.command("ls")
def list_experiments(
    project: str = typer.Option(None, help="Only this project"),
    status: str = typer.Option(None, help="Only this status"),
) -> None:
    """List recent experiments."""
    try:
        experiments = runtime.make_api().list_experiments(project, status)
    except httpx.HTTPStatusError as exc:
        _fail(server_detail(exc))
    for exp in experiments:
        typer.echo(f"{exp['id']}  {exp['status']:<9} {exp['project']:<20} {exp['name']}")


@job_app.command("show")
def job_show(job_id: str) -> None:
    """Show a job's status."""
    try:
        job = runtime.make_api().get_job(job_id)
    except httpx.HTTPStatusError as exc:
        _fail(server_detail(exc))
    typer.echo(
        f"{job['id']} {job['status']} queue={job['queue']} agent={job['agent_id']} "
        f"exit={job['exit_code']} {job['message'] or ''}".rstrip()
    )


@job_app.command("cancel")
def job_cancel(job_id: str) -> None:
    """Cancel a job that has not finished."""
    try:
        job = runtime.make_api().cancel_job(job_id)
    except httpx.HTTPStatusError as exc:
        _fail(server_detail(exc))
    typer.echo(f"{job['id']} {job['status']}")


@app.command()
def logs(
    experiment_id: str,
    follow: bool = typer.Option(False, "--follow", "-f", help="Keep printing until the run ends"),
) -> None:
    """Print the captured stdout and stderr of an experiment."""
    api = runtime.make_api()
    seen: dict[str, int] = {}
    try:
        while True:
            for chunk in api.get_logs(experiment_id):
                if chunk["seq"] > seen.get(chunk["stream"], -1):
                    seen[chunk["stream"]] = chunk["seq"]
                    for line in chunk["lines"]:
                        typer.echo(line["text"])
            if not follow:
                return
            if api.get_experiment(experiment_id)["status"] in TERMINAL_STATUSES:
                return
            time.sleep(2)
    except httpx.HTTPStatusError as exc:
        _fail(server_detail(exc))

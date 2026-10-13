from __future__ import annotations

import json
import platform
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import typer
import yaml
from mlops_common.schemas import TERMINAL_STATUSES

from mlops import runtime
from mlops.config import NotEnrolled
from mlops.data import dvc_command
from mlops.dataset_card import parse_dvc_file, scaffold_card
from mlops.dispatch import DispatchError, dispatch_experiment, server_detail
from mlops.enroll import enroll as do_enroll
from mlops.enroll import whoami as do_whoami
from mlops.idp import LoginFailed
from mlops.repo import find_project, init_repo
from mlops.sync import sync_all

app = typer.Typer(help="mlops client", no_args_is_help=True)
job_app = typer.Typer(help="inspect and cancel jobs", no_args_is_help=True)
repo_app = typer.Typer(help="project repository setup", no_args_is_help=True)
data_app = typer.Typer(help="DVC data helpers using temporary credentials", no_args_is_help=True)
task_app = typer.Typer(
    help="tasks of a project (training, augmentation, ...)", no_args_is_help=True
)
app.add_typer(job_app, name="job")
app.add_typer(repo_app, name="repo")
app.add_typer(data_app, name="data")
dataset_app = typer.Typer(
    help="datasets of linked repositories and their cards", no_args_is_help=True
)
card_app = typer.Typer(
    help="dataset cards: Markdown with YAML front matter, stored in Git", no_args_is_help=True
)
app.add_typer(task_app, name="task")
app.add_typer(dataset_app, name="dataset")
dataset_app.add_typer(card_app, name="card")


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


def _api():
    try:
        return runtime.make_api()
    except NotEnrolled:
        _fail("not enrolled: run mlops enroll")


@contextmanager
def _remote(api) -> Iterator[None]:
    """Turn server and network failures into one line and exit 1 (no traceback)."""
    try:
        yield
    except httpx.HTTPStatusError as exc:
        _fail(server_detail(exc))
    except httpx.TransportError:
        _fail(f"cannot reach {api.server_url}")


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
    api = _api()
    with _remote(api):
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
    typer.echo(f"dispatched {job['id']} (experiment {job['experiment_id']}) status={job['status']}")


@app.command("ls")
def list_experiments(
    project: str = typer.Option(None, help="Only this project"),
    status: str = typer.Option(None, help="Only this status"),
) -> None:
    """List recent experiments."""
    api = _api()
    with _remote(api):
        experiments = api.list_experiments(project, status)
    for exp in experiments:
        typer.echo(f"{exp['id']}  {exp['status']:<9} {exp['project']:<20} {exp['name']}")


@job_app.command("show")
def job_show(job_id: str) -> None:
    """Show a job's status."""
    api = _api()
    with _remote(api):
        job = api.get_job(job_id)
    typer.echo(
        f"{job['id']} {job['status']} queue={job['queue']} agent={job['agent_id']} "
        f"exit={job['exit_code']} {job['message'] or ''}".rstrip()
    )


@job_app.command("cancel")
def job_cancel(job_id: str) -> None:
    """Cancel a job that has not finished."""
    api = _api()
    with _remote(api):
        job = api.cancel_job(job_id)
    typer.echo(f"{job['id']} {job['status']}")


def _parse_value(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return text


@job_app.command("reschedule")
def job_reschedule(
    job_id: str,
    name: str = typer.Option(None, help="New name of the copy"),  # noqa: B008
    queue: str = typer.Option(None, help="Queue for the copy"),  # noqa: B008
    cpu: int = typer.Option(None, help="CPUs for the copy"),  # noqa: B008
    memory_gb: float = typer.Option(None, help="Memory in GB for the copy"),  # noqa: B008
    gpu: int = typer.Option(None, help="GPUs for the copy"),  # noqa: B008
    timeout: int = typer.Option(None, help="Timeout in seconds (at least 60)"),  # noqa: B008
    param: list[str] = typer.Option([], help="Set a parameter KEY=VALUE (repeatable)"),  # noqa: B008
    unset_param: list[str] = typer.Option([], help="Remove a parameter (repeatable)"),  # noqa: B008
) -> None:
    """Copy a job (in any state), change its parameters or resources, and queue the copy."""
    api = _api()
    overrides: dict = {}
    for key, value in (("name", name), ("queue", queue), ("timeout_s", timeout)):
        if value is not None:
            overrides[key] = value
    params: dict = {}
    for item in param:
        key, _, value = item.partition("=")
        params[key] = _parse_value(value)
    params.update({key: None for key in unset_param})
    if params:
        overrides["params"] = params
    with _remote(api):
        if any(value is not None for value in (cpu, memory_gb, gpu)):
            base = api.get_job_spec(job_id)["resources"]
            changed = {"cpu": cpu, "memory_gb": memory_gb, "gpu": gpu}
            overrides["resources"] = {**base, **{k: v for k, v in changed.items() if v is not None}}
        job = api.reschedule_job(job_id, overrides)
    typer.echo(f"queued {job['id']} (experiment {job['experiment_id']}) copied from {job_id}")


@app.command()
def logs(
    experiment_id: str,
    follow: bool = typer.Option(False, "--follow", "-f", help="Keep printing until the run ends"),
) -> None:
    """Print the captured stdout and stderr of an experiment."""
    api = _api()
    seen: dict[str, int] = {}
    with _remote(api):
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


@repo_app.command("link")
def repo_link(
    project: str = typer.Option(..., help="Project slug, e.g. vision/seg"),
    repo: str = typer.Option(..., help="GitHub repository as owner/name"),
    role: str = typer.Option("code", help="code or data"),
) -> None:
    """Link a GitHub repository (code or data) to a project for history and datasets."""
    api = _api()
    with _remote(api):
        try:
            api.link_repo(project, repo, role)
        except httpx.HTTPStatusError as exc:
            _fail(server_detail(exc))
    typer.echo(f"linked {repo} ({role}) to {project}")


@repo_app.command("init")
def repo_init(
    project: str = typer.Option(..., help="Project slug, e.g. vision/seg"),
) -> None:
    """Write .mlops/project.yaml and configure the DVC remote for this repository."""
    api = _api()
    with _remote(api):
        try:
            info = init_repo(Path.cwd(), project, api)
        except (ValueError, RuntimeError) as exc:
            _fail(str(exc))
        except httpx.HTTPStatusError as exc:
            _fail(server_detail(exc))
    typer.echo(f"project {info['project']}: remote {info['remote_url']} ({info['endpoint']})")
    typer.echo(f"GitHub App: {info['github_app']}")


def _data(action: str, targets: list[str]) -> None:
    api = _api()
    with _remote(api):
        try:
            project = find_project(Path.cwd())
            dvc_command(api, project, action, targets, Path.cwd())
        except (ValueError, RuntimeError) as exc:
            _fail(str(exc))
    typer.echo(f"dvc {action} done")


@data_app.command("pull")
def data_pull(targets: list[str] = typer.Argument(None)) -> None:  # noqa: B008
    """Pull DVC data with temporary storage credentials."""
    _data("pull", targets or [])


@data_app.command("push")
def data_push(targets: list[str] = typer.Argument(None)) -> None:  # noqa: B008
    """Push DVC data with temporary storage credentials."""
    _data("push", targets or [])


@app.command()
def sync() -> None:
    """Upload runs that were recorded while the server was unreachable."""
    api = _api()
    failed: list[str] = []
    with _remote(api):
        synced = sync_all(api, failed=failed)
    for failure in failed:
        typer.echo(f"error: {failure}", err=True)
    typer.echo(f"synced {len(synced)} experiment(s)")
    if failed:
        _fail(f"{len(failed)} run(s) not synced; their spool is kept, run `mlops sync` again")


@task_app.command("ls")
def task_ls(project: str = typer.Option(None, help="Only this project")) -> None:  # noqa: B008
    """List tasks and their primary metric."""
    api = _api()
    with _remote(api):
        tasks = api.list_tasks(project)
    for task in tasks:
        metric = (
            f"{task['primary_metric']} ({task['direction']})" if task["primary_metric"] else "-"
        )
        typer.echo(f"{task['project']:<24} {task['name']:<20} {task['kind']:<16} metric={metric}")


@task_app.command("set")
def task_set(
    project: str = typer.Argument(..., help="Project slug"),
    name: str = typer.Argument(..., help="Task name"),
    metric: str = typer.Option(None, help="Primary metric"),  # noqa: B008
    direction: str = typer.Option(None, help="min or max"),  # noqa: B008
    kind: str = typer.Option(None, help="Task kind"),  # noqa: B008
    description: str = typer.Option(None, help="Description"),  # noqa: B008
) -> None:
    """Change a task's metric, direction, kind or description."""
    api = _api()
    fields = {
        k: v for k, v in {
            "primary_metric": metric, "direction": direction, "kind": kind,
            "description": description,
        }.items() if v is not None
    }
    with _remote(api):
        matches = [t for t in api.list_tasks(project) if t["name"] == name]
        if not matches:
            _fail(f"no task {name!r} in project {project}")
        api.patch_task(matches[0]["id"], **fields)
    typer.echo(f"updated {project}/{name}")


@dataset_app.command("ls")
def dataset_ls(project: str = typer.Option(None, help="Only this project")) -> None:  # noqa: B008
    """List the DVC datasets of linked repositories."""
    api = _api()
    with _remote(api):
        rows = api.list_datasets(project)
    for d in rows:
        card = "yes" if d["has_card"] else "no"
        typer.echo(
            f"{d['project']:<24} {d['repo']:<24} {d['path']:<28} "
            f"{d['type'] or '-':<10} {d['license'] or '-':<12} card={card}"
        )


@dataset_app.command("show")
def dataset_show(
    path: str = typer.Argument(..., help="Dataset path without .dvc"),
    project: str = typer.Option(..., help="Project slug"),
    repo: str = typer.Option(None, help="Repository (needed when the path is in several)"),  # noqa: B008
) -> None:
    """Show a dataset's card, DVC hash and experiments that used it."""
    api = _api()
    with _remote(api):
        repo = repo or next(
            (d["repo"] for d in api.list_datasets(project) if d["path"] == path), None
        )
        if repo is None:
            _fail(f"no dataset {path!r} in project {project}")
        detail = api.get_dataset(project, repo, path)
    card = detail["card"] or {}
    license_name = card.get("license") or "-"
    typer.echo(f"{card.get('title') or path} ({card.get('type', '-')}, license {license_name})")
    used = detail["used_by"]["count"]
    typer.echo(f"hash {detail['dvc']['dvc_hash']}  used by {used} experiment(s)")
    typer.echo(card.get("body") or f"No card yet: run `mlops dataset card init {path}`.")


@card_app.command("init")
def card_init(
    path: str = typer.Argument(..., help="Dataset path without .dvc"),
    title: str = typer.Option(None, help="Title"),  # noqa: B008
    license: str = typer.Option(None, help="SPDX id or free text"),  # noqa: B008
    type: str = typer.Option(
        "other", help="tabular, images, text, audio, video, timeseries, other"
    ),
    description: str = typer.Option(None, help="One-paragraph summary"),  # noqa: B008
) -> None:
    """Create PATH.card.md next to the .dvc file, from the DVC metadata. Nothing is uploaded."""
    dvc_file = Path(path + ".dvc")
    if not dvc_file.is_file():
        _fail(f"{path} is not tracked by DVC (no {dvc_file})")
    target = Path(path + ".card.md")
    if target.exists():
        _fail(f"{target} already exists; edit it instead")
    info = parse_dvc_file(dvc_file.read_text())
    target.write_text(
        scaffold_card(path, info, title=title, license=license, type=type, description=description)
    )
    typer.echo(f"created {target}")
    typer.echo(f"next: edit it, then `git add {target} && git commit && git push`")


admin_app = typer.Typer(help="administration (requires the admin role)", no_args_is_help=True)
app.add_typer(admin_app, name="admin")


def _admin(call):
    """Run an admin call as this enrolled client. The server enforces the admin role."""
    api = _api()
    with _remote(api):
        return call(api)


@admin_app.command("agent-token")
def admin_agent_token(
    queue: list[str] = typer.Option(["default"], "--queue", help="Queue the agent may serve"),  # noqa: B008
    ttl: int = typer.Option(900, help="Seconds until the token expires"),
) -> None:
    """Create a one-time token that lets one agent enroll. Prints only the token."""
    typer.echo(_admin(lambda api: api.create_agent_token(list(queue), ttl))["token"])


@admin_app.command("project-create")
def admin_project_create(
    slug: str,
    name: str = typer.Option(None, help="Display name (defaults to the slug)"),
) -> None:
    """Create a project."""
    _admin(lambda api: api.create_project(slug, name or slug))
    typer.echo(f"created project {slug}")


@admin_app.command("project-add-member")
def admin_add_member(slug: str, username: str) -> None:
    """Give a user access to a project."""
    _admin(lambda api: api.add_member(slug, username))
    typer.echo(f"added {username} to {slug}")


@admin_app.command("agents")
def admin_agents() -> None:
    """List agents."""
    for agent in _admin(lambda api: api.list_agents()):
        state = "revoked" if agent["revoked"] else "active"
        typer.echo(
            f"{agent['id']}  {state:<8} queues={','.join(agent['queues'])} "
            f"last_seen={agent['last_seen']}"
        )


@admin_app.command("clients")
def admin_clients() -> None:
    """List enrolled clients."""
    for client in _admin(lambda api: api.list_clients()):
        state = "revoked" if client["revoked"] else "active"
        typer.echo(f"{client['id']}  {state:<8} {client['name']} user={client['user_id']}")


@admin_app.command("revoke-agent")
def admin_revoke_agent(agent_id: str) -> None:
    """Revoke an agent so it can no longer authenticate."""
    _admin(lambda api: api.revoke_agent(agent_id))
    typer.echo(f"revoked {agent_id}")


@admin_app.command("revoke-client")
def admin_revoke_client(client_id: str) -> None:
    """Revoke a client so it can no longer authenticate."""
    _admin(lambda api: api.revoke_client(client_id))
    typer.echo(f"revoked {client_id}")


@admin_app.command("sync-users")
def admin_sync_users() -> None:
    """Check every user against the IdP now (otherwise this runs every minute)."""
    report = _admin(lambda api: api.sync_users())
    typer.echo(
        f"checked {report['checked']}, disabled {len(report['disabled'])}, "
        f"re-enabled {len(report['reenabled'])}, roles changed {len(report['roles_changed'])}, "
        f"errors {report['errors']}"
    )

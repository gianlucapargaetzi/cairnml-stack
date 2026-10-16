# Migration guide: from `mlops` to ClearML

Written for: people who have scripts, notebooks or pipelines that use `mlops`, and need them to keep working after cut-over.

## What changes for you

- **Sign-in.** You no longer have an `mlops` login or a token to copy. Run `clearml-init` once on your machine. Your browser opens the sign-in page; approve it there and the machine is enrolled. Nothing is typed in the terminal.
- **Agents.** `clearml-agent init` does the same, and an admin must approve it. A non-admin is refused by the server.
- **Library.** Replace `mlops` with `clearml`. The concepts map as in the table below.
- **Dispatch.** Jobs go to a ClearML queue. An agent that listens on the queue runs them.
- **Your old runs.** Runs in `mlops` are not copied (decision in section 2). Keep the old server running read-only until you no longer need them, or export what you need before cut-over.

## Calls

| What you did with `mlops` | What you do with ClearML | Notes |
|---|---|---|
| `run = mlops.init(project, name, config=cfg)` | `task = Task.init(project_name=project, task_name=name)` then `task.connect(cfg)` | `connect` records the dictionary as the task's parameters |
| `mlops.init(..., datasets=[...])` | `Dataset.get(dataset_name=..., dataset_project=...)` | the dataset is ClearML's own model; see loss 14 below |
| `run.log_metric(name, value, step)` | `task.get_logger().report_scalar(title=name, series=name, value=value, iteration=step)` | |
| `run.track(value, name, step=, epoch=, context=)` | `report_scalar` with `iteration=step`; put the context into `series`, for example `"val"` | |
| `run.log_metrics({...}, step)` | one `report_scalar` per key | |
| `run.log_params(params)` | `task.connect(params)` | |
| `run.log_text(stream, text)` | `task.get_logger().report_text(text)` | |
| `run.log_image(...)` | `task.get_logger().report_image(...)` | |
| `run.log_figure(fig)` | `task.get_logger().report_matplotlib_figure(...)` | |
| `run.log_distribution(...)` | `task.get_logger().report_histogram(...)` | |
| `run.upload_artifact(name, path)` | `task.upload_artifact(name=name, artifact_object=path)` | the storage location is set by ClearML's configuration (storage is a later topic) |
| `run.close("completed")` | `task.close()` (or `task.mark_completed()`) | `mark_failed()` for a failed run |
| `mlops dispatch ...` (CLI) | `Task.enqueue(task, queue_name=...)` or the web app's "Enqueue" | the queue must be served by an agent |
| `mlops logs ...` | the task's Console tab in the web app | |
| `mlops whoami` | the profile page in the web app | |
| `mlops enroll` | `clearml-init` | |
| `mlops sync` (sending a spool) | `Task.set_offline(True)` to work without a server, then `Task.import_offline_session(...)` | confirm the names against the SDK version pinned by the port |

The method names above are ClearML SDK names. Check them against the SDK version the port pins before you rely on them, since names and arguments change between releases.

## What is lost, and what to do instead

These follow the gap table in `idp-integration-report.md`, section 5a. They were accepted as decisions, not oversights.

- **Per-project access (row 13).** ClearML's open-source server has company-wide access and a public flag, not a member list per project. Anyone in the company can see every project. Do not put data in a project that must be private to a group.
- **Datasets and Git or DVC (row 14).** ClearML's dataset model does not link a run to a Git commit or a DVC hash the way `mlops` did. Record the commit yourself: `task.set_parameter("git_commit", commit)` or a tag on the task.
- **Dispatch model (row 15).** The UI dispatch and the `mlops dispatch` command are replaced by queues and agents. A job runs where an agent listens, not where you pressed the button.
- **Web interface (row 16).** The web app looks and behaves differently. Learn it once; the pages you use most are experiments (tasks), models and datasets.

## Checklist for one script

1. Replace the import: `import mlops` becomes `from clearml import Task`.
2. Replace `mlops.init` with `Task.init`, and keep the names of your project and run.
3. Replace each log call with the table above.
4. Run it once on your machine (`clearml-init` first). Check that the run appears in the web app with its metrics and artifacts.
5. Only then point a queue at it.

## Who to ask

The owner of the ClearML fork (the port's maintainer) answers questions about this guide and about access.

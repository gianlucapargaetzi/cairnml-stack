# MLOps Flow

Our experiment tracking, remote jobs and dataset setup, on a modified fork of [ClearML](https://clear.ml). MLOps Flow is not ClearML and is not endorsed by ClearML, Inc.; see [DISCLAIMER.md](DISCLAIMER.md).

- **Track** a training script with a few lines of Python: metrics, parameters, logs and artifacts are recorded on our server.
- **Explore** runs in the web app.
- **Run** jobs on agents that we operate. A job waits in a queue until an agent that listens to that queue takes it.
- **Version** datasets with git and DVC. A dataset is a git repository, its commit is its version, and every run records the commit it used.
- **Sign in** with our identity provider (Keycloak). Each machine has its own key; nobody copies access keys.

This repository holds the setup: the sign-in service, the ClearML server, and the scripts to start them. The ClearML code itself is in four forks, included as submodules (below).

## What is where

| Path | What it is |
|---|---|
| `deploy/compose.yaml` | The whole stack: Keycloak (sign-in), and the ClearML server built from our forks |
| `deploy/idp/realm-mlops.json` | The realm, with the ClearML clients |
| `deploy/scripts/bootstrap.sh` | Sets up the stack on a host |
| `deploy/scripts/teardown.sh` | Removes the stack and this machine's keys (`--dry-run` first) |
| `deploy/scripts/check-clearml-secrets.sh` | Fails if a secret is committed to a ClearML repository |
| `clearml-server`, `clearml-web`, `clearml`, `clearml-agent` | Our forks, as submodules |
| `clearml/docs/datasets.md` | How datasets work: `clearml-dataset`, `Dataset.get`, outside datasets, the cache |
| `external-datasets` (its own repository, not a submodule) | One pin file and one adapter per outside dataset (Hugging Face, git, local folders), with the tests that keep its `main` working |

The old platform (`mlops`) is removed from this branch. It is still in the history of `main` until the cut-over.

## Requirements

On the server host: Linux (`bootstrap.sh` uses `getent`), Docker Engine with Compose v2.20 or newer, `git`, `openssl`, `python3` and `curl`.

On the machines of users and agents: Python 3 and `git`; the SDK and agent install from source. Agents also need Docker for jobs that run in containers.

The four forks are git submodules at the root of this repository, on their `main` branches. Clone the repository with its submodules:

```bash
git clone --recurse-submodules git@github.com:gianlucapargaetzi/mlops-framework.git
# or, after a plain clone:
git submodule update --init
```

The four forks are private repositories, so the submodule step needs access to them (`gianlucapargaetzi/clearml-server`, `clearml-web`, `clearml` and `clearml-agent`). Without that access the clone still works, but the submodules stay empty.

Each fork has `origin` (our private copy) and `upstream` (ClearML, fetch only). To take ClearML changes: `git -C <fork> fetch upstream --tags`.

## 1. Server

### Host names

The sign-in service and the server are reached by name, and the name must be the same on every machine. Add this line to `/etc/hosts` on the server host, and on every other machine that uses the server, with the server's address in place of `127.0.0.1` on the other machines:

```
127.0.0.1 mlops-idp mlops-clearml
```

`bootstrap.sh` refuses to run until both names resolve.

### Start

```bash
cd deploy
./scripts/bootstrap.sh
```

The first run takes a while: it builds the ClearML images from the forks. It does the following, and prints nothing secret:

1. Starts Keycloak with the `mlops` realm, and sets the admin login from `deploy/.env` (created on the first run with a generated password).
2. Writes the ClearML secrets to `deploy/secrets/clearml/` (once; they are kept on later runs): the token and session keys. If `deploy/secrets/github-app.pem` exists, it is copied there as the GitHub key.
3. Creates the three ClearML clients in Keycloak (`clearml-web`, `clearml-sdk`, `clearml-server`) and updates them to `deploy/idp/realm-mlops.json` on every run. It stores the secret of `clearml-server` (used to read users from Keycloak) in `deploy/secrets/clearml/idp_directory_secret`.
4. Starts the ClearML server (`deploy/compose.yaml`).

Check that the server answers:

```bash
curl -X POST http://mlops-clearml:8008/v2.8/login.supported_modes -H 'Content-Type: application/json' -d '{}'
```

### First sign-in

Open `http://mlops-clearml:8080`. You are sent to the sign-in page of Keycloak. Sign in as the admin user named by `KC_ADMIN` in `deploy/.env`, with the password from the same file. Your ClearML account is created at that first sign-in.

Admins are the users with the `mlops-admin` role in Keycloak. Give other people the role, or leave them as plain users. Keycloak's admin console is at `http://mlops-idp:8180`.

### Optional: GitHub

Jobs that clone a GitHub repository need a GitHub App. Put its private key in `deploy/secrets/github-app.pem`, set `GITHUB_APP_ID` in `deploy/.env`, and run `./scripts/bootstrap.sh` again. Then restart the API server:

```bash
docker compose -f deploy/compose.yaml up -d --force-recreate apiserver
```

Without the App, jobs that clone a repository are refused when they are enqueued.

Jobs that use a dataset clone its repository too. List the dataset repositories, and the `external-datasets` repository, in the server setting `apiserver.idp.dataset_repositories` (`owner/name`, or `owner/*` for all of an owner's), set the same way as the other `apiserver.idp` settings, and install the App on them. A job gets a read-only token for a listed repository only; a person uses their own git login.

### Addresses and https

The addresses are set in `deploy/compose.yaml` (`CLEARML__apiserver__idp__*`): the web app at `http://mlops-clearml:8080`, the API at `http://mlops-clearml:8008`. To serve over https, change those addresses to https, and set `CLEARML_COOKIE_SECURE=true` in `deploy/.env`. The server refuses to start with https addresses and an insecure session cookie.

### Keep the data

The server's data is in `deploy/data/` and its keys in `deploy/secrets/`. Both are git-ignored. Back up both folders; losing `deploy/secrets/clearml/token_secret` signs everyone out, and losing the database loses the runs.

### Object storage and the NAS

Object storage (RustFS, with the buckets `dataset`, `model`, `artifact` and `debug`) runs in this stack, on the server host, and keeps its data in `deploy/data/rustfs`. Artifacts, models and debug data move through presigned URLs. The files of datasets move through DVC, with short-lived keys that the server issues for the `dataset` bucket only (`datachunks.dataset_credentials`), so no access key is stored on a machine. Run `deploy/scripts/bootstrap.sh` again after an update: it gives the server's storage user the policy for issuing those keys. The architecture diagram (`docs/architecture/`) shows it on a separate NAS, which is not set up yet. To move it, change the `rustfs` volume in `deploy/compose.yaml` to the NAS path, and set `MLOPS_STORAGE_PUBLIC_URL` in `deploy/.env` to an address that clients can reach.

## 2. Client (a person's machine)

Install the SDK from the fork, in a virtual environment:

```bash
cd clearml   # from the root of this repository
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Sign in and enrol the machine once, naming the server on the command line. Your browser opens the sign-in page, and the sign-in always asks for your credentials:

```bash
clearml-init --server http://mlops-clearml:8008
clearml-whoami
```

`clearml-whoami` shows the user and the device this machine signs in as. It uses the device key, and needs no browser. The key is in `~/.clearml/device.key` (readable by you only); the configuration is `~/clearml.conf`. No access key is copied.

To enrol again, for example as another person, use `--force`. The previous device is revoked first:

```bash
clearml-init --server http://mlops-clearml:8008 --force
```

To sign this machine out, revoke it and remove its key:

```bash
clearml-logout
```

If the device cannot be revoked (for example, the server is unreachable), `clearml-logout` removes nothing, and you can run it again later.

The machine must be able to resolve `mlops-clearml` and `mlops-idp` to the server, as in "Host names" above.

Check it with a short run:

```python
from clearml import Task

task = Task.init(project_name="demo", task_name="first run")
logger = task.get_logger()
for step in range(10):
    logger.report_scalar(title="loss", series="train", value=1.0 / (step + 1), iteration=step)
task.close()
```

The run appears in the web app under the project `demo`, with its metrics.

### Datasets

A dataset is a git repository with a `data/` folder. Git holds the history, DVC holds the files in the `dataset` bucket, and the commit is the version. Install the extra (Python 3.9 or newer, and `git`):

```bash
pip install -e "./clearml[dataset]"
```

Create an empty repository on GitHub, clone it, and inside it:

```bash
clearml-dataset init                  # git tracking and file storage
cp -r /path/to/measurements data/     # your files
clearml-dataset status                # branch, and what is new, changed or deleted
clearml-dataset add                   # records data/ as it is now, deleted files included
clearml-dataset commit -m "March measurements"
clearml-dataset push                  # the files first, then the commits
```

A script uses a version by its commit. The run records the repository, the commit and a hash of the files, and the files are kept in a per-user cache, so a second run does not download them again:

```python
from clearml.datasets import Dataset

data = Dataset.get("https://github.com/acme/cars-data.git", "3f2a9c1")   # a commit, not a branch, to rerun it later
print(data.path)
```

Outside datasets (Hugging Face, git, a local folder) are read through adapters in the `external-datasets` repository, into one standard shape of samples with named modalities and typed labels:

```python
data = Dataset.get_external("coco-det")            # the latest main of external-datasets
data = Dataset.get_external("coco-det", "a1b2c3d") # a fixed commit, to rerun an earlier run exactly
```

The cache is `~/.clearml/cache/datasets`, limited to 50 GB by default (`clearml-dataset cache info`, `cache limit 20GB`, `cache clean`). See `clearml/docs/datasets.md` for the details, including how to write an adapter.

To enrol a second laptop, run `clearml-init --server ...` on it. Each machine has its own key. A lost machine is revoked by its owner or an admin with the `devices.revoke` call of the API, and its key stops working at once. There is no page for this in the web app yet.

## 3. Agent (a machine that runs jobs)

An agent is enrolled by an admin, because it runs other people's code.

Install the agent from the fork, in its own virtual environment:

```bash
cd clearml-agent   # from the root of this repository
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Enrol it. An admin signs in when the browser opens; a non-admin is refused, and no configuration is written:

```bash
clearml-agent init
```

Then start the agent on a queue. It takes one job at a time from the queue and runs it:

```bash
clearml-agent daemon --queue default
```

Add `--docker` to run each job in a container, and `--gpus 0` to give the agent chosen GPUs. A machine with several GPUs can run one agent per GPU, each on its own queue. Run `clearml-agent daemon --help` for the rest, including services mode.

Each job runs with its own token, issued to this agent when the job starts. The agent renews it while the job runs, and the job never gets the agent's own token. The repository is cloned with a short-lived GitHub token for that one repository.

### In a container

The agent can also run as a container, in `deploy/agent/`. The agent container runs on the host's Docker daemon; it starts each job's container on a second daemon, in a privileged `dind` container. The host's daemon never runs a job and is not reachable from the jobs. Start it from `deploy/agent/`:

```bash
docker compose build agent
docker compose up -d dind
docker compose run --rm agent clearml-agent init
docker compose up -d agent
```

The server address in the agent's configuration must be reachable from inside `dind`: a LAN name or IP, not `localhost`. Only one agent may run per daemon. See `deploy/agent/README.md` for the layout, the volumes and the limits.

### Queues

A job waits in a queue until an agent that listens to it takes the job. The `default` queue exists from the start; create more in the web app (Workers & Queues), for example one per kind of machine.

Put a task in a queue from a script, or from the web app (enqueue on the task's page):

```python
from clearml import Task

task = Task.init(project_name="demo", task_name="training")
Task.enqueue(task, queue_name="default")       # run the recorded task on an agent
# or: task.execute_remotely(queue_name="default")   # stop this process and run the script on an agent
```

An agent takes one job at a time, so a job waits while its agent is busy. A machine that should run several jobs at once runs several agents, each on its own queue or GPU. The Workers page shows each machine, the task it runs and its live usage, and the Queues page shows what waits. A job that is waiting but never starts has no agent listening to its queue.

## 4. Web app

Open `http://mlops-clearml:8080`. To run the web app from its source for development, see `clearml-web/docs/dev-proxy.md`.

The dashboard lists the projects at the top and the recent experiments at the bottom. Double-click a project to open its dashboard: the project's tasks as folders at the top, and its recent experiments at the bottom. Double-click a task folder to list its experiments, numbered in the order they were created. "All experiments" lists every experiment in the project.

### Terms

- **Task**: a procedure, such as "train model X". Its runs are experiments, and they are grouped under it by name.
- **Experiment**: one execution of a task. Each run is an experiment, whether it was started from the web app, with `execute_remotely()` or `enqueue()`, or run locally with `Task.init`. Each experiment has its own id, metrics and artifacts.
- **Job**: one experiment taken from a queue by an agent, from the moment the agent starts it until it ends.

In the SDK and the API, the record of an experiment is still called a `Task`.

## 5. Checks

- `deploy/scripts/check-clearml-secrets.sh` fails if a secret, a private key or an `.env` file is committed to one of the ClearML repositories.

## 6. Troubleshooting

| Symptom | What to do |
|---|---|
| `bootstrap.sh` asks you to add a host line | Add the line from "Host names", then run it again |
| The server does not answer after bootstrap | Elasticsearch takes a minute to start. Check `docker compose -f deploy/compose.yaml logs apiserver` |
| Sign-in loops, or the web app shows a sign-in error | The addresses in `deploy/compose.yaml` must match the address you use in the browser |
| `clearml-init` says the machine is enrolled | The key file `~/.clearml/device.key` exists. Remove it only to enrol again, and revoke the old device in the web app |
| `clearml-agent init` is refused | Only an admin may enrol an agent. Ask an admin to run it |
| A job is refused when it is enqueued | The repository's commit is not on GitHub, or the GitHub App is not installed on it. The message says which |
| A job stays queued | No agent listens to its queue. Start `clearml-agent daemon --queue <name>`, and look for the worker on the Workers page |
| `Dataset.get` says a commit is not on the repository, or its files are not in storage | Push it: `clearml-dataset push`. A commit that exists only on one machine cannot be used by another |
| An adapter stops a run with a message that names it | The source changed its layout. Add an adapter for the new revisions and list them under `overrides` in the dataset's pin file in `external-datasets` |

## 7. Status

The setup is complete. Not yet verified end to end on a live stack: the browser sign-in for each kind of machine, and a job from enqueue through to its artifacts.

## 8. Tests

Two kinds: unit tests in each fork, and the end-to-end suite in `tests/e2e/`, which starts its own stack and checks the
whole workflow against it (see [docs/e2e_testing/E2E.md](docs/e2e_testing/E2E.md) and [docs/e2e_testing/E2E_TESTS.md](docs/e2e_testing/E2E_TESTS.md)).

### Unit tests

| Fork | Command | Notes |
|---|---|---|
| `clearml` (SDK) | `cd clearml && python -m pytest tests` | Runs without services. Last run: 87 passed. The dataset tests start git and DVC and take about a minute. |
| `clearml-agent` | `cd clearml-agent && python -m pytest tests --ignore=tests/requirements` | Needs the fork installed (`pip install -e .`). Last run: 7138 passed, 6 failed in `tests/package/test_task_script.py` (a missing file), which is not yet explained. `tests/requirements` does not import. |
| `clearml-server` | run in the server image, with MongoDB, Redis and Elasticsearch running (see below) | Without the services, 198 tests fail with "connection refused" on `127.0.0.1:27017`. |
| `clearml-web` | `cd clearml-web && npm ci && npm test` | Karma, which needs Chrome. Not run in the last check. |

To run the server's unit tests, start the stack's services and point the image at them. The simplest way is the
end-to-end stack's own compose project (its services are on a private network), or any MongoDB, Redis and Elasticsearch
reachable from the container. Mount `clearml-server/apiserver/tests` into the image and run pytest from `/opt/clearml`,
after creating `/var/log/clearml` (the logging configuration writes there).

### End-to-end tests

Prerequisites, and the full list of what the suite checks, are in [docs/e2e_testing/E2E.md](docs/e2e_testing/E2E.md). In short:

```bash
uv venv .venv --python 3.12
uv pip install -r tests/e2e/requirements.txt
uv pip install -e ./clearml -e ./clearml-agent
playwright install chromium

.venv/bin/pytest tests/e2e                 # everything: starts its own stack, about 70 minutes
.venv/bin/pytest tests/e2e -m "not slow"   # without the long checks
.venv/bin/pytest tests/e2e -k artifacts    # one area
```

The suite does not use `deploy/`. It needs Docker, nine free ports in 18000 to 18999 on the loopback interface, and the forks
checked out as submodules. Known failures are listed in [docs/e2e_testing/E2E_TESTS.md](docs/e2e_testing/E2E_TESTS.md) and as issues in each fork.

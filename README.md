# ClearML MLOps

Our experiment tracking, remote jobs and dataset setup, on a fork of [ClearML](https://clear.ml).

- **Track** a training script with a few lines of Python: metrics, parameters, logs and artifacts are recorded on our server.
- **Explore** runs in the web app.
- **Run** jobs on agents that we operate, from a queue.
- **Sign in** with our identity provider (Keycloak). Each machine has its own key; nobody copies access keys.

This repository holds the setup: the sign-in service, the ClearML server, and the scripts to start them. The ClearML code itself is in four forks (below). The design, the security checks and the migration are in [docs/clearml](docs/clearml/).

## What is where

| Path | What it is |
|---|---|
| `deploy/idp/` | Keycloak (sign-in) and the realm with the ClearML clients |
| `deploy/clearml/` | The ClearML server, built from our forks |
| `deploy/scripts/bootstrap.sh` | Sets up the sign-in service and the ClearML server on a host |
| `deploy/scripts/check-clearml-secrets.sh` | Fails if a secret is committed to a ClearML repository |
| `docs/clearml/` | Design, plan, security checklist, migration guide and cut-over runbook |

The old platform (`mlops`) is removed from this branch. It is still in the history of `main` until the cut-over.

## Requirements

On the server host: Linux (`bootstrap.sh` uses `getent`), Docker Engine with Compose v2.20 or newer, `git`, `openssl`, `python3` and `curl`.

On the machines of users and agents: Python 3 and `git`; the SDK and agent install from source. Agents also need Docker for jobs that run in containers.

The forks are checked out next to this repository, in the same parent folder:

```
Documents/
  mlops/              this repository
  mlops-clearml/
    clearml-server/   our fork of the server and the API (branch idp-port)
    clearml-web/      our fork of the web app (branch idp-port)
    clearml/          our fork of the Python SDK (branch idp-port)
    clearml-agent/    our fork of the agent (branch idp-port)
```

The forks are local checkouts; they have no remote yet. Keep them on `idp-port`.

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
4. Starts the ClearML server (`deploy/clearml/compose.yaml`).

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
docker compose -f clearml/compose.yaml up -d --force-recreate apiserver
```

Without the App, jobs that clone a repository are refused when they are queued.

### Addresses and https

The addresses are set in `deploy/clearml/compose.yaml` (`CLEARML__apiserver__idp__*`): the web app at `http://mlops-clearml:8080`, the API at `http://mlops-clearml:8008`. To serve over https, change those addresses to https, and set `CLEARML_COOKIE_SECURE=true` in `deploy/.env`. The server refuses to start with https addresses and an insecure session cookie.

### Keep the data

The server's data is in `deploy/data/` and its keys in `deploy/secrets/`. Both are git-ignored. Back up both folders; losing `deploy/secrets/clearml/token_secret` signs everyone out, and losing the database loses the runs.

## 2. Client (a person's machine)

Install the SDK from the fork, in a virtual environment:

```bash
cd ../mlops-clearml/clearml
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

To enrol a second laptop, run `clearml-init --server ...` on it. Each machine has its own key. A lost machine is revoked by its owner or an admin with the `devices.revoke` call of the API, and its key stops working at once. There is no page for this in the web app yet.

## 3. Agent (a machine that runs jobs)

An agent is enrolled by an admin, because it runs other people's code.

Install the agent from the fork, in its own virtual environment:

```bash
cd ../mlops-clearml/clearml-agent
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Enrol it. An admin signs in when the browser opens; a non-admin is refused, and no configuration is written:

```bash
clearml-agent init
```

Create the queue the agent should serve in the web app, then start the agent:

```bash
clearml-agent daemon --queue default
```

Each job runs with its own token, issued to this agent when the job starts. The job never gets the agent's own token, and the repository is cloned with a short-lived GitHub token for that one repository.

### Managed mode: resource-aware scheduling

Instead of a queue, a machine can run in managed mode. The server then offers the machine the tasks that fit it, and the agent runs each one in its own container with the CPUs, memory and GPUs of its reservation:

```bash
clearml-agent daemon --managed
```

The machine is one worker. The agent keeps a share of it for the operating system and the host services (by default 1 CPU and 10 % of RAM and disk). Each job is held to its reservation by Docker: its CPUs, a memory limit, its GPUs, and a process limit.

A task says what it needs, or nothing:

```python
from clearml import Task

task = Task.init(project_name="demo", task_name="training")
task.set_requirements(cpus=4, ram_gb=12, gpus=1, gpu_memory_gb=24, disk_gb=50, max_runtime_min=720)
task.set_priority(80)          # 0 to 100, higher runs first; default 50
Task.enqueue(task)             # no queue is needed
```

All of `cpus`, `ram_gb`, `gpus` and `disk_gb` are given together, or none is. A task with none runs alone on a machine.

A job that ends badly is reported with its reason: `oom` (out of memory, with the limit and the peak), `time_limit`, `gpu_error`, `disk_full` or `error`. The reason is on the task and in its log. A job whose machine is lost is retried once, then failed.

The Workers tab shows each machine with its live usage; expanding a machine shows its jobs. The Jobs tab lists the running and waiting jobs, and says why a waiting job waits.

## 4. Web app

Open `http://mlops-clearml:8080`. To run the web app from its source for development, see `clearml-web/docs/dev-proxy.md`.

## 5. Checks

- `deploy/scripts/check-clearml-secrets.sh` fails if a secret, a private key or an `.env` file is committed to one of the ClearML repositories.
- The security checks, with the test that proves each one, are in [docs/clearml/security-checklist.md](docs/clearml/security-checklist.md).

## 6. Troubleshooting

| Symptom | What to do |
|---|---|
| `bootstrap.sh` asks you to add a host line | Add the line from "Host names", then run it again |
| The server does not answer after bootstrap | Elasticsearch takes a minute to start. Check `docker compose -f deploy/clearml/compose.yaml logs apiserver` |
| Sign-in loops, or the web app shows a sign-in error | The addresses in `deploy/clearml/compose.yaml` must match the address you use in the browser |
| `clearml-init` says the machine is enrolled | The key file `~/.clearml/device.key` exists. Remove it only to enrol again, and revoke the old device in the web app |
| `clearml-agent init` is refused | Only an admin may enrol an agent. Ask an admin to run it |
| A job is refused at the queue | The repository's commit is not on GitHub, or the GitHub App is not installed on it. The message says which |

## 7. Status

The setup is complete, and the checks in `docs/clearml/security-checklist.md` are written and mostly passing. Not yet verified end to end on a live stack: the browser sign-in for each kind of machine, and a job from a queue through to its artifacts. Those are the checks of the review in `docs/clearml/cutover.md`.

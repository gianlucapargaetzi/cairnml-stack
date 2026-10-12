# Runbook

From an empty machine to a reproduced experiment. Each step names the command to run. Commands are written as `mlops ...`; from the repository root run them as `uv run mlops ...` unless you activated `.venv`.

**Status.** The steps below were checked against the command help (`--help`) and the source code. The live compose stack has not been run from this runbook yet. Every step that needs the running stack is marked *(not yet verified live)*. If a step fails, fix the runbook together with the code.

Terms: an **agent** runs jobs, a **project** groups **tasks**, an **experiment** is one run with one set of parameters, a **job** is a request to run an experiment on an agent. See ARCHITECTURE.md section 0.

---

## 1. Prerequisites

- Docker with Compose v2.20 or newer (`docker compose version`).
- `uv` (Python package manager), `openssl`, `git`.
- A GitHub account that may create a GitHub App on the organization (or on your GitHub Enterprise instance).
- Your user must be able to use the Docker daemon without sudo, because the agent mounts `/var/run/docker.sock`.

## 2. Hostnames *(not yet verified live)*

The role hostnames must resolve to this machine, so that the host and the containers see the same URLs. Add one line to `/etc/hosts` (needs sudo, once):

```
127.0.0.1 mlops-server mlops-idp mlops-nas
```

`deploy/scripts/bootstrap.sh` checks this and prints the line to add if it is missing.

## 3. GitHub App *(not yet verified live)*

The server reads repositories through a GitHub App. Without it, dispatching a job that clones code is refused (see troubleshooting). The server starts without it.

1. On GitHub, go to **Settings → Developer settings → GitHub Apps → New GitHub App** (on an organization, use the organization's settings).
2. Under **Repository permissions**, set **Contents: Read-only**. Set nothing else. Turn off the webhook.
3. Create the App, then **Generate a private key**. A `.pem` file is downloaded.
4. **Install** the App on every repository that jobs may clone. Include the DVC data repository.
5. Put the key in place and note the App ID (shown on the App's page):

   ```
   mkdir -p deploy/secrets
   cp ~/Downloads/<downloaded-name>.private-key.pem deploy/secrets/github-app.pem
   ```

   The `deploy/secrets/` directory is git-ignored.

6. In `deploy/.env` set:

   ```
   GITHUB_APP_ID=<the App ID>
   ```

7. For GitHub Enterprise only, also set (the defaults are for github.com):

   ```
   GITHUB_API_URL=https://<host>/api/v3
   GITHUB_WEB_URL=https://<host>
   ```

   `GITHUB_API_URL` is used by the server. `GITHUB_WEB_URL` is used by the agent to build clone URLs, so recreate the agent too after you change it.

8. Restart the server. The key file is read at startup, and `up -d` does not recreate a container when only a mounted file changed, so force the recreate:

   ```
   docker compose -f deploy/compose.yaml up -d --force-recreate mlops-server
   ```

   For GitHub Enterprise, add `mlops-agent` to the same command.

## 4. Start the stacks *(not yet verified live)*

```
uv sync --all-packages
deploy/scripts/bootstrap.sh
```

`bootstrap.sh` does the following, in order:

- checks Docker, Compose, `openssl` and `uv`, and the hosts line from step 2;
- creates the `mlops` Docker network if missing;
- creates `deploy/secrets/signing.pem` (the key the server signs access tokens with) if missing;
- creates `deploy/.env` from `deploy/.env.example`, with generated passwords for Keycloak, MinIO, the MinIO service user and PostgreSQL, and builds the client wheels into `$MLOPS_AGENT_HOME/wheels`;
- starts the IdP, MinIO, PostgreSQL and the server.

**The realm admin user.** The committed Keycloak realm contains no users. `bootstrap.sh` creates the realm user `admin` with the realm role `mlops-admin` and prints a generated password **once**. Write it down; it is not stored in any tracked file, and you need it for step 5. If the script reports that `admin` already exists, its password is unchanged and you must use the password you already have, or reset it in the Keycloak console.

**Other users are created by you.** Open the Keycloak admin console at `http://mlops-idp:8080`, sign in to the `master` realm with `KC_ADMIN` and `KC_ADMIN_PASSWORD` from `deploy/.env`, and switch to the realm **mlops**. Under **Users**, create the user, set a password under **Credentials** (turn off "Temporary"), and for administrators add the realm role **mlops-admin** under **Role mapping**. A user can be added to a project only after running `mlops enroll` once (step 5), because the server creates the user record at enrollment. Until then `mlops admin project-add-member` answers `404 user not found`. Roles are kept in step with the IdP by the directory sync (once a minute, or at once with `mlops admin sync-users`, section 14), so a role change needs no re-enrollment.

The bootstrap script ends by waiting for the server health check. Check it yourself:

```
curl -fsS http://mlops-server:8000/api/v1/healthz
```

## 5. Enroll yourself *(not yet verified live)*

```
uv run mlops enroll --server http://mlops-server:8000
```

A browser opens for the IdP login. Sign in as `admin` with the password printed in step 4 (or as your own user). The client generates a key, sends the public key to the server, and stores the key as `key.pem` under `~/.config/mlops/` (or `$MLOPS_CONFIG_DIR`). The private key never leaves this machine.

Then:

```
uv run mlops whoami
```

prints `client <id> (admin=True)` for the admin. It uses the key only and needs no login.

To enroll the same machine again, use `--force`.

## 6. Create a project and add people *(not yet verified live)*

Run these as the admin, on the enrolled admin machine:

```
uv run mlops admin project-create vision/seg
uv run mlops admin project-add-member vision/seg dev
```

`project-add-member` takes the Keycloak username. That user must have run `mlops enroll` once (step 5). `project-create` takes `--name` for a display name; the slug is the identifier.

## 7. Enroll the agent (admin only) *(not yet verified live)*

The agent enrolls with a one-time token that only an admin can create. The token is printed alone, so it can be captured in a variable:

```
TOKEN=$(uv run mlops admin agent-token --queue default)
```

The token expires after 900 seconds (`--ttl` changes this). Put it in `deploy/.env`, and start the agent before it expires:

```
MLOPS_AGENT_ENROLL_TOKEN=<the token>
```

```
docker compose -f deploy/compose.yaml up -d mlops-agent
```

The agent container's entrypoint runs `mlops-agent enroll` on its first start, when no agent state exists yet. Once enrolled, the token is no longer used and can be cleared from `deploy/.env`.

Confirm the agent is registered:

```
uv run mlops admin agents
```

The agent name is `MLOPS_AGENT_NAME` (default `local-agent`).

## 8. First tracked run *(not yet verified live)*

Save as `first_run.py` in any directory:

```python
import mlops

exp = mlops.init(project="vision/seg", name="first-run", config={"lr": 0.1})
for step in range(3):
    exp.log_metric("loss", 1.0 / (step + 1), step=step)
print("first run finished")
with open("model.txt", "w") as f:
    f.write("weights")
exp.upload_artifact("model.txt", path="model.txt")
exp.close()
```

Run it with plain Python: `python first_run.py`. The run is recorded on the server.

```
uv run mlops ls --project vision/seg
uv run mlops logs <experiment id>
```

`mlops ls` shows the experiment IDs. `mlops logs -f` follows a run that is still going.

## 9. Repository setup for datasets *(not yet verified live)*

Datasets are DVC-tracked paths in a Git repository. The framework stores only references. Inside a clone of the project's code repository (it needs at least one commit, and DVC installed with `pip install 'mlops-client[dvc]'`):

```
uv run mlops repo init --project vision/seg
dvc add data/train
git add .mlops data/train.dvc data/.gitignore .dvc
git commit -m "add training data"
git push
uv run mlops data push data/train
```

`repo init` writes `.mlops/project.yaml` and configures the DVC remote on the NAS, without credentials. `data push` and `data pull` get temporary storage credentials from the server. Commit the `.dvc` pointer and `.mlops/project.yaml`; never the data itself.

In your script, register the dataset (the path is relative to the working directory, and it must be DVC-tracked inside the Git repository):

```python
exp.use_dataset("data/train")
```

## 10. Reproduce remotely *(not yet verified live)*

Remote execution needs the code commit on GitHub, because the agent clones it. Push first, then:

```
git push
uv run mlops dispatch <experiment id> --queue default
```

`--queue` must be a queue the agent serves (step 7 used `default`). Resource requests are `--cpu`, `--memory-gb`, `--gpu` and `--label`.

From inside the script, the same thing as a call at the point where the run should continue remotely:

```python
exp.execute_remotely("default")
```

Outside an agent this dispatches the script's experiment and ends the local process; inside an agent it does nothing.

**Compose-based jobs.** A job with runtime type `compose` runs `docker compose up --build --abort-on-container-exit --exit-code-from <service>` in the job's workspace. Compose only receives the agent environment that the agent passes (`PATH`, `HOME`, Docker settings), plus the job variables. The service must forward these variables in its `environment:` list, and must join the job network:

- `MLOPS_SERVER_URL`, `MLOPS_RUN_TOKEN`, `MLOPS_EXPERIMENT_ID`, `MLOPS_JOB_ID`, `MLOPS_PARAMS`;
- the external Docker network **`mlops-jobs`**, not `mlops`. The agent is configured so that job containers join only `mlops-jobs`, which the server also joins. Postgres, MinIO and Keycloak are on `mlops`, and jobs must not reach them.

```yaml
services:
  train:
    build: .
    environment:
      - MLOPS_SERVER_URL
      - MLOPS_RUN_TOKEN
      - MLOPS_EXPERIMENT_ID
      - MLOPS_JOB_ID
      - MLOPS_PARAMS
    networks: [jobs]
networks:
  jobs:
    name: mlops-jobs
    external: true
```

Job specs use `runtime: {type: compose, file: compose.yaml, service: train}`. *(Not yet verified live.)*

## 11. Offline work *(not yet verified live)*

When the server is unreachable, the SDK keeps working:

- metrics, parameters and artifacts from a local run are spooled under the client data directory (`~/.local/share/mlops`, or `MLOPS_DATA_DIR`);
- dispatching does not work offline and fails with `cannot dispatch while the server is unreachable`.

When the server is back, upload the spooled runs:

```
uv run mlops sync
```

## 12. Moving roles to their own machines *(not yet verified live)*

The default setup runs every role on one machine. Each role can move to its own machine. Nothing in the code or config changes, because every URL already uses the role hostnames (`mlops-server`, `mlops-idp`, `mlops-nas`).

| Role | Machine | Compose file | `.env` values it needs | Open ports |
|---|---|---|---|---|
| Identity | machine 5 | `deploy/idp/compose.yaml` | `KC_ADMIN`, `KC_ADMIN_PASSWORD` | 8080 |
| NAS | machine 3 | `deploy/nas/compose.yaml` | `MINIO_ROOT_*`, `MLOPS_S3_*` | 9000 |
| Server | machine 2 | `deploy/server/compose.yaml` | `POSTGRES_PASSWORD`, `MLOPS_*_URL`, `GITHUB_*`, `MLOPS_S3_*`, `deploy/secrets/` | 8000 |
| Agent | machine 4 | `deploy/agent/compose.yaml` | `MLOPS_SERVER_URL`, `MLOPS_AGENT_*` | none inbound |
| Client | machine 1 | `pip install mlops-client` (or the wheel from `deploy/scripts/build-wheels.sh`) | none (`mlops enroll`) | none |

On each machine:

1. `docker network create mlops`.
2. Copy the relevant values from `deploy/.env` (the same passwords and URLs on every machine).
3. Point DNS, or `/etc/hosts`, for `mlops-server`, `mlops-idp` and `mlops-nas` at the machines that run those roles.
4. Start only that role's compose file.

The dashboard (section 13) is served by the Server, so it moves with the server role. When the Server moves to another hostname, the `MLOPS_IDP_SYNC_*` settings and the `mlops-web` redirect URIs in the IdP must use the final server hostname: `<MLOPS_SERVER_URL>/ui/auth/callback` for the redirect, and the sync client secret from `deploy/.env` on both the IdP and the Server.

**Not solved by moving roles:**

- **Job network is single-host.** Job containers join the `mlops-jobs` Docker network. A Docker network exists on one host only, so the agent and the server must run on the same Docker host for jobs to reach the server. Job networking across hosts is not built.
- **TLS is not configured.** All URLs are plain HTTP. Before you expose anything beyond one trusted LAN, put TLS in front of the server, the IdP and MinIO (a reverse proxy per stack), and change the Keycloak realm users and passwords.
- **Keycloak runs in development mode** (`start-dev`), and its port 8080 is published on all host interfaces. The MinIO S3 API (9000) is on the LAN; the MinIO console (9001) is on loopback only.

## 13. Dashboard *(not yet verified live)*

The dashboard is a read-only web view served by the server. Open it in a browser:

```
http://mlops-server:8000/ui/
```

The hosts entry from step 2 is enough. With no session, the page sends you to the Keycloak login. Log in with a realm user: the `admin` user from step 4, or any user you created there. There is no separate dashboard account. The session lasts 8 hours; **Log out** in the header ends it.

What the pages show:

- **Overview:** job counts by status, and projects with their run counts and last activity.
- **Projects and jobs:** the projects you may see, and their jobs.
- **Agents:** liveness and current load of each agent.
- **Experiments:** the list. Open one for metric charts, parameters, code and data versions, and live logs of a running job.
- **Comparison:** in the experiment list, tick 2 to 10 experiments and press **Compare selected**. The comparison shows their metrics, parameters and environment side by side.
- **Admin:** read-only lists of users and agents, for admins only.

The dashboard cannot start or cancel jobs. Use the CLI for that (sections 8 and 10).

The end-to-end browser tests (`tests/e2e`) log in as the realm users `admin`, `dev`, `eve` and `carol`. Their passwords are not in the repository: the tests read them from `MLOPS_E2E_PASSWORD_<USER>` in the environment, for example `MLOPS_E2E_PASSWORD_DEV`. Set those variables to the passwords you gave the users.

## 14. User lifecycle *(not yet verified live)*

Users are managed in the IdP. The server follows the IdP through a directory sync: it checks every known user once a minute (`IDP_SYNC_INTERVAL`, default 60 seconds), and it needs `IDP_SYNC_SECRET` in `deploy/.env` (bootstrap.sh generates it).

**Disable a user.**

1. Open the Keycloak admin console at `http://mlops-idp:8080`. Sign in to the `master` realm as `kcadmin`, with the password `KC_ADMIN_PASSWORD` from `deploy/.env`.
2. Switch to the realm **mlops**, open **Users**, open the user, switch **Enabled** off and save.
3. Either wait up to one minute, or run this as an admin on an enrolled machine:

   ```
   uv run mlops admin sync-users
   ```

   It prints the counts, for example `checked 4, disabled 1, re-enabled 0, roles changed 0, errors 0`.

**What gets revoked** for a disabled user:

- their client keys: CLI and SDK calls with those keys fail with `401`;
- their browser sessions: the dashboard login ends;
- their queued jobs: cancelled, with the message `owner was disabled`;
- their running jobs: asked to stop.

Deleting a user in the IdP counts as disabling it.

**Re-enable a user.** Switch **Enabled** on again. The next sync (or `sync-users`) makes the user active. The old client keys stay revoked, so the user must enroll a new key on each machine:

```
uv run mlops enroll --server http://mlops-server:8000 --force
```

**Change roles.** Change the realm roles in the IdP. The next sync applies them; no re-enrollment is needed.

**If the IdP is unreachable,** nothing is revoked. A user whose lookup fails is left unchanged and counted as an error. If the IdP answers that every known user is gone or disabled in one pass (for example because the directory URL is wrong), the sync disables nobody and logs a warning. The sync messages are in the server log: `docker compose -f deploy/compose.yaml logs mlops-server | grep "user sync"`.

The window between a change in the IdP and its effect is at most one interval.

## 15. Troubleshooting

Server errors quoted here are the exact messages.

| Symptom | Cause and fix |
|---|---|
| `401` on every call after `mlops enroll` | The client stores the server URL that the server reports as its public URL (`MLOPS_PUBLIC_URL`). That URL must be reachable from this machine. If the server was reconfigured, re-enroll with `mlops enroll --server ... --force`. |
| `mlops-idp` does not resolve, or the login page fails | Add the hosts line from step 2. |
| Agent does not start containers, or jobs fail with a Docker permission error | The agent mounts `/var/run/docker.sock`. Your user, or the agent's user, must be allowed to use the Docker daemon. |
| `422 commit not found on GitHub: push it first (<repo>@<sha>)` | The commit that the run used is not on GitHub. `git push`, then dispatch again. |
| `422 GitHub App is not installed on <repo>` | Install the GitHub App (step 3) on that repository. |
| `503 GitHub is not configured` | Set `GITHUB_APP_ID` and place the key at `deploy/secrets/github-app.pem` (step 3), then force-recreate the server. |
| `502 GitHub request failed` | The server could not reach GitHub or the GitHub Enterprise API. Check `GITHUB_API_URL` and the network. |
| `503 storage is not configured` | The server has no MinIO credentials. Check `MLOPS_S3_*` and that the `mlops-nas` service is up. |
| `404 user not found` from `project-add-member` | The user has not run `mlops enroll` yet (step 5). |
| Agent enrollment rejected, or `mlops-agent: not enrolled and MLOPS_AGENT_ENROLL_TOKEN is empty` | The token expired (900 seconds by default) or was already used. Create a new one with `mlops admin agent-token` (step 7). |
| `sync-users` answers `503` | `IDP_SYNC_SECRET` is missing in the server environment (the server reads it as `MLOPS_IDP_SYNC_CLIENT_SECRET`). Set `IDP_SYNC_SECRET` in `deploy/.env` (bootstrap.sh generates it), then `docker compose -f deploy/compose.yaml up -d --force-recreate mlops-server`. |
| Dashboard login loop (the login returns to the login page) | The redirect URI of the `mlops-web` client in the realm must equal `<MLOPS_SERVER_URL>/ui/auth/callback`. For the default host this is `http://mlops-server:8000/ui/auth/callback`. On another host, edit `deploy/idp/realm-mlops.json` before the first start, or change the Valid redirect URIs of `mlops-web` in the Keycloak console. |
| Keycloak did not pick up the new realm | Keycloak imports the realm file only when its data volume is empty. Reset it: `docker compose -f deploy/compose.yaml down -v mlops-idp`, then `up -d mlops-idp`. This deletes all Keycloak users, including `admin`: run bootstrap.sh again for `admin`, and create the other users again. Users recreated in the IdP get new IDs; the server then disables the old rows at the next sync, so those people enroll again. |
| Blank dashboard | Open the browser's developer console. The Content-Security-Policy forbids inline scripts, and the page loads its scripts only from `/ui/static/`. A Content-Security-Policy message there means the page was changed to use an inline script. An error from `/api/v1` usually means the session expired: log in again. |
| A job's environment is stale or its packages are wrong | The job venv is cached in Docker volumes named `mlops-venv-*`. Stop running jobs, then remove them: `docker volume ls -q -f name=mlops-venv- \| xargs -r docker volume rm`. |

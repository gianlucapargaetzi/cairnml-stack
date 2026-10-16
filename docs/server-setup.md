# Server setup

This guide sets up the server stack (identity, storage, database, server) and one agent on a single machine. The same steps work when each role runs on its own machine: see [runbook section 12](runbook.md#12-moving-roles-to-their-own-machines).

For the details behind each step, see the [runbook](runbook.md).

## 1. Prerequisites

- Docker with Compose v2.20 or newer (`docker compose version`). Your user must be able to use the Docker daemon without `sudo`, because the agent mounts `/var/run/docker.sock`.
- `uv`, `openssl`, `git`.
- A GitHub account that may create a GitHub App (only needed to clone repositories on agents).

## 2. Hostnames

The role hostnames must resolve to this machine. Add one line to `/etc/hosts` (once, needs `sudo`):

```
127.0.0.1 mlops-server mlops-idp mlops-nas
```

## 3. Start the stack

```
uv sync --all-packages
deploy/scripts/bootstrap.sh
```

`bootstrap.sh` checks the prerequisites, creates the Docker network, the signing key and `deploy/.env` (with generated passwords), and starts the identity provider, storage, database and server. It prints the password of the first admin user. It is shown once; `deploy/.env` keeps it too.

Check that the server answers:

```
curl -fsS http://mlops-server:8000/api/v1/healthz
```

## 4. Create the first admin

The admin signs in through the identity provider. The realm starts empty, so `bootstrap.sh` creates the admin user named by `KC_ADMIN`, with the role `mlops-admin`. Use it in the next step.

Other people are created in the Keycloak console at `http://mlops-idp:8180` (realm `mlops`). See [runbook section 4](runbook.md#4-start-the-stacks).

## 5. Enroll your machine as admin

```
mlops enroll --server http://mlops-server:8000
mlops whoami
```

`enroll` opens a browser for the login. `whoami` should print `client <id> (admin=True)`.

## 6. Create a project

```
mlops admin project-create vision/seg
mlops admin project-add-member vision/seg <username>
```

A user can be added only after they have enrolled once, because the server creates their user record at enrollment.

## 7. Enroll an agent

The agent enrolls with a one-time token that only an admin can create:

```
TOKEN=$(mlops admin agent-token --queue default)
```

The token expires after 900 seconds. Put it in `deploy/.env` and start the agent before it expires:

```
MLOPS_AGENT_ENROLL_TOKEN=<the token>
```

```
docker compose -f deploy/compose.yaml up -d mlops-agent
```

Once enrolled, the token is no longer used and can be removed from `deploy/.env`. Confirm the agent is registered:

```
mlops admin agents
```

The agent is listed as `active` with its queue. The name is `MLOPS_AGENT_NAME` (default `local-agent`).

## 8. Optional: GitHub App

Without a GitHub App, jobs that clone a repository are refused. Jobs that run an image directly work without it. To set it up (create the App, install it on the repositories, put the key in `deploy/secrets/github-app.pem` and set `GITHUB_APP_ID` in `deploy/.env`), follow [runbook section 3](runbook.md#3-github-app). Then recreate the server:

```
docker compose -f deploy/compose.yaml up -d --force-recreate mlops-server
```

## 9. ClearML (the port)

The ClearML server, built from our forks of `clearml-server` and `clearml-web`, runs next to the mlops stack and signs people in through the same identity provider. It is in `deploy/clearml/compose.yaml`. It is started by `bootstrap.sh`, after the stack in section 3.

- **Hosts.** Add `mlops-clearml` to the same hosts line as the other host names (`127.0.0.1 mlops-clearml`). `bootstrap.sh` checks for it.
- **Forks.** The images are built from `../../mlops-clearml/clearml-server` and `../../mlops-clearml/clearml-web`, next to this repository. Set `CLEARML_SERVER_SRC` and `CLEARML_WEB_SRC` in `deploy/.env` to use other checkouts.
- **Secrets.** `bootstrap.sh` writes `secrets/clearml/token_secret` and `session_secret` (random, 600), copies `secrets/github-app.pem` to `secrets/clearml/github_app_key` if it exists, and writes `idp_directory_secret`, the secret of the read-only `clearml-server` client in Keycloak. The folder is mounted read-only in the API server and is git-ignored.
- **Keycloak clients.** The realm is imported only on Keycloak's first start, so `bootstrap.sh` creates the three `clearml-*` clients when they are missing, and gives the directory client the `view-users` role. Their definitions are in `deploy/idp/realm-mlops.json`.
- **Addresses.** Web app `http://mlops-clearml:8080`; API `http://mlops-clearml:8008`.
- **Signing in.** Open the web app; you are sent to the identity provider. On a laptop, run `clearml-init` once: the browser opens the sign-in page and the machine is enrolled, with no key to copy. An agent is enrolled with `clearml-agent init`, which only an admin can approve.

Until cut-over (see `docs/clearml/cutover.md`), the mlops stack keeps serving its own users. Do not move users to ClearML before the cut-over runbook says to.

## Troubleshooting

| Symptom | Where to look |
|---|---|
| `bootstrap.sh` asks you to add a hosts line | Step 2 |
| `whoami` says `cannot reach` the server | `curl` the health check; `docker compose -f deploy/compose.yaml ps` |
| Login loops back to the login page | [runbook troubleshooting](runbook.md#20-troubleshooting) |
| The agent is missing from `mlops admin agents` | `docker logs` of the agent container; the token may have expired |

For the rest, see [runbook section 20](runbook.md#20-troubleshooting).

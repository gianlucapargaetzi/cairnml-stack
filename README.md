# mlops

Self-hosted MLOps framework: experiment tracking with autologging, remote job dispatch to agents, Git + DVC datasets, and one identity provider for people. Every machine has its own identity: each client and agent holds an Ed25519 key, and the server issues short-lived tokens for it.

The design assumes five physical machines (client, server, NAS, agents, and the external services GitHub Enterprise and the identity provider). The same stack also runs on one machine for development. The architecture, the security model and the machine roles are described in ARCHITECTURE.md, which is kept with the design documents outside this repository.

## Quick start

Requirements: Docker with Compose v2.20+, `uv`, `openssl`, `git`.

1. Add the role hostnames to `/etc/hosts` (once, needs sudo):

   ```
   127.0.0.1 mlops-server mlops-idp mlops-nas
   ```

2. Install the Python packages and start the stacks:

   ```
   uv sync --all-packages
   deploy/scripts/bootstrap.sh
   ```

   The script prints the generated password of the Keycloak user `admin`. It is shown once.

3. Enroll this machine (a browser opens for the login):

   ```
   uv run mlops enroll --server http://mlops-server:8000
   uv run mlops whoami
   ```

The GitHub App, the agent and the first tracked run are covered in the runbook.

A web dashboard runs on the server at `http://mlops-server:8000/ui/`. Its four tabs are **Projects** (experiments, repository graph and datasets), **Datasets** (dataset cards and versions), **Jobs** (scheduled, running and finished jobs, with cancel and copy-and-reschedule) and **Resources** (agents and queues, with allocated and actual load). Runs (with metric charts, parameters, code and data versions and live logs) can be compared two to ten at a time. The dashboard writes only three things: it cancels a job, reschedules a job, and edits an experiment. Log in with a realm user through the same IdP login. Users are managed in the Keycloak console, and disabling a user there revokes their access within a minute. The runbook covers the dashboard (section 13), the user lifecycle (section 14), and projects and experiments, repository links, dataset cards, job control and resources (sections 15 to 19).

## Tests

```
uv run pytest                        # unit and integration tests, no Docker needed
uv run pytest -m docker              # tests that need a local Docker daemon
MLOPS_E2E=1 uv run pytest tests/e2e  # end-to-end tests against the running compose stack
```

The end-to-end suite needs the stack from the quick start and the settings described in [docs/e2e-test-repo.md](docs/e2e-test-repo.md).

## Documentation

- [docs/runbook.md](docs/runbook.md): from an empty machine to a reproduced experiment, moving roles to their own machines, and troubleshooting.
- [docs/glossary.md](docs/glossary.md): the terms used in the code, the CLI, the dashboard and the documentation, with one meaning each.
- Planned features that are not built yet are listed in `ROADMAP.md`, which is kept with the design documents outside this repository (next to ARCHITECTURE.md).

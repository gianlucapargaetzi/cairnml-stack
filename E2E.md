# End-to-end tests

The end-to-end suite checks the framework the way a person uses it: the stack runs, machines are enrolled through
the real sign-in page, runs are recorded, artifacts and datasets move between machines, agents run jobs, and the
web app shows all of it. Every test is listed, with what it checks, in [E2E_TESTS.md](E2E_TESTS.md).

The suite lives in `tests/e2e/`. It starts **its own stack** for each session and runs against that. It does not use
the stack under `deploy/`, and it does not read `deploy/.env`.

## What it needs

On the machine that runs the suite:

- Docker with Compose v2, and the images the stack uses (pulled on first use).
- The two forks checked out as submodules (`clearml-server`, `clearml-web`). The suite builds the `clearml-server-fork:local`
  image from them if it is not there yet.
- `python:3.12-slim` and `alpine:3.20` on the host (the job containers and helper containers use them).
- Python 3.12 with the suite's requirements and the two SDK forks:

  ```bash
  uv venv .venv --python 3.12
  uv pip install -r tests/e2e/requirements.txt
  uv pip install -e ./clearml -e ./clearml-agent
  playwright install chromium   # or reuse a browser already in the Playwright cache
  ```

- Nine free ports in 18000 to 18999 on the loopback interface (`127.0.0.1`). The suite chooses them itself.

Optional, for the GitHub tests: `MLOPS_E2E_GITHUB_REPO=owner/name` names a repository on github.com that the GitHub
App can read; `MLOPS_E2E_GITHUB_PRIVATE_REPO=owner/name` names one it cannot. Without them, the `github`-marked tests
are skipped with that reason.

## How to run

```bash
.venv/bin/pytest tests/e2e                 # everything (about 70 minutes)
.venv/bin/pytest tests/e2e -k artifacts    # one area (module or test name)
.venv/bin/pytest tests/e2e -m "not slow"   # skip the long ones (large upload, 10-minute waits)
.venv/bin/pytest tests/e2e -m agent        # everything that needs the managed agent
MLOPS_E2E_KEEP_STACK=1 .venv/bin/pytest tests/e2e/test_00_isolation.py   # keep the stack for inspection
```

Markers (`tests/e2e/pytest.ini`): `agent`, `docker`, `ui`, `github`, `slow`.

The first step of a session is the stack: about 3 to 5 minutes to start (Elasticsearch is the slow one). If it does not
come up, the session stops there and prints the last log lines of the failing service. With `MLOPS_E2E_KEEP_STACK=1`
the stack and its state folder are left in place, and the session prints where they are.

## The isolated stack

`tests/e2e/support/stack.py` starts the stack described in `tests/e2e/stack/compose.yaml`:

| Part | Isolation |
|---|---|
| Compose project | Named `mlops-e2e-<random>` for each session, so two sessions never share containers or networks. |
| Address | The loopback interface, `127.0.0.1`, only. Every service runs with host networking, so the containers and the host use the same addresses. The machine's own network address is never used, so a change of network does not affect the suite, and nothing is added to `/etc/hosts`. |
| Ports | Nine random free ports in 18000 to 18999: the API, the web app, the sign-in service and its management port, object storage, MongoDB, Redis, and Elasticsearch's HTTP and transport ports. Nothing in the stack uses the ports 8008, 8080, 8180 or 9000 that `deploy/` uses. |
| State | A temporary folder: data of Keycloak, RustFS, MongoDB, Redis and Elasticsearch, the secrets, and a copy of the realm with this stack's addresses. Removed at the end of the session. |
| Secrets | Generated for each session (token, session, S3 key). The directory-sync secret is read from the stack's own Keycloak. |
| Accounts | The admin (`e2e-admin`) gets a password generated for the session. It is a realm user with the `mlops-admin` role. The plain user of each session is created and removed by the suite. |
| Realm | The committed realm (`deploy/idp/realm-mlops.json`) read as a template, with its addresses replaced by this stack's. The suite's directory client gets `view-users`, as `bootstrap.sh` grants it. |
| Web app | Its API address is set to the web server's own `/api` route with `configuration.json` (see "Addresses" below). |

Only two things are shared with the rest of the machine: the Docker daemon, and the image cache. The job containers are
started by the managed agent on the host's Docker daemon, under the same label names as other agents' jobs (see
"Limits" below).

Teardown: `docker compose down --volumes`, then the state folder is removed. The state folder's files were written by
containers as other users, so they are first given back to this user, in a container, the same way `bootstrap.sh`
handles its folders.

`test_00_isolation.py` checks the claims above at run time: the addresses are not those of the deploy stack, and the
API answering is a container of this session's compose project.

## Addresses

The clients (the SDK, the CLI, the agent) take the API address as a command-line argument or from the stack's identity
settings, so nothing depends on a fixed address. Two things in this build assume the default ports, and the suite works
around them:

- The web app takes its API address from its own page address with port `8008` (`clearml-web`, `guessAPIServerURL`).
  The suite writes `{"apiBaseUrl": "/api"}` to the web server's `configuration.json`, which the image reads from
  `/mnt/external_files/configs/`. Without this, a stack on other ports sends its API calls to whatever answers on 8008 of
  the same host. Filed as `clearml-web` issue #3.
- `clearml-init --server <web address>` derives the API address from the web address for ports 8080 and 8008 only. The
  test for that is skipped on other ports (`test_02_enrolment.py::test_init_accepts_the_web_address_and_finds_the_api`).

## Limits

- **Job containers share the host's Docker daemon.** The agent stops "orphan" job containers at start-up by label
  (`clearml.job`), for any agent on the machine. A real agent and the suite's agent on one host would stop each other's
  orphans. Run the suite on a machine without a live agent of the deploy stack.
- **Agents run on the host.** The suite's agent is a process with its own `HOME`, device key and worker name; its jobs run
  in containers on the host's Docker daemon.
- **The GitHub tests need GitHub.** They are skipped unless the repository variables are set.

## How it is built

| Part | What it does |
|---|---|
| `conftest.py` | Starts the stack for the session (autouse), checks that its services answer, gives each session its own `HOME`, and enrols the test client through the real sign-in page. Creates the session project and deletes it, with its contents, at the end. |
| `support/stack.py` | Ports, state folder, secrets, realm copy, nginx template, compose calls, the identity bootstrap, health waits, teardown, and removal of the session's unused networks. |
| `stack/prune-networks.sh` | Removes every Docker network that no container uses, after showing them. Run it by hand after an interrupted run. |
| `support/settings.py` | Addresses and accounts of the running stack. Set at session start by `configure()`; nothing is read from `deploy/`. |
| `support/cli.py` | Runs the venv's console scripts and the example scripts with the session's `HOME`. Sets `BROWSER` so the sign-in page is opened by the headless browser (`support/browser.py`). |
| `support/browser.py` | Fills the identity provider's sign-in form in headless Chromium, as a person would. |
| `support/web.py` | Signs in to the web app in a fresh browser context. |
| `support/keycloak.py` | Creates, disables and removes the test accounts through Keycloak's admin API. |
| `support/api.py` | REST calls as a device: signs the assertion with the device key and exchanges it for a token. |
| `support/client.py` | A person's machine: `client.init()` runs `clearml-init`, and `whoami`, `logout` and the key helpers. |
| `support/agent.py` | A machine that runs jobs: `agent.init()` runs `clearml-agent init` (answered on stdin), and `AgentMachine` runs the managed daemon as a process. |
| `support/git.py` | Local git repositories: a bare remote and a checkout of it. |
| `support/workspace.py`, `support/jobs.py` | Running the example scripts and reading their JSON result; enqueueing and following jobs. |
| `scripts/` | The example scripts the tests run. Each prints one JSON line at the end. They are written as user code, so they also serve as examples. |

Rules the suite follows:

- **Read back in another process.** A check that a run, artifact, dataset or model is stored reads it in a new process,
  so the result is what the server kept, not what the writer still had in memory.
- **Clean up what it creates.** Everything lives in one project per session. Users and devices are removed by the
  session that made them. The stack itself is removed with its state.
- **Known defects are strict expected failures.** A test that fails because of a defect is marked `xfail(strict=True)`
  with the defect's number. When the defect is fixed the test turns into a failure ("XPASS strict"), and the marker is
  then removed. Nothing is silently skipped to hide a defect.
- **Skips say why.** The GitHub tests and the one web-address test skip with the reason in the report.

## Known defects

Each defect has an issue in the repository where the fix belongs. The tests named here are the ones that fail
because of it (strict expected failures) or that would.

| # | Issue | What happens | Tests |
|---|---|---|---|
| D1 | [clearml-agent #1](https://github.com/gianlucapargaetzi/clearml-agent/issues/1) | No job runs. The job container installs the upstream `clearml-agent` from PyPI, which cannot sign in to the server (`auth.login` is gone). | `test_09_jobs.py` (completion, failure, abort, lost agent, release), `test_06_git.py` (clone), `test_12_web_runs.py` (live status), GitHub clone test |
| D2 | [clearml-server #1](https://github.com/gianlucapargaetzi/clearml-server/issues/1) | Enqueue of a github.com repository returns 500: the GitHub App id is read as an integer. | `test_06_git.py::test_repository_on_github_is_refused_at_enqueue_without_the_app` |
| D3 | [clearml-server #2](https://github.com/gianlucapargaetzi/clearml-server/issues/2) | A stopped agent stays `active` until a scheduler pass runs. | `test_08b_agent_heartbeat.py::test_stopped_agent_is_marked_lost_by_the_timeout_alone` |
| D4 | [clearml #1](https://github.com/gianlucapargaetzi/clearml/issues/1) | `Dataset.add_files` on a finalized dataset is accepted, though finalized datasets are documented as immutable. | `test_07_datasets_models.py::test_finalized_dataset_refuses_new_files` |
| D6 | [clearml #2](https://github.com/gianlucapargaetzi/clearml/issues/2) | After any service call, `Task.enqueue` is refused ("upgrade clearml-server"). Enqueueing first works, which hides it. | `test_09_jobs.py::test_enqueue_works_after_the_task_was_read` |
| D7 | [clearml-agent #2](https://github.com/gianlucapargaetzi/clearml-agent/issues/2) | A machine with no device key logs a raw `Errno 2` instead of "run clearml-agent init". | `test_08_agents.py::test_agent_without_its_key_says_to_enrol_it` |
| Policy | [clearml-server #3](https://github.com/gianlucapargaetzi/clearml-server/issues/3) | A plain user can delete another user's run. Expected 403 until user access management exists (decided). | `test_05_artifacts.py::test_a_member_who_is_not_the_owner_cannot_delete_the_run` |
| Config | [clearml-web #3](https://github.com/gianlucapargaetzi/clearml-web/issues/3) | The web app assumes its API is on port 8008 of its own host. The suite works around it with `configuration.json`; no test fails without the workaround. | none (see "Not caught by a test") |

D5 is not a defect: `Task.set_parameters` replaces the whole parameter set, as its docstring says. The example script writes
the group first, and `test_set_parameters_replaces_the_whole_set_and_set_parameter_adds` documents the behaviour. It is not
filed.

### Not caught by a test

- **Config (clearml-web #3).** The workaround hides it. A test would need a stack that runs without the
  `configuration.json`, which is not what this suite does.
- **Fixed-port derivation in `clearml-init`.** Skipped on other ports, so it is not run here.

## Open results

- `test_05_artifacts.py::test_a_member_who_is_not_the_owner_cannot_delete_the_run` stays an expected failure until
  the 403 is implemented (clearml-server #3).
- `test_09_jobs.py::test_higher_priority_job_is_placed_before_a_lower_one` failed in the last full run: the lower
  priority job was placed first. It is not explained yet. Either the first job did not hold the machine's capacity as
  intended, or the scheduler does not order by priority here. It is a real failure, and it is not marked.

## Coverage and gaps

[E2E_TESTS.md](E2E_TESTS.md) lists every test. Still not written:

- Job monitoring while a job runs (usage, console growing, status changes): needs D1 fixed.
- Resource limits inside a job container, and the job's working folder being removed afterwards: needs D1 fixed.
- Dashboard "Unassigned" bucket and the "All experiments" flat list.
- Contrast checks in light and dark mode (the suite checks the painted background only).
- A test for the `configuration.json` requirement (see "Not caught by a test").

## Clean-up of a real stack

The suite does not touch the stack under `deploy/`. Earlier runs, made before the isolated stack existed, left records
there, and they have been removed: the probe project (through the API), 16 workers with their scheduler records
(directly in the database), four `no-project` tasks (through the API), and seven `e2e-member-*` user records (directly in
the database). The tracking test now deletes its own task.

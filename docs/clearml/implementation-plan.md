# Implementation plan: port mlops to a customised ClearML (executor: Haiku 5.5)

## Context

We are replacing our custom `mlops` platform with a fork of ClearML whose **only security layer is our Keycloak IdP** plus device keys and server-signed short-lived tokens, exactly as our current server works. The design, the gap table and the decisions are in `docs/clearml/idp-integration-report.md`, the spikes in `docs/clearml/spike-list.md`, the phases and estimate in `docs/clearml/port-plan.md` (all on branch `port/clearml` of this repo). This file turns them into tasks a smaller model can execute without making design decisions.

Decisions already taken (do not reopen): Option A (server verifies IdP tokens itself), cut over all clients at once, one fork owner (the user), per-project access and per-project storage are **later**, web sign-in uses a **server session cookie** with **SameSite=Strict + Origin check** (no CSRF token), job tokens are server-signed and **refused as soon as the job's status leaves queued/in_progress**, disabled users are refused within ~60 s (sync loop), agent enrolment is approved only by an admin (checked on the server), the pre-submission GitHub commit/App check is ported, audit log is added, secrets are files in one read-only mount, forks live **locally only** (no remote, never push).

## Rules for the executor (read first, obey always)

1. **Port, don't redesign.** Where a task says "port", copy our file, adapt imports and types to ClearML, keep the logic identical. If logic must differ, say why in the commit message.
2. **One task = one commit** in the repo being changed. Message: imperative sentence, then a short "why". **No attribution lines, no mention of any AI tool** (the repo owner's rule overrides any default).
3. **Tests first** for every security check: write the test, see it fail, implement, see it pass. A check without a failing-without-it test is not done.
4. **Never weaken a check to make a test pass.** Never add a test-only bypass to server code. Tests use a stub IdP and a real device key.
5. **Stop rules.** If a command fails twice after you tried a fix, or a file/function named here does not exist, write what you found into `~/Documents/mlops-clearml/BLOCKED.md` and STOP. Do not guess a path: run the "Discover" command given in the task and record the result in `NOTES.md`.
6. **Stay in scope.** Change only files named in the task plus new files under the new folders. No refactors, no formatting sweeps. If the repo has a formatter config (`pre-commit`, `black`, `ruff`), run it only on files you touched.
7. **Secrets.** Never commit a secret, key or `.env`. Never print a secret. Config reads secrets from files only.
8. **Never push.** No `git push`, no remote added to the forks.
9. **Gates.** Where the plan says `STOP-n`, finish the checklist, write the report (what was done, test output summary, open questions) to `~/Documents/mlops-clearml/REPORT-STOP-n.md`, print its path, and wait for the user.
10. Keep `~/Documents/mlops-clearml/NOTES.md` current: commands that worked, discovered paths, version tags.

## Workspace and naming

- Workspace: `~/Documents/mlops-clearml/` containing full clones `clearml-server`, `clearml-agent`, `clearml` (SDK), `clearml-web`. Branch `idp-port` in each, created from the **latest release tag**, not `master`.
- Our reference code (read-only): `/home/parg/Documents/mlops/packages/` (`mlops-server`, `mlops-common`, `mlops-client`). Our repo's `port/clearml` branch receives docs and deployment files only.
- New code goes in **new modules** so upstream merges stay small: server `apiserver/idp/`, `apiserver/services/devices.py`, `apiserver/apimodels/devices.py`, `apiserver/database/model/{device,audit}.py`; SDK `clearml/idp/`; agent `clearml_agent/idp/`.
- Server tests for new code: `apiserver/tests/idp/`. Run infrastructure (Mongo, Redis, Elasticsearch) from `clearml-server/docker/docker-compose.yml`.

## Reference map (what to port from where)

| Our file (`/home/parg/Documents/mlops/packages/…`) | Purpose | Goes to |
|---|---|---|
| `mlops-common/src/mlops_common/assertion.py`, `keys.py` | sign/verify device assertions, key pairs | `apiserver/idp/{assertion,keys}.py`, `clearml/idp/…`, `clearml_agent/idp/…` (identical copies) |
| `mlops-server/src/mlops_server/security/oidc.py` | `OidcVerifier` (JWKS, iss/aud/exp/nonce) | `apiserver/idp/oidc.py` |
| `…/security/tokens.py` (`TokenService`) | issue/verify access tokens | reuse ClearML `Token.create_encoded_token` in `apiserver/idp/tokens.py` |
| `…/security/deps.py` (`principal_dep`) | per-request checks: device revoked, user disabled, job status | `service_repo/auth/auth.py::authorize_token` |
| `…/routers/enroll.py`, `routers/auth.py` (`exchange`) | enrolment, assertion exchange, jti replay | `apiserver/services/devices.py` |
| `…/routers/admin.py` (`admin_only`, agent tokens) | admin-only agent enrolment | enrol endpoint admin check |
| `…/routers/web_auth.py` | OIDC code flow with PKCE, session cookie | `apiserver/idp/web_login.py` |
| `…/services/directory.py` | IdP user sync (60 s) | `apiserver/idp/directory.py` |
| `…/services/github.py`, `routers/jobs.py` (lines ~55–80) | App tokens, commit check | `apiserver/idp/github.py`, hook in `services/tasks.py` |
| `…/services/audit.py`, `models.py::AuditEvent` | audit events | `apiserver/idp/audit.py`, `database/model/audit.py` |
| `…/testing.py` (FakeIdP, ~lines 30–100) | stub IdP for tests | `apiserver/tests/idp/idp_stub.py` |
| `mlops-client/src/mlops/idp.py::device_login`, `enroll.py` | device login + enrol on the client | `clearml/idp/`, `clearml_agent/idp/` |
| `mlops-server/tests/test_tokens_and_deps.py, test_enroll_client.py, test_enroll_agent.py, test_user_sync.py, test_directory.py, test_github.py, test_web_login.py` | behaviour to reproduce | write equivalent tests under `apiserver/tests/idp/` |

## ClearML seams (verified in the code)

- Request auth: `apiserver/service_repo/validators.py::validate_auth` → `get_auth_func(auth_type)` in `service_repo/auth/auth.py` → `authorize_token` / `authorize_credentials`; result becomes `call.auth`, and `call.identity` is `Identity(user, company, role, user_name, company_name)` (`service_repo/auth/identity.py`). 14 files read `call.identity`; keep that object, change only how it is produced.
- Tokens: `service_repo/auth/payload/token.py::Token.create_encoded_token(identity, expiration_sec, entities, **extra_payload)` (PyJWT, secret from `secure.auth.token_secret`, **hard-coded default in `config/default/secure.conf`** — must be replaced); extra claims are merged into the payload; decode via `Token.decode`.
- Cookie: `server_init/request_handlers.py` (`_get_session_auth_cookie`, `before_request`); cookie name `apiserver.auth.session_auth_cookie_name` (`clearml_token_basic`).
- Endpoints: `@endpoint("service.action", authorize=…)` in `apiserver/services/*.py`; `authorize=False` skips auth (the endpoint must check itself). Services are loaded from the `services/` folder by `AppSequence._load_services` (`server_init/app_sequence.py`).
- Users/roles: `apiserver/database/model/auth.py` (`Role`, `User` with `role`); login placeholders `services/login/__init__.py::supported_modes` (`sso`, `sso_providers` empty); credential endpoints `services/auth.py`.
- Jobs: `services/tasks.py` (enqueue/started), `services/queues.py` (get_next_task), `services/workers.py::register`.
- File server auth is **off by default** (`fileserver.auth.enabled=false`); leave it off (storage is a later topic).
- Requirements: `apiserver/requirements.txt` has `pyjwt`, `requests`, `redis`, `mongoengine`; **add `cryptography`** (RS256).
- Tests: `apiserver/tests/api_client.py` authenticates with HTTP basic fixed users — this is the one place to change so the ~40 existing integration tests keep running.

## Phase 0 — workspace and baseline

**P0.0** Copy this plan to `/home/parg/Documents/mlops/docs/clearml/implementation-plan.md`, create `docs/clearml/spike-results.md` (headings S1–S14, empty), commit both on branch `port/clearml` of `/home/parg/Documents/mlops`.
**P0.1** `mkdir ~/Documents/mlops-clearml && cd` it. `git clone https://github.com/clearml/clearml-server.git`, same for `clearml-agent`, `clearml`, `clearml-web`. In each: `git tag --sort=-creatordate | head -5`; pick the newest stable tag (no `rc`/`dev`); `git checkout -b idp-port <tag>`. Record tags and `git rev-parse HEAD` in `NOTES.md` and spike S14.
**P0.2** Server baseline: start Mongo/Redis/Elasticsearch/apiserver from `docker/docker-compose.yml`. **Discover** the test command: `grep -rn "unittest\|pytest\|TestService" apiserver/tests/automated/__init__.py apiserver/tests/api_client.py README.md`, and read how tests pick host and credentials. Run the suite; record command and pass/fail counts in `NOTES.md` (spike S10). Known failures are listed, not fixed.
**P0.3** Agent, SDK, web baseline: find test commands (`ls .github/workflows tox.ini setup.py package.json`), install, run, record. Web: Node 24, `pnpm install --force --frozen-lockfile && pnpm run build`.
**P0.4** Discover and record in `NOTES.md` (spikes S2, S3, S7 inputs):
- Server: `grep -rn "redirect" apiserver/service_repo/apicall.py apiserver/server_init/*.py` (how to send a redirect + cookie); `sed -n 1,80p apiserver/apimodels/login.py` (shape of `sso_providers`); `grep -n "script\|repository\|version_num" apiserver/database/model/task/task.py | head`; fields that identify the worker of a queued/started task (`grep -n "last_worker\|execution" apiserver/database/model/task/task.py`); `ls apiserver/mongo/migrations | tail -3`.
- Agent: `grep -rn "access_key\|secret_key\|CLEARML_API\|api.credentials" clearml_agent | grep -v test`; `grep -rn "ask_pass\|git_pass\|git_user" clearml_agent/helper/repo.py clearml_agent/session.py`.
- SDK: `grep -rn "access_key\|secret_key\|auth.login\|api.credentials" clearml | grep -v test | head -60`; confirm `clearml/backend_api/session/{session,token_manager}.py` and `clearml/cli/config/__main__.py`.
- Web: `grep -rniE "login|credentials|supported_modes|sso_providers" src --include=*.ts -l`.

### STOP-1 (design check)
Report: baselines, tags, the discovered paths, and any finding that contradicts the report (for example the agent cannot use a token as git password, or the web app needs more than a redirect). **Do not write feature code before the user answers.**

## Phase 1 — server: identity layer (new code beside the old auth)

Old basic/credential auth stays working until P1.17. All new endpoints are new names; nothing existing is removed yet.

**P1.1 Secrets from files.** New `apiserver/idp/secrets.py`: `read_secret(name)` reads `/run/secrets-dir/<name>` (dir overridable by env `CLEARML_SECRETS_DIR`), strips one trailing newline, raises if missing. Use it for `token_secret` in `service_repo/auth/payload/token.py` (keep config fallback only when env `CLEARML_ALLOW_CONFIG_SECRET=1`, for tests) and **refuse to start if the secret equals the default literal in `secure.conf`**. Test: `tests/idp/test_secrets.py`.
**P1.2 Config.** Add section `idp { issuer, web_client_id, sdk_client_id, directory_client_id, admin_role: "admin", sync_interval_sec: 60, access_token_ttl_sec: 900, job_token_ttl_sec: 3600, public_url, company_name }` to `config/default/apiserver.conf`; read through `config.get`. Test that defaults load.
**P1.3 Crypto helpers.** Copy `mlops_common/assertion.py`, `keys.py` to `apiserver/idp/`; add `cryptography` to `requirements.txt`. Port our assertion tests (sign/verify, wrong audience, expired, tampered, missing `jti`).
**P1.4 IdP verifier.** Port `security/oidc.py` to `apiserver/idp/oidc.py` using `requests` (JWKS fetched with a TTL cache; check `iss`, `aud`/`azp`, `exp`, optional nonce). Copy `FakeIdP` from our `testing.py` to `tests/idp/idp_stub.py` (RSA key, JWKS on a localhost thread, `make_token(claims)`). Tests: valid, wrong issuer, wrong audience, expired, bad signature, unknown `kid`.
**P1.5 Models.** `apiserver/database/model/device.py`: `Device` (`id` like `dev_<hex>`, `user`, `company`, `kind` in `client|agent`, `name`, `public_key`, `created`, `last_used`, `revoked`). In `database/model/auth.py::User` add `idp_subject` (unique, sparse) and `idp_disabled` (bool, default False). Add a migration only if the baseline's migration folder requires one (see P0.4). Test: create/read, uniqueness.
**P1.6 User provisioning.** `apiserver/idp/users.py::upsert_idp_user(identity)`: deterministic id (`uuid5(NAMESPACE_URL, issuer + "|" + sub).hex`), single company (reuse the default company helper used by `fixed_user.py`), `name` from `preferred_username`, role `Role.admin` if `admin_role` in the token's roles else `Role.user`. Test: first sight creates, second sight updates role.
**P1.7 Replay store.** `apiserver/idp/replay.py::claim_jti(jti, ttl)` using `redman.connection("apiserver")` with `SET key NX EX`. Test: second claim of the same `jti` returns False.
**P1.8 Audit.** `apiserver/database/model/audit.py` (`AuditEvent`: ts, actor, device, action, ip, details) and `apiserver/idp/audit.py::record(...)`, ported from our `services/audit.py`. Test: record then query.
**P1.9 Access tokens.** `apiserver/idp/tokens.py`: `issue_access_token(user, device, kind)` = `Token.create_encoded_token(identity, access_token_ttl_sec, kind=kind, device=device.id)`; `read_claims(encoded)` via `Token.decode`. Test: claims round-trip, expiry.
**P1.10 Authorize func.** Extend `service_repo/auth/auth.py::authorize_token`: after the existing parse, read claims; if `kind` in `client|agent`: refuse unless the `Device` exists and is not revoked and the `User` exists and `idp_disabled` is False; if `kind == "job"`: refuse unless the task exists, `task.status` is `queued` or `in_progress`, and its owner is not disabled. Tokens without `kind` (old style) still pass until P1.17. Tests: revoked device, disabled user, job with each task status (queued/in_progress accepted; created, stopped, failed, completed, closed, published refused). **This is gap row 6.**
**P1.11 Device endpoints** in `apiserver/services/devices.py` with models in `apiserver/apimodels/devices.py`:
- `devices.enroll` (`authorize=False`): IdP bearer token in `Authorization`; verify with client id `sdk_client_id`; `upsert_idp_user`; **if `kind == "agent"` require the admin role in the IdP token (server-side)**; validate the public key; create `Device`; audit `device.enrolled`; return the device id. Port from `routers/enroll.py`.
- `devices.exchange` (`authorize=False`): body `{assertion}`; read the issuer (device id) unverified, load `Device`, reject revoked or disabled owner, verify the assertion with the stored key and audience `public_url`, `claim_jti`, issue token, audit `token.issued`, return `{access_token, expires_in}`. Port from `routers/auth.py::exchange`.
- `devices.get_all` (own devices; admins all) and `devices.revoke` (owner or admin; sets `revoked`; audit `device.revoked`).
Tests: ported equivalents of `test_enroll_client.py`, `test_enroll_agent.py` (non-admin refused for agents, admin accepted, disabled admin refused), replayed assertion refused, revoked device refused on the very next request.
**P1.12 Directory sync.** Port `services/directory.py` to `apiserver/idp/directory.py` (Keycloak admin REST with a client-credentials token, secret from `read_secret("idp_directory_secret")`): `get_user(subject) -> enabled, roles`. Start a daemon thread from `server_init/app_sequence.py::AppSequence._start_worker` every `sync_interval_sec` updating `User.role` and `User.idp_disabled` for users with `idp_subject`. Tests with a stub directory (ported from `test_user_sync.py`, `test_directory.py`); one test shows a disabled user is refused after one sync run. **Gap row 5.**
**P1.13 Web login.** `apiserver/idp/web_login.py` ported from `routers/web_auth.py`: `login.idp_start` (state, nonce, PKCE verifier stored in Redis with a short TTL, redirect to Keycloak) and `login.idp_callback` (exchange code, verify id token and nonce, `upsert_idp_user`, set cookie `session_auth_cookie_name` with `Token`, `HttpOnly; SameSite=Strict`, `Secure` when `public_url` is https, redirect to the app). Use the redirect mechanism found in P0.4. Update `login.supported_modes` to list the IdP provider using the `sso_providers` shape found in P0.4. **CSRF:** in `request_handlers.before_request`, for non-GET calls authenticated by cookie, refuse (403, audit `csrf.refused`) unless `Origin` (else `Referer`) equals the origin of `public_url`. Tests: login happy path with the stub IdP, wrong state, replayed code, forged Origin refused, no Origin refused, same-origin accepted.
**P1.14 Job tokens.** `devices.job_token` (authorized, requires an `agent` token): body `{task}`; the task must exist, have status `queued` or `in_progress`, and be assigned to this agent's worker (field found in P0.4); issue a token with `kind="job"`, `task=<id>`, the **task owner** as identity, TTL `job_token_ttl_sec`; audit `job_token.issued`. Tests: wrong agent refused, stopped task refused, accepted token refused after the task becomes `stopped`.
**P1.15 GitHub.** Port `services/github.py` to `apiserver/idp/github.py` with `requests` (App JWT from `read_secret("github_app_key")`, `installation_token(repo)`, `commit_exists(repo, sha)`, `RepoNotAccessible`, `GitHubError`). Hook in `services/tasks.py` enqueue: when the task's repository is on github.com and the App is configured, refuse with a clear `errors.bad_request` message if the commit is missing or the App is not installed (port the logic around lines 55–80 of our `routers/jobs.py`); skip silently when the App is not configured. New `devices.git_token` (job or agent token): returns an installation token for the task's repository (`x-access-token` user). Tests with a stub GitHub (ported from `test_github.py`). **Gap row 9.**
**P1.16 Audit hooks.** Record events at: enrol, exchange (success and failure), revoke, login callback, job token, git token, CSRF refusal, agent enrolment refusal. Test that each endpoint writes its event.

### STOP-2 (new auth works beside the old)
Checklist: all new tests pass; baseline suite still passes unchanged; list each gap row (1–7, 9, 10) and the test that proves it. Report and wait.

**P1.17 Remove the old auth.** Remove: `auth.login/logout/create_credentials/edit_credentials/revoke_credentials/get_credentials/create_user/update/fixed_users_mode` in `services/auth.py`; the `AuthType.basic` branch and `authorize_credentials` in `service_repo/auth/auth.py`; `payload/basic.py`; `fixed_user.py` use; password/credential handling in `services/users.py`, `bll/auth`, `bll/user`; tokens without `kind`; `Credentials` usage. Keep `Token`, `Identity`, `Role`. Set `verify_user_tokens: true`. Hard-fail startup if any legacy credential config is present.
**P1.18 Test base.** In `apiserver/tests/api_client.py` replace basic auth with: at session start, start the stub IdP, create a device key, call `devices.enroll` (admin and normal user variants) and `devices.exchange`, and use the bearer token. Existing integration tests must pass without edits to their bodies; fix only fixtures. Record the pass/fail table next to the P0.2 baseline.

### STOP-3 (old auth gone)
Report: baseline vs now (same tests pass), list of removed endpoints, and anything that depended on credentials (for example the file server's service credential, which stays unused because file server auth is off). Wait.

## Phase 2 — SDK

**P2.1 Vendor** `assertion.py`, `keys.py` into `clearml/idp/` (byte-identical; add `scripts/check_vendored.sh` that compares `sha256sum` with `apiserver/idp/`), plus a device-login helper ported from `mlops-client/src/mlops/idp.py::device_login` (OAuth device flow against `issuer`, client id `clearml-sdk`, prints URL + code, opens the browser).
**P2.2 Session.** In `clearml/backend_api/session/session.py` add an IdP mode used when `api.idp.device_id` is configured: load the device key (`~/.clearml/device.key`, mode 0600), sign an assertion (`aud` = API host, unique `jti`, `exp` 60 s), call `devices.exchange`, keep the token and expiry, and re-exchange on expiry via `token_manager.py`. If env `CLEARML_JOB_TOKEN` is set, use it as the bearer and never exchange. Unit tests with mocked HTTP.
**P2.3 `clearml-init`** (`clearml/cli/config/__main__.py`): ask for the API server URL (and web/files hosts as today), run the device login, create a key pair, call `devices.enroll` (kind `client`, name = hostname), write `clearml.conf` with `api { api_server, web_server, files_server, idp { enabled: true, device_id } }` and **no credentials**. Test with a mocked server.
**P2.4 Remove** access/secret key config, env `CLEARML_API_ACCESS_KEY/SECRET_KEY`, and the credential prompts and template entries. Update README snippets. Run the SDK baseline tests.

## Phase 3 — agent

**P3.1 Vendor** the same `idp` helpers and the same session change in `clearml_agent/backend_api/session/session.py`; `check_vendored.sh` covers this copy too.
**P3.2 `clearml-agent init`**: device login with the client id `clearml-sdk`, kind `agent`. The person signing in must be an admin (the server enforces it; show its refusal message). Store the key like the SDK.
**P3.3 Job start.** After the agent takes a task from the queue, call `devices.job_token(task)`; pass the token to the job through env `CLEARML_JOB_TOKEN` (find where the agent builds the job and docker environment in P0.4's list; remove the code that writes the access and secret key into the task config near `helper/snug.py:484` and into docker env).
**P3.4 Git.** Before cloning, call `devices.git_token(task)` and provide it through a `GIT_ASKPASS` helper (username `x-access-token`, password the token), using the agent's existing ask-pass support (`session.py`, `helper/repo.py`). The token must not be written to any file or log. If P0.4/STOP-1 found this impossible, stop and report.
**P3.5 Remove** credential configuration from the agent. Run the agent baseline tests.

## Phase 4 — web app

**P4.1** Using the paths from P0.4: replace the login screen with an automatic redirect to `/api/login.idp_start` (keep the post-login route handling); remove the credentials-creation page, the user-management/invite pages and their menu entries; keep the profile display (name from `users.get_current_user`).
**P4.2** `pnpm install --force --frozen-lockfile && pnpm run build`; fix only errors caused by the removals. Run the web unit tests found in P0.3.
**P4.3** Document the dev proxy (`proxy.config.mjs`) for running against the server fork.

### STOP-4 (end to end on a local stack)
Bring up the fork stack locally with the stub-free real Keycloak from `/home/parg/Documents/mlops/deploy/idp`. Print the manual scenario list (below) for the user to perform the browser approvals; run every non-browser step yourself. Report results per scenario. Wait.

## Phase 5 — deployment and documents (in `/home/parg/Documents/mlops`, branch `port/clearml`)

**P5.1 Keycloak realm.** Edit `deploy/idp/realm-mlops.json`: add clients `clearml-web` (public, PKCE S256, redirect `<web url>/api/login.idp_callback`), `clearml-sdk` (public, device flow enabled), `clearml-server` (confidential, service account allowed to view users; copy the existing `mlops-server` client pattern).
**P5.2 Compose.** New `deploy/clearml/compose.yaml` (do not touch the current stack): apiserver and webserver built from the forks' `docker/build` files, fileserver, mongo, redis, elasticsearch; mount `../secrets:/run/secrets-dir:ro`; env for hosts and `idp.*`. Reuse the secrets-mount pattern of `deploy/server/compose.yaml`.
**P5.3 Bootstrap.** Extend `deploy/scripts/bootstrap.sh` to generate `deploy/secrets/token_secret` (48 random bytes, base64) and prompt for `idp_directory_secret` and `github-app.pem`; confirm `deploy/secrets/` is git-ignored (it is). Add a "ClearML" section to `docs/server-setup.md`.
**P5.4 Migration guide** `docs/clearml/migration-guide.md`: `mlops.init(...)` → `Task.init(...)`, metrics, artifacts, parameters, dispatch → queues; table of equivalents; what is lost (gap rows 13–16).

## Phase 6 — security checklist

**P6.1** Write `docs/clearml/security-checklist.md`: one row per attack, the test that proves it, and the command: forged token, wrong-key assertion, replayed assertion, revoked device, disabled user (within 60 s), non-admin agent enrolment, cancelled job token, token of another task, missing GitHub commit, forged Origin, default `token_secret`, secret in logs (grep test logs for the secret values), secrets in API responses. Every row must name an existing passing test; add missing tests.

### STOP-5 (before cut-over)
Report with the checklist results. The user arranges the independent review and runs the cut-over runbook below; the executor does not switch off the old server.

**P6.2** Write `docs/clearml/cutover.md`: preconditions (STOP-5 approved, backup of our database), parity check against report section 5a, ordered steps, rollback (keep the old stack stopped but intact for 2 weeks).

## Manual scenarios for STOP-4 (real Keycloak)

1. Web sign-in; sign-out; a request without the cookie is refused; a cross-origin POST is refused.
2. `clearml-init` on a laptop (device approval in the browser); run a `Task`; metrics and artifacts appear.
3. Revoke that laptop's device; its next request fails; another laptop of the same user still works.
4. Disable the user in Keycloak; within about 60 s all their devices fail.
5. `clearml-agent init` with a non-admin: refused. With an admin: accepted.
6. Enqueue a task whose commit is not on GitHub: refused at enqueue with a clear message.
7. Enqueue a good task; agent runs it; the job uses a job token; clone works with the installation token and no token is left on disk.
8. Cancel the running task; the job token is refused on the next request.
9. Server refuses to start with the default `token_secret`.
10. Audit events exist for each step above.

## Hardening backlog (after STOP-5, not in scope now)

H1 restrict `kind=job` tokens to the endpoints a job needs; H2 store the device key in the OS keychain; H3 CSRF token instead of Origin check; H4 per-project access and per-project storage credentials (gap rows 8, 13); H5 `audit.get_all` for admins; H6 rate limiting on `devices.exchange` and `devices.enroll`.

## Critical files

Server: `apiserver/service_repo/auth/auth.py`, `service_repo/auth/payload/token.py`, `service_repo/validators.py`, `server_init/request_handlers.py`, `server_init/app_sequence.py`, `services/{auth,login,users,tasks,queues}.py`, `database/model/auth.py`, `config/default/{apiserver,secure}.conf`, `tests/api_client.py`, plus the new `apiserver/idp/*`, `services/devices.py`.
SDK: `clearml/backend_api/session/{session,token_manager}.py`, `clearml/cli/config/__main__.py`. Agent: `clearml_agent/backend_api/session/session.py`, `definitions.py`, `helper/{snug,repo}.py`, `commands/worker.py`. Web: login, credentials and user-management components found in P0.4. This repo: `deploy/idp/realm-mlops.json`, `deploy/clearml/compose.yaml`, `deploy/scripts/bootstrap.sh`, `docs/server-setup.md`.

## Verification (what "done" means)

- Per task: the task's test fails before and passes after; `git status` clean after the commit.
- STOP-2/3: server baseline suite identical to P0.2 plus all `apiserver/tests/idp/` tests.
- STOP-4: the ten manual scenarios pass; `scripts/check_vendored.sh` reports identical copies in the three repos.
- STOP-5: every row of `security-checklist.md` has a passing test; no secret appears in any committed file (`git grep` for the token secret, key headers `BEGIN` and `.env`).
- Parity: each "closed by design" row in report section 5a is demonstrated by a named test or scenario.

# Security checklist for the ClearML port

Written for: the person doing the independent security review, and the owner who approves cut-over.

Each row is one attack or failure. The proof is an existing test in `clearml-server/apiserver/tests/idp/` (or a manual scenario from the port plan where a test cannot show it). A row marked **gap** has no test yet; it must be closed or accepted in writing before cut-over.

Results were taken from the identity suite run inside the server container on branch `idp-port` (commit `f66022f`): 133 tests, all passing. The automated suite runs 146 tests with two known failures that are not security-related (a project-name clash and a missing test setting).

## Checks

| # | Attack or failure | Proof | Status |
|---|---|---|---|
| 1 | Forged access token | `test_oidc` (bad signature, wrong issuer, wrong audience, expired, unknown key id) for IdP tokens; `test_assertion` for device assertions | passes |
| 2 | Assertion signed with another key | `test_assertion_signed_by_another_key_is_refused`; `test_exchange_refuses_an_assertion_signed_by_another_key` | passes |
| 3 | Replayed assertion | `test_exchange_gives_a_token_once_per_assertion`; `test_replay` (a `jti` can be claimed once) | passes |
| 4 | Assertion with a wrong audience, expired, tampered, no `jti`, too long-lived | `test_assertion` (wrong audience, expired, tampered, missing `jti`, from the future, lifetime above 300 s) | passes |
| 5 | Revoked device, on its next request | `test_revoked_device_is_refused_on_its_next_request`; `test_revoked_device_is_refused` (checks) | passes |
| 6 | Disabled user (in the IdP), within about 60 s | `test_disabled_in_the_idp_is_disabled_here_and_its_devices_are_refused`; `test_user_sync` (disabled, missing, mass anomaly, failed lookup) | **partly**: the 60 s bound is the sync interval and is measured only at STOP-4 (scenario 4) |
| 7 | Non-admin enrols an agent | `test_agent_enrolment_is_refused_for_a_non_admin`; `test_agent_enrolment_is_allowed_for_an_admin` | passes |
| 8 | Disabled admin enrols an agent | `test_disabled_user_cannot_sign_in` (web); the enrolment path refuses a disabled user (`devices.enroll`) | **gap**: no test that enrols an agent as a disabled admin |
| 9 | Forged sign-in when enrolling a device | `test_enrol_refuses_a_forged_sign_in` | passes |
| 10 | Job token after the task stops or is cancelled | `test_the_job_token_is_refused_once_the_task_stops`; `test_finished_or_stopped_jobs_are_refused` (checks) | passes |
| 11 | Job token for another task | `test_a_job_token_for_another_task_is_refused`; `test_another_agents_task_is_refused` | passes |
| 12 | Agent that did not start the task gets its token | `test_an_agent_cannot_get_a_token_for_another_agents_task`; `test_a_laptop_that_starts_nothing_gets_no_job_token` | passes |
| 13 | Job token for a task that has not started | `test_a_task_that_has_not_started_is_refused` | passes |
| 14 | Laptop asks for a job token | `test_a_laptop_cannot_get_a_job_token` | passes |
| 15 | Job token for a disabled owner | `test_job_of_a_disabled_owner_is_refused` | passes |
| 16 | Missing GitHub commit at submission | `test_a_missing_commit_is_refused_with_a_clear_message`; `test_a_github_repository_without_a_recorded_commit_is_refused` | passes |
| 17 | GitHub App not configured or not installed on the repository | `test_a_repository_without_the_app_is_refused` (checks); `test_without_a_configured_app_no_repository_token_is_given` (git token) | passes; the App-installed-elsewhere case is covered only by the stub, see gap in row 16 |
| 18 | Repository token for another task, or a laptop | `test_without_a_configured_app_no_repository_token_is_given`; `test_a_job_token_for_another_task_is_refused` | passes |
| 19 | Forged Origin on a cookie-authenticated change | `test_cookie_change_from_another_site_is_refused`; `test_cookie_change_without_origin_is_refused` | passes |
| 20 | Same-origin change is accepted (no false refusal) | `test_cookie_change_from_the_web_app_is_accepted`; `test_bearer_request_is_not_checked_for_origin` | passes |
| 21 | Web sign-in: replayed or unknown state, wrong nonce, failed code exchange | `test_a_state_can_be_used_only_once`; `test_unknown_state_is_refused`; `test_wrong_nonce_is_refused`; `test_refused_token_exchange_is_refused` | passes |
| 22 | Web sign-in by a disabled user | `test_disabled_user_cannot_sign_in` | passes |
| 23 | Basic credentials or a token without a kind | `test_basic_credentials_over_http_are_refused`; `test_a_token_without_a_kind_is_refused`; `test_legacy_removed` | passes |
| 24 | Credential endpoints still reachable | `test_the_credential_endpoints_are_gone` | passes |
| 25 | Server starts with the public default token secret | `test_default_secret_is_refused` (`test_secrets`) checks the refusal; the start-up path itself is verified at STOP-4 (scenario 9) | passes at unit level |
| 26 | Server starts with access keys or fixed users configured | `test_access_keys_refuse_to_start`; `test_fixed_users_refuse_to_start` | passes |
| 27 | Audit event for each sign-in, enrolment, exchange, revoke, refusal | `test_enrolment_and_exchange_and_revoke_are_recorded`; `test_a_refused_exchange_is_recorded`; `test_a_refused_agent_enrolment_is_recorded`; `test_a_refused_job_token_is_recorded`; `test_a_cross_site_cookie_change_is_recorded` | passes |
| 28 | Secret appears in an API response | `test_the_settings_name_the_issuer_and_the_sdk_client` checks that the settings answer holds no secret | **gap**: no test over the other endpoints; add a sweep of every response for the token and key values |
| 29 | Secret appears in logs | none | **gap**: grep the server and agent logs for the token secret and key headers after a run |
| 30 | Secret committed to the repository | none automated | **gap**: `git grep` for the token secret, `BEGIN` key headers and `.env` before cut-over. The existing `deploy/idp/realm-mlops.json` has a client secret for `mlops-server` in plain text; it predates this port and is outside it, but it should be moved out |
| 31 | Agent job can call any endpoint with its token | by design (job token is accepted by every endpoint the job's SDK uses) | **accepted for now**: restricting job tokens to the endpoints a job needs is hardening item H1 |
| 32 | Session secret for the web (`http.session_secret`) is in the configuration | none | **gap**: move it to a secret file (plan section 4.9), before cut-over |
| 33 | JWKS keys are cached without an expiry | none | **gap**: add a time-to-live and a re-fetch on an unknown key id |
| 34 | Test-only settings in production (`jwks_file`, `CLEARML_ALLOW_CONFIG_SECRET`) | none | **gap**: refuse to start when either is set outside a test run |
| 35 | Cookie is sent over plain HTTP | none | **gap**: the `Secure` flag follows the URL scheme; check it on the deployed host |

## Manual scenarios still to run (STOP-4)

These need a running stack and a person at the browser. They are listed in `port-plan.md` and in the port plan.

1. Web sign-in, sign-out, a request without the cookie refused, a cross-origin change refused.
2. `clearml-init` on a laptop: the browser sign-in and approval; run a task; metrics and artifacts appear.
3. Revoke that laptop's device; its next request fails; another laptop of the same user still works.
4. Disable the user in Keycloak; within about 60 s every device of that user fails. **Measure the time.**
5. `clearml-agent init` as a non-admin: refused. As an admin: accepted.
6. Enqueue a task whose commit is not on GitHub: refused at enqueue with a clear message.
7. Enqueue a good task; the agent runs it with a job token; the clone uses the installation token; no token is left on disk.
8. Cancel the running task; the job token is refused on the next request.
9. The server refuses to start with the default token secret.
10. Audit events exist for each step above.

## Decision needed from the reviewer

Rows 8, 28, 29, 30, 32, 33, 34 and 35 are gaps. Each is small. The recommendation is to close them before cut-over, not to accept them.

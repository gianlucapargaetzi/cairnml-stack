# Spike list: ClearML port

Each spike answers one question that the design in [idp-integration-report.md](idp-integration-report.md) depends on. A spike is time-boxed. It ends with a finding, a pass or fail, and a note in the report if the design changes.

Run spikes on a branch of the ClearML fork, never on `main` of this repository. Record each finding in `docs/clearml/spike-results.md`, one section per spike.

## Order

Spikes S1 to S4 come first, because they decide whether the design works at all. S5 to S9 can run in parallel with the implementation of the server. S10 to S14 are checks that can be done late without blocking.

## Spikes

### S1. Device enrolment with a key pair (SDK)

- **Question:** can the SDK sign in through the IdP, create a key pair, register the public key with the ClearML server, and then obtain a short-lived access token by signing an assertion?
- **Why it matters:** this is the laptop enrolment in section 4.3. It is the same mechanism our server uses today.
- **How:** port the request signing from `packages/mlops-server/src/mlops_server/routers/auth.py` and `routers/enroll.py` into a prototype endpoint in the fork. Call it from a script that performs the steps.
- **Pass:** a token is issued for the device, and a request with a changed or replayed assertion is refused.
- **Time box:** 3 days.

### S2. Web sign-in and the session cookie

- **Question:** can the web app redirect to the IdP with PKCE, have the ClearML server exchange the code, and set a session cookie with a CSRF check? And does the web app read `login.supported_modes` (the empty `sso` and `sso_providers` placeholders) in a way that we must change?
- **Why it matters:** section 4.2, and gap row 1.
- **How:** find the web app's login code in `clearml-web` and trace what it does after the user signs in. Build a minimal login against the IdP in the fork.
- **Pass:** a signed-in browser reaches the app, a request without the cookie is refused, and a change without the CSRF token is refused.
- **Time box:** 4 days.

### S3. Agent Git access with a short-lived GitHub token

- **Question:** can the agent clone a private GitHub repository at one commit, using a short-lived GitHub App installation token passed as an HTTP header through the environment (the mode of our current agent, `workspace.py`), without the token reaching argv, any file, or any error message?
- **Why it matters:** section 4.8 and gap row 9.
- **How:** port `_git` and `clone_at` into a scratch copy of the agent and clone a private test repository with an installation token. Then grep the agent's working directory, the process list during the clone, and a forced failure's error text for the token.
- **Pass:** the clone succeeds at the given commit; the token appears nowhere on disk or in output.
- **Time box:** 2 days.

### S4. Admin-only agent approval

- **Question:** does the ClearML server refuse an agent approval from a user without the admin role, on the server and not only in the UI?
- **Why it matters:** section 4.4 and gap row 3. Our server enforces this with `admin_only` on the endpoint.
- **How:** write the approval check in the fork. Test it with an admin, a normal user and a disabled admin, both through the UI and directly through the API.
- **Pass:** only an enabled admin can approve, through any path.
- **Time box:** 2 days.

### S5. Job-token status check

- **Question:** can a job token be refused as soon as the job is cancelled, finished or reassigned, the same as our run tokens?
- **Why it matters:** section 4.6 and gap row 6.
- **How:** compare with `security/deps.py` (the check on `job.status` and `job.run_id`). Implement the check in the fork, then cancel a running test job.
- **Pass:** the token fails on the next request after the status changes.
- **Time box:** 2 days.

### S6. User disablement timing

- **Question:** after a user is disabled in the IdP, how long until the ClearML server refuses that user, given the 60-second sync loop?
- **Why it matters:** section 4.5 and gap row 5.
- **How:** port the sync loop from `services/directory.py`. Disable a test user and measure the time to refusal.
- **Pass:** refusal within about 60 seconds, with no refusal before the sync.
- **Time box:** 1 day.

### S7. Storage session tokens in the ClearML SDK

- **Question:** can the ClearML SDK and agent upload to and download from our RustFS with temporary credentials that include a session token, which is what the STS flow returns?
- **Why it matters:** section 4.7. The SDK may only accept long-lived keys.
- **How:** read the SDK's storage code (`clearml/storage`). Upload a file with a temporary credential from our current STS endpoint.
- **Pass:** upload and download work with the session token, without a long-lived key in the SDK's configuration.
- **Time box:** 3 days. Storage is a later topic, so this spike can be scheduled after S1 to S6.

### S8. Keycloak 26.0 settings

- **Question:** which Keycloak settings do S1, S2 and S4 need on our realm: a public client for the web app with PKCE, a client for the SDK, and the admin group mapping?
- **Why it matters:** the realm must be right before the first client test.
- **How:** read `deploy/idp/realm-mlops.json` and the existing clients (`mlops-web`, `mlops-cli`). Add the new clients on a test realm first.
- **Pass:** the settings are written down and the realm imports cleanly.
- **Time box:** 1 day.

### S9. Where audit events are recorded

- **Question:** where in the ClearML server should audit events be written, so that every sign-in, enrolment, approval, job token, storage request and GitHub token is recorded, the same as in our `AuditEvent` table?
- **Why it matters:** gap row 10. The open-source server has no audit code.
- **How:** list the endpoints in the fork that issue or check credentials. Mark the points where a record is needed.
- **Pass:** a list of hook points, with a decision on the table layout.
- **Time box:** 1 day.

### S10. Baseline test suite

- **Question:** do the ClearML server, agent and SDK test suites run and pass on an unmodified fork on our machines?
- **Why it matters:** without a passing baseline, failures after the port cannot be attributed.
- **How:** clone the four repositories at a fixed tag. Run each suite. Record the commit hashes.
- **Pass:** the suites run and the results are recorded.
- **Time box:** 2 days.

### S11. Cost of assertion checks

- **Question:** what is the cost of checking an assertion and an access token on each request, in the ClearML server's request path?
- **Why it matters:** the RSA checks on every request could slow the server noticeably.
- **How:** measure a request with and without the check in the fork, using a load test.
- **Pass:** the overhead is small enough for the expected load. Record the number.
- **Time box:** 1 day.

### S12. Secrets from files

- **Question:** can the ClearML server, agent and SDK read their secrets from files in a read-only mount, the same as our server, without putting them in configuration files that are committed?
- **Why it matters:** section 4.9.
- **How:** check how ClearML loads its configuration (`config` modules and environment variables). Add file-based loading for the four secrets.
- **Pass:** the server starts with the secrets in files and no secret in the repository.
- **Time box:** 2 days.

### S13. Existing data

- **Question:** do we migrate our existing projects, experiments and runs into ClearML, or start fresh?
- **Why it matters:** the cut-over plan depends on it.
- **How:** list what our database holds, and how much of it ClearML can represent. This is a decision, not a technical spike.
- **Pass:** a decision recorded in the report.
- **Time box:** half a day.

### S14. Upstream version to fork

- **Question:** which ClearML release do we fork, and how far has it moved since the sources we read?
- **Why it matters:** every later merge starts from this point.
- **How:** pick the latest stable tag of each of the four repositories. Record the tags and commit hashes in `docs/clearml/spike-results.md`.
- **Pass:** a recorded set of tags.
- **Time box:** half a day.

## Exit criteria for the spike phase

- S1 to S4 pass, or the report is changed to match a finding.
- S5 to S9 have findings recorded, even if one of them fails.
- S10 has a recorded baseline.
- A go or no-go decision is written at the top of `spike-results.md`.

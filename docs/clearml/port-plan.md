# Port plan: from our mlops to a heavily customised ClearML

This plan turns the design in [idp-integration-report.md](idp-integration-report.md) into steps. It starts after the spikes in [spike-list.md](spike-list.md). The estimate is for one experienced developer, with one review at the end.

## Working agreement

- **Branch:** `port/clearml` holds this plan, the report, the spikes and all work on the fork. `main` keeps the current mlops solution and is not changed by the port until cut-over.
- **Fork layout:** one fork per ClearML repository (server, agent, SDK, web app), each pinned to the tag chosen in S14. Our changes are kept in separate modules where possible, to make upstream merges easier.
- **Commits:** one logical change per commit, with a message that says what and why. No attribution lines to tools.
- **Tests:** every security check has a test that fails without the check. The baseline from S10 must still pass after each phase, or the failure must be explained in the commit.
- **Pushing:** nothing is pushed to a shared remote without a decision on which remote and when.
- **Decisions:** each decision is recorded in the report's decision list, with the date.

## Phases

### Phase 0: decisions and baseline (week 1)

- Pick the ClearML tags to fork (S14) and the baseline tests (S10).
- Confirm the decisions in the report, in particular the storage and per-project topics, which are later.
- Set up the four forks and the `port/clearml` branch.

**Exit:** the four forks build and their tests pass unmodified.

### Phase 1: spikes (weeks 1 to 2)

- Run S1 to S9 and S11 to S13 as described in the spike list. Start with S1 to S4.
- Record each finding in `docs/clearml/spike-results.md`.
- Change the report wherever a finding changes the design.

**Exit:** S1 to S4 pass, and the go or no-go decision is written at the top of the spike results.

**Stop condition:** if S1 or S4 fails and the report cannot be changed to fix it, stop and decide again. Do not start the implementation on a design that has failed.

### Phase 2: identity in the server (weeks 2 to 5)

In this order, each with tests:

1. **Configuration:** the IdP settings, and the secrets read from files (S12).
2. **IdP sign-in and user records:** the OIDC token check, user creation and update, and the 60-second status sync (S6).
3. **Device enrolment:** the endpoint that registers a public key after an IdP sign-in, and the assertion check (S1).
4. **Access tokens:** issued by the server, signed with its key, with a short lifetime and the same checks as ours.
5. **Admin-only agent approval** (S4).
6. **Job tokens:** issued at job start, refused when the job's status changes (S5).
7. **GitHub submission check:** the commit and the App installation are checked when a job is submitted (gap row 9).
8. **Audit log:** the events from S9.
9. **Removal:** the password, login, logout and access-key endpoints, and the revoked-token list.

**Exit:** the server's tests pass with the new checks, and each check has a failing test that shows it is needed.

### Phase 3: SDK and agent (weeks 4 to 6)

- **SDK:** `clearml-init` runs the device sign-in, creates the key pair, stores the private key in the operating system's keychain where possible, and signs assertions. Remove the access-key configuration.
- **Agent:** `clearml-agent init` runs the device sign-in, the admin approval is shown to the operator, the agent keeps its key, uses job tokens, and clones with a GitHub installation token (S3).
- **Compatibility:** the old access-key path is removed in this phase, because cut-over is at once (decision 2).

**Exit:** a laptop and an agent can each enrol, run a job end to end, and clone a private repository.

### Phase 4: web app (weeks 5 to 7)

- Add the IdP sign-in and the session cookie (S2).
- Remove the login, credentials and user management pages.
- Keep the ClearML pages that show experiments, tasks, datasets and models as they are.

**Exit:** a person can sign in, view the pages they are allowed to see, and sign out.

### Phase 5: deployment (weeks 7 to 8)

- Add the ClearML stack to `deploy/`, next to the identity provider, with the secrets mounted as files (S12).
- Update `bootstrap.sh` and the setup document, so a new server can be started as it is today.
- Write the migration guide for scripts that use `mlops` (gap row 12 in the report).

**Exit:** a clean machine can run the stack from the setup document.

### Phase 6: security review (weeks 8 to 9, plus 2 weeks for a review by someone other than the author)

- Checklist: forged access tokens, replayed assertions, a disabled user, a revoked device, a non-admin approving an agent, a cancelled job's token, a missing GitHub commit, secrets in logs or API responses.
- Run each check against the running stack. Record the result.
- Fix every failure before cut-over.

**Exit:** the checklist passes, and the review's findings are closed or accepted in writing.

### Phase 7: cut-over (week 10)

- Compare the parity list in report section 5a with the running fork. Every row marked "closed by design" must be shown working.
- Move every user and machine to the new SDK and agent on the same day.
- Turn off our server, after a final backup of its database.

**Exit:** all users and machines work on the fork, and our server is switched off.

## Later

- **Per-project access and storage access per project** (gap rows 8 and 13), after cut-over.
- **Upstream merges:** each new ClearML release is merged on the `port/clearml` branch, with the tests from S10.

## Estimate

| Phase | Weeks |
|---|---|
| 0 Decisions and baseline | 1 |
| 1 Spikes | 2 |
| 2 Identity in the server | 4 |
| 3 SDK and agent | 2 |
| 4 Web app | 2 |
| 5 Deployment | 2 |
| 6 Security review | 2 (plus a review by someone else) |
| 7 Cut-over | 1 |
| **Total** | **about 16 weeks, including review** |

This is longer than the 7 to 10 weeks in the report, which counted only the implementation. The difference is the spikes, the baseline and the review, which the report left out. Use the longer figure for planning.

## Risks

| Risk | Mitigation |
|---|---|
| A spike fails and the design changes | Stop at phase 1 and decide again before implementing |
| Upstream ClearML changes its authentication code between tags | Pin the tags; merge deliberately |
| The web app's SSO placeholders need more work than expected | Covered by S2; the time box is four days |
| The agent cannot clone with a short-lived token | Covered by S3; the fallback is a per-job Git token, decided at that point |
| Cut-over breaks a team's scripts | The migration guide, and a dry run with one user before the cut-over day |
| One person maintains everything | Keep the commits small, and document each security check where it is made |

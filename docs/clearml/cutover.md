# Cut-over runbook: from `mlops` to the ClearML fork

Written for: the owner of the cut-over, who runs it on the day, and the reviewer who signs it off.

Cut-over is one day. Every user and every machine changes over together, because the old client path is removed in Phase 3 (decision 2 of the port plan). There is no period in which both work.

## Preconditions (all must hold before the day)

1. The independent security review of `security-checklist.md` is done and signed off in writing. Every gap row is closed, or accepted in writing by the owner.
2. The manual scenarios 1 to 10 have been run on a full stack, and the results are written down.
3. The parity list in `idp-integration-report.md`, section 5a, has been checked against the running fork. Every row marked "closed by design" or "closed by decision" is shown working.
4. A full backup of the `mlops` database (Postgres) and of the RustFS data has been taken and restored once on a scratch machine.
5. The migration guide (`migration-guide.md`) has been sent to every user. A dry run has been done with one user.
6. Every user and every agent machine has been told the day and the time, and has a person who will run `clearml-init` or `clearml-agent init` on it.
7. The GitHub App is installed on every repository that jobs clone, and its private key is in `secrets/github-app.pem` on the server.
8. The identity provider has the `clearml-web`, `clearml-sdk` and `clearml-server` clients, and the directory client has its secret in the ClearML secrets folder.

## Steps on the day

Times are indicative. Each step has a check; do not go on until the check passes.

1. **Freeze.** Ask users to stop starting new jobs in `mlops`. Let running jobs finish, or stop them. Check: no job is running in `mlops`.
2. **Back up.** Take the final backup of the `mlops` database and the data folders. Check: the backup file exists and its size is plausible.
3. **Stop the old server.** Stop the `mlops` stack (keep its volumes). Check: its health address no longer answers.
4. **Start the ClearML stack** from `deploy/clearml/`. Check: the server answers `login.supported_modes`, and the web app loads and redirects to the sign-in page.
5. **Sign in as the owner.** Check: the owner's account is created on first sign-in, with the admin role.
6. **Enrol the owner's laptop** with `clearml-init`. Check: a task from the laptop shows in the web app with metrics and an artifact.
7. **Enrol an agent** with `clearml-agent init`, as the admin. Check: the agent shows in the web app and listens on its queue.
8. **Run one job end to end.** Enqueue a task from the web app. Check: the job runs with a job token, clones its repository with an installation token, and finishes with its metrics.
9. **Let users in.** Send the message that says the migration is done and the first step for each person is `clearml-init`. Check: each person's first sign-in creates their account.
10. **Enrol the other agents** with `clearml-agent init`, one by one. Check: each agent's first job runs.

## Rollback

Keep the old stack stopped but intact for two weeks, with its volumes and its backup.

Roll back if, in the first two hours, a user cannot sign in, or a job cannot start on any agent, and the cause is not fixed within one hour.

To roll back:

1. Stop the ClearML stack.
2. Start the `mlops` stack again from its volumes.
3. Tell users to run the old `mlops` login again. The `clearml-init` configuration they got on the day is not used by `mlops`; keep it, and do not delete it, so that the next attempt works.
4. Record in writing what failed and when.

Runs created in ClearML during the day are not copied back to `mlops`. Say so to the users who created them.

## After the day

- Remove the old access keys from the ClearML database (the keys seeded before the removal are still stored in the user records; their basic-auth path is closed, but the stored values should be deleted).
- After two weeks with no rollback, retire the old stack: keep one final backup, then remove the volumes.
- Record the cut-over in `NOTES` with the times of each step.

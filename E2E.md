# End-to-end tests (planned)

Status: planned, not built. Unit and live API tests exist in the forks; this file describes the
end-to-end suite that checks the whole workflow against a running stack.

## Goal

Check the framework the way a user uses it: bring the stack up, enrol a client and an agent, sign in,
run experiments and jobs, and check the results through the API and the web app. Unit tests stay as
they are.

## Scenario (run in order, each step asserts on what it produced)

### 1. Stack and sign-in

1. **Stack up.** `docker compose up` in `deploy/`; wait until the API, RustFS, Keycloak and
   Elasticsearch report healthy.
2. **Enrol the client.** Run `clearml-init --server http://mlops-clearml:8008`. Assert that
   `~/.clearml/device.key` and the device id are written to the config.
3. **Sign in.** The device exchanges its signed assertion for an access token. Assert that the token
   is accepted by `users.get_current_user`.
4. **`clearml-whoami`.** Assert that the output names the expected user and device.
5. **Re-enrol and revoke.** `clearml-init --force` revokes the old device; assert that the old key no
   longer gets a token. `clearml-logout` removes the key and the config entry.

### 2. Artifacts

6. **Upload each kind.** In one `Task.init`, call `upload_artifact` for a file, a folder (zipped), a
   dict (JSON), a DataFrame (`.csv.gz`), a numpy array (`.npz`), a PIL image (`.png`) and a pickled
   object (`auto_pickle=True`). Use `wait_on_upload=True`.
7. **Round trip.** Read each artifact back with `task.artifacts[name].get_local_copy()` and
   `Task.get_task(...).artifacts`. Assert that the content equals what was uploaded.
8. **Integrity.** For each artifact, the sha256 in the record matches the downloaded bytes.
9. **Large object.** Upload a file above the multipart threshold (several hundred MB, or a lowered
   threshold in test mode). Assert that the upload is multipart, completes, and downloads intact.
10. **Metadata.** `metadata={...}` is stored and returned with the artifact.
11. **Access.** Redirects from `/datachunks` work for the task owner. Another user gets `403`.

### 3. Metrics and logging

12. **Scalars.** Report a series with `Logger.report_scalar` (for example loss over 100 iterations,
    two series, two titles). Assert that the API returns every point with the right iteration.
13. **Single values and parameters.** `task.set_parameter` and `report_single_value` appear in the
    task's configuration and in the summary.
14. **Debug samples and console.** Log one image and one text line through `report_image` and the
    console. Assert that both are returned by the events API.
15. **Visualisation in the web app.** Open the task's scalars page (Playwright). Assert that:
    - the chart draws both series and the x-axis ends at the last iteration;
    - hovering a point shows the value from step 12;
    - the console tab shows the line from step 14;
    - the debug image renders (not a broken image).
16. **Compare runs.** Run two tasks with the same metric names. Assert that the comparison view
    overlays both series.

### 4. Git integration

17. **Repository recorded.** Run the example from a git checkout with a remote. Assert that the task
    records the repository URL, branch, commit and the uncommitted diff.
18. **Clone in the job.** A job for that task clones the repository with the per-job git credentials
    and checks out the recorded commit. Assert that `git rev-parse HEAD` in the job matches the commit.
    The repository is hosted in the Gitea container in compose.
19. **Credentials scoped to the job.** The git token in the job is the job's own: after the job ends,
    the token no longer works, and no other job's token works for that repo.
20. **Private repository refused.** Ask for a repository the job's credentials do not cover. Assert
    that the job fails at clone time with a clear message, and that the token is not in the logs.

### 5. Agent enrolment

21. **Agent enrols.** Enrol an agent machine with its own device key (the same flow as steps 2 and 3,
    for an agent role). Assert that the server lists the agent as online with its resources.
22. **Heartbeat.** Stop the agent process; assert it goes offline after the timeout. Start it again;
    assert it comes back online without re-enrolling.
23. **Agent without a valid key.** Remove the agent's device key and start it. Assert that it does not
    register and logs a sign-in error.
24. **Resources reported.** The agent reports CPU, memory and GPUs. Assert that the values match the
    machine (checked against the host's own counts).

### 6. Job dispatch, execution and monitoring

25. **Enqueue.** Submit a job that asks for 1 CPU and 0 GPU, with a small script that logs scalars and
    writes one artifact, then sleeps for 30 s. Assert that the job is `queued`.
26. **Placement.** The scheduler places the job on an agent that has the requested resources. Assert
    that the job moves to `running` on that agent, and that a job asking for a GPU the agent does not
    have stays `queued`.
27. **Live monitoring.** While the job runs, assert that its status is `running`, its scalars update
    in the web app (step 15), and its console grows.
28. **Completion.** Assert that the job ends `completed` with exit code 0, and that its artifact from
    step 25 is present and downloadable.
29. **Failure.** Submit a script that raises after two scalars. Assert that the job ends `failed`,
    the traceback is in the console, the two scalars are stored, and the agent is free for the next job.
30. **Abort.** Submit a long job and abort it from the web app. Assert that the agent stops the
    process within 30 s and the job ends `aborted`.
31. **Resource release.** After 25–30, assert that the agent reports no running job and that its
    working directory for the job is removed.
32. **Lost agent.** Kill the agent during a running job. Assert that, after the heartbeat timeout:
    - the lost attempt is recorded in the task's scheduler history (release reason `worker lost`, and a
      `worker_lost` / `retried` event);
    - the task goes back to `queued` and runs to completion on another target (or the same one, once
      it is back online);
    - a second loss of the same task fails it with reason `worker_lost` (cap of 2 attempts,
      `max_attempts`), and the task is not left `running`.
33. **Internal failure.** A job that fails inside the script (step 29) or on the agent's own error
    (for example a missing image) shows the task as `failed`. Assert that it is **not** re-scheduled.
    Only a lost attempt is retried.

### 7. Datasets and models

34. **Dataset.** Create a dataset with `Dataset.create`, add files, finalize and upload. Assert that a
    second `Dataset.get` downloads the same files and the same hashes.
35. **Model.** Register a model file with `OutputModel`. Assert that it is listed under the task and
    can be downloaded.

### 8. Clean up

36. **Delete.** Delete the test tasks, the dataset and the model. Assert that their objects are gone
    from RustFS, and that the `/datachunks` route returns `404`.
37. **Stack down.** `teardown.sh --dry-run` lists what it would remove; the real run removes the stack
    and this machine's keys, and the next run starts clean.

## UI checks (Playwright)

- **Sign in through the browser.** Drive the Keycloak form against the committed test realm, with
  its fixed test user. Assert that the dashboard renders (sidebar, project sections, user area).
  The same form is used for the `clearml-init` browser step.
- **Restart regression.** Sign in, restart the API container, reload the page, and assert the same
  rendering.
- **Stale session.** Load the page with an expired cookie, and with a cookie for a device that no
  longer exists. Assert that the app goes to sign-in and does not show a half-loaded page.
  This is the cookie problem reported after a restart.
- **Job status.** The jobs list shows the states from section 6 as they change, without a reload.
- **Dashboards.** On the global dashboard, double-clicking a project opens its project dashboard. Assert that:
  - the global dashboard lists projects on top and RECENT EXPERIMENTS at the bottom (a single click
    on a project does not navigate);
  - the project dashboard lists its tasks as folders on top and RECENT EXPERIMENTS at the bottom;
  - double-clicking a task folder lists its experiments;
  - each task from the scenario is one folder, and its experiments are listed in it, numbered in
    creation order (the local run and the two remote runs of the same script share one folder);
  - a run with no task (no name, or a parent outside the project) is in "Unassigned";
  - "All experiments" opens the flat experiments list with every run;
  - the header shows TASKS and EXPERIMENTS tabs, and the folder breadcrumb shows the folder name.
- **Light and dark mode.** Each page in the checks above is captured in both themes; assert that no
  text is unreadable (contrast check) and no element is cut off at phone width.

## Tooling

- pytest package under `tests/e2e/`, with a session fixture that brings the stack up and waits for
  health.
- Scenario tests run in order and share the enrolled device, agent and task ids. Sections 2 to 6 can
  each run on their own if the earlier ones have left their objects in place.
- Playwright for Python for the UI checks (Chromium is already in the local Playwright cache).
- Each test cleans up what it created, even on failure (pytest finalizers).
- A single command runs everything, for example `pytest tests/e2e`; `-k artifacts` runs one area.

## Open points

- `clearml-init` opens a browser for sign-in. The test drives that page against the test realm.
- The test realm and the test-mode settings currently live in a scratch override. They need to
  become a committed test overlay.
- The stale-session check needs a token for a device that is not in the database. The test can mint
  one with the server's own signing code.
- Job steps (section 6) run the agent on the same host as the stack, in test mode. Check that the
  compose overlay can start the agent without a second machine.
- The lost-agent path (step 32) needs the scheduler to log the lost run on the task's execution
  history and schedule a new run. Confirm the data model for execution runs before writing the
  assertion.
- The git server is a Gitea container in compose. Add its image, admin user and seed repository to
  the test overlay.
- Thresholds and timeouts (multipart size, 30 s abort, heartbeat timeout) are placeholders until the
  test overlay sets them.

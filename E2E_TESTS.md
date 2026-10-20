# End-to-end tests: the catalogue

Every test of the suite in `tests/e2e/`, module by module, with what it checks. How the suite works, what it needs and how to
run it is in [E2E.md](E2E.md). The defects (D1 to D7, and the access and web items) are described there, with their issues.

A test that names a defect fails because of that defect; no test is marked as expected to fail.
**Skip**: skipped with the reason shown in the report.

Run one module with `pytest tests/e2e/<file>`, one test with `pytest tests/e2e -k <name>`.

**Last full run:** see "Status of the last full run" in [E2E.md](E2E.md).

## test_00_isolation.py: the suite runs on its own stack

| Test | Checks |
|---|---|
| `test_the_addresses_are_not_the_ones_of_the_deploy_stack` | The API, web, sign-in and storage addresses are not the ports or host names of the stack under `deploy/`. |
| `test_the_api_is_served_by_this_suites_compose_project` | The API answering is a container of this session's compose project, on the published port. |

## test_02_enrolment.py: enrolling a machine

Section 1 of E2E.md. Every enrolment goes through `clearml-init` and the real sign-in page.

| Test | Checks |
|---|---|
| `test_init_enrols_the_machine_and_writes_its_key` | The device key is written with mode 0600; the configuration names the device and the server. |
| `test_whoami_names_the_admin_and_the_device` | `clearml-whoami` prints the signed-in user and the device id. |
| `test_whoami_uses_the_device_key_without_a_browser` | `clearml-whoami` never opens a sign-in page (the browser command is set to fail). |
| `test_init_again_without_force_is_refused` | An enrolled machine refuses a second `clearml-init`; the key is unchanged. |
| `test_init_with_force_revokes_the_old_device` | `--force` revokes the previous device; its old key gets no token, the new key does. |
| `test_logout_revokes_the_device_and_removes_its_key` | `clearml-logout` revokes the device on the server and removes the key. |
| `test_whoami_after_logout_says_not_enrolled` | After logout, `clearml-whoami` says the machine is not enrolled. |
| `test_logout_on_a_machine_that_is_not_enrolled_does_nothing` | Logout on an unenrolled machine exits cleanly and says so. |
| `test_init_with_an_unreachable_server_writes_nothing` | An unreachable server is reported as such, and no key is written. |
| `test_init_accepts_the_web_address_and_finds_the_api` | The web address is accepted and the API address derived from it. **Skip** on ports other than 8080/8008 (the derivation is fixed to them). |
| `test_member_enrols_as_a_plain_user` | A plain user enrols; `whoami` shows the user, not the admin role. |

## test_03_device_security.py: what the server refuses

Section 1, the trust side of enrolment. Each request is built with the REST client, to be wrong in one way.

| Test | Checks |
|---|---|
| `test_assertion_signed_with_another_key_is_refused` | An assertion signed with another key gets no token. |
| `test_assertion_for_another_server_is_refused` | An assertion addressed to another server gets no token. |
| `test_expired_assertion_is_refused` | An expired assertion gets no token. |
| `test_assertion_cannot_be_used_twice` | A replayed assertion gets no second token. |
| `test_token_of_a_device_is_refused_once_the_user_is_disabled` | A disabled account's device is refused within the directory sync interval (60 s). The test polls for up to 150 s. |

## test_04_tracking.py: metrics, parameters, console, debug samples

Section 3 of E2E.md. A training script records a run on the client; every check reads the run back in another process.

| Test | Checks |
|---|---|
| `test_scalars_keep_every_point_of_both_series` | 100 points each for `loss/train` and `loss/val`. |
| `test_scalars_keep_the_iteration_of_each_point` | Iterations run from 0 to 99. |
| `test_scalar_values_are_the_ones_reported` | First and last values equal what the script reported. |
| `test_parameters_are_stored_in_the_configuration` | `General/epochs` and `General/lr` are in the run's configuration. |
| `test_set_parameters_replaces_the_whole_set_and_set_parameter_adds` | A group write replaces the parameters; a single write adds one (the SDK's documented behaviour; see E2E.md, D5). |
| `test_single_value_appears_in_the_summary` | The single value `accuracy` is in the summary. |
| `test_console_line_is_stored` | The console line printed by the script is stored. |
| `test_debug_image_is_stored` | The debug image is stored as a debug sample. |
| `test_run_is_completed_after_it_closes` | Status is `completed` after `task.close()`. |
| `test_run_is_listed_under_its_project` | The run is listed under the project, by name. |
| `test_two_runs_of_one_name_are_two_experiments` | Two runs with one name are two different experiments. |
| `test_run_without_a_project_name_goes_to_the_default_project` | An empty project name is accepted; the run is filed under a project. The run is deleted at the end. |

## test_05_artifacts.py: artifacts of every kind

Section 2 of E2E.md. One task uploads every kind of artifact; each check reads it back in a new process.

| Test | Checks |
|---|---|
| `test_artifact_content_matches_after_read_back[file, folder, dict, frame, array, image, pickled, with_metadata]` | Each kind comes back with the same content as uploaded (the folder as a zip, extracted and compared file by file). |
| `test_artifact_content_matches_after_read_back[kind]` | For each kind (file, folder, dict, frame, array, image, pickled, with_metadata): the content read back on another process equals the content uploaded. |
| `test_every_uploaded_artifact_is_listed_on_the_task` | All uploaded names are listed on the task. |
| `test_file_artifact_records_its_sha256` | The recorded hash is the sha256 of the uploaded bytes. |
| `test_metadata_is_stored_and_returned` | `metadata={...}` is returned with the artifact. |
| `test_artifacts_without_metadata_have_none` | An artifact without metadata has none. |
| `test_large_file_uploads_and_downloads_intact` (slow) | A 20 MB file, above the 8 MB multipart threshold, comes back intact. |
| `test_download_link_serves_the_stored_bytes_from_object_storage` | `datachunks.prepare_download` gives a link on the storage service; the bytes behind it have the uploaded sha256. |
| `test_a_member_who_is_not_the_owner_cannot_delete_the_run` | Fails on defect: a plain user may delete another user's run; 403 is expected (clearml-server #3). |
| `test_a_downloaded_artifact_is_identical_on_a_second_download` | Two downloads give the same bytes and the same recorded hash. |

## test_06_git.py: git-managed and unmanaged code

Section 4 of E2E.md. The repositories are local (a bare remote and a checkout); the GitHub tests need GitHub.

| Test | Checks |
|---|---|
| `test_run_from_a_checkout_records_repository_branch_and_commit` | The run records the remote, the branch `main`, and the commit; the script sees the same commit. |
| `test_uncommitted_changes_are_recorded_as_a_diff` | An uncommitted change is recorded as the diff; the commit stays the last one. |
| `test_script_outside_git_is_recorded_without_a_repository` | A script outside git has no repository recorded, and its code is kept with the run. |
| `test_checkout_without_a_remote_records_commit_but_no_url` | A checkout with no remote records its commit and no URL. |
| `test_job_clones_the_recorded_commit_and_reports_it` | Fails on defect (D1): a job clones the recorded commit and reports it. |
| `test_repository_on_github_is_refused_at_enqueue_without_the_app` | Fails on defect (D2): enqueueing a github.com repository is refused with a message that names GitHub. Today the enqueue is accepted (the last full run). |
| `test_private_repository_is_refused_at_clone_time` | **Skip** unless `MLOPS_E2E_GITHUB_PRIVATE_REPO` is set. Fails on defect (D1) otherwise: a job whose repository the App cannot read fails at clone, with no token in its message. |
| `test_a_client_device_cannot_get_a_repository_token` | **Skip** unless `MLOPS_E2E_GITHUB_REPO` is set. A person's machine gets no repository token. |

## test_07_datasets_models.py: datasets and models

Section 7 of E2E.md. Each step runs in its own process.

| Test | Checks |
|---|---|
| `test_dataset_is_created_and_finalized` | A dataset of three files and a CSV is created, uploaded and finalized. |
| `test_finalized_dataset_refuses_new_files` | Fails on defect (D4): adding files to a finalized dataset is refused. |
| `test_second_machine_gets_the_same_files_and_hashes` | `Dataset.get` in another process gives the same files with the same hashes. |
| `test_dataset_fetch_of_an_unknown_id_fails` | An unknown dataset id fails. |
| `test_model_is_listed_under_its_run` | The model is listed in the run's output models. |
| `test_model_downloads_intact_on_another_machine` | The model's weights come back with the same digest. |

## test_08_agents.py: enrolling and running an agent

Section 5 of E2E.md. The agent is the managed daemon, in its own home, with its own device key and worker name.

| Test | Checks |
|---|---|
| `test_admin_enrols_the_agent_machine_with_its_own_key` | `clearml-agent init` (as admin) writes an agent key with mode 0600 and a device id. |
| `test_agent_device_is_kind_agent` | The device is listed as kind `agent`, not revoked. |
| `test_member_cannot_enrol_an_agent` | A plain user is refused ("only an admin may enrol an agent"); no key is written. |
| `test_agent_registers_as_a_worker_with_its_host_resources` | The worker is active; CPUs equal the host's, RAM is within 5 % of the host's, the GPU count equals `nvidia-smi`. |
| `test_agent_keeps_a_share_of_the_machine_for_the_host` | The agent reserves at least one CPU and some RAM for the host. |
| `test_agent_reports_its_usage` | Usage is reported at each sync: CPU percent, RAM in use, disk in use percent, all in range. |
| `test_agent_without_its_key_does_not_register` | An agent whose key is removed never registers, and its log names the key. |
| `test_agent_without_its_key_says_to_enrol_it` | Fails on defect (D7): the log says to run `clearml-agent init`, not a raw `Errno 2`. |
| `test_stopped_agent_is_lost_by_the_sweep_and_comes_back_without_enrolling` | The scheduler's sweep (its own timer, not a placement pass) marks the stopped agent lost within about 30 s; it returns active on its own, with the same device and key. |

## test_08b_agent_heartbeat.py: the heartbeat on its own

| Test | Checks |
|---|---|
| `test_stopped_agent_is_marked_lost_by_the_timeout_alone` | Fails on defect (D3): with no other scheduler activity, a stopped agent is marked lost after the heartbeat timeout. |

## test_09_jobs.py: queue, placement, execution

Section 6 of E2E.md. Scheduling tests run now; execution tests need a job to run, which D1 prevents.

| Test | Checks |
|---|---|
| `test_job_that_no_machine_fits_stays_queued_with_the_reason` | A job asking for 50 GPUs stays queued, and the Jobs view (`scheduler.get_jobs`, pending) gives its reason. |
| `test_job_that_fits_is_placed_on_the_agent` | A job that fits gets a `placed` event on the agent. |
| `test_job_placed_on_the_agent_is_claimed_by_it` | The agent claims a placed job (`claimed` event). |
| `test_enqueueing_a_queued_task_again_leaves_it_queued_once` | Enqueueing a queued task again is accepted and leaves it queued, once. |
| `test_enqueue_works_after_the_task_was_read` | Fails on defect (D6): enqueue after a service call is refused ("upgrade clearml-server"). |
| `test_job_with_a_missing_image_fails_once_and_is_not_rescheduled` | An image that cannot be pulled ends the job `failed`, with no retry: only lost attempts are retried. |
| `test_higher_priority_job_is_placed_before_a_lower_one` | A holder job takes the whole machine; a low and a high priority job wait behind it; the high one must be placed first. **Currently failing** in the last full run: the low priority job was placed first. Not yet explained. |
| `test_job_runs_to_completion_with_its_scalars_and_artifact` | Fails on defect (D1): the job completes, with its scalars and its artifact. |
| `test_failing_job_is_failed_with_its_traceback_and_the_agent_is_free` | Fails on defect (D1): a job raising after two scalars ends `failed`, with the traceback in its log. |
| `test_aborted_job_stops_within_thirty_seconds` | Fails on defect (D1): a job whose body has started is aborted, and stops within 30 s. |
| `test_lost_agent_during_a_job_retries_the_job_once` | Fails on defect (D1): a job whose agent is killed mid-run is retried once (`retried` event). |
| `test_agent_reports_no_running_job_once_a_job_completes` | Fails on defect (D1): after a job completes, the agent reports no running job. |

Not yet covered (E2E.md, section 6): live usage of a running job, resource limits inside the container, and the job's
working folder removed afterwards (all need D1 fixed).

## test_10_web_app.py: the web app as a person sees it

UI checks of E2E.md, in headless Chromium. Each test signs in through the real sign-in form, in a fresh context.

| Test | Checks |
|---|---|
| `test_sign_in_renders_the_dashboard` | Sign-in lands on the dashboard, with recent projects, recent experiments and "Manage workers and jobs". |
| `test_recent_experiments_list_a_run_recorded_from_the_client` | A run recorded from the client appears under recent experiments. |
| `test_stale_cookie_goes_to_the_sign_in_page` | A stale session cookie sends the browser to sign-in; no half-loaded page. |
| `test_dark_mode_renders_with_a_dark_background` | In dark mode the painted background is dark. |
| `test_light_mode_renders_with_a_light_background` | In light mode the painted background is light. |
| `test_dashboard_has_no_horizontal_scroll_at_phone_width` | At 390 px wide the dashboard does not scroll sideways. |
| `test_manage_workers_and_jobs_page_opens` | "Manage workers and jobs" opens the workers and jobs page. |
| `test_restarting_the_api_keeps_the_dashboard_rendering` (`test_13_api_restart.py`) | Restart regression: after the API container restarts, a reload renders the same dashboard. Runs last, in its own module. |

## test_11_cleanup.py: deleting what the suite made

Section 8 of E2E.md. The stack itself is removed at the end of the session (`conftest.py`).

| Test | Checks |
|---|---|
| `test_deleted_run_loses_its_stored_bytes` | After a run is deleted, the asynchronous delete service removes its artifact from object storage (the link stops serving the bytes). |
| `test_datachunk_route_refuses_a_deleted_run` | Asking for a download link of a deleted run is refused. |

## test_12_web_runs.py: runs in the web app

The scalars chart, console, debug samples, comparison, dashboards and live job status.

| Test | Checks |
|---|---|
| `test_scalars_page_draws_both_series_of_the_loss` | The legend names `train` and `val`; the summary shows `accuracy 0.93`; the chart is drawn. |
| `test_hovering_the_chart_shows_a_tooltip` | Moving the pointer over the plot changes what is drawn (the tooltip and guide line). The tooltip values are drawn on a canvas, so the stored values are checked through the API in `test_04` instead. |
| `test_console_tab_shows_the_line_the_script_printed` | The console tab shows the line the script printed. |
| `test_debug_sample_renders_as_an_image` | The debug sample is an image that renders (natural width above zero). |
| `test_comparison_view_overlays_both_runs` | The project's scalars view lists both runs and draws `loss` across them. The view is opened by clicking the scalars button of the experiments toolbar (by position, as the toolbar has no text). |
| `test_project_tabs_offer_tasks_and_experiments` | The project header shows the TASKS and EXPERIMENTS tabs. |
| `test_task_folder_lists_its_experiments` | The project's TASKS tab lists the run's task. |
| `test_single_click_selects_and_double_click_opens_a_project` | A single click on a project does not navigate; a double click opens the project. |
| `test_jobs_list_shows_a_running_job_without_a_reload` | Fails on defect (D1): the job's own row on the Jobs page shows it running, without a reload. |

## Status of the last full run

The status of the last full run, the open results and the known defects are in [E2E.md](E2E.md). The status is kept there
so the catalogue does not repeat it.

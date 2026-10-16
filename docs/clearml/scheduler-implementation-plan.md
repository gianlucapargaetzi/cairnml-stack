# Implementation plan: scheduler, agent enforcement, and the Workers and Jobs views

This plan builds the design in [scheduler-concept.md](scheduler-concept.md). The concept says what the system does and why; this plan says what to change, in which file, in which order, and how each step is proven. Read the concept's "Terms and rules" first.

Scope, in three parts:

1. **Scheduling and management of jobs** (server): requirements and priority on tasks, placement, reservations, retry, failure reasons.
2. **Enforcement** (clearml-agent): one agent per machine, several jobs at once, hard limits, host reserve, failure classification.
3. **Visibility** (web app, "Workers and Queues"): a tree of workers with their jobs and live usage, and a flat list of running and scheduled jobs in place of the queues page.

## Rules for the executor

These repeat the rules of [implementation-plan.md](implementation-plan.md); they apply unchanged.

1. **One task is one commit** in the repository being changed. Imperative message, then a short "why". **No attribution lines and no mention of any AI tool**: the repository owner's rule overrides any default.
2. **Tests first.** For every rule in the concept, write the failing test, then the code. A rule without a test that fails without it is not done.
3. **Never weaken a check to pass a test.** No test-only bypass in server or agent code.
4. **Stay in scope.** New code goes in new modules (below). Touch existing files only where a task names them. No refactors, no formatting sweeps.
5. **Stop rules.** If a command fails twice after a fix, or a file or function named here does not exist, write what you found to `~/Documents/mlops-clearml/BLOCKED.md` and stop. Do not guess a path.
6. **Secrets** are never committed, printed, or logged. **Never push.**
7. **Gates.** At each `STOP-n`, write `~/Documents/mlops-clearml/REPORT-SCHED-n.md` (done, test output summary, open questions), print its path, and wait for the user.
8. Keep `~/Documents/mlops-clearml/NOTES.md` current with discovered paths and commands.
9. **Versions.** Each fork keeps its own version; bump per the repository's convention when a phase is merged. The main repository's version rules refer to packages that no longer exist on this branch and do not apply.

## Workspace and new modules

Work in `~/Documents/mlops-clearml/` on branch `idp-port` (create `sched-port` from it in each fork and merge back at each STOP).

| Repo | New module | Existing file that is changed |
|---|---|---|
| clearml-server | `apiserver/bll/scheduler/` (`model.py`, `placement.py`, `ledger.py`, `lifecycle.py`, `failure.py`, `events.py`, `usage.py`) | `database/model/task/task.py`, `services/tasks.py`, `bll/task/task_operations.py`, `bll/workers/__init__.py`, `apimodels/workers.py`, `config/default/services/scheduler.conf` (new) |
| clearml-server | `apiserver/services/scheduler.py`, `apiserver/apimodels/scheduler.py`, `apiserver/schema/services/scheduler.conf`, `apiserver/database/model/scheduler.py` | |
| clearml-agent | `clearml_agent/scheduler/` (`capacity.py`, `ledger.py`, `client.py`, `runner.py`, `enforce.py`, `usage.py`, `failure.py`, `daemon.py`) | `commands/worker.py` (new `daemon --managed` entry only), `definitions.py`, `helper/resource_monitor.py` (export the sampling functions only) |
| clearml (SDK) | `clearml/backend_interface/task/requirements.py` | `clearml/task.py` (`set_requirements`, `enqueue`), `clearml/automation/*` (pipeline step mapping) |
| clearml-web | `src/app/features/orchestration/` (new feature folder: `workers-tree/`, `jobs/`, `dumb/`, `store/`) | `features/workers-and-queues/workers-and-queues.{routes,consts}.ts`, `resources-dashboard.component.ts` (real data), enqueue dialog in `webapp-common/experiments/` |

Tests: server `apiserver/tests/automated/` and `apiserver/tests/scheduler/` (unit tests of pure functions need no database); agent `tests/scheduler/`; web `*.spec.ts` beside the component, and Playwright scenarios as a script in `clearml-web/e2e/` (see phase 7).

## What the code looks like today (checked)

- **Workers** are entries in **Redis** with a timeout, written by `workers.register` and `workers.status_report` (`bll/workers/__init__.py`, `WorkerEntry` in `apimodels/workers.py`). They are not durable, and they carry no capacity. Machine statistics go to Elasticsearch through `log_stats_to_es`.
- **Queues** are Mongo documents holding an ordered list of entries. `tasks.enqueue` (`bll/task/task_operations.py:203`) needs a queue and falls back to the default queue. The agent takes work with `queues.get_next_task` and then calls `tasks.started`.
- **Tasks** have `execution.queue`, `last_worker`, `last_worker_report`, `last_device` (ours), and `runtime`.
- **The agent runs one task at a time** in its loop: `run_one_task` blocks until the job ends (`commands/worker.py:1135`). The only concurrency today is the dynamic-GPU and services modes, which work by registering extra workers named `<name>:gpuN` and parsing those names (`_dynamic_gpu_get_available`, around line 1840). The concept replaces that.
- **The agent has no out-of-memory detection**: `grep -n "OOMKilled\|oom" commands/worker.py` finds nothing. It starts Docker through `_get_docker_cmd` and adds `--gpus` but no `--memory` or `--cpuset-cpus`.
- **The web app** has the feature `features/workers-and-queues` with the routes dashboard (mock data, ours), workers and queues. `chart.js` with `ng2-charts` is already used (`sm-line-chart`), and `sm-table` supports row expansion.

## Design decisions fixed by this plan

These are the choices the plan makes so the executor does not have to. Each can be reversed before the phase that uses it.

| # | Choice | Why |
|---|---|---|
| D1 | **Pending tasks stay in one hidden internal queue per company** (`scheduler`). The scheduler orders them; nothing else reads that order. | The task state machine, pipelines, the `queued` status and all existing task endpoints keep working. Queues are removed from the UI and the API in the last phase, with the state machine untouched. |
| D2 | **Reservations and worker capacity are stored in Mongo**, not Redis. | They must survive an API-server restart. Redis keeps its present role for liveness and statistics. |
| D3 | **Placement runs in the API server, under one Redis lock per company**, on events (enqueue, job end, worker sync, offer expiry), plus a timer every 15 s as a safety net. | The API server runs several processes; the lock keeps one pass at a time. No new service. |
| D4 | **The agent talks to the server through one call, `scheduler.sync`, every 10 s.** It carries machine and per-job usage up and offers, stops and settings down. | One round trip, no queue polling, per-job usage arrives with the same call. |
| D5 | **Placement is an offer.** The server writes a reservation in state `offered` with a 60 s expiry. The agent claims it (`scheduler.claim`), which sets the task `in_progress` and issues the job token. An unclaimed offer expires and the task goes back to pending. | A crashed or slow agent cannot hold a task. |
| D6 | **Each job runs in its own `clearml-agent execute --id <task> --docker …` subprocess**, started by the new managed daemon. | `execute` is the supported single-task entry (the Slurm glue uses it). A subprocess per job avoids the shared mutable state of `Worker` (`worker_id`, environment, `docker_image_func`), which is not thread-safe. Spike S1 confirms it. |
| D7 | **Limits are Docker flags**: `--cpuset-cpus`, `--memory`, `--memory-swap` equal to memory, `--gpus device=…`, `--pids-limit`, plus a timer for `max_runtime_min`. | Kernel-enforced, and the OOM kill is visible in `docker inspect`. |
| D8 | **Exclusive jobs** (virtualenv, or no requirements) run through the existing path with no limits, and the worker takes nothing else until they end. | The concept's rule. They cannot be capped, so they are alone. |
| D9 | **Priority is a plain integer** (default 50, range 0 to 100), ordered by priority then submission time. Optional aging is off by default (`aging_points_per_hour: 0`). | The user chose plain integers; aging stays available if large jobs starve. |
| D10 | **The Jobs list is one endpoint, `scheduler.get_jobs`**; the Workers tree is one endpoint, `scheduler.get_overview`. The web app polls them every 5 s while the tab is visible. | The server has no push channel; polling is simple and enough for second-level freshness. |
| D11 | **Usage history** is stored in Elasticsearch next to the existing worker statistics, with a `task` field for per-job points. | Reuses the existing indices and the chart components. |

## Data model

### Task (Mongo, `database/model/task/task.py`)

New embedded fields, all optional:

```text
requirements:   {cpus:int, ram_gb:float, gpus:{count:int, min_memory_gb:float, model:str},
                 disk_gb:float, max_runtime_min:int}      # all four main fields or none
priority:       int 0..100, default 50
schedule:       {state: pending|offered|running|done, worker:str, reservation:str,
                 submitted:datetime, attempts:int, pending_reason:str}
failure:        {reason:str, detail:str, exit_code:int, worker:str, time:datetime,
                 reserved:{cpus,ram_gb,gpus}, peak:{ram_gb,gpu_mem_gb}}
```

Validation (in `bll/scheduler/model.py`, called by `tasks.edit`, `tasks.enqueue`, `tasks.create`): the four main fields are given together or not at all; `cpus >= 1`, `ram_gb > 0`, `gpus.count >= 0`, `disk_gb >= 0`; upper bounds from `scheduler.max_requirements` in the server config (so a typo cannot ask for 10 000 GB). The error message names the missing fields.

### Collections (Mongo, `database/model/scheduler.py`)

- **`SchedulerWorker`**: `id` (worker name, one per machine), `company`, `device` (the agent device, from the token), `capacity`, `reserved`, `schedulable` (capacity minus reserved), `can_enforce` (flags: docker, gpu-device-limit, cpuset), `state` (`active`, `draining`, `lost`), `last_sync`, `exclusive_task` (set while an exclusive job runs), `agent_version`.
- **`Reservation`**: `id`, `task`, `worker`, `company`, `cpus` (ids), `ram_gb`, `gpus` (indices), `disk_gb`, `state` (`offered`, `claimed`, `released`), `offered_at`, `claimed_at`, `released_at`, `release_reason`. A unique index on `(task, state in offered|claimed)` stops a task being reserved twice.
- **`SchedulerEvent`**: `time`, `company`, `kind` (`placed`, `claimed`, `released`, `failed`, `retried`, `worker_lost`, `worker_back`, `priority_changed`, `cancelled`), `task`, `worker`, `detail`. Feeds the event log in the dashboard. Retained 30 days.

Free capacity is always computed as `schedulable - sum(claimed or offered reservations)`; it is never stored, so it cannot drift.

## API (`services/scheduler.py`, version 2.30 or the next free)

All agent calls require a token of kind `agent` and the worker's bound device; the others use the normal user token.

| Endpoint | Caller | Purpose |
|---|---|---|
| `scheduler.register_worker` | agent | Capacity, reserved, `can_enforce`, version. Idempotent. Refuses a worker name already bound to another device. |
| `scheduler.sync` | agent | Body: worker, machine usage, `jobs: [{task, state, usage}]`. Returns `{offers, stop, settings}`. Updates `last_sync`. Expires stale offers, may run a placement pass for this worker. |
| `scheduler.claim` | agent | Takes an offer: checks the reservation is still `offered` and belongs to this worker, sets the task `in_progress`, marks `claimed`. The job token is then obtained as today (`devices.job_token`). |
| `scheduler.release` | agent | Job ended. Body: task, exit code, `failure` (structured) or success. Releases the reservation, sets the task state, applies retry, triggers a pass. |
| `scheduler.get_overview` | web | Workers with capacity, allocation, live usage, and their running jobs. One call for the whole tree. |
| `scheduler.get_jobs` | web | Flat list: running and pending jobs, with state, priority, requirements, worker, wait time or run time, `pending_reason`, `failure`. Filters: state, user, project, free text. Paging. |
| `scheduler.get_usage_history` | web | Time series for a worker or a task: cpu, ram, gpu, gpu memory, disk; interval and range. |
| `scheduler.get_events` | web | Event log, newest first. |
| `scheduler.set_priority` | user | Owner or admin. Audited. |
| `scheduler.drain_worker` | admin | No new offers to the worker; running jobs finish. |
| `tasks.enqueue` (changed) | user | `queue` becomes optional and ignored in managed mode; requires requirements-or-none per the rules; sets `schedule.state = pending`; triggers a pass. |

Audit events (existing audit log): `scheduler.worker_registered`, `scheduler.offered`, `scheduler.claimed`, `scheduler.released`, `scheduler.priority_changed`, `scheduler.cancelled`.

Security rules: an agent can only sync, claim or release for its own worker and its own reservations; a task owner is never taken from the request; the job token is issued only after a successful claim by the device that holds the reservation.

## Scheduler behaviour (pure, in `placement.py`)

Input: pending tasks and worker states. Output: a list of `(task, worker, reservation)`. No database access, so it can be tested exhaustively and simulated.

1. Pending tasks sorted by `(-effective_priority, submitted)`. `effective_priority = priority + aging_points_per_hour × hours_waiting` (zero by default).
2. For each task:
   - **With requirements:** candidate workers are `active`, not holding an exclusive job, `can_enforce` the limits the task needs, and with enough free CPUs, RAM, disk and matching GPUs (`count`, `min_memory_gb`, `model`). Choose the **best fit**: the smallest leftover RAM, then fewest free CPUs, so large holes stay open. Choose concrete CPU ids and GPU indices.
   - **Without requirements (exclusive):** candidate workers are `active` and have no reservations. Choose the one with the smallest capacity.
   - If nothing fits, write `pending_reason` (see below) and go on to the next task (backfill).
3. A worker never gets an offer while it holds an exclusive job.

`pending_reason` is a short sentence, computed per task on each pass: "needs 24 GB GPU memory; no worker has a free GPU that large", "needs 12 GB RAM; best candidate gpu-box-01 has 9 GB free", "waiting for a whole machine; all workers are busy". The Jobs list shows it.

**Lost workers.** A worker with no `sync` for 3 intervals (30 s) becomes `lost`. Its claimed reservations are released with reason `worker_lost`. Each affected task is requeued once (`schedule.attempts == 0`); on the second loss it is failed with reason `worker_lost`. A worker that syncs again is `active`; the agent stops any container the server no longer lists in its `running` set.

## Agent (clearml-agent)

New mode: `clearml-agent daemon --managed [--reserve-cpus N --reserve-ram-gb X --reserve-disk-gb Y --docker IMAGE]`. It replaces `--queue`, `--dynamic-gpus` and `--services-mode` for managed machines. One daemon per machine; a second is refused by the existing singleton lock.

Components:

- **`capacity.py`**: detects CPUs (`os.sched_getaffinity`), RAM (`/proc/meminfo`), disk (the work directory's filesystem), and GPUs (the existing `gpustat`/NVML helpers used by `ResourceMonitor`). Applies the reserve from the configuration (`agent.managed.reserve` with the defaults from the concept) and reports `can_enforce` after probing Docker (`docker info`, a `--cpuset-cpus` dry run, NVIDIA runtime).
- **`ledger.py`**: the local copy of the reservations: what is running, with the CPU ids, GPU indices and memory each job holds. It is rebuilt on start from `docker ps --filter label=clearml.job` so a restarted agent finds its containers again.
- **`client.py`**: `register`, `sync` loop (10 s, jittered, back off on error), `claim`, `release`. While the server is unreachable the agent keeps its jobs running and accepts no new offers.
- **`runner.py`**: for a claimed offer, builds the command and starts `clearml-agent execute --id <task> --docker <image>` as a subprocess with the limits from `enforce.py`, labels the container `clearml.job=<task>`, and watches it in a thread. One thread per job, no shared state.
- **`enforce.py`**: turns a reservation into Docker flags and the environment: `--cpuset-cpus 4-7`, `--memory 12g --memory-swap 12g`, `--gpus "device=0,1"`, `--pids-limit`, `--stop-timeout`, and a deadline timer for `max_runtime_min`. The sum of all limits can never exceed `schedulable` because the server only offers what is free and the agent re-checks against its ledger before starting (it refuses and returns the offer if not).
- **`usage.py`**: every 2 s samples per-container usage from the cgroup files (`cpu.stat`, `memory.current`, `memory.peak`) or `docker stats --no-stream` as fallback, and per-GPU usage and memory per process from NVML. Machine totals come from the existing `ResourceMonitor` sampling. Aggregates are sent in each `sync`.
- **`failure.py`**: classifies a finished job. Order matters; the first strong signal wins:
  1. `docker inspect` `State.OOMKilled == true` → `oom`, with `reserved.ram_gb` and `peak.ram_gb`. Detail: "killed by the kernel: memory limit 12 GB reached (peak 12.0 GB)".
  2. Timer fired → `time_limit`.
  3. Exit code 137 or 143 with a stop requested by the server → `cancelled` (not a failure).
  4. Log tail matches `CUDA out of memory`, `CUDA error`, or an NVML Xid → `gpu_error` with the GPU index. These also count as **bad compute** with the GPU memory limit and peak.
  5. Log tail matches `No space left on device`, or the free-space check at exit is under 1 % → `disk_full`.
  6. Otherwise `error` with the exit code and the last 20 log lines.
  The reasons `oom`, `gpu_error`, `disk_full` and `time_limit` are grouped as "bad compute" in the UI. The reason, a one-line human sentence and the numbers are written both to the task (`failure`, `status_message`) and as a line in the task's console log, so the person reading the log sees why.
- **Exclusive jobs** use the same path without limits and with the whole machine's reservation; the worker reports `exclusive_task` in `sync`.
- **Crash reconciliation:** on start, containers with `clearml.job` labels are matched against the server's view in the first `sync` reply; containers the server does not list are stopped.

Spikes (phase 0) that can change this section: S1 `execute` as a subprocess with a Docker limit passed in; S2 `OOMKilled` is visible after `--rm` containers exit (the plan runs without `--rm`, removing the container after the state is read); S3 cgroup v2 versus v1 sampling paths.

## Web app

All UI follows `clearml-web/CLAUDE.md`: shared components only, theme variables, light and dark checked. No new colours.

Feature folder `src/app/features/orchestration/` with its own NgRx slice (`store/`: `overview`, `jobs`, `history`) and an effect that polls every 5 s while the page is visible (`document.visibilityState`), pauses when hidden, and keeps the last result on an error with a small inline notice. The route component keeps setting the header tabs the way `orchestration.component.ts` does today.

### Tabs

| Tab | Route | Content |
|---|---|---|
| Dashboard | `/workers-and-queues/dashboard` | The existing page, fed from `scheduler.get_overview` and `scheduler.get_events` instead of the mock |
| Workers | `/workers-and-queues/workers` | The worker and job tree (below) |
| Jobs | `/workers-and-queues/jobs` | The flat job list. `/workers-and-queues/queues` redirects here. The queue create, edit and rename dialogs are removed. |

The feature title stays "WORKERS AND QUEUES" until queues are gone from the API (phase 8), then becomes "WORKERS AND JOBS".

### Workers tab: tree of workers and their jobs

One `sm-table` with row expansion, the table's own mechanism (no accordion built by hand). Each row has a unique `id`, as the guide requires.

Worker row (level 1), left to right:

- A chevron (the expansion control), a `sm-circle-status` dot (active, draining, lost; the same status names and colours as elsewhere), and the worker name.
- **Jobs** count, and an "exclusive" label when it holds an exclusive job.
- Four usage cells with `mat-progress-bar`, each showing **allocated** (the reservation, a darker bar) over **used** (the live value, a lighter overlay) and a text such as "20 / 30 GB": CPU, RAM, GPU (count allocated of total, with utilisation), GPU memory. A fifth thin bar for disk.
- Reserved-for-host amounts appear in the tooltip, not as a column.
- A small live sparkline of the last 10 minutes of total CPU and GPU utilisation (`sm-line-chart` in compact mode).

Expanded content, a nested table of jobs (level 2):

- Job name (a link to the experiment), project, user's avatar, priority, run time, state.
- Reserved versus used per resource, as the same paired bars: CPU, RAM, GPU, GPU memory. A job that approaches its limit (above 90 % of the reservation) has its bar in the warning colour; a job killed for compute shows the failure reason in the error colour on its last row for the next 10 minutes.
- A "details" action that opens the job's side panel (below).

Master and detail: clicking a worker row opens a detail panel with `as-split` (as the current workers page does): charts over a selectable range (1 h, 3 h, 12 h, 24 h) for CPU, RAM, GPU utilisation, GPU memory, disk and network, drawn with `sm-line-chart`, from `scheduler.get_usage_history`. Selecting a job row opens the same panel for the job: its reserved-versus-used series, its requirements, and the failure block if it failed (reason, sentence, numbers).

Controls above the table: search (`sm-search`), a state filter, and "Expand all / Collapse all". Admin-only actions in the row menu: drain a worker, with `sm-confirm-dialog`. Empty state: "No workers are registered. Start an agent with `clearml-agent daemon --managed`." with a copyable command (`sm-copy-clipboard`).

### Jobs tab: flat list of running and scheduled jobs

One `sm-table`, sorted running first, then pending by the scheduler's order. Columns: **state** (running, pending, offered, failed in the last 24 h), **position** (for pending), **priority** (inline edit through `sm-inline-edit`, owner or admin), name (link), project, user, **requirements** summary ("4 CPU · 12 GB · 1 GPU 24 GB" or "whole machine"), **worker** (running), **waiting or running time**, and a **why waiting** cell (the `pending_reason`, muted, truncated with a tooltip). Row menu: cancel (confirmed), change priority.

Filters: state buttons (`sm-button-toggle`), user, project, free text. Selecting a row opens the same job panel as in the Workers tab. Empty state: "No jobs are running or waiting. Enqueue a task from its page."

The queue-only features are removed with the queues page: queue creation, rename, tags, "move to front".

### Enqueue dialog

The experiment's Enqueue dialog drops the queue picker (`select-queue`) and gets: a priority field (number, default 50), and a "Compute" section with a choice "Whole machine" or "Specify" (CPUs, RAM in GB, GPUs, GPU memory, disk, maximum run time). "Specify" requires all four main fields (the form shows what is missing); "Whole machine" sends no requirements and says that it blocks a machine. Pipelines and clones use the values of the cloned task.

### Dashboard tab

Totals (workers online, GPUs, CPUs allocated of total), resource-group table (a group is a worker tag), the usage chart and the event log become real: events from `scheduler.get_events`, totals from `scheduler.get_overview`. The mock file is deleted at the end of the phase.

## SDK

- `task.set_requirements(cpus=4, ram_gb=12, gpus=1, gpu_memory_gb=24, disk_gb=50, max_runtime_min=720)` stores the requirements; calling it with a missing main field raises `ValueError` listing what is missing. `task.set_priority(n)`.
- `Task.enqueue(task, queue_name=None, priority=None)` works without a queue. With `queue_name` the call still works in managed mode but the name is ignored with a warning, for one release.
- `Task.init(...)` is unchanged.
- Pipelines (`clearml/automation/controller.py`): a step's `execution_queue` is accepted and ignored with a warning; a step gets `requirements=` and `priority=` arguments instead. The step inherits the pipeline's priority by default.

## Phases

Each phase ends with the listed tests passing and a commit per task. Server tests need the stack from `deploy/clearml/compose.yaml` (or the test stack used for the identity tests).

### Phase 0 — baseline and spikes

- **P0.1** Create `sched-port` branches. Record the baselines: server test count, agent test count, web build.
- **P0.2** Spike **S1**: on one machine start `clearml-agent execute --id <task> --docker <image>` twice at the same time with different `--docker_args`/environment limits; confirm they do not interfere and that extra docker arguments can be passed per process (find the exact switch with `grep -n "docker_args\|extra_docker" clearml_agent/commands/worker.py`). Record the command.
- **P0.3** Spike **S2**: run a container that allocates more than `--memory`; confirm `docker inspect` shows `OOMKilled: true` and exit code 137, with and without `--rm`. Spike **S3**: confirm the cgroup files used for sampling on this host (cgroup v2: `/sys/fs/cgroup/system.slice/docker-<id>.scope/{cpu.stat,memory.current,memory.peak}`).
- **P0.4** Spike **S4**: confirm `sm-table` row expansion can hold a nested `sm-table` and keeps its state across a data refresh every 5 s (no collapse). Spike **S5**: send per-job points into the existing Elasticsearch worker-stats index and query them (`bll/workers/__init__.py::log_stats_to_es`).

**STOP-S1.** Report the spikes, with any finding that changes D5 to D8. Wait for the user.

### Phase 1 — data model and validation (server, SDK)

- **P1.1** `database/model/scheduler.py` models and indexes; migration only if the baseline requires it. Test: create, read, unique reservation per task.
- **P1.2** Task fields `requirements`, `priority`, `schedule`, `failure`; validation in `bll/scheduler/model.py` wired into `tasks.edit`, `tasks.create`, `tasks.enqueue`. Tests: all-or-none, bounds, error message names the missing fields, default priority.
- **P1.3** Config `scheduler.conf`: intervals, expiry, retry count (1), aging (0), max requirements, event retention, default host reserve. Test: defaults load.
- **P1.4** SDK `set_requirements`, `set_priority`, `Task.enqueue` without a queue. Tests with a mocked server.

### Phase 2 — scheduler core (pure)

- **P2.1** `placement.py`: ordering, fit, best fit, CPU and GPU choice, exclusive rule, drain, `pending_reason`. Test matrix (each is a named test): empty cluster; fits exactly; does not fit anywhere; GPU memory and model matching; best fit leaves the large hole; exclusive job needs an empty worker; exclusive job blocks others; priority order; ties by submission time; backfill past a blocked head; aging off and on; a draining worker gets nothing.
- **P2.2** `ledger.py` (server side): free-capacity computation; invariant test with random sequences of place and release (property test): free never negative, reservations never overlap on CPU ids or GPU indices.
- **P2.3** A **simulator** in `tests/scheduler/sim.py`: a few hundred tasks and ten workers over simulated time, asserts no over-allocation and bounded waiting. Run in CI; its seed is printed.

### Phase 3 — server protocol and lifecycle

- **P3.1** `scheduler.register_worker` and the worker-to-device binding. Tests: second device refused, sync from another device refused.
- **P3.2** `scheduler.sync`: heartbeat, offer delivery, offer expiry (60 s), stop list. Tests with fake time.
- **P3.3** `scheduler.claim` and `scheduler.release`; state changes through the existing task status machinery (`ChangeStatusRequest`), D1's hidden queue; retry once then fail; `failure` stored; status message "Failure due to bad compute: …" for the grouped reasons. Tests: claim of an expired offer refused; claim by another worker refused; double claim refused; release success; release with each reason; retry then fail on the second `worker_lost`.
- **P3.4** Placement pass under the Redis lock, triggered by enqueue, release, sync and the 15 s timer. Test: two concurrent passes cannot double-allocate (run 50 times with threads).
- **P3.5** Lost-worker detection and recovery (30 s). Test with fake time: loss requeues once, second loss fails, return of the worker stops unlisted containers.
- **P3.6** Events and audit: every state change writes a `SchedulerEvent` and the audit line. Test per endpoint.
- **P3.7** Read endpoints: `get_overview`, `get_jobs`, `get_events`, `set_priority`, `drain_worker`, `get_usage_history`; per-job usage points into Elasticsearch (S5). Tests for filters, paging, ownership (only the owner or an admin changes priority).
- **P3.8** Remove the agent's need for queues: `tasks.enqueue` without a queue; the hidden queue is created on demand; the old queue endpoints still work (agents in the old mode keep working until phase 8).

**STOP-S2.** Server done: all tests pass, baseline suite unchanged, the checklist rows for phase 3 listed with their tests. Wait.

### Phase 4 — agent

Build on one machine first; this is the largest risk.

- **P4.1** `capacity.py` with the reserve; tests with fake `/proc` content and fake NVML.
- **P4.2** `client.py` and `daemon.py`: register, sync loop, backoff, offline behaviour; `daemon --managed` entry in `commands/worker.py` (only the argument and the dispatch). Tests with a fake server.
- **P4.3** `ledger.py` (agent): reserve, release, rebuild from labelled containers; refuse an offer that does not fit (returns it).
- **P4.4** `enforce.py` and `runner.py`: Docker flags, the subprocess per job, the deadline timer, container labels, container kept until classified. Tests: the produced command contains each limit; two jobs get disjoint CPU ids and GPU indices; the sum of limits never exceeds schedulable.
- **P4.5** `usage.py` and the per-job points in `sync`. Tests with fake cgroup files.
- **P4.6** `failure.py` with the order in the design. Tests: one per reason, using recorded `docker inspect` JSON fixtures and log tails; a container with both OOM and a stack trace in the log is classified `oom`.
- **P4.7** Exclusive jobs through the existing path; the worker reports and the server blocks it. Test: no offer while exclusive.
- **P4.8** Crash reconciliation: restart the daemon with a running container; it rejoins; a container the server does not list is stopped.
- **P4.9** Real runs on the host (not mocked), recorded in the report: a job that exceeds its memory limit fails with `oom` and the right numbers; two small jobs run side by side with disjoint CPUs; a job that exceeds `max_runtime_min` is stopped with `time_limit`; killing the agent and starting it again keeps the job; stopping a task in the UI stops the container.

**STOP-S3.** Agent report with the real-run evidence (task ids, the failure lines as shown in the console log). Wait.

### Phase 5 — SDK, pipelines, CLI

- **P5.1** Pipeline steps: `requirements=`, `priority=`, ignore `execution_queue` with a warning; tests with a mocked server.
- **P5.2** `clearml-task` and the `clearml-agent` CLI help text: remove queue options from the managed path, document `--managed`.
- **P5.3** Migration helper `clearml-scheduler-migrate` (admin): lists tasks pending in old queues and re-enqueues them without a queue, with whole-machine requirements. Test on a copy of data.

### Phase 6 — web

- **P6.1** Store slice and polling effect in `features/orchestration/store/`, with a visibility pause. Tests: polling starts and stops, an error keeps the last data.
- **P6.2** `workers-tree` component (S4): paired allocated/used bars, nested job table, expand state kept across refresh, the worker detail panel with charts. Unit tests for the view model (allocation versus usage, warning at 90 %).
- **P6.3** `jobs` component and routes (redirect from `queues`), inline priority edit, cancel with `sm-confirm-dialog`, the "why waiting" cell, the job panel with the failure block.
- **P6.4** Enqueue dialog: priority and compute section; the all-or-nothing form validation.
- **P6.5** Dashboard fed from real data; delete `resources-dashboard.mock.ts`.
- **P6.6** Remove the queue pages and dialogs; keep the code until phase 8 compiles without them. `pnpm run build` passes.

**STOP-S4.** Take screenshots with Playwright at desktop width and about 1200 px, in light and dark mode, of the Workers tree (collapsed and expanded, with a job near its limit), the Jobs list (running, pending with reasons, a failed job), and the enqueue dialog. Check against an existing page for spacing and components. Wait.

### Phase 7 — end-to-end, load and security

- **P7.1** End-to-end scenarios on the real stack (Playwright for the web, shell for the agent), each recorded in `REPORT-SCHED-7.md`:
  1. Two workers; submit six tasks with different priorities and sizes; they are placed by priority and best fit; the tree shows reserved and used live.
  2. A task with no requirements waits for an empty worker and blocks it; small tasks go to the other worker.
  3. A partial requirement set is refused with a message in the UI and the SDK.
  4. A job exceeds its memory: the task fails with "Failure due to bad compute: out of memory …", the console log shows the line, the tree and list show the reason.
  5. A job exceeds its run time: `time_limit`.
  6. Kill the agent during a job: the worker turns `lost` after 30 s, the task is requeued once, runs elsewhere; killed again: fails with `worker_lost`.
  7. Restart the API server during a job: reservations survive, the job continues, nothing is placed twice.
  8. Cancel a running task: the container stops and the reservation is released within one sync.
  9. Change a priority: the order changes in the list at the next refresh.
  10. Revoke the agent's device: its next `sync` is refused and its offers expire.
- **P7.2** Load test: 500 pending tasks and 50 simulated workers (the fake-agent client); a placement pass stays under 200 ms on the test host; the API's `sync` p95 stays under 50 ms. Record the numbers.
- **P7.3** Security checklist rows (add to [security-checklist.md](security-checklist.md), each with its test): a worker cannot be taken over by another device; an agent cannot claim another worker's offer; a job token is issued only after a valid claim; a user cannot change another user's priority; requirements are bounded; scheduler events carry no secrets; an expired offer cannot be claimed.
- **P7.4** Documentation: README agent section (`daemon --managed`, the reserve), migration guide section "queues to requirements", an operator note on `can_enforce`.

**STOP-S5.** Final report with all scenario results, the load numbers and the checklist. The user arranges the review.

### Phase 8 — remove queues

- **P8.1** Remove `queues.*` endpoints, the queue models' use, the `execution_queue` handling in the SDK, `get_next_task` use in the agent, the old daemon modes (`--queue`, `--dynamic-gpus`, `--services-mode`), and the unused web code. Keep the hidden `scheduler` queue record only if the task state machine still needs a queue id; otherwise drop it with a migration.
- **P8.2** Rename the feature to "WORKERS AND JOBS" in the header, route data and breadcrumbs.
- **P8.3** Run all suites, the scenarios again, and the vendored-file check.

## Effort and order

About 14 to 18 weeks for one experienced developer: phase 0 one week; phases 1 to 3 five to six weeks; phase 4 four to five weeks (the largest risk, and the only phase that needs real hardware); phase 5 one week; phase 6 three weeks; phases 7 and 8 two weeks. Phases 1 to 3 and the first half of phase 6 (store, tree with mocked responses) can run in parallel if two people work on it.

## Risks

- **Docker is required for sharing.** A worker without working Docker, GPU device limits or cpuset reports `can_enforce` without them, and only exclusive jobs are placed on it. The Workers tree shows the missing capabilities.
- **`execute` as a subprocess (D6)** may not accept per-job Docker limits cleanly. Spike S1 decides; the fallback is a small addition to `execute` that reads the limits from an environment variable.
- **cgroup layout differs between hosts** (v1 or v2, systemd or cgroupfs). Sampling falls back to `docker stats`, which is slower but works everywhere.
- **Memory accounting in containers.** `--memory` counts page cache; a job that reads a large dataset can approach its limit without being in trouble. The failure line shows `peak` from `memory.peak` (which includes cache), and the doc says so. If it produces false alarms, count `memory.stat` anon plus file-mapped instead.
- **Starvation of large or whole-machine jobs** by many small jobs. Mitigation: aging (D9). Measure it in the simulator before turning it on.
- **Elasticsearch volume** from per-job points every 10 s. At 50 workers and 8 jobs each this is about 40 points per second; the existing daily indices cope, and retention follows the existing worker statistics.
- **Polling load** from many open browsers: one `get_overview` per 5 s per viewer. The call reads Mongo and Redis only and is cached for 2 s per company.
- **Disk limits** are checks, not enforcement (the concept says so). A full disk is reported as `disk_full` after the fact.

## Definition of done

- Every rule in the concept's "Terms and rules" has a named test, and the scenarios of P7.1 pass.
- `grep -rn "get_next_task\|queues\." ` in the managed paths of the agent and web app finds nothing after phase 8.
- The Workers tab shows every registered worker with live paired allocation and usage bars, and expanding it shows every running job of that worker with its own bars. The Jobs tab lists every running and waiting job with the reason it waits.
- A job killed for memory shows, on the task, in its console log, in the Jobs list and in the Workers tree, the same sentence naming the limit and the peak.
- No secret in any log, event or API response of the new endpoints.

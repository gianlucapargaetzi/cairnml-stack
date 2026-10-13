# Phase 6 progress: our own pages in the fork

**Status:** In progress. Plan: `docs/AIM_UI_IMPLEMENTATION_PLAN.md`, section D.6 (parity checklist) and Phase 6. The old dashboard (`packages/mlops-server/src/mlops_server/ui/static`) is deleted only when the checklist is complete.

## Done

- **Jobs** (`pages/Jobs`): groups, detail with the spec, cancel, copy and reschedule. The reschedule body is JobOverrides: only changed fields are sent.
- **Resources** (`pages/Resources`): agents with capacity, usage and running jobs; queues with the stuck, busy and idle state.
- **Administration** (`pages/Admin`): users, agents and client keys, read-only, as before.
- **Datasets** (`pages/Datasets`): list with filters; detail with the card, schema, splits, DVC contents, versions and users.
- **Projects** (`pages/Projects`): the project tree and summary; the project overview with experiments (best result), repositories, datasets, containers and recent runs; the repository history graph with branch chips and the runs on each commit. Zoom and drag-to-pan of the old graph are not ported.
- **Experiment** (`pages/Experiment`): settings saved through the experiment API, best result, runs table (sorted, varying parameters as columns), primary-metric chart. The unrouted Aim-era page under `pages/Experiment` is replaced.
- **Compare** (`pages/Compare`): 2 to 10 runs side by side: metric charts and table, parameters (differences by default), code and data, requirement differences. Opened from the experiment page.
- **Run detail**: Images tab (see PHASE5_PROGRESS); overview with the command line, environment, packages, git state and artifacts (downloads through presigned URLs); "Run on an agent" dispatch form.
- **Tags** (`pages/Tags`): tags of a project (create, rename, recolour, describe, delete). Attaching a tag from a run's sidebar resolves the name in the run's project and creates the tag when needed. Server fix: a browser session can write the runs it owns.

## Not done (parity checklist)

- Pinned sequences and the activity feed (projects and experiments endpoints; deferred from Phase 3 and 5).
- Run detail: datasets used by the run (the old run page showed them with their DVC hash).
- Graph zoom and pan.
- Distributions, audio, text and figure pages: see issue #2 and the distributions decision.
- After the checklist is complete: delete the old dashboard (`packages/mlops-server/src/mlops_server/ui/static`) and update the docs.

## Verified

- Each page was loaded in a headless browser against the harness (real Postgres, real storage) with no console errors. The jobs page was exercised end to end: select, copy with a changed queue, and the request body (`{"queue": "gpu-queue"}`).
- The harness has no GitHub repository and no agent, so the datasets detail with a real card and the resources agent cards were checked only in their empty states.
- UI Jest: 40 suites, 128 tests. `tsc` clean. Bundle builds with the host guard.
- Python: 799 passed, 2 skipped. ruff clean.

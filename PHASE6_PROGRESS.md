# Phase 6 progress: our own pages in the fork

**Status:** In progress. Plan: `docs/AIM_UI_IMPLEMENTATION_PLAN.md`, section D.6 (parity checklist) and Phase 6. The old dashboard (`packages/mlops-server/src/mlops_server/ui/static`) is deleted only when the checklist is complete.

## Done

- **Jobs** (`pages/Jobs`): groups (active, finished, failed, cancelled), detail with the spec, cancel, copy and reschedule. The reschedule body is JobOverrides: only changed fields are sent.
- **Resources** (`pages/Resources`): agents with capacity, usage and running jobs; queues with the stuck, busy and idle state.
- **Administration** (`pages/Admin`): users, agents and client keys, read-only, as before. Non-administrators see "Administrators only.".
- **Datasets** (`pages/Datasets`): list with filters, detail with the card (Markdown), schema, splits, DVC contents, versions and users. Detail is selected by the query parameters, as in the old dashboard.
- Run detail: **Images** tab (see PHASE5_PROGRESS).

## Not done (parity checklist)

- Projects: overview with experiments, best runs per primary metric, repo graph.
- Experiment page with edit (the component exists in `pages/Experiment`, not routed).
- Run detail: Run Params, code and data, artifact download, dispatch to an agent ("Run on agent").
- Compare 2 to 10 runs.
- Tags: attach and CRUD from the explorer (deferred here from Phase 4).
- Pinned sequences and the activity feed (projects/experiments endpoints; deferred from Phase 3/5).
- Distributions, audio, text and figure pages: see issue #2 and the distributions decision.

## Verified

- Each page was loaded in a headless browser against the harness (real Postgres, real storage) with no console errors. The jobs page was exercised end to end: select, copy with a changed queue, and the request body (`{"queue": "gpu-queue"}`).
- The harness has no GitHub repository and no agent, so the datasets detail with a real card and the resources agent cards were checked only in their empty states.
- UI Jest: 34 suites, 106 tests. `tsc` clean. Bundle builds with the host guard.

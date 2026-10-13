# Phase 3 progress: explorer API v1

**Status:** Done for the search, run actions, tags, bookmarks and filter language. The audit of the Aim UI calls is complete. Deferred items are listed below and in `docs/explorer_api.md`.

## What changed

- `services/query.py`: the filter language. It is parsed with `ast`, checked against a whitelist, and translated to SQL with bound parameters. It is never executed. Numbers bind as floats.
- `services/explorer.py`: search, run info, sampled traces, and the project parameter listing.
- `routers/explorer.py`: 17 endpoints under `/api/v1/explorer` (see `docs/explorer_api.md`). Reads need a client or browser session. Writes add the CSRF check. Bookmarks are private to their owner.
- `services/access.py`: `accessible_project_ids` replaces the per-project loop in the runs router.
- `ProjectOut` now includes the project `id`, which the explorer uses in paths.
- Tests: `test_query_language.py` (49 cases), `test_explorer_api.py` (17 endpoint cases plus every accepted filter form run against the database).

## Known limits

- A run returns at most 50 traces. Each trace costs about three queries, so a page of 50 runs with many traces is slow. Batching the trace queries is a Phase 7 performance item.
- `run.tags` is only usable inside `any()`. Tags are attached by run, through the explorer.
- Runs with no matching trace are left out of search/metric.

## Deferred

- `runs/search/metric/align`, the `get-batch` and `get-step` calls: the chart work in the Phase 4 fork (metric detail) and Phase 5 (sequences).
- `metric.last` in filters.
- Sequence filters (`images.*`, `audios.*`, ...): Phase 5.
- Run deletion: needs a decision on artifacts and sequence blobs.
- `experiments/{id}/activity`, `projects/activity`, `projects/pinned-sequences`.

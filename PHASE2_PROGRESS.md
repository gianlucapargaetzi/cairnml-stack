# Phase 2 progress: data model

**Status:** Data model and SDK surface done. Explorer endpoints for tags and bookmarks come in Phase 3, media ingestion in Phase 5.

## What changed

- Runs: `description` and `archived` columns, exposed in the run output and in PATCH. PATCH also accepts `name`. The existing `notes` column is the run's notes field.
- Metrics: `metric_series` (one per run, name and context) and `metric_points` (points of a series, with `step`, `epoch`, `value`, `ts`). Points posted with a `context` such as `{"subset": "val"}` go to their own series. The context has at most 8 keys; each key is at most 64 characters and each string value at most 128. Both sides (server and SDK) share these limits.
- Legacy metric reads (`GET /runs/{id}/metrics`, run compare, project best values) read only the default series (empty context). Their numbers do not change when context series are added. Phase 3 adds context-aware reads.
- Tables added: `tags`, `run_tags`, `sequences`, `sequence_items`, `explorer_states` (bookmarks). They are in the baseline migration; the constraints are tested.
- SDK: `Run.track(value, name="metric", *, step, epoch, context)`. `log_metric` calls it. `run[key] = value` sets one parameter and the server merges it. A bad context raises `ValueError` in user code.

## Not in Phase 2

- `log_image`, `log_audio`, `log_text`, `log_figure`, `log_distribution`: the plan lists them under both Phase 2 and Phase 5. They are in Phase 5 here, with their ingestion and S3 storage.
- Endpoints for tags and bookmarks: Phase 3.

## Verification

- `uv run pytest -q`: 644 passed, 2 skipped, 14 deselected.
- `uv run ruff check .`: clean.
- The migration test checks that the baseline matches the models.

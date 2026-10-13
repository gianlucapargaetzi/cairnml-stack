# Phase 1 progress: rename and baseline reset

**Status:** Complete. Phase 1 of `docs/AIM_UI_IMPLEMENTATION_PLAN.md` is done.

## What changed

- Database: one baseline migration (`0001_baseline.py`). Tables `runs` (executions) and `experiments` (groupings). Old migrations 0001–0005 removed.
- Models: `Run` (was `Experiment`) and `Experiment` (was `Task`).
- Server: `routers/runs.py` (was `experiments.py`), `routers/experiments.py` (was `tasks.py`), `services/experiments.py` (was `tasks.py`), `services/experiment_stats.py` (was `task_stats.py`). API paths swapped: `/api/v1/runs/*` for executions, `/api/v1/experiments/*` for groupings.
- Job creation flushes the run before inserting the job (the job's foreign key points at the run).
- SDK: `mlops/run.py` (was `experiment.py`), `mlops.Run`, `mlops.current_run()`, `mlops.init(experiment=...)`.
- CLI: `mlops experiment ls|set` (was `mlops task`).
- Env var `MLOPS_RUN_ID` (was `MLOPS_EXPERIMENT_ID`). IDs use the prefixes `run_` and `exp_`.
- Dashboard (old UI, until Phase 6 parity): views and CSS renamed to match.
- Docs: `docs/glossary.md`, `docs/runbook.md`, `README.md`.

## Verification

- `uv run pytest -q`: 627 passed, 2 skipped, 14 deselected (live and docker tests).
- `uv run ruff check .`: clean.
- `node --test packages/mlops-server/ui-tests/*.mjs`: 39 passed.
- `tests/test_glossary.py::test_the_code_does_not_use_retired_words` fails if a retired word returns to the code.
- Not run: the live e2e suite (needs the compose stack) and the browser check of the old dashboard.

## Notes for Phase 2

- `docs/AIM_UI_IMPLEMENTATION_PLAN.md` Phase 2 starts from here: data model additions and the SDK aliases (`track`, `log_image`, and so on).

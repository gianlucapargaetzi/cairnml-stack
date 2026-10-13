# NEXT: where the project stands and what to do next

Read this first when you start a new session in this directory.

## Where things are

- Repository: `~/Documents/mlops`, branch `build/mlops-framework` (110 commits). `main` holds only the empty start commit.
- Remote: private GitHub repo `gianlucapargaetzi/mlops-framework`. Only the scaffold commit and the CLAUDE.md commit were pushed. Everything after `2e4e66a` is local only.
- Plans, decisions, rulings and per-task reports: `~/Documents/concepts/docs/superpowers/plans/` (index in `2026-10-11-00-index.md`), plus the SDD ledgers under `.superpowers/sdd/` (git-ignored).
- Architecture: `~/Documents/concepts/ARCHITECTURE.md`, diagram `mlops-architecture.typ` / `.pdf`, roadmap `ROADMAP.md`.
- Repo-level rules: `CLAUDE.md` (no AI attribution in commits, code or docs).

## What is built

All 69 planned tasks are implemented in eight phases:

1. Foundation and auth (keys, signed assertions, token exchange, enrollment, admin agent tokens, revocation).
2. Tracking, storage and GitHub (projects, experiments, metrics, logs, artifacts via presigned URLs, DVC STS, read-only GitHub App).
3. Jobs and scheduling (dispatch, scheduler, lifecycle, run tokens, reaper).
4. Agent (identity, executors for python, image and compose, runner, log shipper, main loop).
5. Client SDK and CLI (`mlops init`, `Experiment`, uplink with spool and sync, dispatch, admin commands, repo and dataset commands).
6. Deploy (Dockerfiles, per-role compose stacks, Keycloak realm, bootstrap, Alembic baseline, runbook).
7. User lifecycle and web UI (IdP directory sync with automatic revocation, browser login with PKCE, read-only web access, UI shell and views, comparison, CSRF-protected cancel and task edit).
8. Projects, tasks, datasets and resources (task entity, repo links and history, commit graph, dataset cards, reschedule, resource usage, four-tab navigation, e2e tests).

Test status at the last run:
- `uv run pytest -q`: 627 passed, 14 deselected (the live and docker tests), 2 skipped.
- `uv run ruff check .`: clean.
- `node --test packages/mlops-server/ui-tests/*.mjs`: 39 passed.

## What is NOT verified

- Nothing has run against the live compose stack from this machine. The hostnames `mlops-server`, `mlops-idp`, `mlops-nas` do not resolve, `deploy/.env` does not exist, and host port 8000 is used by another container (`scenegraph-editor`).
- The end-to-end suite (`MLOPS_E2E=1 uv run pytest tests/e2e -m e2e`) has never run. It needs the stack, `uv sync --group ui` and `playwright install chromium`.
- The web UI has never been rendered in a browser. Only the pure helpers and the static tests are checked.
- Keycloak's `${…}` substitution for the sync secret is unverified. If it fails, directory sync fails closed.
- `bootstrap.sh`'s `kcadm` and `mc` match strings are unverified.

## Next steps, in order

1. Get the stack running. Add `127.0.0.1 mlops-server mlops-idp mlops-nas` to `/etc/hosts` (sudo, once). Free port 8000 or change the mapping. Create `deploy/.env` from `deploy/.env.example`, then run `deploy/scripts/bootstrap.sh`. Follow `docs/runbook.md`.
2. Run the live suite: `MLOPS_E2E=1 uv run pytest tests/e2e -m e2e -v`. Fix whatever breaks. Expect selector and timing issues in the Playwright tests (they were written from the view source, not a live run).
3. Walk through the Phase 7 and Phase 8 acceptance lists in the plan files by hand in a browser.
4. Decide and then push. Nothing after the scaffold has been pushed. Ask before pushing to GitHub.
5. Hardening backlog (all parked with rulings in the ledgers):
   - metric replay duplicates after a lost response (needs a batch id and server-side dedupe)
   - artifact register and experiment creation can duplicate on a crash between writes
   - concurrent `mlops sync` has no lock
   - the token cache can double-fetch under load
   - check the admin base URL at startup so a bad URL cannot disable a user
   - compose teardown has no timeout
   - `.dvc`-remote session-token exposure (decision pending)
   - UI polling runs forever on finished runs
   - card and dataset listing make one GitHub read per file
   - `scaffold_card` path checks
   - one `parse_dvc` duplicate to merge

## Decisions the user still has to make

- Commit author: commits use `Gianluca Pargaetzi <parg@zhaw.ch>` from git config. The session email is `parmail.ch`. Keep or rewrite history?
- Any project member can link any repository the GitHub App is installed on. Keep, or add an admin gate?
- Agent names and load are visible to every signed-in user. Keep?
- Patches include `.claude/` if it is untracked in a user's repo. Exclude `settings.local.json`?
- `.dockerignore` ships `packages/*/tests` into images (no secrets). Keep?
- Demo users: none carry committed passwords. Who creates `dev`, `carol` and others in Keycloak?

## Conventions to keep

- Commit messages carry no AI attribution (no `Co-Authored-By`, no "Generated with"). `CLAUDE.md` says so.
- Stage explicit paths only. Never `git add -A`: `.claude/` must stay out of commits.
- Views use text nodes and `h()` only. No `innerHTML`, no inline `style` attributes; the CSP forbids them. The forbidden-API test in `tests/test_ui_static.py` enforces this.
- Vocabulary follows `docs/glossary.md`: Agent, Project, Experiment (a grouping of runs), Run (one execution), Job, Dataset, Resource.

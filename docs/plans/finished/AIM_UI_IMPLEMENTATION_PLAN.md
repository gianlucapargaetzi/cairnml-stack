# Aim UI implementation plan

Comprehensive plan for integrating and customizing Aim UI. All decisions are locked; this document describes the design and phased work plan.

## Status of decisions

| # | Decision | Status |
|---|---|---|
| 1 | Terminology scope | ✓ Rename everywhere (Experiment→Run, Task→Experiment), database reset to baseline |
| 2 | Wire format | ✓ JSON (not Aim's binary format) |
| 3 | Old dashboard | ✓ Delete at feature parity with fork |
| 4 | Media features | ✓ In scope: Images, Audio, Text, Figures, Distributions, Tags, Bookmarks, Params, Scatters |
| 5 | Branding removal | ✓ All Aim branding removed; product name is "MLOps Flow" |
| 6 | Telemetry/external requests | ✓ Audited; all removed (Segment, GitHub API, Pyodide, external links) |
| 7 | Filter language | ✓ Parse with `ast`, translate to SQL, never execute |
| 8 | Data model | ✓ Metric series, tags, sequences, run fields, bookmarks |
| 9 | Security | ✓ Real auth replaces adapter; every search filters by project membership |
| 10 | UI fork location | ✓ Vendored at `packages/mlops-ui/`, Node build stage in Docker |

---

## A. Rename (everywhere, DB reset)

**Terminology:** Old **Experiment → Run**, old **Task → Experiment**. Project, Job, Agent, Dataset, Resource, Artifact unchanged; `Repo` keeps its Git meaning.

### A.1 Rename order (two passes)

Pass 1: **Experiment → Run** everywhere
- `experiments` table, `experiment_id` columns, `exp_` ID prefixes
- `/api/v1/experiments` → `/api/v1/runs` paths
- `ExperimentOut` → `RunOut`, `mlops.Experiment` → `mlops.Run`
- `MLOPS_EXPERIMENT_ID` env var → `MLOPS_RUN_ID`

Pass 2: **Task → Experiment** everywhere
- `tasks` table, `task_id` columns, `tsk_` ID prefixes  
- `/api/v1/tasks` → `/api/v1/experiments` paths
- `TaskOut` → `ExperimentOut`, `mlops.init(task=...)` → `mlops.init(experiment=...)`
- Job spec field `task` → `experiment`

**File moves** (use `git mv`):
- `routers/experiments.py` ↔ `routers/tasks.py`
- `routers/tasks.py` → `routers/experiments.py` (new, replaces old tasks)
- `services/tasks.py` → `services/experiments.py`
- `ui/static/views/task.js` ↔ `ui/static/views/experiment.js`

### A.2 Database reset and squash

- Wipe PoC data (7 test runs and S3 objects)
- Replace migrations 0001–0005 with one clean baseline in `packages/mlops-server/src/mlops_server/migrations/versions/`
- New ID prefixes: `run_` and `exp_` (update `mlops_server/ids.py::new_id`)
- Params stored as JSONB (replaces separate `config` and `params` tables)
- Keycloak data untouched

### A.3 API and SDK contracts

**API routes swap:**
- `/api/v1/experiments/*` (run operations) ↔ `/api/v1/runs/*`
- `/api/v1/tasks/*` (experiment operations) ↔ `/api/v1/experiments/*`

**CLI:**
- `mlops task` → `mlops experiment`

**Env vars:**
- `MLOPS_EXPERIMENT_ID` → `MLOPS_RUN_ID`

**JWT claim:**
- `exp_id` → `run_id` (existing tokens invalidate after reset, acceptable)

**Artifact keys in S3:**
- `<project>/<run_id>/<name>` (was `<project>/<experiment_id>/<name>`)

**Audit fields:**
- `from_experiment` → `from_run`
- Note text: `dispatched from run_…` (was `dispatched from experiment_…`)

### A.4 SDK and CLI (Aim-style aliases)

- `mlops.Run` (main class; was `mlops.Experiment`)
- `mlops.init(experiment=...)` (parameter; was `task=`)
- `current_run()` (was `current_experiment()`)
- Keep: `log_metric`, `log_metrics`, `log_params`, `upload_artifact`
- Add: `track(value, name=, step=, context=)`, item assignment for params (`run["hparams"] = {…}`)
- Add: `log_image`, `log_audio`, `log_text`, `log_figure`, `log_distribution`
- `config` folds into `params`

**Critical files to update:**
- `packages/mlops-client/src/mlops/experiment.py` → `run.py`
- `packages/mlops-client/src/mlops/api.py`, `cli.py`, `sync.py`, `uplink.py`, `dispatch.py`

### A.5 Scale and testing

- ~250–350 of ~531 tests need edits
- `tests/test_glossary.py` must be rewritten (not search-and-replaced); asserts retired words are gone
- Old dashboard JS renamed too (lives until parity)
- Do not rename: JWT expiry claim `exp`, generic prose uses of "task"

---

## B. Data model additions

| Feature | Schema |
|---|---|
| **Metric context** | `metric_series(id, run_id, name, context JSONB, UNIQUE(run_id,name,context))` + `metric_points(series_id, step, value, epoch, ts)` |
| **Sequences** (image, audio, text, figure, distribution) | `sequences(id, run_id, kind, name, context)` + `sequence_items(sequence_id, step, idx, epoch, ts, caption, format, width, height, blob_key, text, data JSONB)` |
| **Sequence storage** | S3 at `<project>/<run_id>/<kind>/<name>/<step>_<idx>.<ext>`; text, Plotly, histograms inline |
| **Tags** | `tags(id, project_id, name, color, description)` + `run_tags(run_id, tag_id)` |
| **Run fields** | `name`, `description`, `archived`, `notes` (text) |
| **Bookmarks** | `explorer_states(id, user_id, kind, title, description, state JSONB, created_at)` |

---

## C. Explorer API v1 (replaces the adapter)

### C.1 Endpoints and routing

**New router:** `packages/mlops-server/src/mlops_server/routers/explorer.py` under `/api/v1/explorer/`

**Paths (mirroring Aim UI calls):**
- Runs: `search/run`, `search/run/`, `active`, `{id}/info`, `{id}/patch`, `archive`, `tags`, `{id}/note`, `{id}/logs`
- Metrics: `search/metric`, `search/metric/`, `align`, `get-batch`
- Projects: `info`, `params`, `activity`, `pinned-sequences`
- Sequences: search and get-batch for images, audios, texts, figures, distributions
- Experiments: `list`, `get`, `{id}/runs`, `activity`, `{id}/note`
- Tags: CRUD endpoints
- Bookmarks: CRUD (`apps` key in request body for Aim compatibility)

**Not implemented:** dashboards, boards, reports (removed from UI scope)

### C.2 Auth and access control

- Reuse `security/deps.py`: `READERS`, `_web_principal`, `check_csrf`, `require_writer`
- Reuse `_accessible_project_ids` from `routers/experiments.py`
- Every search filters by project membership
- Fixes adapter's missing auth

### C.3 JSON format

**Search responses:**
```json
{
  "runs": {
    "<run_id>": {"props": {...}, "params": {...}, "traces": {...}},
    ...
  },
  "progress": [checked, total]
}
```

- UI stops "searching" when `progress[0] == progress[1]`
- Metric arrays are plain `number[]` (not binary)
- Paging via `limit`, `offset`, `X-Total-Count` header
- No streaming in v1

**Replace Aim's binary decoder** in:
- `utils/encoder/streamEncoding.ts` → simple JSON
- `getRunData.ts` → `response.json()`
- `services/api/api.ts` (`getStream`, `getStream1`) → JSON fetch
- `NetworkService/index.ts`
- `live-update/Worker.ts`

### C.4 Media and presigned URLs

- `blob_uri` field contains short-lived presigned S3 URL
- Browser fetches directly (no server base64 encoding)
- Remove: `POST runs/{images|audios}/get-batch`, `arrayBufferToBase64`
- Sampling: `record_range`/`record_density` and `index_range`/`index_density` implemented server-side (defaults 50 and 5)

### C.5 Project scope

- Default: all projects the user can access
- `run.project` becomes a query filter attribute
- Fork gets a project filter in the top bar

---

## D. UI fork: vendoring, build, serving

### D.1 Location and licensing

- Vendored hard fork at `packages/mlops-ui/` (monorepo)
- Base: `aim-ui` v3.29.1 (Apache-2.0)
- Keep: `LICENSE` file
- Add: `NOTICE` (origin and version), `CHANGES.md` (what we changed)
- Modified files carry a change notice in their header
- Size: ~24 MB (src 9.7 MB, public 14 MB—mostly Monaco assets)
- **No upstream merges**; security fixes cherry-picked by hand

### D.2 Docker build and deployment

**Node build stage in `deploy/server/Dockerfile`:**
```dockerfile
FROM node:24 as ui-builder
ENV NODE_OPTIONS=--openssl-legacy-provider
WORKDIR /build
COPY packages/mlops-ui .
RUN npm ci && npm run build
```

- Copy build output into image as `/app/mlops_server/ui/static`
- No Node at runtime

**Serving:** Keep `/ui/` base path
- Rewrite `routers/ui.py` to serve `index.html` for all `/ui/*` except `/ui/auth/*` and `/ui/static/*` (history routing)
- Set `publicPath` to `/ui/static/` in build config

### D.3 Content Security Policy

Update `app.py` middleware:
```
script-src 'self'
style-src 'self' 'unsafe-inline'  (CSS-in-JS, Monaco)
worker-src 'self' blob:
img-src 'self' data: blob: <S3_origin>
font-src 'self' data:
connect-src 'self' <S3_origin>
```

No `unsafe-eval` (Pyodide removed).

### D.4 Session auth in the fork

Replace in `services/api/api.ts` and `NetworkService/index.ts`:
- localStorage bearer token → session cookie (from Keycloak)
- `token` refresh cookie and `auth/refresh` endpoint → gone
- `X-CSRF-Token` sent on writes (from `/api/v1/me`)
- Redirect to `/ui/auth/login` on 401

### D.5 Old dashboard (delete at parity)

**Delete on parity:**
- `packages/mlops-server/src/mlops_server/ui/static/` (entire old UI)
- `ui-tests/*.mjs`
- `tests/test_ui_static.py`
- `tests/e2e/test_dashboard.py`, `test_tabs.py`
- Update: `tests/test_glossary.py`, `tests/e2e/conftest.py` (`logged_in`), `docs/runbook.md`, `README.md`, `NEXT.md`, `pyproject.toml` (`ui` group)

**Keep:**
- `routers/web_auth.py` (`/ui/auth/*` endpoints)
- `_web_principal` and CSRF in `security/deps.py`
- `WebLogin`/`WebSession` models
- `GET /api/v1/me`
- `mlops-web` Keycloak client redirects
- `testing.py::browser` fixture
- `test_web_access/login/writes.py`

### D.6 Parity checklist

**Old UI features that must exist in fork before deletion:**
- Overview (home page)
- Projects with experiments, best runs per primary metric, repo graph
- Experiment (old Task) page with edit
- Datasets and dataset cards with versions
- Jobs (list, spec, cancel, copy, reschedule form)
- Resources (agents, queues, load)
- Run list (filters, paging)
- Run detail (metrics, params, code/data, live logs, artifact download, markdown, "Run on agent" dispatch)
- Compare 2–10 runs
- Admin (agents, clients, users)

---

## E. Branding removal and telemetry audit

### E.1 Findings and actions

| Item | File(s) | Today | Action |
|---|---|---|---|
| **Segment analytics** | `services/analytics.ts`, `public/index.html:209` | Off unless `telemetry_enabled=1` | Delete module and snippet; no-op stub first, then codemod removes 93 call sites in 50 files |
| **Pyodide** | `public/index.html:18` from `cdn.jsdelivr.net` | Always loaded | Removed with Boards and Reports |
| **Google Fonts** | `public/index.html:156` Material Icons CSS | Always loaded | Vendor Material Icons font into build |
| **GitHub release notes** | `endpoints.ts` → `api.github.com/repos/aimhubio/aim/releases` | Called on home page | Remove component and endpoint |
| **Community/docs links** | `CommunityPopup.tsx`, `SideBar.tsx`, `config/references/index.ts`, 46 readthedocs refs | Links only (no request) | Remove; central references file → no-op |
| **Page titles, logo, favicon, manifest** | `public/index.html`, `manifest.json`, `favicon.ico`, sidebar logo | "Aim" branding | "MLOps Flow"; new logo and favicon |
| **Browser storage** | localStorage | UI state + auth token | Keep UI state; auth token → session cookie |

### E.2 Logo and UI

**Logo files:** `assets/MLOpsFlow_Logo.jpeg` (1024×1024) and `assets/MLOpsFlow.jpeg` (1408×768 wordmark)
- Both opaque off-white JPEGs; Aim sidebar is dark navy
- Derive transparent PNG and favicon; check contrast; if poor, place logo on light tile

**Guards before deployment:**
1. Build step scans bundle for hosts outside allow-list
2. Playwright test walks every explorer page, fails on cross-origin request
3. CSP `default-src 'self'` as defence in depth

---

## F. Filter language

**Principle:** Parse with Python `ast`, whitelist nodes, translate to SQL; never execute.

### F.1 Namespaces and operators

**Namespaces:**
- `run.*`: `name`, `hash`, `experiment`, `project`, `tags`, `active`, `archived`, `creation_time`, `hparams.*`, any param
- `metric.*`: `name`, `context.<k>`, `last`
- `images.*`, `audios.*`, `texts.*`, `figures.*`, `distributions.*`: `name`, `context.<k>`

**Forms the UI generates (must accept):**
- Comparisons (`==`, `<`, `>`, etc.)
- Logical: `and`, `or`, `not`
- `in [...]` (list membership)
- `== True/False`
- `.startswith('...')`
- Single comprehension: `any(t.name in [...] for t in run.tags)`

**Return 400 with reason for anything else.**

### F.2 Implementation

**New file:** `packages/mlops-server/src/mlops_server/services/query.py`
- Parser (AST whitelist)
- Translator (to Postgres JSONB operators, casts for numeric comparison)
- Tests for every accepted form and every refusal
- No expression reaches SQL except through bound parameters

**Autocomplete:** `GET /api/v1/explorer/projects/{id}/params` returns:
```json
{
  "params": {...},
  "metric": {"name1": [context_keys...], ...},
  "images": {"name1": [context_keys...], ...},
  ...
}
```

---

## G. Work plan (phases)

### Phase 1: Rename and baseline reset

- Two-pass rename across database, API, SDK, CLI, tests, docs
- Database migration: squash 0001–0005 into one clean baseline, new ID prefixes
- Update `tests/test_glossary.py`; add test that retired words are gone
- Run full test suite; update old dashboard to use new names
- **Done when:** full suite green, old dashboard works

### Phase 2: Data model

- Add `metric_series`, `metric_points` (replaces old metric structure)
- Add `sequences` and `sequence_items` tables
- Add `tags`, `run_tags`
- Add run fields: `name`, `description`, `archived`, `notes`
- Add `explorer_states` (bookmarks)
- SDK: add `track()`, aliases, item assignment for params, `log_image/audio/text/figure/distribution`
- **Done when:** tests pass, SDK changes verified

### Phase 3: Explorer API v1

- New router `routers/explorer.py`, all endpoints from section C
- Auth: project membership filtering
- JSON shapes and paging
- Filter language parser and translator
- Contract tests for all endpoints
- **Done when:** contract tests pass, API audit complete

### Phase 4: UI fork

- Vendor `aim-ui` v3.29.1 at `packages/mlops-ui/`
- Strip Segment analytics (no-op stub, codemod)
- Remove Pyodide, GitHub API, external links
- Vendor Material Icons font
- Update page titles, logo, favicon, manifest
- Rewrite data layer to JSON (replace binary decoder)
- Update CSP headers
- Session auth (bearer token → session cookie, X-CSRF-Token)
- Docker Node build stage
- History routing in `routers/ui.py`
- **Done when:** fork builds, serves on `/ui/`, runs against explorer API

### Phase 5: Sequences and media

- SDK: implement `log_image/audio/text/figure/distribution` ingestion
- S3 upload with presigned URLs
- Explorer endpoints for all five kinds
- UI: sequences pages (Images, Audio, Text, Figures, Distributions)
- **Done when:** e2e: log a sequence, see it in UI

### Phase 6: Our own pages in fork

- Rewrite as needed to reach parity checklist (section D.6):
  - Jobs, Resources, Datasets, Projects, Admin
  - Dispatch and reschedule forms
  - Comparison view (2–10 runs)
- **Done when:** parity checklist complete
- **Then:** delete old dashboard, update docs

### Phase 7: Hardening

- Playwright e2e suite (all explorer pages, cross-origin guard, CSP check)
- Performance testing (paging, filtering under load)
- Bundle scan for external hosts
- Docs: glossary, runbook, this plan
- **Done when:** e2e green, no regressions, all docs updated

---

## Verification

**Per phase:**
- `uv run pytest -q` (full suite)
- `uv run ruff check .` (linting)
- Contract tests for API changes (endpoint set, JSON shapes)

**Rename (Phase 1):**
- Test that no retired word (old meaning) remains in code, docs, or UI strings
- Migration test on fresh Postgres (testcontainers) from baseline

**Filter language (Phase 3):**
- Unit tests for every accepted form and refusal
- Test that no expression reaches SQL except via bound parameters

**UI (Phase 4):**
- Playwright against seeded stack: all explorer pages
- Assertion of zero cross-origin requests
- CSP header check

**End to end (Phase 7):**
- `deploy/scripts/prune.sh --yes`
- `deploy/scripts/bootstrap.sh`
- Log in via Keycloak
- Run `first_run.py` with new SDK
- Find run in UI
- Dispatch it to agent
- See job finish
- View run in fork

**Docs (all phases):**
- `docs/glossary.md`, `docs/runbook.md`, this plan kept consistent

---

## Scope decisions confirmed

**Keep in UI:** Runs, Metrics, Params, Scatters, Images, Audio, Text, Figures, Distributions, Tags, Bookmarks, Run detail, Aim's home page

**Drop from UI:** Boards, Reports, Dashboards (require Pyodide and server-side app storage), release-notes panel, community popup

**Keep forever:** Project, Job, Agent, Queue, Resource, Dataset, Client, User, Member (no Aim equivalents)

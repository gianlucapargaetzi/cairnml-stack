# Phase 4 progress: UI fork

**Status:** Not finished. The fork builds and is served at `/ui-next/`. Every route the fork still offers (Runs, Metrics, Params, Scatters, Run detail, dashboard) loads with no console errors, failed requests or cross-origin calls, and its search works against the explorer API. Phase 4's done criterion is not fully met: the fork is served at `/ui-next/`, not `/ui/` (see below). Sequence pages, tags and project pages are later phases.

## Done

- Aim UI 3.29.1 vendored at `packages/mlops-ui/` (Apache-2.0 license kept). Storybook and the Python packaging are left out.
- Removed: Pyodide, Boards, Reports, the release-notes panel, the community popup, the Segment analytics module (replaced by a no-op stub), the Google Fonts link, and the external documentation URLs (now `#`).
- Served at `/ui-next/` next to the old dashboard at `/ui/`. Own CSP (no inline scripts). Built with `npm run build:server` (needs `NODE_OPTIONS=--openssl-legacy-provider`, as in the Dockerfile) into `packages/mlops-server/src/mlops_server/ui/next` (git-ignored).
- Auth: session cookie; `X-CSRF-Token` on writes; a 401 sends the user to `/ui/auth/login?next=...`, which returns them to an allowed UI path.
- Data: an adapter (`src/utils/explorer/explorerJson.ts`) turns explorer JSON into the typed-array shapes the models read. The wire format is JSON; the internal shapes are unchanged.
- Explorer additions for the UI: run props (experiment id, tags with colours, creator, times, active), points with epoch and timestamp, run info with the metric series list.
- Routes limited to Runs, Metrics, Params, Scatters, Run detail and the dashboard. Image, audio, text, figure, tag, bookmark and experiment pages are hidden until Phases 5 and 6. The hidden "Metrics Explorer V2" route (`/metrics_v2`) is removed from the route table; its page folder `src/pages/MetricsExplorer` is now unused and can be deleted.
- Titles and user-facing "Aim" copy changed to "MLOps Flow" in the main places.
- Legacy `GET /projects/params` call replaced by the explorer listing (`modules/core/api/projectApi/index.ts`). It was a 404 and left the metric picker empty.
- Parallel-coordinates chart with a single selected param no longer produces `Infinity` widths (`utils/d3/drawParallelAxes.ts`).

## Verified in a browser (live harness, real Postgres, headless Chromium)

- Runs explorer: runs listed; filter `run.lr > 0.005` returns the two runs that match.
- Metrics explorer (`/metrics`): `metric.name == 'loss'` draws the three loss curves with the right step counts.
- Params explorer: "Run Params" dialog lists params; selecting `batch` and `lr` draws the chart and fills the table with the right values; a filter narrows the rows.
- Scatters explorer: X `lr`, Y `acc` plots three points at the expected coordinates; a filter narrows the rows.
- Run detail (`/runs/run_fast`): loads with the Overview params shown and no errors. Metrics, Logs and Notes were checked in an earlier pass, not in this one.
- Dashboard home: loads; Quick start shows the MLOps SDK.
- Unit: `projectApi.test.ts` (new) covers the explorer-backed `getParams`; `tsc --noEmit` clean.

## Built and checked in the build

- Bundle host guard (`scripts/check-bundle-hosts.js`) runs in `build:server` and in the Docker build. Documentation and library strings are on a list; a new host fails the build.
- Docker image `deploy/server/Dockerfile` builds with a node:24 stage; the image contains the explorer under `mlops_server/ui/next`.
- Logo and favicon are from `assets/MLOpsFlow_Logo.jpeg` (sidebar logo on a light tile).
- Deploy test checks the Dockerfile stage and the guard.
- Backend: `test_explorer_api.py` and `test_deploy_files.py` pass (64 tests).
- UI Jest: 9 suites fail on the base commit too, all snapshot tests with no stored snapshots (`CI=true` refuses to write them). Not caused by Phase 4 changes; they need their snapshots committed or regenerated.

## Known broken or not verified

- Sequence data (images, audios, texts, figures, distributions) and metric alignment: explicit "not supported yet" errors until Phase 5.
- Run detail Messages, System, Distributions, Images, Audios, Texts tabs: sequence or system data (Phases 5 and 6).
- Pinned sequences and the activity feed read as empty.
- Tags: attaching a tag to a run, creating, renaming, archiving and deleting tags, and listing a tag's runs show explicit "not supported yet" errors. The server endpoints exist (`/api/v1/explorer/runs/{id}/tags/{tag}`, `/projects/{id}/tags`, `/tags/{id}`), but the UI services say these arrive with the project pages (Phase 6). Attach-by-name needs a tag lookup that is part of that work.
- Deleting runs: explicit "not supported yet". The server has no delete endpoint; the plan does not list one.
- Params "Search" with a filter on a single selected param draws an axis with no lines. Expected for one dimension; not a bug.

## Decisions to confirm

- Served at `/ui-next/` rather than `/ui/`, which the plan's D.2 names. The old dashboard still owns `/ui/` until Phase 6 deletes it; moving the fork to `/ui/` before then means choosing between the two.

## Not done

- CSP `connect-src` for presigned S3 URLs: done in Phase 5 (the explorer CSP admits the storage origin).
- Browser test that no runtime request leaves the origin (Phase 7).
- Browser checks of every route, and the Playwright suite (Phase 7).
- Committing the Phase 4 changes made in this pass (uncommitted in the working tree).

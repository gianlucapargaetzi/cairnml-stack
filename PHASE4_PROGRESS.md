# Phase 4 progress: UI fork

**Status:** Not finished. The fork builds and is served at `/ui-next/`. The runs and metrics explorers work against the explorer API in a browser. Other pages are not verified or are known broken (see below). Phase 4's done criterion is not met.

## Done

- Aim UI 3.29.1 vendored at `packages/mlops-ui/` (Apache-2.0 license kept). Storybook and the Python packaging are left out.
- Removed: Pyodide, Boards, Reports, the release-notes panel, the community popup, the Segment analytics module (replaced by a no-op stub), the Google Fonts link, and the external documentation URLs (now `#`).
- Served at `/ui-next/` next to the old dashboard at `/ui/`. Own CSP (no inline scripts). Built with `npm run build:server` into `packages/mlops-server/src/mlops_server/ui/next` (git-ignored).
- Auth: session cookie; `X-CSRF-Token` on writes; a 401 sends the user to `/ui/auth/login?next=...`, which returns them to an allowed UI path.
- Data: an adapter (`src/utils/explorer/explorerJson.ts`) turns explorer JSON into the typed-array shapes the models read. The wire format is JSON; the internal shapes are unchanged.
- Explorer additions for the UI: run props (experiment id, tags with colours, creator, times, active), points with epoch and timestamp, run info with the metric series list.
- Routes limited to Runs, Metrics, Params, Scatters, Run detail and the dashboard. Image, audio, text, figure, tag, bookmark and experiment pages are hidden until Phases 5 and 6.
- Titles and user-facing "Aim" copy changed to "MLOps Flow" in the main places.

## Verified in a browser (live harness, real Postgres)

- Runs explorer: both runs listed with experiment, creator, date, duration and tags.
- Metrics explorer: `metric.name == 'loss'` draws both loss curves and the run table.
- Params and Scatters pages load without errors (not exercised with a query).

## Verified in a browser since the last update

- Run detail: Overview (params, information, creator, insights), Metrics (loss card), Logs (seeded lines), Notes (one note per run, saved in the run's `notes` field).
- Dashboard home: loads with no errors. Quick start shows the MLOps SDK; the Aim integrations panel is removed.

## Built and checked in the build

- Bundle host guard (`tasks/check-bundle-hosts.js`) runs in `build:server` and in the Docker build. Documentation and library strings are on a list; a new host fails the build.
- Docker image `deploy/server/Dockerfile` builds with a node:24 stage; the image contains the explorer under `mlops_server/ui/next`.
- Logo and favicon are from `assets/MLOpsFlow_Logo.jpeg` (sidebar logo on a light tile).
- Deploy test checks the Dockerfile stage and the guard.

## Known broken or not verified

- Params explorer: a query runs without error, but results need parameters selected through the "Run Params" dialog, which is not tested yet.
- Scatters: loads; not tested with a query.
- Run detail Messages, System, Distributions, Images, Audios, Texts tabs: sequence or system data (Phases 5 and 6).
- Sequence data (images, audios, texts, figures, distributions) and metric alignment: explicit "not supported yet" errors until Phase 5.
- Pinned sequences and the activity feed read as empty.
- Deleting runs and attaching tags from the explorer: explicit "not supported yet" errors.

## Not done

- CSP `connect-src` for presigned S3 URLs: needed once the fork fetches sequence blobs (Phase 5).
- Browser test that no runtime request leaves the origin (Phase 7).
- Browser checks of every route, and the Playwright suite (Phase 7).

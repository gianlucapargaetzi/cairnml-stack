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

## Known broken or not verified

- Run detail: the header loads, but the Overview stays on a spinner. The info response has the fields the model reads; the cause is not yet found.
- Run detail tabs (metrics, logs, messages) are not verified. Logs use the existing run logs endpoint, adapted to line records.
- Dashboard home: not verified (Aim onboarding cards are still there, with "MLOps Flow" wording).
- Sequence data (images, audios, texts, figures, distributions) and metric alignment: explicit "not supported yet" errors until Phase 5.
- Pinned sequences and the activity feed read as empty.
- Deleting runs and attaching tags from the explorer: explicit "not supported yet" errors.

## Not done

- Bundle scan for third-party hosts. The built JavaScript still contains URLs from map, gravatar and docs libraries. The Phase 7 browser test must confirm nothing is requested at runtime.
- CSP `connect-src` for presigned S3 URLs.
- Docker node build stage in `deploy/server/Dockerfile`.
- Logo and favicon from `assets/` (the fork still shows Aim's logo).
- Browser checks of every route, and the Playwright suite (Phase 7).

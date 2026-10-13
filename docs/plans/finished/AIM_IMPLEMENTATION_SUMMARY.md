# Aim UI implementation: summary

The full plan is [AIM_UI_IMPLEMENTATION_PLAN.md](AIM_UI_IMPLEMENTATION_PLAN.md) in this folder. This page summarises what was built, how it ended up, and what is still open.

## Goal

Replace the Aim UI and the old vanilla dashboard with one web UI, **MLOps Flow**, built on a vendored fork of Aim UI (`packages/mlops-ui`) and served at `/ui-next/`. The UI reads the explorer API (`/api/v1/explorer`), which returns JSON, and it runs with the same login and access rules as the rest of the server.

## Decisions

| Decision | Result |
|---|---|
| Terminology: Experiment becomes Run, Task becomes Experiment | Done. Database reset to the new baseline. |
| JSON wire format instead of Aim's binary format | Done. |
| Old dashboard deleted at feature parity | Done. Removed in the last phase; `/`, `/ui` and `/ui/` redirect to `/ui-next/`. |
| Media in scope: images, audio, text, figures, distributions, tags, bookmarks, params, scatters | Partly. Images, tags, params and scatters are done. Audio, text, figures and distributions are open (issue #2). Bookmarks are in the explorer API. |
| All Aim branding and external calls removed | Done. The product name is MLOps Flow. The bundle scan guards the hosts (see below). |
| Filter language parsed with `ast`, translated to SQL, never executed | Done. Values are bound parameters. |
| Real auth replaces the adapter; every search filters by project membership | Done. Browser sessions use a cookie and a CSRF header. |
| The fork is vendored at `packages/mlops-ui` and built in Docker | Done. |

## Phases

| Phase | What it covers | Status |
|---|---|---|
| 1. Rename | Experiment to Run, Task to Experiment, across code, API, database and UI strings | Complete |
| 2. Data model and SDK surface | Metric series, tags, sequences, run fields, bookmarks | Done |
| 3. Explorer API and filter language | Search per kind, run actions, tags, bookmarks, the filter language | Done. The audit of the Aim UI calls is complete. |
| 4. Fork in the browser | Runs, Metrics, Params, Scatters, Run detail, served at `/ui-next/` | Done. Fixes to the params explorer, scatters, metrics picker and single-axis chart are committed. |
| 5. Sequences and media | The SDK logs sequences, the server stores them, the explorer reads them | Partly done. Images work end to end. Audio, text, figure and distribution pages are open (issue #2). |
| 6. Our own pages | Jobs, Resources, Admin, Datasets, Projects, Experiment, Compare, Run detail, Tags | Done, except for the dropped and deferred items below. The old dashboard is deleted. |
| 7. Hardening | UI end-to-end suite, the end-to-end flow, performance, bundle scan, docs | Open (issue #3). |

## Open items

These are tracked as GitHub issues. Each one is still open.

- **[#1 Explorer: delete runs from the UI](https://github.com/gianlucapargaetzi/mlops-framework/issues/1)** (`enhancement`). Deleting a run also has to delete its blobs. It is not built yet.
- **[#2 Explorer: audio, text, figure and distribution pages](https://github.com/gianlucapargaetzi/mlops-framework/issues/2)** (`feature`). The server and the SDK already store these kinds, and the search endpoints exist. The fork has no pages for them, and the run detail tabs still say "not supported yet". Distributions are part of this issue. Priority is low.
- **[#3 Phase 7: UI end-to-end suite, flow test, performance and bundle scan](https://github.com/gianlucapargaetzi/mlops-framework/issues/3)** (`testing`). The existing end-to-end suite covers the API and the CLI but no UI page. The central piece is a Playwright suite over every page of the fork. The rest of Phase 7 is the full flow on a fresh stack, performance thresholds for the explorer, and the bundle scan in CI.

## Dropped

- **Pinned sequences and the activity feed.** They were not in the parity checklist of Phase 6. The fork reads their endpoints and shows them empty. The server endpoints remain.
- **Boards, reports and dashboards** (from the plan's scope decisions). They need Pyodide and server-side app storage, so the fork does not have them.
- **Release-notes panel and community popup** (from the plan's scope decisions).

## Verification

- Server tests: `uv run pytest packages/mlops-server` passes (493 tests). Ruff is clean for the whole workspace.
- UI: at the end of Phase 6, Jest passed (40 suites), `tsc` was clean and the bundle built with the host guard. These were not rerun after the dashboard deletion, which does not touch the UI code.
- The explorer, the run detail and each Phase 6 page were checked in a headless browser against the compose stack, with no console errors and no failed requests.
- Not yet verified: the full flow on a fresh stack, the performance thresholds, and the UI end-to-end suite. These are issue #3.

## Bundle scan

`packages/mlops-ui/scripts/check-bundle-hosts.js` fails the build when the bundle mentions an external host that is not on its list. The list separates documentation and licence strings (never requested) from library tile and avatar strings (never rendered). The Content-Security-Policy of `/ui-next` blocks runtime requests to any other host. The scan runs at build time; running it in CI on the built output is part of issue #3.

# Phase 4 progress: UI fork (parts 1 and 2)

**Status:** The fork compiles, is served at `/ui-next/` next to the old dashboard at `/ui/`, and has no inline scripts. It does not talk to the explorer API yet, so the phase's done criteria are not met.

## Done

- Vendored Aim UI 3.29.1 (`v3.29.1` tag of aimhubio/aim, `aim/web/ui`) at `packages/mlops-ui/`. Storybook and the Python packaging are left out. `LICENSE` is the Apache-2.0 license from upstream.
- Removed the Pyodide CDN script, the Segment snippet, the Google Fonts link, and the Pyodide-based Boards and Reports pages (with their routes and the board model).
- Replaced `services/analytics` with a no-op stub that keeps the same exports, so no analytics call leaves the browser.
- Documentation URLs in `config/references` are now `#`. The sidebar's Discord and Docs anchors and the dashboard's release-notes panel are removed.
- The title is "MLOps Flow".
- `npm run build` exits 0 with `NODE_OPTIONS=--openssl-legacy-provider`.

## Part 2: serving

- Served at `/ui-next/` (decided: the old dashboard stays at `/ui/` until parity). The build is copied into `packages/mlops-server/src/mlops_server/ui/next` by `npm run build:server` and is git-ignored.
- Own CSP for `/ui-next` (no inline scripts, `unsafe-inline` styles only); the preloader script and the inline runtime globals moved out of `index.html`.
- Tests: `test_ui_next.py` (index, history fallback, static files, traversal, 503 when unbuilt, old dashboard unchanged).
- Bundle scan: the built JS still contains URLs from third-party libraries (map tiles, gravatar, docs). They are not called by the explorer's own code. The Playwright cross-origin check in Phase 7 must confirm no request is made.

## Not done

- Data layer: the stream decoder (`utils/encoder/streamEncoding.ts`) and its consumers still expect Aim's binary `(path, value)` protocol. The endpoint table still points at Aim paths under `/api`.
- Session auth: the UI still uses the bearer token in localStorage. Writes need the `X-CSRF-Token` from `/api/v1/me`.
- CSP, favicon and logo, Monaco asset path, and the bundle scan for external hosts.

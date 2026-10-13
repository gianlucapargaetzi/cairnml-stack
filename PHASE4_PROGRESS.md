# Phase 4 progress: UI fork (part 1)

**Status:** Part 1 of 2. The fork compiles and no longer loads external services at build time. It is not served yet, and it does not talk to the explorer API yet, so the phase's done criteria are not met.

## Done

- Vendored Aim UI 3.29.1 (`v3.29.1` tag of aimhubio/aim, `aim/web/ui`) at `packages/mlops-ui/`. Storybook and the Python packaging are left out. `LICENSE` is the Apache-2.0 license from upstream.
- Removed the Pyodide CDN script, the Segment snippet, the Google Fonts link, and the Pyodide-based Boards and Reports pages (with their routes and the board model).
- Replaced `services/analytics` with a no-op stub that keeps the same exports, so no analytics call leaves the browser.
- Documentation URLs in `config/references` are now `#`. The sidebar's Discord and Docs anchors and the dashboard's release-notes panel are removed.
- The title is "MLOps Flow".
- `npm run build` exits 0 with `NODE_OPTIONS=--openssl-legacy-provider`.

## Not done (part 2)

- Data layer: the stream decoder (`utils/encoder/streamEncoding.ts`) and its consumers still expect Aim's binary `(path, value)` protocol. The endpoint table still points at Aim paths under `/api`.
- Session auth: the UI still uses the bearer token in localStorage. Writes need the `X-CSRF-Token` from `/api/v1/me`.
- Serving: `routers/ui.py` does not serve the fork build yet. The build uses `/static-files/` as its public path; the plan says `/ui/static/`. The location of the fork (`/ui/` versus a separate path while the old dashboard remains) is still undecided.
- CSP, favicon and logo, Monaco asset path, and the bundle scan for external hosts.

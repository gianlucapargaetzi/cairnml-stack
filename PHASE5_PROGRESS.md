# Phase 5 progress: sequences and media

**Status:** Partly done. The plan's done criterion is met for images: a sequence logged with the SDK appears in the explorer, with its image, caption and sliders. Audio, text and figure pages are deferred (issue #2); distribution pages are not started.

## Decisions (rulings)

- **Kinds.** The database and the SDK use the singular kind names (`image`, `audio`, `text`, `figure`, `distribution`). The explorer paths and filter namespaces use the plural names the UI already uses (`images`, `audios`, ...).
- **Blob keys.** `<project>/<run_id>/<kind>/<name>/<step>_<idx>.<format>`, as the plan says, with one addition: when the context is not empty, a segment `ctx-<hash>/` (first 10 hex chars of a SHA-1 of the sorted context) follows the name. Without it, two contexts with the same name and step would overwrite each other's blobs.
- **Two-step upload for binary kinds.** `POST /runs/{id}/sequences/presign` returns a presigned PUT URL and the key. The SDK PUTs the bytes, then `POST /runs/{id}/sequences` registers the items. The server re-derives the key from the item's fields and refuses any other key.
- **Inline kinds.** Text, figure and distribution items carry their value in the register request. No storage is used.
- **Browser reads.** Image and audio items carry `blob_uri`, a presigned GET. The UI fetches the bytes from storage and converts them to base64 in the browser, so the image components are unchanged. This needs a CORS rule on the bucket (runbook 19a) and the storage origin in the explorer CSP.
- **Steps.** The SDK numbers items per (kind, name, context) when no step is given. The server requires `step >= 0` when a step is set.
- **Retries.** Registering an item whose (sequence, step, idx) exists is a no-op, so a retried batch does not duplicate.
- **Offline.** A blob that cannot be uploaded is spooled and uploaded by `mlops sync`, in spool order, once each (a `sequence_blob` event with its own ordinal in the spool meta). Text and inline items are spooled as `sequence` events and replayed like metrics.
- **Reads.** Explorer search per kind returns each run's sequences with `blob_uri` for image and audio items. Sampling: `record_range`/`record_density` over steps (default density 50), `index_range`/`index_density` over the item index within a step (default density 5).
- **Pinned sequences moved to Phase 6.** Pinning needs its own table, and it belongs with the project pages. The plan had it in Phase 5.

## Done

- **Shared schemas** (`mlops_common/schemas.py`): `SequenceItemIn`, `SequenceBatch`, presign request and response, with the size limits.
- **Server**
  - `services/sequences.py`: keys, validation of the whole batch before any write, idempotent writes.
  - `routers/sequences.py`: presign and register, for clients, agents and run tokens.
  - `services/explorer.py`: `search_sequences` with sampling, presigned blob URLs, slider ranges (`ranges` per run) and the sequence names per kind in the project parameter listing.
  - `routers/explorer.py`: `GET /explorer/runs/search/{kind}`.
  - `services/query.py`: `images.*` (and the other four kinds) in the filter language, kept apart from run and metric clauses. Refused on a search of another kind.
  - `app.py`: the explorer CSP admits the storage origin for `img-src` and `connect-src`.
  - `services/metrics.py`: `sample_ranks` no longer divides by zero at density 1.
- **SDK** (`mlops-client`)
  - `mlops/sequences.py`: encoders. Images: PNG, JPEG, GIF, WEBP bytes, a file, or a PIL image (size read from the header). Audio: WAV, MP3, OGG, FLAC. Text. Figures: Plotly dicts or `to_plotly_json()` objects. Distributions: numbers (64 bins) or `{bin_counts, bin_range}`. Each refuses a value it cannot store, before sending.
  - `run.py`: `log_image`, `log_audio`, `log_text`, `log_figure`, `log_distribution`.
  - `uplink.py`, `sync.py`, `api.py`: delivery, spool and replay.
- **UI** (`mlops-ui`)
  - `utils/explorer/sequenceJson.ts`: explorer JSON to the model's run and trace shape, and the index-range conversion.
  - `services/api/imagesExplore`: the JSON search, and browser-side blob fetch (replaces the Aim binary get-batch).
  - `services/models/imagesExplore`: uses the sequence loader and the new fetch.
  - `services/api/projects/projectsService.ts`: merges sequence names for all five kinds (the selector was empty before).
  - `routes/routes.tsx`: the Images page is back in the route table and the sidebar.
  - `explorerJson.ts`: the run props conversion is shared.
- **Tests**
  - Server: `test_sequences.py` (16), query-language cases, explorer contract, CSP.
  - SDK: `test_sequences.py` (15), including offline spool and retry-once sync.
  - UI: `sequenceJson.test.ts` (5), `projectsService.test.ts` (1).
- **Docs:** `docs/explorer_api.md` (sequence endpoints, filters, ranges, limits), `docs/runbook.md` 19a (storage reachability and CORS).

## Verified

- `uv run pytest -q`: 796 passed, 2 skipped, 14 deselected. `uv run ruff check .`: clean.
- UI Jest: 30 suites, 84 tests passing. `tsc --noEmit`: clean. `npm run build:server`: passes, including the bundle host guard.
- End to end, against the compose stack's RustFS (not stubs), with the SDK logging over HTTP:
  - SDK upload, registration, explorer search: the search returns the items with presigned URLs; a direct fetch of one returns a 96x64 PNG (HTTP 200).
  - Browser (headless Chromium, real session): the Images explorer lists the `prediction` sequence from two runs, shows nine images with their captions, sliders read steps 0 to 3 and indices 0 to 1, and there are no console errors and no failed requests.

## Not done

- **UI pages for audio, text and figures, and the run detail tabs for them.** Deferred by the owner because of low priority; tracked in issue #2 (label `feature`). The fork has no models for these explorers, so each needs its own model and page.
- **Distributions UI.** Not started; the owner has not yet said whether it is deferred with the others.
- **Pinned sequences.** Moved to Phase 6 (see decisions).
- **Metric alignment** (`runs/search/metric/align`) and metric detail get-batch: still deferred, as before.
- **Sampling cost.** The search fetches every item of the sampled steps, then samples the indices per step in Python. Fine for the usual sizes; a window-function query would be needed for steps with thousands of items.
- **Run deletion.** Deleting a run's blobs is not built; tracked as GitHub issue #1 (`enhancement`).
- **Browser test in the Playwright suite.** Phase 7.

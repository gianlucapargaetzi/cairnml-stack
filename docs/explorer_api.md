# Explorer API v1

The explorer API serves the runs, metrics, tags and bookmarks pages. It replaces the Aim adapter. Every search filters by the projects the caller belongs to; admins see all projects.

All endpoints live under `/api/v1/explorer`. Reads accept client and browser sessions. Writes need the same, plus the CSRF token for browser sessions. Runs, jobs and agents cannot call the explorer.

## Search

`GET /runs/search` returns runs that match a filter, each with its display fields, params, and sampled traces.

Query parameters:

| Name | Default | Meaning |
|---|---|---|
| `q` | none | Filter expression (below). |
| `project` | none | Project slug. Only runs in that project. |
| `limit` | 50 | 1 to 500 runs per page. |
| `offset` | 0 | Runs to skip. |
| `points` | 50 | 1 to 500 points per trace. The first and last points are always included. |

The total number of matching runs is in the `X-Total-Count` header.

```json
{
  "runs": {
    "run_3f9a...": {
      "props": {
        "name": "fast", "description": null, "archived": false, "status": "finished",
        "project": "vision/seg", "experiment": "training",
        "created_at": "2026-10-13T14:05:54.633009+00:00", "tags": ["baseline"]
      },
      "params": {"lr": 0.1},
      "traces": [
        {"name": "loss", "context": {}, "count": 5, "last": 0.1,
         "points": [[0, 1.0], [1, 0.5], [2, 0.25], [3, 0.2], [4, 0.1]]},
        {"name": "loss", "context": {"subset": "val"}, "count": 2, "last": 0.7,
         "points": [[0, 1.1], [1, 0.7]]}
      ]
    }
  },
  "progress": [1, 1]
}
```

- Runs are ordered newest first.
- A run has at most 50 traces. Each trace is one metric series.
- `progress` is `[returned, returned]`, because the search is synchronous.

`GET /runs/search/metric` takes the same parameters. It accepts `metric.*` clauses, which choose the traces. Runs with no matching trace are left out.

`GET /runs/active` is a search for runs that have not finished (created, queued or running).

Only `search/metric` accepts `metric.*` clauses. `search/run` refuses them with HTTP 400.

## Sequences

`GET /runs/search/{kind}` returns the runs that have a sequence of the kind, for `kind` = `images`, `audios`, `texts`, `figures` or `distributions`. It takes the same query parameters as search, plus:

| Name | Default | Meaning |
|---|---|---|
| `record_range` | none | `low:high`, a closed range of steps. |
| `record_density` | 50 | 1 to 500 steps to sample, evenly spaced, first and last included. |
| `index_range` | none | `low:high`, a closed range of indices within a step. |
| `index_density` | 5 | 1 to 50 indices to sample per step. |

Each run lists its sequences with their sampled items:

```json
{
  "runs": {
    "run_3f9a...": {
      "props": {"name": "fast", "...": "..."},
      "params": {"lr": 0.1},
      "ranges": {"record_range_total": [0, 10], "index_range_total": [0, 3],
                 "record_range_used": [0, 10], "index_range_used": [0, 2]},
      "sequences": [
        {"name": "prediction", "context": {}, "count": 30,
         "items": [
           {"step": 0, "idx": 0, "epoch": null, "ts": 1.0, "caption": "epoch 0",
            "format": "png", "width": 96, "height": 64,
            "blob_uri": "https://storage/...presigned..."}
         ]}
      ]
    }
  },
  "progress": [1, 1]
}
```

- Image and audio items carry `blob_uri`, a presigned GET valid for one hour. The browser reads the bytes from it, not through the server. The storage bucket must allow GET from the UI origin (CORS).
- Text items carry `text`; figure and distribution items carry `data` (the Plotly figure, or `{bin_counts, bin_range}`).
- The `ranges` are `[low, high + 1]` pairs for the step and index sliders. `total` covers every matching item; `used` covers the items in this response.
- A clause for another kind (for example `audios.name` on the images search) or a `metric.*` clause is refused with HTTP 400.

Sequence clauses in the filter language: `images.name`, `images.context.<key>` (and the same for `audios`, `texts`, `figures`, `distributions`).

Writes go through the run API, not the explorer:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/runs/{run_id}/sequences/presign` | Body `{kind: image or audio, name, context, step, idx, format}`. Returns `{upload_url, key, expires_in}`. The key is `<project>/<run>/<kind>/<name>/[ctx-<hash>/]<step>_<idx>.<format>`. |
| POST | `/api/v1/runs/{run_id}/sequences` | Body `{items: [...]}`, at most 500. Registers items. A binary item must name the key its presign call returned. An item whose (sequence, step, idx) is stored already is skipped, so a retry is harmless. Returns `{accepted: n}`. |

Limits: names at most 200 characters and safe as a path (no `..`, no empty parts); captions at most 2000 characters; text at most 64 000 characters; figure and distribution JSON at most 256 KB; a distribution has at most 10 000 bins.

## Filter language

A filter is a Python-style expression. It is parsed with `ast`, checked against a whitelist, and translated to SQL. It is never executed. Values reach the database as bound parameters.

```
run.name == 'baseline' and run.lr > 0.01
run.hparams.model in ['resnet', 'vit']
run.archived == False
run.active                                  # same as run.active == True
run.name.startswith('vis')
any(t.name in ['vision'] for t in run.tags)
metric.name == 'loss' and metric.context.subset == 'val'      # search/metric only
```

Fields:

| Field | Type | Notes |
|---|---|---|
| `run.name`, `run.hash`, `run.id` | text | `hash` and `id` are the run id. |
| `run.experiment` | text | Experiment name. Runs without one read `general`. |
| `run.project` | text | Project slug. |
| `run.active`, `run.archived` | boolean | Compare with `== True` or `== False`, or use alone. |
| `run.creation_time` | number | Seconds since 1970. |
| `run.<key>`, `run.<a>.<b>` | any | A parameter. Nested keys use dots. Mixed types compare as false, not as errors. |
| `run.tags` | | Only inside `any(t.name ... for t in run.tags)`. |
| `metric.name` | text | Series name. Search/metric only. |
| `metric.context.<key>` | text | Series context value. Search/metric only. |

Operators: `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `and`, `or`, `not`, `startswith()`. Values are strings, numbers, booleans, `None`, or lists of one of these. A filter may be at most 2000 characters.

Refused with HTTP 400, each with a reason:

- Calls other than `startswith()` and `any()`, lambdas, comprehensions outside `any()`, arithmetic, attribute access on values.
- Chained comparisons (`1 < run.x < 3`), and comparisons whose left side is not a field.
- Run and metric clauses joined by `or` or `not`. Join them with `and`.
- `metric.last`, which is not supported yet.
- A sequence clause on a search of another kind, and `metric.*` clauses on `search/run`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/runs/search` | Runs with traces (above). |
| GET | `/runs/search/metric` | Runs with traces, filtered by metric clauses. |
| GET | `/runs/active` | Unfinished runs. |
| GET | `/runs/{run_id}/info` | Props and params of one run. |
| POST | `/runs/archive?archive=true` | Body `{"ids": [...]}`. All runs must be writable, or none change. |
| POST | `/runs/{run_id}/tags/{tag_id}` | Attach a tag of the run's project. |
| DELETE | `/runs/{run_id}/tags/{tag_id}` | Detach a tag. |
| GET | `/projects/{project_id}/params` | Autocomplete: `{"params": [...], "metric": {name: [context keys]}}`. Reads the 1000 newest runs. |
| GET | `/projects/{project_id}/tags` | Tags of a project. |
| POST | `/projects/{project_id}/tags` | Body `{name, color?, description?}`. 409 on a duplicate name. |
| PATCH | `/tags/{tag_id}` | Change name, color or description. |
| DELETE | `/tags/{tag_id}` | Delete a tag and its attachments. |
| GET | `/bookmarks` | The caller's bookmarks. Optional `kind`. |
| POST | `/bookmarks` | Body `{kind, title, description?, state}`. `state` is at most 64 KB. |
| GET | `/bookmarks/{id}` | One bookmark. Owner only; anyone else gets 404. |
| PATCH | `/bookmarks/{id}` | Change title, description or state. |
| DELETE | `/bookmarks/{id}` | Delete. |

Run fields that are not in the explorer use the existing run API: `PATCH /api/v1/runs/{id}` changes `name`, `description`, `archived`, `notes`, `params` (merged) and `status`. `GET /api/v1/runs/{id}/logs` returns logs.

## Audit of the Aim UI calls

The source is Aim UI 3.29.1 (the `main.js` bundle in the aim-ui package). The table lists every API call the bundle makes, with the decision for each.

| Aim call | Decision |
|---|---|
| `runs/search/run` | Implemented: `GET /explorer/runs/search`. |
| `runs/search/metric` | Implemented: `GET /explorer/runs/search/metric`. |
| `runs/search/metric/align` | Deferred. Aligning traces on a shared x axis is chart work for the Phase 4 fork. |
| `runs/{id}/info` | Implemented: `GET /explorer/runs/{id}/info`. |
| `runs/{id}/logs` | Existing: `GET /api/v1/runs/{id}/logs`. |
| `runs/{id}/metric/get-batch`, `runs/{id}/{kind}/get-batch`, `get-step` | Metric detail: deferred. Sequences: replaced by `blob_uri` in the search. |
| `runs/{id}` (edit) | Existing: `PATCH /api/v1/runs/{id}`. |
| `runs/archive-batch?archive=` | Implemented: `POST /explorer/runs/archive?archive=`. |
| `runs/delete-batch`, delete run | Not implemented. Deleting a run must also remove its artifacts and sequence blobs, which needs a decision first. |
| `runs/{id}/tags/new`, `runs/{id}/tags/{tag}` | Implemented: `POST` and `DELETE /explorer/runs/{id}/tags/{tag_id}`. |
| `runs/active` | Implemented: `GET /explorer/runs/active`. |
| `runs/{id}/note` | Existing: the run's `notes` field through `PATCH /api/v1/runs/{id}`. |
| `experiments`, `experiments/search` | Existing: `GET /api/v1/experiments`. Search by `q` already works there. |
| `experiments/{id}/activity`, `experiments/{id}/note` | Deferred. |
| `projects` | Existing: `GET /api/v1/projects`. Now includes the project `id`. |
| `projects/activity` | Deferred. |
| `projects/params` | Implemented: `GET /explorer/projects/{id}/params`. |
| `projects/pinned-sequences` | Deferred. Pinning needs a table; it belongs with the project pages (Phase 6). |
| `tags` (CRUD) | Implemented: `/explorer/projects/{id}/tags` and `/explorer/tags/{id}`. |
| `bookmarks` | Implemented: `/explorer/bookmarks`. |
| `dashboards`, `boards`, `reports` | Dropped. The plan removes them from the UI (they need Pyodide and server-side app storage). |
| GitHub release notes, `auth/refresh` | Dropped. The fork uses browser sessions instead of tokens. |
| `images`, `audios`, `texts`, `figures`, `distributions` search | Implemented: `GET /explorer/runs/search/{kind}`. Blobs are read through presigned URLs, so there is no get-batch. |

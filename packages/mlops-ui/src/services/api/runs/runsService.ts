import { IApiRequest } from 'types/services/services';

import API from '../api';

// Paths are relative to /api. The explorer API lives under /api/v1/explorer; run actions that
// predate it use /api/v1/runs.
const endpoints = {
  GET_RUNS: 'v1/explorer/runs/search',
  GET_RUN_INFO: (id: string) => `v1/explorer/runs/${id}/info`,
  GET_RUN_LOGS: (id: string) => `v1/runs/${id}/logs`,
  EDIT_RUN: (id: string) => `v1/runs/${id}`,
  ARCHIVE_RUNS: (archived: boolean) =>
    `v1/explorer/runs/archive?archive=${archived}`,
  ATTACH_RUNS_TAG: (id: string, tagId: string) =>
    `v1/explorer/runs/${id}/tags/${tagId}`,
  DELETE_RUNS_TAG: (id: string, tagId: string) =>
    `v1/explorer/runs/${id}/tags/${tagId}`,
};

// Searches runs. The response is JSON; see utils/explorer/explorerJson.ts for its shape.
function getRunsData(query?: string, limit?: number, offset?: string) {
  return API.get<any>(endpoints.GET_RUNS, {
    q: query || '',
    ...(limit ? { limit } : {}),
    ...(offset ? { offset } : {}),
  });
}

// Logs are a JSON list of chunks: {stream, seq, lines}.
function getRunLogs(id: string) {
  return API.get<any[]>(endpoints.GET_RUN_LOGS(id));
}

function getRunInfo(id: string) {
  return API.get(endpoints.GET_RUN_INFO(id));
}

function archiveRun(id: string, archived: boolean = false) {
  return API.patch(endpoints.EDIT_RUN(id), { archived });
}

function editRunNameAndDescription(
  id: string,
  name: string,
  description: string,
  archived: boolean,
) {
  return API.patch(endpoints.EDIT_RUN(id), { name, description, archived });
}

function archiveRuns(ids: string[], archived: boolean = false) {
  return API.post(endpoints.ARCHIVE_RUNS(archived), { ids });
}

// Deleting runs is not offered by the MLOps Flow API yet (the decision is open, see docs).
function deleteRun(id: string) {
  return unsupported(`Deleting run ${id}`);
}

function deleteRuns(ids: string[]) {
  return unsupported(`Deleting ${ids.length} runs`);
}

// The fork attaches tags by name. The explorer attaches by tag id inside a project, which the
// project pages (Phase 6) will provide.
function attachRunsTag(body: { tag_name: string }, runId: string) {
  return unsupported(`Attaching the tag ${body.tag_name} to run ${runId}`);
}

function deleteRunsTag(runId: string, tagId: string) {
  return API.delete(endpoints.DELETE_RUNS_TAG(runId, tagId));
}

// Scalar metrics of one run: the explorer search for `run.hash`, with dense points. The `body`
// argument of the old get-batch call (which traces to fetch) is not needed: the search returns
// all of the run's traces.
function getRunMetricsBatch(body: unknown, runHash: string) {
  const id = runHash.replace(/[^A-Za-z0-9_]/g, '');
  return API.get<any>(endpoints.GET_RUNS, {
    q: `run.hash == '${id}'`,
    points: 500,
  });
}

// A request for something the API does not offer yet. It fails when it is called, the way a
// failed request does, so the callers' error handling runs.
function unsupported(what: string): IApiRequest<never> {
  return {
    call: () => Promise.reject(new Error(`${what} is not supported yet.`)),
    abort: () => undefined,
  };
}

// Sequence batches (distributions, figures, images, audios, texts) arrive in Phase 5.
function getBatch(runId: string, trace: string, ..._args: unknown[]) {
  return unsupported(`Sequence data (${trace}) for run ${runId}`);
}

function getBatchByStep(runId: string, trace: string, ..._args: unknown[]) {
  return unsupported(`Sequence data (${trace}) by step for run ${runId}`);
}

// The experiment list of the run detail page (the MLOps Flow experiments API).
function getExperimentsData() {
  return API.get<any>('v1/experiments');
}

const runsService = {
  endpoints,
  getExperimentsData,
  getRunMetricsBatch,
  getBatch,
  getBatchByStep,
  getRunsData,
  getRunInfo,
  getRunLogs,
  archiveRun,
  deleteRun,
  attachRunsTag,
  deleteRunsTag,
  archiveRuns,
  deleteRuns,
  editRunNameAndDescription,
};

export default runsService;

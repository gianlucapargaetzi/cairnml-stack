import API from 'services/api/api';

import { SequenceTypesEnum } from 'types/core/enums';
import { IApiRequest } from 'types/services/services';

import { RunsSearchQueryParams, RunsSearchResult } from './types';

// The runs requests go to the explorer API (/api/v1/explorer) and return JSON. Sequence requests
// (images, audios, texts, figures, distributions) and metric alignment arrive in Phase 5; until
// then they fail when called.

export interface RequestInstance {
  call: (...args: any[]) => Promise<any>;
  cancel: () => void;
}

// The explorer's names for the fork's query parameters: p (density) is points.
function toExplorerQuery(queryParams: RunsSearchQueryParams = {}) {
  const { p, ...rest } = queryParams as RunsSearchQueryParams & {
    [key: string]: unknown;
  };
  return { ...rest, ...(p ? { points: p } : {}) };
}

function unsupported(what: string): RequestInstance {
  return {
    call: () => Promise.reject(new Error(`${what} is not supported yet.`)),
    cancel: () => undefined,
  };
}

function requestWithCancel(
  make: (...args: any[]) => IApiRequest<any>,
): RequestInstance {
  let current: IApiRequest<any> | null = null;
  return {
    call: (...args: any[]) => {
      current = make(...args);
      return current.call();
    },
    cancel: () => current?.abort(),
  };
}

async function searchRuns(
  sequenceType: SequenceTypesEnum,
  queryParams: RunsSearchQueryParams,
): Promise<RunsSearchResult> {
  throw new Error(`${sequenceType} search is not supported yet.`);
}

function createSearchRunsRequest(
  sequenceType: SequenceTypesEnum,
): RequestInstance {
  return unsupported(`${sequenceType} search`);
}

function createSearchRunRequest(): RequestInstance {
  return requestWithCancel((queryParams?: RunsSearchQueryParams) =>
    API.get<any>('v1/explorer/runs/search', toExplorerQuery(queryParams)),
  );
}

function createRunLogRecordsRequest(): RequestInstance {
  return requestWithCancel((runId: string) =>
    API.get<any[]>(`v1/runs/${runId}/logs`),
  );
}

function createBlobsRequest(
  sequenceType: `${SequenceTypesEnum}`,
): RequestInstance {
  return unsupported(`${sequenceType} data`);
}

function createActiveRunsRequest(): RequestInstance {
  return requestWithCancel(() => API.get<any>('v1/explorer/runs/active'));
}

function alignMetricsRequest(): RequestInstance {
  return unsupported('Metric alignment');
}

export {
  searchRuns,
  createSearchRunsRequest,
  createActiveRunsRequest,
  createSearchRunRequest,
  createBlobsRequest,
  createRunLogRecordsRequest,
  alignMetricsRequest,
};
export * from './types';

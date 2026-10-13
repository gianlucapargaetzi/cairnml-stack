import {
  IPinnedSequencesResData,
  IProject,
  IProjectParamsMetrics,
} from 'types/services/models/projects/projectsModel';
import { IApiRequest } from 'types/services/services';

import API from '../api';

// Projects come from /api/v1/projects. The fork shows one instance-wide project header, so the
// list is summarised into that shape. Parameter names come from each project's explorer
// listing, merged into the nested shape the query builder reads.
const endpoints = {
  GET_PROJECTS: 'v1/projects',
  GET_PROJECT_PARAMS: (id: string) => `v1/explorer/projects/${id}/params`,
};

interface IListedProject {
  id: string;
  slug: string;
  name: string;
}

interface IExplorerParams {
  params: string[];
  metric: { [name: string]: string[] };
}

function getProjectsData(): IApiRequest<IProject> {
  const list = API.get<IListedProject[]>(endpoints.GET_PROJECTS);
  return {
    call: async (detail?: any) => {
      await list.call(detail);
      return {
        name: 'MLOps Flow',
        description: '',
        telemetry_enabled: false,
        warn_index: false,
        warn_runs: false,
      };
    },
    abort: list.abort,
  };
}

// Builds {params, metric} from the explorer listings of every project the user can read.
// The sequence list of the old endpoint is not needed: every project's params are read.
function getProjectParams(
  _sequences: string[] = ['metric'],
): IApiRequest<IProjectParamsMetrics> {
  const requests: IApiRequest<any>[] = [];
  return {
    call: async (detail?: any) => {
      const list = API.get<IListedProject[]>(endpoints.GET_PROJECTS);
      requests.push(list);
      const projects = await list.call(detail);
      const listings = await Promise.all(
        projects.map((project) => {
          const request = API.get<IExplorerParams>(
            endpoints.GET_PROJECT_PARAMS(project.id),
          );
          requests.push(request);
          return request.call(detail);
        }),
      );
      return mergeParams(listings);
    },
    abort: () => requests.forEach((request) => request.abort()),
  };
}

function mergeParams(listings: IExplorerParams[]): IProjectParamsMetrics {
  const params: { [key: string]: any } = {};
  const metric: { [name: string]: { [key: string]: string }[] } = {};
  for (const listing of listings) {
    for (const path of listing.params) {
      let node = params;
      const keys = path.split('.');
      keys.forEach((key, index) => {
        if (index === keys.length - 1) {
          node[key] = node[key] ?? '';
        } else {
          node[key] = typeof node[key] === 'object' ? node[key] : {};
          node = node[key];
        }
      });
    }
    for (const [name, contextKeys] of Object.entries(listing.metric)) {
      const contexts = contextKeys.length
        ? contextKeys.map((key) => ({ [key]: '' }))
        : [{}];
      metric[name] = [...(metric[name] ?? []), ...contexts];
    }
  }
  return { params, metric, images: {} };
}

// Pinned sequences and the activity feed belong to the sequence and project pages (Phases 5, 6).
// Until then they read as empty, and saving them fails clearly.
function getPinnedSequences(): IApiRequest<IPinnedSequencesResData> {
  return {
    call: () => Promise.resolve({} as IPinnedSequencesResData),
    abort: () => undefined,
  };
}

function setPinnedSequences(
  body: IPinnedSequencesResData,
): IApiRequest<IPinnedSequencesResData> {
  return {
    call: () =>
      Promise.reject(new Error('Pinning sequences is not supported yet.')),
    abort: () => undefined,
  };
}

function fetchActivityData(): IApiRequest<any> {
  return { call: () => Promise.resolve([]), abort: () => undefined };
}

const projectsService = {
  endpoints,
  getProjectsData,
  fetchActivityData,
  getProjectParams,
  getPinnedSequences,
  setPinnedSequences,
};

export default projectsService;

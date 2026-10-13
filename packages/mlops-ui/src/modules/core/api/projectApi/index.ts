import projectsService from 'services/api/projects/projectsService';

import {
  GetParamsQueryOptions,
  GetParamsResult,
  GetProjectContributionsResult,
} from './types';

/**
 * function getParams
 * this call is used for i.e. autosuggestions etc.
 * The explorer API has no /projects/params route: the params and metric names come from the
 * explorer listing of every project the user can read. The sequence list is not needed, since
 * every project's listing is read.
 * @param {GetParamsQueryOptions} queryParams
 */
async function getParams(
  queryParams: GetParamsQueryOptions,
): Promise<GetParamsResult> {
  const { params, metric, images } = await projectsService
    .getProjectParams()
    .call();
  return queryParams.exclude_params
    ? { metric, images }
    : { params, metric, images };
}

/**
 * function getProjectContributions
 * this call is used from DashboardPage page to show project contributions data
 */
async function getProjectContributions(): Promise<GetProjectContributionsResult> {
  // The activity feed arrives with the project pages (Phase 6).
  return {
    num_experiments: 0,
    num_archived_runs: 0,
    num_runs: 0,
    num_active_runs: 0,
    activity_map: {},
  };
}

export { getParams, getProjectContributions };
export * from './types';

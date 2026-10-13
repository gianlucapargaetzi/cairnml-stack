import { createSearchRunRequest } from 'modules/core/api/runsApi';
import createResource from 'modules/core/utils/createResource';

import { RequestOptions } from 'services/NetworkService';

import { IRun } from 'types/services/models/metrics/runModel';

import { runsList } from 'utils/explorer/explorerJson';

function createDashboardContributionsFeedEngine() {
  let { call } = createSearchRunRequest();

  const { fetchData, state, destroy } = createResource<IRun<unknown>[]>(
    async (queryParams: RequestOptions['query_params']) =>
      runsList(await call(queryParams)),
  );
  return {
    fetchContributionsFeed: (queryParams: RequestOptions['query_params']) =>
      fetchData(queryParams),
    contributionsFeedState: state,
    destroy,
  };
}

export default createDashboardContributionsFeedEngine();

import { createActiveRunsRequest } from 'modules/core/api/runsApi';
import createResource from 'modules/core/utils/createResource';

import { IRun } from 'types/services/models/metrics/runModel';

import { runsList } from 'utils/explorer/explorerJson';

function createActiveRunsEngine() {
  let { call } = createActiveRunsRequest();

  const { fetchData, state, destroy } = createResource<IRun<unknown>[]>(
    async () => runsList(await call()),
  );
  return { fetchActiveRuns: fetchData, activeRunsState: state, destroy };
}

export default createActiveRunsEngine();

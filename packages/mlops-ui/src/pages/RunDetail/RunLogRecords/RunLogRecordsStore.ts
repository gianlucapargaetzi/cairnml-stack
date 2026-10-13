import { createRunLogRecordsRequest } from 'modules/core/api/runsApi';
import createResource from 'modules/core/utils/createResource';

import { sortedLogLines } from 'utils/explorer/explorerJson';

import { RunLogRecordStateType } from '.';

function createRunLogRecordsEngine() {
  let { call, cancel } = createRunLogRecordsRequest();

  // One record per log line, keyed by its position in the run's logs.
  const { fetchData, state, destroy } = createResource<RunLogRecordStateType>(
    async ({ runId }: { runId: string; record_range?: string }) => {
      const lines = sortedLogLines(await call(runId));
      const records: RunLogRecordStateType['runLogRecordsList'] = {};
      lines.forEach((line, index) => {
        records[index] = {
          hash: index,
          message: line.text,
          log_level: 'INFO',
          args: { stream: line.stream },
          is_notified: false,
          timestamp: line.ts,
        };
      });
      return {
        runLogRecordsList: records,
        runLogRecordsTotalCount: lines.length,
      };
    },
  );

  function abortRunLogRecordsFetching() {
    cancel();
    const request = createRunLogRecordsRequest();
    call = request.call;
    cancel = request.cancel;
  }

  return {
    fetchRunLogRecords: (options: { runId: string; record_range?: string }) =>
      fetchData(options),
    abortRunLogRecordsFetching,
    runLogRecordsState: state,
    destroy,
  };
}

export default createRunLogRecordsEngine();

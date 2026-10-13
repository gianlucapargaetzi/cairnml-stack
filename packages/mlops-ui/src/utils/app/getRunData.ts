import { IExplorerSearch, iterExplorerRuns } from 'utils/explorer/explorerJson';

import { IRequestProgress } from './setRequestProgress';

// Folds a runs search response into run objects. The progress record goes to setProgress.
export default async function getRunData(
  search: IExplorerSearch,
  setProgress?: (progress: IRequestProgress) => void,
) {
  const runData = [];

  for await (let [keys, val] of iterExplorerRuns(search)) {
    const data = { ...(val as any), hash: keys[0] };
    if (data.hash.startsWith('progress')) {
      const { 0: checked, 1: trackedRuns } = data;
      setProgress?.({
        matched: runData.length,
        checked,
        trackedRuns,
      });
    } else {
      runData.push(data);
    }
  }

  return runData;
}

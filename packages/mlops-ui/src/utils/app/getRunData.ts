import {
  IExplorerSearch,
  iterExplorerRuns,
  toSequence,
} from 'utils/explorer/explorerJson';
import {
  ExplorerSequenceKind,
  IExplorerSequenceSearch,
  toSequenceRun,
} from 'utils/explorer/sequenceJson';

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

// The same folding for the metric explorer, where each run is a sequence (see toSequence).
export async function getSequenceData(
  search: IExplorerSearch,
  setProgress?: (progress: IRequestProgress) => void,
) {
  const sequences = [];
  for await (let [keys, val] of iterExplorerRuns(search, toSequence)) {
    const data = { ...(val as any), hash: keys[0] };
    if (data.hash.startsWith('progress')) {
      const { 0: checked, 1: trackedRuns } = data;
      setProgress?.({ matched: sequences.length, checked, trackedRuns });
    } else {
      sequences.push(data);
    }
  }
  return sequences;
}

// The same folding for the sequence explorers (images, audio, text, figures, distributions).
export async function getSequenceRunData(
  search: IExplorerSequenceSearch,
  kind: ExplorerSequenceKind,
  setProgress?: (progress: IRequestProgress) => void,
) {
  const runs = Object.entries(search.runs).map(([runId, run]) =>
    toSequenceRun(runId, run, kind),
  );
  const [checked, trackedRuns] = search.progress;
  setProgress?.({ matched: runs.length, checked, trackedRuns });
  return runs;
}

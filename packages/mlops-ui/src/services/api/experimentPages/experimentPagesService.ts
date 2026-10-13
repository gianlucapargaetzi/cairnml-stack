import { IExperimentRun } from 'utils/experiments/experiments';

import API from '../api';

// The experiment page reads one experiment's summary: its settings, the best run of the primary
// metric, and its most recent runs. The settings change through the experiment API.
export interface IExperimentSummary {
  experiment: {
    id: string;
    project: string;
    name: string;
    kind: string;
    description: string | null;
    primary_metric: string | null;
    direction: string | null;
  };
  stats: {
    runs: number;
    running: number;
    best: { run_id: string; name: string; value: number } | null;
  };
  runs: (IExperimentRun & {
    name: string;
    status: string;
    owner: string | null;
    created_at: string;
    started_at: string | null;
    finished_at: string | null;
    commit: string | null;
    dirty: boolean;
  })[];
}

export interface IExperimentSettings {
  kind?: string;
  description?: string | null;
  primary_metric?: string | null;
  direction?: string | null;
}

function getSummary(id: string) {
  return API.get<IExperimentSummary>(`v1/experiments/${id}/summary`);
}

function patchSettings(id: string, body: IExperimentSettings) {
  return API.patch<IExperimentSummary['experiment']>(
    `v1/experiments/${id}`,
    body,
  );
}

const experimentPagesService = { getSummary, patchSettings };

export default experimentPagesService;

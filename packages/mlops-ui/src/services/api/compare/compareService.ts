import { ICompareMetric } from 'utils/compare/compare';

import API from '../api';

// Runs side by side: their settings, code and data, requirements, and the summary of each metric
// (the last, minimum and maximum values, and the series for the chart).
export interface ICompareRun {
  id: string;
  name: string;
  status: string;
  experiment: string;
  config: { [key: string]: unknown };
  params: { [key: string]: unknown };
  git: {
    repo?: string;
    branch?: string;
    commit?: string;
    dirty?: boolean;
  } | null;
  script: string | null;
  python_version: string | null;
  platform: string | null;
  datasets: { path: string; dvc_hash: string | null }[];
  requirements: string[];
  metrics: {
    [name: string]: ICompareMetric & {
      min: number;
      max: number;
      count: number;
      series: [number, number][];
    };
  };
}

function getCompare(ids: string[]) {
  return API.get<{ runs: ICompareRun[] }>('v1/runs/compare', {
    ids: ids.join(','),
  });
}

const compareService = { getCompare };

export default compareService;

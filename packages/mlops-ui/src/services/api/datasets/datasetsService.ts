import { IDatasetRow } from 'utils/datasets/datasets';

import API from '../api';

// Datasets are DVC files in linked Git repositories, with an optional card (Markdown with a
// front matter block) next to each .dvc file. The listing reads GitHub through the server.
export interface IDatasetCard {
  title: string | null;
  type: string;
  license: string | null;
  source: string | null;
  version: string | null;
  created: string | null;
  owners: string[];
  tags: string[];
  size_bytes: number | null;
  rows: number | null;
  columns: { name: string; type: string | null; description: string | null }[];
  splits: { [split: string]: number };
  warnings: string[];
  error: string | null;
  body: string;
}

export interface IDatasetDetail {
  repo: string;
  path: string;
  ref: string;
  dvc: {
    dvc_hash: string | null;
    size_bytes: number | null;
    nfiles: number | null;
  };
  card: IDatasetCard | null;
  versions: {
    commit: string | null;
    date: string | null;
    message: string;
    dvc_hash: string | null;
  }[];
  used_by: {
    count: number;
    runs: {
      id: string;
      name: string;
      status: string;
      experiment: string;
      created_at: string;
    }[];
  };
}

function getDatasets() {
  return API.get<IDatasetRow[]>('v1/datasets');
}

function getDatasetDetail(project: string, repo: string, path: string) {
  return API.get<IDatasetDetail>('v1/datasets/detail', { project, repo, path });
}

const datasetsService = { getDatasets, getDatasetDetail };

export default datasetsService;

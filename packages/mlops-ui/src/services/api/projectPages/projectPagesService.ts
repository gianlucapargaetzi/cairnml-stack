import { IProjectRef } from 'utils/projects/projects';

import API from '../api';

// The projects pages read the project list, the summary of every project the caller is in, and one
// project's overview (experiments, containers, recent runs, linked repositories).
export interface IProjectSummary {
  slug: string;
  name: string;
  runs: number;
  running: number;
  last_activity: string | null;
}

export interface IOverviewRun {
  id: string;
  name: string;
  project: string;
  status: string;
  experiment: string;
  owner: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface IProjectOverview {
  project: { slug: string; name: string; created_at: string };
  repos: { repo: string; role: string }[];
  experiments: {
    id: string;
    name: string;
    kind: string;
    description: string | null;
    primary_metric: string | null;
    direction: string | null;
    runs: number;
    running: number;
    last_activity: string | null;
    best: { run_id: string; value: number } | null;
  }[];
  containers: {
    kind: string;
    name: string;
    jobs: number;
    last_used: string;
    last_status: string;
  }[];
  counts: { runs: number; running: number; jobs: { [status: string]: number } };
  recent: IOverviewRun[];
}

function getProjects() {
  return API.get<IProjectRef[]>('v1/projects');
}

function getOverview() {
  return API.get<{ projects: IProjectSummary[] }>('v1/overview');
}

function getProjectOverview(slug: string) {
  return API.get<IProjectOverview>('v1/projects/overview', { project: slug });
}

const projectPagesService = { getProjects, getOverview, getProjectOverview };

export default projectPagesService;

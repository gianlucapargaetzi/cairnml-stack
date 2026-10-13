import { IGraphBranch, IGraphCommit } from 'utils/graph/layout';
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

// The commit history of a linked repository, with the runs that ran on each commit.
export interface IRepoGraph {
  repo: string;
  default_branch: string;
  head: string;
  branches: IGraphBranch[];
  commits: IGraphCommit[];
  truncated: boolean;
  runs: {
    [sha: string]: {
      id: string;
      name: string;
      experiment: string;
      status: string;
    }[];
  };
}

function getRepoGraph(project: string, repo: string) {
  return API.get<IRepoGraph>('v1/projects/graph', { project, repo });
}

const projectPagesService = {
  getProjects,
  getOverview,
  getProjectOverview,
  getRepoGraph,
};

export default projectPagesService;

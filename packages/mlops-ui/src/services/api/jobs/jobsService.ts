import { IJobOverrides } from 'utils/jobs/jobs';

import API from '../api';

// The jobs API (/api/v1/jobs). Reads need a client or browser session; the writes add the CSRF
// token through the API client.
const endpoints = {
  JOBS: 'v1/jobs',
  JOB: (id: string) => `v1/jobs/${id}`,
  SPEC: (id: string) => `v1/jobs/${id}/spec`,
  CANCEL: (id: string) => `v1/jobs/${id}/cancel`,
  RESCHEDULE: (id: string) => `v1/jobs/${id}/reschedule`,
};

export interface IJobRow {
  id: string;
  run_id: string;
  run_name: string;
  project: string;
  status: string;
  queue: string;
  agent_id: string | null;
  agent_name: string | null;
  cpu: number;
  memory_gb: number;
  gpu: number;
  labels: string[];
  exit_code: number | null;
  message: string | null;
  created_at: string;
  assigned_at: string | null;
  finished_at: string | null;
  experiment: string;
  cancel_requested: boolean;
}

export interface IJobSpec {
  name: string;
  project: string;
  queue: string;
  resources: { cpu: number; memory_gb: number; gpu: number; labels: string[] };
  params: { [key: string]: unknown };
  env: { [key: string]: string };
  timeout_s: number | null;
  experiment: string;
  runtime: { [key: string]: unknown };
  code: { repo: string; commit: string; workdir: string } | null;
  data: { repo?: string; commit?: string; path?: string }[];
}

// The most recent jobs, all statuses. The page groups them.
function getJobs(limit = 200) {
  return API.get<IJobRow[]>(endpoints.JOBS, { limit });
}

function getJobSpec(id: string) {
  return API.get<IJobSpec>(endpoints.SPEC(id));
}

function cancelJob(id: string) {
  return API.post<IJobRow>(endpoints.CANCEL(id), {});
}

function rescheduleJob(id: string, overrides: IJobOverrides) {
  return API.post<IJobRow>(endpoints.RESCHEDULE(id), overrides);
}

const jobsService = {
  endpoints,
  getJobs,
  getJobSpec,
  cancelJob,
  rescheduleJob,
};

export default jobsService;

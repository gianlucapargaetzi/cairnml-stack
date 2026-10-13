// Helpers for the jobs page: status groups, cancel rules, and the body of a reschedule request.
// The reschedule body is JobOverrides on the server: only the changed fields are sent, and a
// null removes a param or env key.

export type JobGroup = 'active' | 'finished' | 'failed' | 'cancelled';

export const JOB_GROUPS: { key: JobGroup; label: string }[] = [
  { key: 'active', label: 'Active' },
  { key: 'finished', label: 'Finished' },
  { key: 'failed', label: 'Failed' },
  { key: 'cancelled', label: 'Cancelled' },
];

const ACTIVE_STATUSES = ['queued', 'assigned', 'running'];

export function jobGroup(status: string): JobGroup {
  if (ACTIVE_STATUSES.includes(status)) {
    return 'active';
  }
  if (status === 'failed') {
    return 'failed';
  }
  return status === 'cancelled' ? 'cancelled' : 'finished';
}

export function canCancel(job: {
  status: string;
  cancel_requested?: boolean;
}): boolean {
  return ACTIVE_STATUSES.includes(job.status);
}

export interface IJobResources {
  cpu: number;
  memory_gb: number;
  gpu: number;
  labels: string[];
}

export interface IJobSpecLike {
  name: string;
  queue: string;
  resources: IJobResources;
  params: { [key: string]: unknown };
  env: { [key: string]: string };
  timeout_s?: number | null;
}

export interface IJobForm {
  name: string;
  queue: string;
  resources: IJobResources;
  params: { [key: string]: unknown };
  env: { [key: string]: string };
  // Blank keeps the original timeout; the server cannot clear one.
  timeout_s: number | '';
}

export interface IJobOverrides {
  name?: string;
  queue?: string;
  resources?: IJobResources;
  params?: { [key: string]: unknown };
  env?: { [key: string]: string | null };
  timeout_s?: number;
}

export function parseLabels(text: string): string[] {
  return text
    .split(',')
    .map((label) => label.trim())
    .filter(Boolean);
}

// Keys in `after` with new values, and keys missing from `after` with null.
export function mapDiff<T>(
  before: { [key: string]: T } = {},
  after: { [key: string]: T } = {},
): { [key: string]: T | null } {
  const out: { [key: string]: T | null } = {};
  for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
    if (!(key in after)) {
      out[key] = null;
    } else if (JSON.stringify(before[key]) !== JSON.stringify(after[key])) {
      out[key] = after[key];
    }
  }
  return out;
}

export function buildJobOverrides(
  original: IJobSpecLike,
  form: IJobForm,
): IJobOverrides {
  const out: IJobOverrides = {};
  if (form.name !== original.name) {
    out.name = form.name;
  }
  if (form.queue !== original.queue) {
    out.queue = form.queue;
  }
  const resourcesChanged = (
    ['cpu', 'memory_gb', 'gpu', 'labels'] as const
  ).some(
    (field) =>
      JSON.stringify(form.resources[field]) !==
      JSON.stringify(original.resources[field]),
  );
  if (resourcesChanged) {
    out.resources = form.resources;
  }
  if (form.timeout_s !== '' && form.timeout_s !== original.timeout_s) {
    out.timeout_s = form.timeout_s;
  }
  const params = mapDiff(original.params, form.params);
  if (Object.keys(params).length) {
    out.params = params;
  }
  const env = mapDiff(original.env, form.env);
  if (Object.keys(env).length) {
    out.env = env;
  }
  return out;
}

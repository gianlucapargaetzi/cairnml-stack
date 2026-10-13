// The body of a dispatch request from the run page's form. Empty resource fields are left out, so
// the server applies its defaults. A value that is not a number of 0 or more is refused.

export interface IDispatchForm {
  queue: string;
  cpu: string;
  memory_gb: string;
  gpu: string;
  labels: string;
}

export interface IDispatchBody {
  queue: string;
  labels: string[];
  cpu?: number;
  memory_gb?: number;
  gpu?: number;
}

export function dispatchBody(form: IDispatchForm): IDispatchBody {
  const body: IDispatchBody = {
    queue: form.queue.trim() || 'default',
    labels: form.labels
      .split(',')
      .map((label) => label.trim())
      .filter(Boolean),
  };
  for (const field of ['cpu', 'memory_gb', 'gpu'] as const) {
    const raw = form[field];
    if (raw === '' || raw === null || raw === undefined) {
      continue;
    }
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0) {
      throw new Error(`${field} must be a number of 0 or more`);
    }
    body[field] = value;
  }
  return body;
}

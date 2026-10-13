// Helpers for the experiment page: the run table's sort, the best run, the parameters that vary
// across runs, and the text of a save error.

export const EXPERIMENT_KINDS = [
  'training',
  'data-preparation',
  'augmentation',
  'evaluation',
  'testing',
  'compilation',
  'inference',
  'other',
];

export const DIRECTIONS = ['min', 'max'];

export interface IExperimentRun {
  id: string;
  primary_value: number | null;
  params: { [key: string]: unknown };
}

// The row with the best non-null value: the largest for "max", the smallest otherwise.
export function bestId(
  rows: IExperimentRun[],
  direction: string | null,
): string | null {
  const valued = rows.filter((r) => typeof r.primary_value === 'number');
  if (!valued.length) {
    return null;
  }
  const better =
    direction === 'max'
      ? (a: IExperimentRun, b: IExperimentRun) =>
          (b.primary_value as number) > (a.primary_value as number) ? b : a
      : (a: IExperimentRun, b: IExperimentRun) =>
          (b.primary_value as number) < (a.primary_value as number) ? b : a;
  return valued.reduce(better).id;
}

// A copy sorted by one field. "asc" and "min" ascend, anything else descends. Missing values go last
// in both orders.
export function sortRows<T extends { [key: string]: any }>(
  rows: T[],
  by: string,
  direction: string,
): T[] {
  const sign = direction === 'asc' || direction === 'min' ? 1 : -1;
  const missing = (v: unknown) => v === null || v === undefined;
  return [...rows].sort((a, b) => {
    const x = a[by];
    const y = b[by];
    if (missing(x)) {
      return missing(y) ? 0 : 1;
    }
    if (missing(y)) {
      return -1;
    }
    return (x < y ? -1 : x > y ? 1 : 0) * sign;
  });
}

// Parameters whose values differ between runs. A key missing from a run counts as its own value.
export function varyingKeys(rows: IExperimentRun[], limit = 5): string[] {
  if (rows.length < 2) {
    return [];
  }
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r.params ?? {})))];
  return keys
    .map((key) => {
      const seen = new Set(
        rows.map((r) =>
          r.params && key in r.params
            ? JSON.stringify(r.params[key])
            : '\u0000missing',
        ),
      );
      return { key, count: seen.size };
    })
    .filter((k) => k.count > 1)
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key))
    .slice(0, limit)
    .map((k) => k.key);
}

export function paramText(value: unknown): string {
  return typeof value === 'object' && value !== null
    ? JSON.stringify(value)
    : String(value);
}

// The settings form is shown to everyone; the server answers 404 to a non-member and 403 to a
// read-only session, and the message says which.
export function explainSaveError(error: {
  status?: number;
  message: string;
}): string {
  if (error.status === 404) {
    return 'Could not save: only members of this project can change its experiment.';
  }
  if (error.status === 403) {
    return `Could not save: this session may not change the experiment (${error.message}).`;
  }
  return `Could not save: ${error.message}`;
}

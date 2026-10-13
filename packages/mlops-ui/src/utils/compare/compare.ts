// Helpers for the compare page: the differences between runs, and the winner of a metric.

export const MAX_COMPARE = 10;

export function flatten(
  obj: unknown,
  prefix = '',
  out: { [key: string]: unknown } = {},
) {
  for (const [key, value] of Object.entries((obj as object) ?? {})) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flatten(value, path, out);
    } else {
      out[path] = value;
    }
  }
  return out;
}

export interface IDiffRow {
  key: string;
  values: unknown[];
  differs: boolean;
}

// One row per key across the runs. `pick` gives each run's object to read the keys from.
export function diffRows<T>(runs: T[], pick: (run: T) => unknown): IDiffRow[] {
  const flat = runs.map((run) => flatten(pick(run)));
  const keys = [...new Set(flat.flatMap((f) => Object.keys(f)))].sort();
  return keys.map((key) => {
    const values = flat.map((f) => (key in f ? f[key] : undefined));
    const first = JSON.stringify(values[0]);
    return {
      key,
      values,
      differs: values.some((v) => JSON.stringify(v) !== first),
    };
  });
}

export function setDiff(base: string[], other: string[]) {
  const a = new Set(base);
  const b = new Set(other);
  return {
    added: [...b].filter((x) => !a.has(x)),
    removed: [...a].filter((x) => !b.has(x)),
  };
}

export interface ICompareMetric {
  last: number;
}

// The run with the lowest last value of a metric. Needs at least two runs that logged it.
export function metricWinner(
  runs: { id: string; metrics: { [name: string]: ICompareMetric } }[],
  name: string,
): string | null {
  const present = runs.filter((run) => run.metrics[name]);
  if (present.length < 2) {
    return null;
  }
  return present.reduce((a, b) =>
    b.metrics[name].last < a.metrics[name].last ? b : a,
  ).id;
}

// The run ids of the URL: distinct, in order, at most MAX_COMPARE.
export function parseCompareIds(text: string): string[] {
  return [...new Set(text.split(',').filter(Boolean))].slice(0, MAX_COMPARE);
}

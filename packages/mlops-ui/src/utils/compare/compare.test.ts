import {
  diffRows,
  flatten,
  metricWinner,
  parseCompareIds,
  setDiff,
} from './compare';

describe('flatten and diffRows', () => {
  it('flattens nested objects to dotted keys and keeps arrays whole', () => {
    expect(flatten({ a: { b: 1 }, c: [1, 2] })).toEqual({
      'a.b': 1,
      c: [1, 2],
    });
  });

  it('gives one row per key, with each run value and whether any run differs', () => {
    const rows = diffRows(
      [
        { config: { lr: 0.1 }, params: { batch: 8 } },
        { config: { lr: 0.1 }, params: { batch: 16 } },
      ],
      (run) => ({ ...run.config, ...run.params }),
    );
    expect(rows).toEqual([
      { key: 'batch', values: [8, 16], differs: true },
      { key: 'lr', values: [0.1, 0.1], differs: false },
    ]);
  });

  it('shows a missing value as undefined and counts it as a difference', () => {
    const [row] = diffRows([{ x: { a: 1 } }, { x: {} }], (run) => run.x);
    expect(row).toEqual({ key: 'a', values: [1, undefined], differs: true });
  });
});

describe('setDiff', () => {
  it('lists what the other set adds and removes against the base', () => {
    expect(setDiff(['numpy', 'torch'], ['torch', 'pillow'])).toEqual({
      added: ['pillow'],
      removed: ['numpy'],
    });
  });
});

describe('metricWinner and parseCompareIds', () => {
  const runs: { id: string; metrics: { [name: string]: { last: number } } }[] =
    [
      { id: 'a', metrics: { loss: { last: 0.3 } } },
      { id: 'b', metrics: { loss: { last: 0.1 } } },
      { id: 'c', metrics: {} },
    ];

  it('marks the lowest last value, and only when two runs logged the metric', () => {
    expect(metricWinner(runs, 'loss')).toBe('b');
    expect(metricWinner([runs[0], runs[2]], 'loss')).toBeNull();
  });

  it('keeps distinct ids and caps them at ten', () => {
    expect(parseCompareIds('a,b,a,,c')).toEqual(['a', 'b', 'c']);
    const many = Array.from({ length: 12 }, (_, i) => `r${i}`).join(',');
    expect(parseCompareIds(many)).toHaveLength(10);
  });
});

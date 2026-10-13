import {
  bestId,
  explainSaveError,
  paramText,
  sortRows,
  varyingKeys,
} from './experiments';

const rows = [
  { id: 'a', name: 'a', primary_value: 0.3, params: { lr: 0.1, epochs: 3 } },
  { id: 'b', name: 'b', primary_value: null, params: { lr: 0.01, epochs: 3 } },
  { id: 'c', name: 'c', primary_value: 0.1, params: { lr: 0.1, epochs: 5 } },
];

describe('bestId', () => {
  it('picks the smallest value for min and the largest for max, ignoring missing values', () => {
    expect(bestId(rows, 'min')).toBe('c');
    expect(bestId(rows, 'max')).toBe('a');
    expect(
      bestId([{ id: 'x', primary_value: null, params: {} }], 'min'),
    ).toBeNull();
  });
});

describe('sortRows', () => {
  it('sorts a copy, with missing values last in both orders', () => {
    expect(sortRows(rows, 'primary_value', 'asc').map((r) => r.id)).toEqual([
      'c',
      'a',
      'b',
    ]);
    expect(sortRows(rows, 'primary_value', 'desc').map((r) => r.id)).toEqual([
      'a',
      'c',
      'b',
    ]);
    expect(rows[0].id).toBe('a');
  });
});

describe('varyingKeys', () => {
  it('lists the parameters whose values differ between runs, most varied first', () => {
    // Both keys take two values; ties sort alphabetically.
    expect(varyingKeys(rows)).toEqual(['epochs', 'lr']);
    expect(varyingKeys([rows[0]])).toEqual([]);
  });
});

describe('paramText and explainSaveError', () => {
  it('shows structured values as JSON and everything else as text', () => {
    expect(paramText({ a: [1, 2] })).toBe('{"a":[1,2]}');
    expect(paramText(0.1)).toBe('0.1');
  });

  it('explains a 404 and a 403 in terms of the caller', () => {
    expect(
      explainSaveError(Object.assign(new Error('x'), { status: 404 })),
    ).toMatch(/only members/);
    expect(
      explainSaveError(Object.assign(new Error('nope'), { status: 403 })),
    ).toMatch(/may not change/);
    expect(explainSaveError(new Error('boom'))).toBe('Could not save: boom');
  });
});

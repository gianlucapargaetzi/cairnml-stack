import { bestLabel, buildProjectTree, fmtNumber } from './projects';

describe('buildProjectTree', () => {
  it('nests projects by the parts of their slug, and sorts groups before leaves', () => {
    const tree = buildProjectTree([
      { id: '1', slug: 'vision/seg', name: 'Segmentation' },
      { id: '2', slug: 'vision', name: 'Vision' },
      { id: '3', slug: 'audio', name: 'Audio' },
    ]);
    expect(tree.map((node) => node.name)).toEqual(['vision', 'audio']);
    expect(tree[0].project?.name).toBe('Vision');
    expect(tree[0].children[0].name).toBe('seg');
    expect(tree[0].children[0].project?.slug).toBe('vision/seg');
    expect(tree[1].children).toEqual([]);
  });
});

describe('fmtNumber and bestLabel', () => {
  it('rounds to four decimals and uses exponents for very large and very small values', () => {
    expect(fmtNumber(0.123456)).toBe('0.1235');
    expect(fmtNumber(12345)).toBe('1.235e+4');
    expect(fmtNumber(0.0001)).toBe('1.000e-4');
    expect(fmtNumber(null)).toBe('–');
  });

  it('names the primary metric of the best result, or shows a dash', () => {
    expect(
      bestLabel({ best: { run_id: 'r', value: 0.25 }, primary_metric: 'loss' }),
    ).toEqual({ text: '0.25 (loss)', runId: 'r' });
    expect(bestLabel({ best: null, primary_metric: 'loss' })).toEqual({
      text: '–',
      runId: null,
    });
  });
});

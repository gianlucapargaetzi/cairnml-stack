import { layoutGraph } from './layout';

const commit = (sha: string, parents: string[], date: string) => ({
  sha,
  parents,
  message: sha,
  author: 'dev',
  date,
});

describe('layoutGraph', () => {
  it('keeps a linear history in one lane, newest row first', () => {
    const { nodes, edges, laneCount } = layoutGraph(
      [
        commit('c', ['b'], '2026-01-03'),
        commit('b', ['a'], '2026-01-02'),
        commit('a', [], '2026-01-01'),
      ],
      [{ name: 'main', sha: 'c' }],
    );
    expect(nodes.map((n) => [n.sha, n.lane, n.row])).toEqual([
      ['c', 0, 0],
      ['b', 0, 1],
      ['a', 0, 2],
    ]);
    expect(edges).toHaveLength(2);
    expect(laneCount).toBe(1);
    expect(nodes[0].branches).toEqual(['main']);
  });

  it('gives a merged branch its own lane and joins it at the fork', () => {
    // m merges feature (f) into main (b); both come from a.
    const { nodes, laneCount } = layoutGraph(
      [
        commit('m', ['b', 'f'], '2026-01-04'),
        commit('f', ['a'], '2026-01-03'),
        commit('b', ['a'], '2026-01-02'),
        commit('a', [], '2026-01-01'),
      ],
      [],
    );
    const lanes = Object.fromEntries(nodes.map((n) => [n.sha, n.lane]));
    expect(lanes.m).toBe(0);
    expect(lanes.b).toBe(0);
    expect(lanes.f).not.toBe(lanes.b);
    expect(laneCount).toBe(2);
    // A child always sits above its parent.
    const rowOf = Object.fromEntries(nodes.map((n) => [n.sha, n.row]));
    expect(rowOf.m).toBeLessThan(rowOf.b);
    expect(rowOf.f).toBeLessThan(rowOf.a);
  });

  it('ignores parents that are not in the listed history', () => {
    const { edges } = layoutGraph([commit('x', ['outside'], '2026-01-01')], []);
    expect(edges).toEqual([]);
  });
});

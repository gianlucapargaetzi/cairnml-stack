// Pure lane layout for a commit history. No DOM: the node tests cover it directly.

const byDateDesc = (a, b) => Date.parse(b.date) - Date.parse(a.date);

// commits: [{sha, parents, date, ...}] in any order; branches: [{name, sha}].
// Rows run newest first and a child always sits above its parents. A commit takes the lane that
// expects it (else the first free lane); its first parent continues that lane and other parents
// get lanes of their own. Lanes that wait for the same commit merge when that commit is reached.
export function layoutGraph(commits, branches) {
  const known = new Map(commits.map((c) => [c.sha, c]));
  const waiting = new Map(commits.map((c) => [c.sha, 0]));
  for (const c of commits) {
    for (const p of c.parents) if (known.has(p)) waiting.set(p, waiting.get(p) + 1);
  }

  // Topological order, newest first: a commit is emitted only after all of its children.
  const ready = commits.filter((c) => waiting.get(c.sha) === 0).sort(byDateDesc);
  const order = [];
  while (ready.length) {
    const next = ready.shift();
    order.push(next);
    for (const p of next.parents) {
      if (!known.has(p)) continue;
      waiting.set(p, waiting.get(p) - 1);
      if (waiting.get(p) === 0) {
        const parent = known.get(p);
        const at = ready.findIndex((r) => byDateDesc(parent, r) < 0);
        ready.splice(at === -1 ? ready.length : at, 0, parent);
      }
    }
  }

  const heads = new Map();
  for (const b of branches) heads.set(b.sha, [...(heads.get(b.sha) || []), b.name]);

  const lanes = []; // lanes[i] = sha that lane i is waiting for, or null when free
  const nodes = [];
  const place = new Map();
  order.forEach((commit, row) => {
    let lane = lanes.indexOf(commit.sha);
    if (lane === -1) {
      lane = lanes.indexOf(null);
      if (lane === -1) {
        lane = lanes.length;
        lanes.push(null);
      }
    }
    for (let i = 0; i < lanes.length; i++) {
      if (i !== lane && lanes[i] === commit.sha) lanes[i] = null;
    }
    place.set(commit.sha, { lane, row });
    nodes.push({ sha: commit.sha, lane, row, commit, branches: heads.get(commit.sha) || [] });

    const parents = commit.parents.filter((p) => known.has(p));
    lanes[lane] = parents.length ? parents[0] : null;
    for (const p of parents.slice(1)) {
      if (lanes.includes(p)) continue;
      let free = lanes.indexOf(null);
      if (free === -1) {
        free = lanes.length;
        lanes.push(null);
      }
      lanes[free] = p;
    }
  });

  const edges = [];
  for (const node of nodes) {
    for (const p of node.commit.parents) {
      const to = place.get(p);
      if (to) edges.push({ from: node.sha, to: p, fromLane: node.lane, fromRow: node.row, toLane: to.lane, toRow: to.row });
    }
  }
  return { nodes, edges, laneCount: nodes.reduce((max, n) => Math.max(max, n.lane + 1), 0) };
}

import test from "node:test";
import assert from "node:assert/strict";
import { buildProjectTree } from "../src/mlops_server/ui/static/lib.js";
import { layoutGraph } from "../src/mlops_server/ui/static/graph-layout.js";

test("projects are grouped by slug prefix, groups first", () => {
  const tree = buildProjectTree([{ slug: "vision/seg" }, { slug: "nlp/chat" }, { slug: "solo" }, { slug: "vision/depth" }, { slug: "vision" }]);
  assert.deepEqual(tree.map((n) => n.name), ["nlp", "vision", "solo"]);
  const vision = tree.find((n) => n.name === "vision");
  assert.equal(vision.project.slug, "vision");           // a project can also be a group
  assert.deepEqual(vision.children.map((c) => c.name), ["depth", "seg"]);
  assert.equal(tree.find((n) => n.name === "solo").children.length, 0);
});

const c = (sha, parents = [], date = 0) => ({ sha, parents, date: new Date(2026, 0, 1 + date).toISOString() });

test("a linear history uses one lane, newest on top", () => {
  const { nodes, edges, laneCount } = layoutGraph([c("a", ["b"], 3), c("b", ["c"], 2), c("c", [], 1)], []);
  assert.deepEqual(nodes.map((n) => [n.sha, n.lane, n.row]), [["a", 0, 0], ["b", 0, 1], ["c", 0, 2]]);
  assert.equal(laneCount, 1);
  assert.deepEqual(edges.map((e) => [e.from, e.to]), [["a", "b"], ["b", "c"]]);
});

test("a merge opens a second lane and the branch point closes it", () => {
  // m merges main work (x) and feature work (f); both come from root r
  const commits = [c("m", ["x", "f"], 5), c("x", ["r"], 3), c("f", ["r"], 4), c("r", [], 1)];
  const { nodes, laneCount } = layoutGraph(commits, []);
  const by = Object.fromEntries(nodes.map((n) => [n.sha, n]));
  assert.equal(by.m.row, 0);
  assert.equal(by.m.lane, 0);
  assert.equal(by.x.lane, 0);              // first parent continues the lane
  assert.notEqual(by.f.lane, by.x.lane);   // second parent has its own lane
  assert.equal(by.r.lane, 0);              // both lanes end at the root, which sits in the first one
  assert.equal(laneCount, 2);
  assert.ok(by.m.row < by.f.row && by.f.row < by.r.row && by.x.row < by.r.row);
});

test("input order does not matter and children always precede parents", () => {
  const commits = [c("r", [], 1), c("b", ["r"], 3), c("a", ["b"], 4), c("z", ["r"], 2)];
  const { nodes } = layoutGraph(commits, []);
  const row = Object.fromEntries(nodes.map((n) => [n.sha, n.row]));
  assert.ok(row.a < row.b && row.b < row.r && row.z < row.r);
});

test("parents outside the set produce no edge and branch heads are labelled", () => {
  const { nodes, edges } = layoutGraph([c("a", ["missing"], 2), c("b", ["a"], 3)], [{ name: "main", sha: "b" }, { name: "dev", sha: "b" }]);
  assert.deepEqual(edges.map((e) => [e.from, e.to]), [["b", "a"]]);
  assert.deepEqual(nodes.find((n) => n.sha === "b").branches.sort(), ["dev", "main"]);
  assert.deepEqual(nodes.find((n) => n.sha === "a").branches, []);
});

test("two branches from one commit get separate lanes", () => {
  const { nodes } = layoutGraph([c("a", ["r"], 3), c("b", ["r"], 2), c("r", [], 1)], [{ name: "main", sha: "a" }, { name: "dev", sha: "b" }]);
  const by = Object.fromEntries(nodes.map((n) => [n.sha, n]));
  assert.notEqual(by.a.lane, by.b.lane);
  assert.equal(by.r.lane, 0);
});

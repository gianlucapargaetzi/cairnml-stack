import test from "node:test";
import assert from "node:assert/strict";
import { varyingKeys, bestId, sortRows } from "../src/mlops_server/ui/static/lib.js";

const rows = [
  { id: "a", primary_value: 0.5, params: { lr: 0.1, bs: 32, seed: 1 }, created_at: "2026-01-01" },
  { id: "b", primary_value: 0.3, params: { lr: 0.2, bs: 32, seed: 2 }, created_at: "2026-01-02" },
  { id: "c", primary_value: null, params: { lr: 0.3, bs: 32, seed: 3, extra: "x" }, created_at: "2026-01-03" },
];

test("only keys that differ are shown, most varied first", () => {
  assert.deepEqual(varyingKeys(rows), ["lr", "seed", "extra"]);
  assert.deepEqual(varyingKeys(rows, 2), ["lr", "seed"]);
  assert.deepEqual(varyingKeys([rows[0]]), []);
});

test("best respects the direction and ignores missing values", () => {
  assert.equal(bestId(rows, "min"), "b");
  assert.equal(bestId(rows, "max"), "a");
  assert.equal(bestId(rows, undefined), "b");
  assert.equal(bestId([{ id: "x", primary_value: null }], "min"), null);
});

test("sorting by value puts missing values last", () => {
  assert.deepEqual(sortRows(rows, "primary_value", "min").map((r) => r.id), ["b", "a", "c"]);
  assert.deepEqual(sortRows(rows, "primary_value", "max").map((r) => r.id), ["a", "b", "c"]);
  assert.deepEqual(sortRows(rows, "created_at", "desc").map((r) => r.id), ["c", "b", "a"]);
});

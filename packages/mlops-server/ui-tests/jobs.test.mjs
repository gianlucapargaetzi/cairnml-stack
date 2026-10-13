import test from "node:test";
import assert from "node:assert/strict";
import { buildOverrides, jobGroup, parseValue } from "../src/mlops_server/ui/static/lib.js";

test("values are JSON when possible", () => {
  assert.equal(parseValue("0.1"), 0.1);
  assert.equal(parseValue("true"), true);
  assert.equal(parseValue("[1,2]").length, 2);
  assert.equal(parseValue("fast"), "fast");
  assert.equal(parseValue("007"), "007");
  assert.equal(parseValue(""), "");
});

test("jobs are grouped for the three sub-tabs", () => {
  assert.equal(jobGroup("running"), "running");
  assert.equal(jobGroup("queued"), "scheduled");
  assert.equal(jobGroup("assigned"), "scheduled");
  for (const s of ["finished", "failed", "cancelled"]) assert.equal(jobGroup(s), "finished");
});

const original = { name: "train", queue: "default", resources: { cpu: 2, memory_gb: 4, gpu: 0, labels: [] },
                   params: { lr: 0.1, seed: 7 }, env: { A: "1" }, timeout_s: null };

test("an unchanged form produces no overrides", () => {
  assert.deepEqual(buildOverrides(original, structuredClone(original)), {});
});

test("changed scalars, resources and params are sent, removed keys become null", () => {
  const form = structuredClone(original);
  form.name = "train v2"; form.queue = "gpu"; form.resources.gpu = 1; form.timeout_s = 3600;
  form.params = { lr: 0.5, batch: 64 };           // seed removed, lr changed, batch added
  form.env = {};                                    // A removed
  assert.deepEqual(buildOverrides(original, form), {
    name: "train v2", queue: "gpu", resources: { cpu: 2, memory_gb: 4, gpu: 1, labels: [] }, timeout_s: 3600,
    params: { lr: 0.5, seed: null, batch: 64 }, env: { A: null },
  });
});

test("a timeout that is not a number is ignored", () => {
  const form = structuredClone(original);
  form.timeout_s = NaN;
  assert.deepEqual(buildOverrides(original, form), {});
});

test("resource key order does not count as a change", () => {
  const form = structuredClone(original);
  form.resources = { labels: [], gpu: 0, memory_gb: 4, cpu: 2 };
  assert.deepEqual(buildOverrides(original, form), {});
});

import test from "node:test";
import assert from "node:assert/strict";
import { barPercent, usageLabel, queueState } from "../src/mlops_server/ui/static/lib.js";

test("bar percentages are clamped and safe", () => {
  assert.equal(barPercent(4, 8), 50);
  assert.equal(barPercent(9, 8), 100);
  assert.equal(barPercent(-1, 8), 0);
  assert.equal(barPercent(1, 0), 0);
  assert.equal(barPercent(undefined, 8), 0);
  assert.equal(barPercent(1, null), 0);
});

test("labels", () => {
  assert.equal(usageLabel(6, 8, "cpu"), "6 / 8 cpu");
  assert.equal(usageLabel(10.55, 32, "GB"), "10.6 / 32 GB");
  assert.equal(usageLabel(null, 8, "cpu"), "– / 8 cpu");
});

test("queue state tells a stuck queue from a busy one", () => {
  assert.equal(queueState({ queued: 3, agents: 0 }), "stuck");
  assert.equal(queueState({ queued: 3, agents: 2 }), "busy");
  assert.equal(queueState({ queued: 0, agents: 0 }), "idle");
});

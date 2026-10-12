import test from "node:test";
import assert from "node:assert/strict";
import {
  fmtDuration, shortSha, safeHttpsUrl, commitUrl, flatten, diffRows, setDiff, parseHash, statusClass, fmtNumber, colorFor,
} from "../src/mlops_server/ui/static/lib.js";

test("durations", () => {
  assert.equal(fmtDuration(null), "–");
  assert.equal(fmtDuration("2026-01-01T00:00:00Z", "2026-01-01T00:00:42Z"), "42s");
  assert.equal(fmtDuration("2026-01-01T00:00:00Z", "2026-01-01T01:02:03Z"), "1h 2m");
  assert.equal(fmtDuration("2026-01-01T00:00:00Z", null, Date.parse("2026-01-01T00:05:09Z")), "5m 9s");
  assert.equal(fmtDuration("2026-01-01T00:00:00Z", "2026-01-03T05:00:00Z"), "2d 5h");
});

test("short sha and numbers", () => {
  assert.equal(shortSha("0123456789abcdef"), "01234567");
  assert.equal(shortSha(null), "–");
  assert.equal(fmtNumber(0.123456789), "0.1235");
  assert.equal(fmtNumber(123456), "1.235e+5");
  assert.equal(fmtNumber(undefined), "–");
  assert.equal(fmtNumber("text"), "text");
});

test("only https urls become links", () => {
  assert.equal(safeHttpsUrl("javascript:alert(1)"), null);
  assert.equal(safeHttpsUrl("http://example.com/a"), null);
  assert.equal(safeHttpsUrl("not a url"), null);
  assert.equal(safeHttpsUrl("https://github.com/o/r"), "https://github.com/o/r");
  assert.equal(commitUrl({ remote_url: "https://github.com/o/r.git", commit: "abc" }), "https://github.com/o/r/commit/abc");
  assert.equal(commitUrl({ remote_url: "git@github.com:o/r.git", commit: "abc" }), null);
  assert.equal(commitUrl(null), null);
});

test("flatten and diff rows", () => {
  assert.deepEqual(flatten({ a: 1, b: { c: 2, d: [3] } }), { a: 1, "b.c": 2, "b.d": [3] });
  const experiments = [
    { params: { lr: 0.1, args: { epochs: 3 } } },
    { params: { lr: 0.1, args: { epochs: 5 }, extra: "x" } },
  ];
  const rows = diffRows(experiments, (e) => e.params);
  assert.deepEqual(rows.map((r) => [r.key, r.differs]), [["args.epochs", true], ["extra", true], ["lr", false]]);
  assert.deepEqual(rows[1].values, [undefined, "x"]);
});

test("set diff", () => {
  assert.deepEqual(setDiff(["a==1", "b==1"], ["b==1", "c==1"]), { added: ["c==1"], removed: ["a==1"] });
});

test("hash routing", () => {
  assert.deepEqual(parseHash("#/experiments/exp_1"), { parts: ["experiments", "exp_1"], params: {} });
  assert.deepEqual(parseHash("#/compare?ids=a,b"), { parts: ["compare"], params: { ids: "a,b" } });
  assert.deepEqual(parseHash(""), { parts: [], params: {} });
});

test("status classes are safe css class names", () => {
  assert.equal(statusClass("running"), "status status-running");
  assert.equal(statusClass('x" onmouseover="'), "status status-xonmouseover");
  assert.equal(colorFor(0), colorFor(10));
});

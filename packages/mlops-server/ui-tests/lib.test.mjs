import test from "node:test";
import assert from "node:assert/strict";
import {
  fmtDuration, shortSha, safeHttpsUrl, commitUrl, flatten, diffRows, setDiff, parseHash, statusClass, fmtNumber, colorFor,
  createScope, createPageScope, shouldRedirectToLogin, attributeAllowed, linkAllowed, downsample, mergeLogs,
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

test("commit links encode the commit and never carry credentials", () => {
  assert.equal(
    commitUrl({ remote_url: "https://github.com/o/r.git", commit: "a/b?c" }),
    "https://github.com/o/r/commit/a%2Fb%3Fc",
  );
  const withCredentials = commitUrl({ remote_url: "https://user:tok3n@github.com/o/r.git", commit: "abc" });
  assert.equal(withCredentials, "https://github.com/o/r/commit/abc");
  assert.ok(!withCredentials.includes("user") && !withCredentials.includes("tok3n"));
  assert.equal(commitUrl({ remote_url: "http://user:pw@github.com/o/r", commit: "abc" }), null);
});

test("a scope runs cleanups once on dispose and refuses later work", () => {
  const scope = createScope();
  const seen = [];
  scope.onCleanup(() => seen.push("a"));
  scope.onCleanup(() => { throw new Error("boom"); });
  scope.onCleanup(() => seen.push("c"));
  assert.equal(scope.canRun(), true);
  scope.dispose();
  scope.dispose();
  assert.deepEqual(seen, ["a", "c"]);
  assert.equal(scope.canRun(), false);
  assert.equal(scope.disposed, true);
  scope.onCleanup(() => seen.push("late"));
  assert.deepEqual(seen, ["a", "c", "late"]);
});

test("login redirect happens once and never on the login page", () => {
  assert.equal(shouldRedirectToLogin("/ui/", false), true);
  assert.equal(shouldRedirectToLogin("/ui/", true), false);
  assert.equal(shouldRedirectToLogin("/ui/auth/login", false), false);
});

test("dom attributes are an allowlist and links must be safe", () => {
  for (const name of ["class", "id", "title", "type", "name", "value", "checked", "aria-label", "data-run"]) {
    assert.equal(attributeAllowed(name), true, name);
  }
  for (const name of ["style", "srcdoc", "formaction", "onclick", "innerhtml", "xlink:href"]) {
    assert.equal(attributeAllowed(name), false, name);
  }
  assert.equal(linkAllowed("href", "#/experiments/exp_1"), true);
  assert.equal(linkAllowed("href", "https://github.com/o/r"), true);
  assert.equal(linkAllowed("href", "javascript:alert(1)"), false);
  assert.equal(linkAllowed("href", "data:text/html,x"), false);
  assert.equal(linkAllowed("src", "http://example.com/a.js"), false);
  assert.equal(linkAllowed("href", "#/x\" onclick=\"y"), false);
  assert.equal(linkAllowed("class", "anything"), true);
});

test("downsample keeps the first and last point and the order", () => {
  const points = Array.from({ length: 1200 }, (_, i) => [i, i * 2]);
  const small = downsample(points, 500);
  assert.ok(small.length <= 501);
  assert.deepEqual(small[0], [0, 0]);
  assert.deepEqual(small.at(-1), [1199, 2398]);
  for (let i = 1; i < small.length; i++) assert.ok(small[i][0] > small[i - 1][0]);
  assert.deepEqual(downsample([[1, 1], [2, 2]], 500), [[1, 1], [2, 2]]);
});

test("merge logs by time and keep the stream", () => {
  const out = mergeLogs([
    { stream: "stdout", lines: [{ ts: 1, text: "a" }, { ts: 3, text: "c" }] },
    { stream: "stderr", lines: [{ ts: 2, text: "b" }] },
  ]);
  assert.deepEqual(out.map((l) => [l.stream, l.text]), [["stdout", "a"], ["stderr", "b"], ["stdout", "c"]]);
});

test("page scope guards every write made after the route changed", () => {
  const scope = createPageScope();
  const writes = [];
  assert.equal(scope.active(), true);
  assert.equal(scope.run(() => writes.push("first")), 1);
  let cleaned = 0;
  scope.onCleanup(() => { cleaned += 1; });
  scope.dispose();
  scope.dispose();
  assert.equal(scope.active(), false);
  assert.equal(cleaned, 1);
  assert.equal(scope.run(() => writes.push("late")), undefined);
  assert.deepEqual(writes, ["first"]);
  // A cleanup registered after disposal runs at once, so nothing can outlive the page.
  scope.onCleanup(() => { cleaned += 1; });
  assert.equal(cleaned, 2);
});

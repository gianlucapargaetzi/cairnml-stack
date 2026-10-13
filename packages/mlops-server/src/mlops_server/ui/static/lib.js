export const PALETTE = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d", "#475569", "#ea580c"];

export function colorFor(i) {
  return PALETTE[i % PALETTE.length];
}

export function fmtTime(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "–" : d.toLocaleString();
}

export function fmtDuration(startIso, endIso, nowMs = Date.now()) {
  if (!startIso) return "–";
  const start = Date.parse(startIso);
  const end = endIso ? Date.parse(endIso) : nowMs;
  let s = Math.max(0, Math.round((end - start) / 1000));
  const d = Math.floor(s / 86400); s %= 86400;
  const hh = Math.floor(s / 3600); s %= 3600;
  const m = Math.floor(s / 60); s %= 60;
  if (d) return `${d}d ${hh}h`;
  if (hh) return `${hh}h ${m}m`;
  if (m) return `${m}m ${s}s`;
  return `${s}s`;
}

export function shortSha(sha) {
  return sha ? String(sha).slice(0, 8) : "–";
}

export function fmtNumber(v) {
  if (v === null || v === undefined) return "–";
  if (typeof v !== "number") return String(v);
  if (Math.abs(v) >= 1000 || (Math.abs(v) < 0.001 && v !== 0)) return v.toExponential(3);
  return String(Math.round(v * 10000) / 10000);
}

export function safeHttpsUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

export function commitUrl(git) {
  if (!git || !git.remote_url || !git.commit) return null;
  let remote;
  try {
    remote = new URL(String(git.remote_url).replace(/\.git$/, ""));
  } catch {
    return null;
  }
  remote.username = "";
  remote.password = "";
  remote.search = "";
  remote.hash = "";
  const base = safeHttpsUrl(remote.href);
  return base ? `${base}/commit/${encodeURIComponent(git.commit)}` : null;
}

export function flatten(obj, prefix = "", out = {}) {
  for (const [key, value] of Object.entries(obj || {})) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value)) flatten(value, path, out);
    else out[path] = value;
  }
  return out;
}

export function diffRows(experiments, pick) {
  const flat = experiments.map((e) => flatten(pick(e)));
  const keys = [...new Set(flat.flatMap((f) => Object.keys(f)))].sort();
  return keys.map((key) => {
    const values = flat.map((f) => (key in f ? f[key] : undefined));
    const first = JSON.stringify(values[0]);
    return { key, values, differs: values.some((v) => JSON.stringify(v) !== first) };
  });
}

export function setDiff(base, other) {
  const a = new Set(base);
  const b = new Set(other);
  return { added: [...b].filter((x) => !a.has(x)), removed: [...a].filter((x) => !b.has(x)) };
}

export function parseHash(hash) {
  const raw = String(hash || "").replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  return { parts: path.split("/").filter(Boolean), params: Object.fromEntries(new URLSearchParams(query)) };
}

export function statusClass(status) {
  return `status status-${String(status).replace(/[^a-z]/g, "")}`;
}

// A page-scoped lifetime: cleanups run once on dispose, and nothing may start after that.
export function createScope() {
  let disposed = false;
  const cleanups = [];
  return {
    get disposed() {
      return disposed;
    },
    canRun() {
      return !disposed;
    },
    onCleanup(fn) {
      if (disposed) fn();
      else cleanups.push(fn);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      for (const fn of cleanups.splice(0)) {
        try { fn(); } catch { /* one failing cleanup must not block the others */ }
      }
    },
  };
}

// The lifetime a view receives: writes made after a route change are dropped by run(), so a
// slow response can never paint into a page the user has already left.
export function createPageScope() {
  const scope = createScope();
  return Object.assign(scope, {
    active: () => scope.canRun(),
    run(fn) {
      return scope.canRun() ? fn() : undefined;
    },
  });
}

// Statuses after which a run no longer changes, so its detail page can stop polling.
export const TERMINAL_STATUSES = new Set(["finished", "failed", "cancelled"]);

export function shouldRedirectToLogin(pathname, alreadyRedirected) {
  return !alreadyRedirected && pathname !== "/ui/auth/login";
}

const ATTRIBUTES = new Set(["class", "id", "title", "type", "name", "value", "role", "checked", "disabled", "hidden", "open", "placeholder"]);
const LINK_ATTRIBUTES = new Set(["href", "src"]);

// Whether dom.h() may set this attribute. Event handlers are functions and are checked separately.
export function attributeAllowed(name) {
  if (LINK_ATTRIBUTES.has(name)) return true;
  return ATTRIBUTES.has(name) || name.startsWith("aria-") || name.startsWith("data-");
}

// href and src only take a validated https URL or an in-app hash route such as "#/experiments/a".
export function linkAllowed(name, value) {
  if (!LINK_ATTRIBUTES.has(name)) return true;
  const text = String(value);
  if (/^#\/[^\s"'<>]*$/.test(text)) return true;
  return safeHttpsUrl(text) !== null;
}

// Keeps at most about `max` points with an even stride; the first and last point always stay.
export function downsample(points, max) {
  if (points.length <= max) return points;
  const stride = Math.ceil(points.length / max);
  const out = points.filter((_, i) => i % stride === 0);
  const last = points[points.length - 1];
  if (out[out.length - 1] !== last) out.push(last);
  return out;
}

// Interleaves log chunks from several streams by timestamp. Each line keeps its stream.
export function mergeLogs(chunks) {
  return chunks
    .flatMap((chunk) => chunk.lines.map((line) => ({ stream: chunk.stream, ts: line.ts, text: line.text })))
    .sort((a, b) => a.ts - b.ts);
}

// Projects grouped by their slug prefixes ("vision/seg" sits under "vision"). A slug part that is
// both a project and a group keeps both: the node carries the project and the children.
export function buildProjectTree(projects) {
  const root = { children: new Map() };
  for (const project of projects) {
    let node = root;
    const parts = project.slug.split("/");
    parts.forEach((part, index) => {
      if (!node.children.has(part)) node.children.set(part, { name: part, project: null, children: new Map() });
      node = node.children.get(part);
      if (index === parts.length - 1) node.project = project;
    });
  }
  const convert = (node) => [...node.children.values()]
    .map((child) => ({ name: child.name, project: child.project, children: convert(child) }))
    .sort((a, b) => (b.children.length > 0) - (a.children.length > 0) || a.name.localeCompare(b.name));
  return convert(root);
}

// Parameter keys whose values differ between rows, most varied first, ties alphabetical.
// A key missing from a row counts as its own value, so a late-added parameter still shows.
export function varyingKeys(rows, limit = 5) {
  if (rows.length < 2) return [];
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r.params || {})))];
  return keys
    .map((key) => {
      const seen = new Set(rows.map((r) => (r.params && key in r.params ? JSON.stringify(r.params[key]) : "\u0000missing")));
      return { key, count: seen.size };
    })
    .filter((k) => k.count > 1)
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key))
    .slice(0, limit)
    .map((k) => k.key);
}

// The id of the row with the best non-null primary value. "max" picks the largest, anything else the smallest.
export function bestId(rows, direction) {
  const valued = rows.filter((r) => typeof r.primary_value === "number");
  if (!valued.length) return null;
  const better = direction === "max"
    ? (a, b) => (b.primary_value > a.primary_value ? b : a)
    : (a, b) => (b.primary_value < a.primary_value ? b : a);
  return valued.reduce(better).id;
}

// Sorts a copy by one field. "asc" and "min" ascend, anything else descends. Missing values go last in both orders.
export function sortRows(rows, by, direction) {
  const sign = direction === "asc" || direction === "min" ? 1 : -1;
  const missing = (v) => v === null || v === undefined;
  return [...rows].sort((a, b) => {
    const x = a[by];
    const y = b[by];
    if (missing(x)) return missing(y) ? 0 : 1;
    if (missing(y)) return -1;
    return (x < y ? -1 : x > y ? 1 : 0) * sign;
  });
}

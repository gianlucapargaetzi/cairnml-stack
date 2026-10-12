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
  const base = safeHttpsUrl(String(git.remote_url).replace(/\.git$/, ""));
  return base ? `${base}/commit/${git.commit}` : null;
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

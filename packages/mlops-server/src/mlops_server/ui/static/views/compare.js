import { api } from "../api.js";
import { lineChart } from "../charts.js";
import { h } from "../dom.js";
import { statusBadge } from "../components.js";
import { colorFor, diffRows, fmtNumber, setDiff, shortSha } from "../lib.js";

const MAX_COMPARE = 10;

const cell = (value) => (value === undefined || value === null ? "–" : typeof value === "object" ? JSON.stringify(value) : String(value));

export default async function compare(root, route, ctx) {
  // The server takes 2 to 10 distinct ids: duplicates are dropped and the rest is capped.
  const requested = [...new Set((route.params.ids || "").split(",").filter(Boolean))];
  const ids = requested.slice(0, MAX_COMPARE);
  const capHint = requested.length > MAX_COMPARE
    ? h("p", { class: "muted" }, `Only the first ${MAX_COMPARE} of ${requested.length} selected runs are compared.`)
    : null;
  if (ids.length < 2) {
    root.replaceChildren(
      h("h1", {}, "Compare runs"),
      h("p", { class: "muted" }, "Select two or more runs in the list and press “Compare selected”."),
      h("a", { href: "#/runs" }, "Go to runs"));
    return;
  }
  const { runs } = await api.compare(ids);
  // A newer route may have replaced this page while the request was in flight.
  if (!ctx.active()) return;

  const color = (i) => colorFor(i);

  const chips = h("div", { class: "chips" }, runs.map((e, i) => {
    // The swatch colour goes through the CSSOM: the CSP forbids style attributes.
    const swatch = h("span", { class: "swatch" });
    swatch.style.background = color(i);
    return h("span", { class: "chip" },
      swatch,
      h("a", { href: `#/runs/${encodeURIComponent(e.id)}` }, e.name), " ",
      statusBadge(e.status), " ",
      runs.length > 2
        ? h("a", { class: "muted", href: `#/compare?ids=${encodeURIComponent(ids.filter((x) => x !== e.id).join(","))}` }, "remove")
        : null);
  }));

  // Metric charts: one per metric name, one line per run that logged it.
  const names = [...new Set(runs.flatMap((e) => Object.keys(e.metrics)))].sort();
  const chartTargets = [];
  const charts = h("div", { class: "chart-grid" }, names.map((name) => {
    const canvas = h("canvas", { "aria-label": `compare ${name}` });
    chartTargets.push({ name, canvas });
    return h("section", { class: "chart-box" }, h("h3", {}, name), canvas);
  }));

  // The lowest last value is marked, and only when at least two runs logged the metric.
  const best = (name) => {
    const present = runs.filter((e) => e.metrics[name]);
    if (present.length < 2) return null;
    return present.reduce((a, b) => (b.metrics[name].last < a.metrics[name].last ? b : a)).id;
  };
  const metricsTable = names.length
    ? h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Metric"), runs.map((e) => h("th", {}, e.name)))),
      h("tbody", {}, names.map((name) => {
        const winner = best(name);
        return h("tr", {}, h("th", {}, name), runs.map((e) => {
          const m = e.metrics[name];
          return h("td", { class: m && winner === e.id ? "best" : null },
            m ? `${fmtNumber(m.last)} (${fmtNumber(m.min)} – ${fmtNumber(m.max)})` : "–");
        }));
      })))
    : h("p", { class: "muted" }, "None of these runs logged metrics.");

  // Parameters: config and params merged, with an "only differences" filter that is on by default.
  let onlyDiffs = true;
  const paramsBox = h("div");
  function renderParams() {
    const rows = diffRows(runs, (e) => ({ ...e.config, ...e.params })).filter((r) => !onlyDiffs || r.differs);
    paramsBox.replaceChildren(rows.length
      ? h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Parameter"), runs.map((e) => h("th", {}, e.name)))),
        h("tbody", {}, rows.map((r) => h("tr", { class: r.differs ? "differs" : null },
          h("th", {}, r.key),
          r.values.map((v) => h("td", { class: "mono" }, cell(v)))))))
      : h("p", { class: "muted" }, onlyDiffs ? "All parameters are identical." : "No parameters recorded."));
  }
  const toggle = h("label", {},
    h("input", { type: "checkbox", checked: true, onchange: (ev) => { onlyDiffs = ev.target.checked; renderParams(); } }),
    " only differences");
  renderParams();

  // Code and data: git state, script, interpreter, and the DVC hash of each dataset path.
  const codeRows = diffRows(runs, (e) => ({
    repository: e.git && e.git.repo,
    branch: e.git && e.git.branch,
    commit: e.git && shortSha(e.git.commit),
    "uncommitted changes": e.git ? (e.git.dirty ? "yes" : "no") : undefined,
    script: e.script,
    python: e.python_version,
    platform: e.platform,
    ...Object.fromEntries(e.datasets.map((d) => [`data ${d.path}`, d.dvc_hash || "unversioned"])),
  }));
  const codeTable = h("table", {},
    h("thead", {}, h("tr", {}, h("th", {}, ""), runs.map((e) => h("th", {}, e.name)))),
    h("tbody", {}, codeRows.map((r) => h("tr", { class: r.differs ? "differs" : null },
      h("th", {}, r.key),
      r.values.map((v) => h("td", { class: "mono" }, cell(v)))))));

  // Installed packages, each run against the first.
  const base = runs[0];
  const packages = runs.slice(1).map((e) => {
    const diff = setDiff(base.requirements, e.requirements);
    const lines = [...diff.added.map((x) => `+ ${x}`), ...diff.removed.map((x) => `- ${x}`)];
    return h("details", {},
      h("summary", {}, `${e.name} vs ${base.name}: +${diff.added.length} added, −${diff.removed.length} removed`),
      h("pre", { class: "log" }, lines.join("\n") || "identical"));
  });

  root.replaceChildren(
    h("h1", {}, "Compare runs"), capHint, chips,
    h("h2", {}, "Metrics"), charts, metricsTable,
    h("h2", {}, "Parameters"), toggle, paramsBox,
    h("h2", {}, "Code and data"), codeTable, packages);

  // Charts are created after the canvases are attached, and destroyed when the route changes.
  const instances = chartTargets.map(({ name, canvas }) => lineChart(canvas, runs.flatMap((e, i) =>
    e.metrics[name] ? [{ label: e.name, points: e.metrics[name].series, color: color(i) }] : [])));
  ctx.onCleanup(() => instances.forEach((c) => c.destroy()));
}

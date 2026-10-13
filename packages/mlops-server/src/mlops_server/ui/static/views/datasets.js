import { api } from "../api.js";
import { statusBadge, table } from "../components.js";
import { h } from "../dom.js";
import { fmtTime } from "../lib.js";
import { renderMarkdown } from "../markdown.js";

const bytes = (n) => (n === null || n === undefined ? "–" : n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : n >= 1e3 ? `${(n / 1e3).toFixed(1)} kB` : `${n} B`);
const datasetHref = (d) => `#/datasets?project=${encodeURIComponent(d.project)}&repo=${encodeURIComponent(d.repo)}&path=${encodeURIComponent(d.path)}`;

// h() allows a fixed set of attributes, so the selected option is set on the select after it is built.
function select(label, options, value, onChange) {
  const control = h("select", { "aria-label": label, onchange: (e) => onChange(e.target.value) },
    options.map(([v, text]) => h("option", { value: v }, text)));
  control.value = value;
  return h("label", {}, `${label} `, control);
}

export default async function datasets(root, route, ctx) {
  if (route.params.path) return detailPage(root, route.params, ctx);
  const [rows, projects] = await Promise.all([api.datasets(), api.projects()]);
  const state = { project: route.params.project || "", type: "", q: "" };
  const body = h("div");
  const types = [...new Set(rows.map((d) => d.type).filter(Boolean))].sort();

  function render() {
    const q = state.q.toLowerCase();
    const shown = rows.filter((d) => (!state.project || d.project === state.project)
      && (!state.type || d.type === state.type)
      && (!q || d.path.toLowerCase().includes(q) || (d.title || "").toLowerCase().includes(q)));
    body.replaceChildren(table([
      { title: "Dataset", render: (d) => h("a", { href: datasetHref(d) }, d.title ? `${d.path} (${d.title})` : d.path) },
      { title: "Project", render: (d) => d.project },
      { title: "Repository", render: (d) => d.repo },
      { title: "Type", render: (d) => d.type || "–" },
      { title: "License", render: (d) => d.license || "–" },
      { title: "Size", render: (d) => bytes(d.size_bytes) },
      { title: "Files", render: (d) => d.nfiles ?? "–" },
      { title: "Card", render: (d) => (d.has_card ? "yes" : "missing") },
    ], shown, "No datasets found. Link a data repository with `mlops repo link --role data` and add .dvc files."));
  }

  ctx.render(() => root.replaceChildren(
    h("h1", {}, "Datasets"),
    h("p", { class: "muted" }, "Datasets are tracked with DVC in Git. A card is a Markdown file next to the .dvc file."),
    h("div", { class: "toolbar" },
      select("Project", [["", "all"], ...projects.map((p) => [p.slug, p.slug])], state.project,
        (v) => { state.project = v; render(); }),
      select("Type", [["", "any"], ...types.map((t) => [t, t])], state.type,
        (v) => { state.type = v; render(); }),
      h("label", {}, "Search ", h("input", { type: "search", oninput: (e) => { state.q = e.target.value; render(); } }))),
    body));
  render();
}

async function detailPage(root, { project, repo, path }, ctx) {
  const d = await api.datasetDetail(project, repo, path);
  const card = d.card;
  const header = card
    ? [
      h("h1", {}, card.title || path, " ", h("span", { class: "status" }, card.type)),
      h("p", { class: "muted" }, [repo, path, `license ${card.license || "–"}`,
        card.version ? `version ${card.version}` : null,
        card.owners.length ? `owners ${card.owners.join(", ")}` : null].filter(Boolean).join(" · ")),
      card.tags.length ? h("p", {}, card.tags.map((t) => h("span", { class: "status" }, t))) : null,
      card.source ? h("p", {}, `Source: ${card.source}`) : null,
      card.error ? h("p", { class: "error" }, `Card problem: ${card.error}`) : null,
      ...card.warnings.map((w) => h("p", { class: "muted" }, `Note: ${w}`)),
    ]
    : [
      h("h1", {}, path),
      h("p", { class: "muted" }, repo),
      h("div", { class: "hint" },
        h("p", {}, "This dataset has no card yet. Cards live in Git next to the .dvc file. Create one with:"),
        h("pre", { class: "log" }, `mlops dataset card init ${path}`),
        h("p", { class: "muted" }, "Then edit it, commit and push.")),
    ];

  ctx.render(() => root.replaceChildren(
    h("p", {}, h("a", { href: "#/datasets" }, "← all datasets")),
    ...header,
    card && card.body ? h("section", { class: "card-body" }, renderMarkdown(card.body)) : null,
    card && card.columns.length ? [h("h2", {}, "Schema"), table([
      { title: "Column", class: "mono", render: (c) => c.name },
      { title: "Type", render: (c) => c.type || "–" },
      { title: "Description", render: (c) => c.description || "" },
    ], card.columns)] : null,
    card && Object.keys(card.splits).length ? [h("h2", {}, "Splits"), table([
      { title: "Split", render: (r) => r[0] },
      { title: "Rows", render: (r) => r[1] },
    ], Object.entries(card.splits))] : null,
    h("h2", {}, "Contents"),
    h("dl", { class: "kv" },
      h("dt", {}, "DVC hash"), h("dd", { class: "mono" }, d.dvc.dvc_hash || "–"),
      h("dt", {}, "Size"), h("dd", {}, bytes(d.dvc.size_bytes ?? (card && card.size_bytes))),
      h("dt", {}, "Files"), h("dd", {}, d.dvc.nfiles ?? "–"),
      h("dt", {}, "Rows"), h("dd", {}, card && card.rows !== null ? card.rows : "–")),
    h("h2", {}, "Versions"),
    table([
      { title: "Commit", class: "mono", render: (v) => (v.commit || "").slice(0, 8) || "–" },
      { title: "Date", render: (v) => fmtTime(v.date) },
      { title: "Change", render: (v) => v.message },
      { title: "DVC hash", class: "mono", render: (v) => (v.dvc_hash && v.dvc_hash === d.dvc.dvc_hash ? `${v.dvc_hash} (current)` : v.dvc_hash || "–") },
    ], d.versions, "No history found."),
    h("h2", {}, `Used by ${d.used_by.count} run(s)`),
    table([
      { title: "Run", render: (e) => h("a", { href: `#/runs/${encodeURIComponent(e.id)}` }, e.name) },
      { title: "Experiment", render: (e) => e.experiment },
      { title: "Status", render: (e) => statusBadge(e.status) },
      { title: "Created", render: (e) => fmtTime(e.created_at) },
    ], d.used_by.runs, "Not used by any run yet."),
  ));
}

import { h } from "./dom.js";
import { fmtDuration, fmtNumber, fmtTime, shortSha, statusClass } from "./lib.js";

export const statusBadge = (status) => h("span", { class: statusClass(status) }, status);

export function card(title, value, href) {
  const body = [h("div", { class: "card-value" }, value), h("div", { class: "card-title" }, title)];
  return href ? h("a", { class: "card", href }, body) : h("div", { class: "card" }, body);
}

export function table(columns, rows, empty = "Nothing here yet.") {
  if (!rows.length) return h("p", { class: "muted" }, empty);
  return h("table", {},
    h("thead", {}, h("tr", {}, columns.map((c) => h("th", {}, c.title)))),
    h("tbody", {}, rows.map((row) => h("tr", {}, columns.map((c) => h("td", { class: c.class }, c.render(row)))))));
}

// The best run of a experiment (see experiment_stats on the server) as "value metric" linked to it.
export function bestCell(experiment) {
  const best = experiment.best;
  if (!best) return h("span", {}, "–");
  return h("a", { href: `#/runs/${encodeURIComponent(best.run_id)}` },
    `${fmtNumber(best.value)} (${experiment.primary_metric})`);
}

export function runColumns({ selected, onToggle } = {}) {
  const columns = [];
  if (selected) {
    columns.push({
      title: "", render: (e) => h("input", {
        type: "checkbox", "aria-label": `select ${e.name}`, checked: selected.has(e.id),
        onchange: (ev) => onToggle(e.id, ev.target.checked),
      }),
    });
  }
  columns.push(
    { title: "Name", render: (e) => h("a", { href: `#/runs/${encodeURIComponent(e.id)}` }, e.name) },
    { title: "Project", render: (e) => e.project },
    { title: "Status", render: (e) => statusBadge(e.status) },
    { title: "Experiment", render: (e) => e.experiment },
    { title: "Owner", render: (e) => e.owner },
    { title: "Source", render: (e) => e.source },
    { title: "Started", render: (e) => fmtTime(e.started_at || e.created_at) },
    { title: "Duration", render: (e) => fmtDuration(e.started_at, e.finished_at) },
    { title: "Commit", class: "mono", render: (e) => shortSha(e.git && e.git.commit) + (e.git && e.git.dirty ? " +changes" : "") },
  );
  return columns;
}

export function jobColumns() {
  return [
    { title: "Job", class: "mono", render: (j) => j.id },
    { title: "Run", render: (j) => h("a", { href: `#/runs/${encodeURIComponent(j.run_id)}` }, j.run_name) },
    { title: "Project", render: (j) => j.project },
    { title: "Status", render: (j) => statusBadge(j.status) },
    { title: "Queue", render: (j) => j.queue },
    { title: "Agent", render: (j) => j.agent_name || "–" },
    { title: "Resources", render: (j) => `${j.cpu} cpu · ${j.memory_gb} GB${j.gpu ? ` · ${j.gpu} gpu` : ""}` },
    { title: "Created", render: (j) => fmtTime(j.created_at) },
    { title: "Duration", render: (j) => fmtDuration(j.assigned_at, j.finished_at) },
    { title: "Result", render: (j) => (j.message || (j.exit_code === null ? "" : `exit ${j.exit_code}`)) },
  ];
}

export function keyValues(obj) {
  const entries = Object.entries(obj || {});
  if (!entries.length) return h("p", { class: "muted" }, "None");
  return h("dl", { class: "kv" }, entries.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, typeof v === "object" ? JSON.stringify(v) : String(v))]));
}

// A line that reports a failed refresh. It sits outside the part a poll redraws, so the last
// good content stays on screen under it.
export function refreshError() {
  const el = h("p", { class: "error", role: "alert" });
  return {
    el,
    show(error) { el.replaceChildren(`Could not refresh, showing the last data: ${error.message}`); },
    clear() { el.replaceChildren(); },
  };
}

import { h } from "./dom.js";
import { fmtDuration, fmtTime, shortSha, statusClass } from "./lib.js";

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

export function experimentColumns({ selected, onToggle } = {}) {
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
    { title: "Name", render: (e) => h("a", { href: `#/experiments/${encodeURIComponent(e.id)}` }, e.name) },
    { title: "Project", render: (e) => e.project },
    { title: "Status", render: (e) => statusBadge(e.status) },
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
    { title: "Experiment", render: (j) => h("a", { href: `#/experiments/${encodeURIComponent(j.experiment_id)}` }, j.experiment_name) },
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

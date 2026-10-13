import { api } from "../api.js";
import { card, runColumns, refreshError, table } from "../components.js";
import { h } from "../dom.js";
import { fmtTime } from "../lib.js";

export default async function overview(root, route, ctx) {
  const status = refreshError();
  const body = h("div");
  async function render() {
    const o = await api.overview();
    const jobs = o.jobs || {};
    ctx.render(() => body.replaceChildren(
      h("div", { class: "cards" },
        card("Running jobs", jobs.running || 0, "#/jobs?status=running"),
        card("Queued jobs", jobs.queued || 0, "#/jobs?status=queued"),
        card("Running runs", o.runs_running, "#/runs?status=running"),
        card("Agents online", `${o.agents.online} / ${o.agents.total}`, "#/resources")),
      h("h2", {}, "Projects"),
      table([
        { title: "Project", render: (p) => h("a", { href: `#/runs?project=${encodeURIComponent(p.slug)}` }, p.slug) },
        { title: "Runs", render: (p) => p.runs },
        { title: "Running", render: (p) => p.running },
        { title: "Last activity", render: (p) => fmtTime(p.last_activity) },
      ], o.projects, "You are not a member of any project yet. Ask an administrator."),
      h("h2", {}, "Recent runs"),
      table(runColumns(), o.recent, "No runs yet.")));
    status.clear();
  }
  ctx.render(() => root.replaceChildren(h("h1", {}, "Overview"), status.el, body));
  await render();
  ctx.poll(render, 5000, status.show);
}

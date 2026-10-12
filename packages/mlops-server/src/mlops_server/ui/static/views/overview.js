import { api } from "../api.js";
import { card, experimentColumns, table } from "../components.js";
import { h } from "../dom.js";
import { fmtTime } from "../lib.js";

export default async function overview(root, route, ctx) {
  async function render() {
    const o = await api.overview();
    const jobs = o.jobs || {};
    root.replaceChildren(
      h("h1", {}, "Overview"),
      h("div", { class: "cards" },
        card("Running jobs", jobs.running || 0, "#/jobs?status=running"),
        card("Queued jobs", jobs.queued || 0, "#/jobs?status=queued"),
        card("Running experiments", o.experiments_running, "#/experiments?status=running"),
        card("Agents online", `${o.agents.online} / ${o.agents.total}`, "#/agents")),
      h("h2", {}, "Projects"),
      table([
        { title: "Project", render: (p) => h("a", { href: `#/experiments?project=${encodeURIComponent(p.slug)}` }, p.slug) },
        { title: "Experiments", render: (p) => p.experiments },
        { title: "Running", render: (p) => p.running },
        { title: "Last activity", render: (p) => fmtTime(p.last_activity) },
      ], o.projects, "You are not a member of any project yet. Ask an administrator."),
      h("h2", {}, "Recent experiments"),
      table(experimentColumns(), o.recent, "No experiments yet."));
  }
  await render();
  ctx.poll(render, 5000);
}

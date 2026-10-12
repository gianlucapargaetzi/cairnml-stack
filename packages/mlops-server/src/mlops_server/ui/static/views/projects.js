import { api } from "../api.js";
import { table } from "../components.js";
import { h } from "../dom.js";
import { fmtTime } from "../lib.js";

export default async function projects(root, route, ctx) {
  const o = await api.overview();
  ctx.render(() => root.replaceChildren(
    h("h1", {}, "Projects"),
    table([
      { title: "Slug", render: (p) => h("a", { href: `#/experiments?project=${encodeURIComponent(p.slug)}` }, p.slug) },
      { title: "Name", render: (p) => p.name },
      { title: "Experiments", render: (p) => p.experiments },
      { title: "Running", render: (p) => p.running },
      { title: "Last activity", render: (p) => fmtTime(p.last_activity) },
    ], o.projects, "You are not a member of any project yet.")));
}

import { api } from "../api.js";
import { jobColumns, refreshError, table } from "../components.js";
import { h } from "../dom.js";

const STATUSES = ["", "running", "queued", "assigned", "finished", "failed", "cancelled"];

export default async function jobs(root, route, ctx) {
  let status = route.params.status || "";
  const body = h("div");
  const notice = refreshError();
  async function render() {
    const rows = await api.jobs({ status, limit: 200 });
    ctx.render(() => body.replaceChildren(table(jobColumns(), rows, "No jobs match.")));
    notice.clear();
  }
  const select = h("select", {
    "aria-label": "status filter",
    onchange: (e) => { status = e.target.value; render().catch(notice.show); },
  }, STATUSES.map((s) => h("option", { value: s }, s || "all")));
  select.value = status;
  ctx.render(() => root.replaceChildren(h("h1", {}, "Jobs"), h("label", {}, "Status ", select), notice.el, body));
  await render();
  ctx.poll(render, 5000, notice.show);
}

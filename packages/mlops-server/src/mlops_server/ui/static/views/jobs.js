import { api } from "../api.js";
import { jobColumns, table } from "../components.js";
import { h } from "../dom.js";

const STATUSES = ["", "running", "queued", "assigned", "finished", "failed", "cancelled"];

export default async function jobs(root, route, ctx) {
  let status = route.params.status || "";
  const body = h("div");
  const showError = (error) => body.replaceChildren(h("p", { class: "error" }, `Could not load jobs: ${error.message}`));
  async function render() {
    try {
      const rows = await api.jobs({ status, limit: 200 });
      body.replaceChildren(table(jobColumns(), rows, "No jobs match."));
    } catch (error) {
      showError(error);
    }
  }
  const select = h("select", {
    "aria-label": "status filter",
    onchange: (e) => { status = e.target.value; render(); },
  }, STATUSES.map((s) => h("option", { value: s }, s || "all")));
  select.value = status;
  root.replaceChildren(h("h1", {}, "Jobs"), h("label", {}, "Status ", select), body);
  await render();
  ctx.poll(render, 5000);
}

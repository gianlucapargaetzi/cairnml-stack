import { api } from "../api.js";
import { experimentColumns, table } from "../components.js";
import { h } from "../dom.js";

const PAGE = 50;
const MIN_COMPARE = 2;
const MAX_COMPARE = 10;
const STATUSES = ["", "running", "queued", "created", "finished", "failed", "cancelled"];
const SORTS = [["created_at:desc", "newest first"], ["created_at:asc", "oldest first"], ["name:asc", "name A-Z"], ["status:asc", "status"]];

export default async function experiments(root, route, ctx) {
  if (route.parts[1]) {
    const detail = await import("./experiment.js");
    return detail.default(root, route, ctx);
  }

  const state = {
    project: route.params.project || "",
    status: route.params.status || "",
    q: route.params.q || "",
    sort: "created_at",
    order: "desc",
    offset: 0,
  };
  const selected = new Set();
  const body = h("div");
  let renderSeq = 0;

  const compareButton = h("button", {
    type: "button", disabled: true,
    onclick: () => { window.location.hash = `#/compare?ids=${encodeURIComponent([...selected].join(","))}`; },
  }, "Compare selected");

  function updateCompare() {
    const count = selected.size;
    compareButton.disabled = count < MIN_COMPARE || count > MAX_COMPARE;
    compareButton.textContent = count ? `Compare selected (${count})` : "Compare selected";
  }

  async function render() {
    const mine = ++renderSeq;
    const { json: rows, total } = await api.experiments({ ...state, limit: PAGE });
    if (mine !== renderSeq || !ctx.active()) return;
    const columns = experimentColumns({
      selected,
      onToggle: (id, on) => {
        if (on) selected.add(id); else selected.delete(id);
        updateCompare();
      },
    });
    const first = total ? state.offset + 1 : 0;
    const last = Math.min(total, state.offset + PAGE);
    const pager = h("div", { class: "pager" },
      h("button", {
        type: "button", disabled: state.offset === 0,
        onclick: () => { state.offset = Math.max(0, state.offset - PAGE); render(); },
      }, "Previous"),
      h("span", { class: "muted" }, ` ${first}-${last} of ${total} `),
      h("button", {
        type: "button", disabled: state.offset + PAGE >= total,
        onclick: () => { state.offset += PAGE; render(); },
      }, "Next"));
    body.replaceChildren(table(columns, rows, "No experiments match."), pager);
  }

  // h() allowlists attributes, so the selected option is set on the property instead.
  const projectOptions = (await api.projects()).map((p) => p.slug);
  if (state.project && !projectOptions.includes(state.project)) projectOptions.push(state.project);
  const projectSelect = h("select", {
    "aria-label": "project filter",
    onchange: (e) => { state.project = e.target.value; state.offset = 0; render(); },
  }, ["", ...projectOptions].map((p) => h("option", { value: p }, p || "all projects")));
  projectSelect.value = state.project;

  const statusSelect = h("select", {
    "aria-label": "status filter",
    onchange: (e) => { state.status = e.target.value; state.offset = 0; render(); },
  }, STATUSES.map((s) => h("option", { value: s }, s || "any status")));
  statusSelect.value = state.status;

  const search = h("input", {
    type: "search", placeholder: "name contains...", "aria-label": "name search", value: state.q,
    oninput: (e) => { state.q = e.target.value; state.offset = 0; render(); },
  });

  const sortSelect = h("select", {
    "aria-label": "sort",
    onchange: (e) => {
      const [sort, order] = e.target.value.split(":");
      Object.assign(state, { sort, order, offset: 0 });
      render();
    },
  }, SORTS.map(([value, label]) => h("option", { value }, label)));

  const control = (label, el) => h("label", { class: "control" }, label, " ", el);
  root.replaceChildren(
    h("h1", {}, "Experiments"),
    h("div", { class: "toolbar" },
      control("Project", projectSelect),
      control("Status", statusSelect),
      control("Search", search),
      control("Sort", sortSelect),
      compareButton),
    body);
  updateCompare();
  await render();
  ctx.poll(render, 5000);
}

import { api, writes } from "../api.js";
import { lineChart } from "../charts.js";
import { refreshError, table } from "../components.js";
import { h } from "../dom.js";
import { bestId, colorFor, fmtDuration, fmtNumber, fmtTime, shortSha, sortRows, varyingKeys } from "../lib.js";

const KINDS = ["training", "data-preparation", "augmentation", "evaluation", "testing", "compilation", "inference", "other"];
const DIRECTIONS = ["min", "max"];
const MAX_COMPARE = 10;
const TOP = 3;

// The summary carries no membership flag, so the form is shown to everyone. The server answers
// 404 to a non-member and 403 to a read-only session; both are reported in the form.
function explainSaveError(error) {
  if (error.status === 404) return "Could not save: only members of this project can change its task.";
  if (error.status === 403) return `Could not save: this session may not change the task (${error.message}).`;
  return `Could not save: ${error.message}`;
}

const paramText = (value) => (typeof value === "object" && value !== null ? JSON.stringify(value) : String(value));

export default async function taskPage(root, route, ctx) {
  const id = route.params.id;
  if (!id) {
    root.replaceChildren(h("p", { class: "error" }, "No task was given. Open a task from its project."));
    return;
  }
  let summary = await api.taskSummary(id);
  const selected = new Set();
  let sortBy = "created_at";
  let sortDir = "desc";
  let chart = null;
  const notice = refreshError();
  const header = h("div");
  const body = h("div");

  ctx.onCleanup(() => {
    if (chart) chart.destroy();
    chart = null;
  });

  function renderHeader() {
    const { task } = summary;
    header.replaceChildren(
      h("h1", {}, task.name, " ", h("span", { class: "status" }, task.kind)),
      h("p", { class: "muted" },
        h("a", { href: `#/projects?project=${encodeURIComponent(task.project)}` }, task.project),
        task.description ? ` · ${task.description}` : ""));
  }

  function renderBody() {
    const { task, stats } = summary;
    if (chart) {
      chart.destroy();
      chart = null;
    }
    const rows = sortRows(summary.experiments, sortBy, sortDir);
    const best = bestId(rows, task.direction);
    const keys = varyingKeys(rows);
    const valued = rows.filter((r) => r.primary_value !== null && r.primary_value !== undefined);
    const direction = task.direction || "min";

    const compareSelected = h("button", {
      type: "button",
      disabled: selected.size < 2 || selected.size > MAX_COMPARE,
      onclick: () => { window.location.hash = `#/compare?ids=${encodeURIComponent([...selected].join(","))}`; },
    }, selected.size ? `Compare selected (${selected.size})` : "Compare selected");

    const compareTop = h("button", {
      type: "button",
      disabled: valued.length < 2,
      onclick: () => {
        const ids = sortRows(valued, "primary_value", direction).slice(0, TOP).map((r) => r.id);
        window.location.hash = `#/compare?ids=${encodeURIComponent(ids.join(","))}`;
      },
    }, `Compare top ${Math.min(TOP, valued.length)}`);

    const sortSelect = h("select", {
      "aria-label": "sort experiments",
      onchange: (event) => {
        [sortBy, sortDir] = event.target.value.split(":");
        renderBody();
      },
    }, [
      ["created_at:desc", "newest first"],
      ["created_at:asc", "oldest first"],
      [`primary_value:${direction}`, "best first"],
    ].map(([value, label]) => h("option", { value }, label)));
    sortSelect.value = `${sortBy}:${sortDir}`;

    const columns = [
      {
        title: "",
        render: (r) => h("input", {
          type: "checkbox",
          "aria-label": `select ${r.name}`,
          checked: selected.has(r.id),
          onchange: (event) => {
            if (event.target.checked) selected.add(r.id); else selected.delete(r.id);
            renderBody();
          },
        }),
      },
      { title: "Experiment", render: (r) => h("a", { href: `#/experiments/${encodeURIComponent(r.id)}` }, r.name) },
      { title: "Status", render: (r) => h("span", { class: `status status-${String(r.status).replace(/[^a-z]/g, "")}` }, r.status) },
      {
        title: task.primary_metric || "Primary value",
        class: "num",
        render: (r) => h("span", { class: r.id === best ? "best" : null }, fmtNumber(r.primary_value)),
      },
      ...keys.map((key) => ({
        title: key,
        render: (r) => (r.params && key in r.params ? paramText(r.params[key]) : "–"),
      })),
      { title: "Started", render: (r) => fmtTime(r.started_at || r.created_at) },
      { title: "Duration", render: (r) => fmtDuration(r.started_at, r.finished_at) },
      { title: "Commit", class: "mono", render: (r) => shortSha(r.commit) + (r.dirty ? " +changes" : "") },
    ];

    const hasValues = valued.length > 0;
    body.replaceChildren(
      h("div", { class: "cards" },
        h("div", { class: "card" },
          h("div", { class: "card-value" }, stats.best ? fmtNumber(stats.best.value) : "–"),
          h("div", { class: "card-title" }, stats.best
            ? h("span", {},
              `best ${task.primary_metric} (${direction}) · `,
              h("a", { href: `#/experiments/${encodeURIComponent(stats.best.experiment_id)}` }, stats.best.name))
            : "Set a primary metric to see the best result")),
        h("div", { class: "card" },
          h("div", { class: "card-value" }, stats.experiments),
          h("div", { class: "card-title" }, `experiments (${stats.running} running)`))),
      h("h2", {}, "Experiments"),
      h("div", { class: "toolbar" }, h("label", {}, "Sort ", sortSelect), compareSelected, compareTop),
      table(columns, rows, "No experiments in this task yet."),
      hasValues
        ? h("section", { class: "chart-box" },
          h("h3", {}, `${task.primary_metric} by experiment`),
          h("canvas", { "aria-label": "primary metric chart" }))
        : null);

    const canvas = body.querySelector("canvas");
    if (canvas) {
      const points = [...summary.experiments].reverse()
        .map((r, i) => [i + 1, r.primary_value])
        .filter(([, v]) => v !== null && v !== undefined);
      chart = lineChart(canvas, [{ label: task.primary_metric, points, color: colorFor(0) }]);
    }
  }

  function renderAll() {
    renderHeader();
    renderBody();
  }

  function settingsForm() {
    const { task } = summary;
    const message = h("p", { class: "muted", role: "status" });
    const kind = h("select", { "aria-label": "kind" }, KINDS.map((k) => h("option", { value: k }, k)));
    kind.value = task.kind;
    const description = h("textarea", { "aria-label": "description" }, task.description || "");
    const metric = h("input", { "aria-label": "primary metric", value: task.primary_metric || "", placeholder: "e.g. val_loss" });
    const direction = h("select", { "aria-label": "direction" }, DIRECTIONS.map((d) => h("option", { value: d }, d)));
    direction.value = task.direction || "min";

    const form = h("form", {
      onsubmit: async (event) => {
        event.preventDefault();
        message.textContent = "Saving…";
        try {
          await writes.patchTask(id, {
            kind: kind.value,
            description: description.value || null,
            primary_metric: metric.value || null,
            direction: metric.value ? direction.value : null,
          });
        } catch (error) {
          message.textContent = explainSaveError(error);
          return;
        }
        message.textContent = "Saved.";
        try {
          const fresh = await api.taskSummary(id);
          if (!ctx.active()) return;
          summary = fresh;
          renderAll();
        } catch (error) {
          message.textContent = `Saved, but the page could not refresh: ${error.message}`;
        }
      },
    },
    h("label", {}, "Kind ", kind),
    h("label", {}, "Description ", description),
    h("label", {}, "Primary metric ", metric),
    h("label", {}, "Better is ", direction),
    h("div", {}, h("button", { type: "submit" }, "Save")),
    message);
    return h("details", { class: "task-settings" }, h("summary", {}, "Settings"), form);
  }

  root.replaceChildren(header, settingsForm(), notice.el, body);
  renderAll();
  ctx.poll(async () => {
    summary = await api.taskSummary(id);
    notice.clear();
    renderBody();
  }, 10000, (error) => notice.show(error));
}

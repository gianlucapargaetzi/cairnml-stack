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
  if (error.status === 404) return "Could not save: only members of this project can change its experiment.";
  if (error.status === 403) return `Could not save: this session may not change the experiment (${error.message}).`;
  return `Could not save: ${error.message}`;
}

const paramText = (value) => (typeof value === "object" && value !== null ? JSON.stringify(value) : String(value));

export default async function experimentPage(root, route, ctx) {
  const id = route.params.id;
  if (!id) {
    root.replaceChildren(h("p", { class: "error" }, "No experiment was given. Open a experiment from its project."));
    return;
  }
  let summary = await api.experimentSummary(id);
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
    const { experiment } = summary;
    header.replaceChildren(
      h("h1", {}, experiment.name, " ", h("span", { class: "status" }, experiment.kind)),
      h("p", { class: "muted" },
        h("a", { href: `#/projects?project=${encodeURIComponent(experiment.project)}` }, experiment.project),
        experiment.description ? ` · ${experiment.description}` : ""));
  }

  function renderBody() {
    const { experiment, stats } = summary;
    if (chart) {
      chart.destroy();
      chart = null;
    }
    const rows = sortRows(summary.runs, sortBy, sortDir);
    const best = bestId(rows, experiment.direction);
    const keys = varyingKeys(rows);
    const valued = rows.filter((r) => r.primary_value !== null && r.primary_value !== undefined);
    const direction = experiment.direction || "min";

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
      "aria-label": "sort runs",
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
      { title: "Run", render: (r) => h("a", { href: `#/runs/${encodeURIComponent(r.id)}` }, r.name) },
      { title: "Status", render: (r) => h("span", { class: `status status-${String(r.status).replace(/[^a-z]/g, "")}` }, r.status) },
      {
        title: experiment.primary_metric || "Primary value",
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
              `best ${experiment.primary_metric} (${direction}) · `,
              h("a", { href: `#/runs/${encodeURIComponent(stats.best.run_id)}` }, stats.best.name))
            : "Set a primary metric to see the best result")),
        h("div", { class: "card" },
          h("div", { class: "card-value" }, stats.runs),
          h("div", { class: "card-title" }, `runs (${stats.running} running)`))),
      h("h2", {}, "Runs"),
      h("div", { class: "toolbar" }, h("label", {}, "Sort ", sortSelect), compareSelected, compareTop),
      table(columns, rows, "No runs in this experiment yet."),
      hasValues
        ? h("section", { class: "chart-box" },
          h("h3", {}, `${experiment.primary_metric} by run`),
          h("canvas", { "aria-label": "primary metric chart" }))
        : null);

    const canvas = body.querySelector("canvas");
    if (canvas) {
      const points = [...summary.runs].reverse()
        .map((r, i) => [i + 1, r.primary_value])
        .filter(([, v]) => v !== null && v !== undefined);
      chart = lineChart(canvas, [{ label: experiment.primary_metric, points, color: colorFor(0) }]);
    }
  }

  function renderAll() {
    renderHeader();
    renderBody();
  }

  function settingsForm() {
    const { experiment } = summary;
    const message = h("p", { class: "muted", role: "status" });
    const kind = h("select", { "aria-label": "kind" }, KINDS.map((k) => h("option", { value: k }, k)));
    kind.value = experiment.kind;
    const description = h("textarea", { "aria-label": "description" }, experiment.description || "");
    const metric = h("input", { "aria-label": "primary metric", value: experiment.primary_metric || "", placeholder: "e.g. val_loss" });
    const direction = h("select", { "aria-label": "direction" }, DIRECTIONS.map((d) => h("option", { value: d }, d)));
    direction.value = experiment.direction || "min";

    const form = h("form", {
      onsubmit: async (event) => {
        event.preventDefault();
        message.textContent = "Saving…";
        try {
          await writes.patchExperiment(id, {
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
          const fresh = await api.experimentSummary(id);
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
    return h("details", { class: "experiment-settings" }, h("summary", {}, "Settings"), form);
  }

  root.replaceChildren(header, settingsForm(), notice.el, body);
  renderAll();
  ctx.poll(async () => {
    summary = await api.experimentSummary(id);
    notice.clear();
    renderBody();
  }, 10000, (error) => notice.show(error));
}

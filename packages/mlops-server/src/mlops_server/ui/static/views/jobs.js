import { api, writes } from "../api.js";
import { refreshError, statusBadge, table } from "../components.js";
import { h } from "../dom.js";
import { buildOverrides, fmtDuration, fmtTime, jobGroup, parseValue, shortSha } from "../lib.js";

const GROUPS = [["running", "Running"], ["scheduled", "Scheduled"], ["finished", "Finished"]];
const FINISHED_LIMIT = 100;
const ROW_LIMIT = 200;

// Each status is fetched on its own, so active jobs never fall out of a window of recent rows.
const FETCHES = [
  { status: "running", limit: ROW_LIMIT },
  { status: "queued", limit: ROW_LIMIT },
  { status: "assigned", limit: ROW_LIMIT },
  { status: "finished", limit: FINISHED_LIMIT },
  { status: "failed", limit: FINISHED_LIMIT },
  { status: "cancelled", limit: FINISHED_LIMIT },
];

// A parameter value as text. A string that would not read back as itself is shown quoted.
function paramText(value) {
  if (typeof value === "string") {
    return JSON.stringify(parseValue(value)) === JSON.stringify(value) ? value : JSON.stringify(value);
  }
  return JSON.stringify(value);
}

const resultText = (job) => job.message || (job.exit_code === null || job.exit_code === undefined ? "" : `exit ${job.exit_code}`);

function runtimeText(runtime) {
  if (runtime.type === "python") return `python ${runtime.python}`;
  if (runtime.type === "image") return `image ${runtime.image}`;
  return `compose ${runtime.file} / ${runtime.service}`;
}

// Key and value rows for the parameter and environment editors. Empty keys are dropped. A duplicate key is an error.
function pairEditor(label, entries, parse) {
  const rows = new Set();
  const box = h("div", { class: "pairs" });
  const add = (key = "", text = "") => {
    const entry = {
      k: h("input", { value: key, placeholder: "key", "aria-label": `${label} key` }),
      v: h("input", { value: text, placeholder: "value", "aria-label": `${label} value` }),
    };
    const row = h("div", { class: "pair" }, entry.k, entry.v, h("button", {
      type: "button", onclick: () => { rows.delete(entry); row.remove(); },
    }, "Remove"));
    rows.add(entry);
    box.append(row);
  };
  for (const [key, value] of entries) add(key, parse ? paramText(value) : String(value));
  const read = () => {
    const out = {};
    for (const { k, v } of rows) {
      const key = k.value.trim();
      if (key === "") continue;
      if (key in out) throw new Error(`${label} "${key}" is listed twice`);
      out[key] = parse ? parseValue(v.value) : v.value;
    }
    return out;
  };
  const el = h("div", { class: "pair-editor" }, box, h("button", { type: "button", onclick: () => add() }, `Add ${label}`));
  return { el, read };
}

// Detail rows that come from the job spec. They are shown once the spec has loaded.
function specRows(spec) {
  const runtime = spec.runtime;
  return [
    h("dt", {}, "Code"), h("dd", { class: "mono" }, spec.code
      ? `${spec.code.repo} @ ${shortSha(spec.code.commit)}${spec.code.patch_key ? " + local changes" : ""}`
      : "none (input files only)"),
    h("dt", {}, "Runtime"), h("dd", { class: "mono" }, runtimeText(runtime)),
    h("dt", {}, "Command"), h("dd", { class: "mono" }, runtime.command ? runtime.command.join(" ") : "–"),
    h("dt", {}, "Datasets"), h("dd", {}, spec.data.length
      ? spec.data.map((d) => `${d.path}${d.dvc_hash ? ` (${d.dvc_hash})` : ""}`).join(", ")
      : "none"),
  ];
}

export default async function jobs(root, route, ctx) {
  const state = {
    group: route.params.status ? jobGroup(route.params.status) : "running",
    project: "",
    rows: [],
    selected: null,
    spec: null, // { id, value } for the selected job. A spec never changes, so it is fetched once.
    banner: null,
  };
  let editing = false; // while the reschedule form is open, polls do not redraw the detail panel
  const projects = (await api.projects()).map((p) => p.slug);
  const tabs = h("div", { class: "subtabs", role: "tablist" });
  const list = h("div");
  const panel = h("div", { class: "job-panel" });
  const notice = refreshError();

  async function specOf(id) {
    if (state.spec && state.spec.id === id) return state.spec.value;
    const value = await api.jobSpec(id);
    state.spec = { id, value };
    return value;
  }

  async function refresh() {
    const batches = await Promise.all(FETCHES.map((f) => api.jobs({ ...f, project: state.project })));
    const rows = batches.flat().sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    ctx.render(() => {
      state.rows = rows;
      renderList();
      if (state.selected && !editing) paintDetail();
    });
    notice.clear();
  }

  function renderList() {
    const counts = Object.fromEntries(GROUPS.map(([g]) => [g, state.rows.filter((j) => jobGroup(j.status) === g).length]));
    tabs.replaceChildren(...GROUPS.map(([g, label]) => h("button", {
      type: "button", role: "tab", class: g === state.group ? "active" : null,
      "aria-selected": String(g === state.group),
      onclick: () => { state.group = g; state.banner = null; renderList(); },
    }, `${label} (${counts[g]})`)));
    const shown = state.rows.filter((j) => jobGroup(j.status) === state.group);
    const limited = state.group === "finished" ? shown.slice(0, FINISHED_LIMIT) : shown;
    const empty = state.group === "running" ? "Nothing is running."
      : state.group === "scheduled" ? "No scheduled jobs." : "No finished jobs.";
    list.replaceChildren(
      state.banner,
      table([
        { title: "Job", render: (j) => h("button", { type: "button", class: "linkish", onclick: () => showDetail(j.id) }, j.run_name) },
        { title: "Experiment", render: (j) => j.experiment },
        { title: "Project", render: (j) => j.project },
        { title: "Status", render: (j) => statusBadge(j.status) },
        { title: "Queue", render: (j) => j.queue },
        { title: "Agent", render: (j) => j.agent_name || "–" },
        { title: "Resources", render: (j) => `${j.cpu} cpu · ${j.memory_gb} GB${j.gpu ? ` · ${j.gpu} gpu` : ""}` },
        { title: "Created", render: (j) => fmtTime(j.created_at) },
        { title: state.group === "finished" ? "Took" : "Elapsed", render: (j) => fmtDuration(j.assigned_at, j.finished_at) },
        { title: "Result", render: (j) => resultText(j) },
        { title: "", render: (j) => h("span", { class: "actions" },
          ["queued", "assigned", "running"].includes(j.status)
            ? (j.cancel_requested
              ? h("span", { class: "muted" }, "cancelling…")
              : h("button", { type: "button", onclick: () => cancel(j) }, "Cancel"))
            : null,
          h("button", { type: "button", onclick: () => openEditor(j.id) }, "Copy and reschedule")) },
      ], limited, empty));
  }

  async function cancel(job) {
    if (!window.confirm(`Cancel the job for "${job.run_name}"?`)) return;
    try {
      await writes.cancelJob(job.id);
      state.banner = h("p", { class: "muted", role: "status" }, `Cancel requested for ${job.id}.`);
    } catch (error) {
      state.banner = h("p", { class: "error", role: "alert" }, `Could not cancel: ${error.message}`);
    }
    await refresh().catch(notice.show);
  }

  // Redraws the detail panel from the job row and the cached spec.
  function paintDetail() {
    if (editing) return;
    const job = state.rows.find((j) => j.id === state.selected);
    if (!job) { panel.replaceChildren(); return; }
    const spec = state.spec && state.spec.id === job.id ? state.spec.value : null;
    panel.replaceChildren(
      h("h2", {}, job.run_name, " ", statusBadge(job.status)),
      h("dl", { class: "kv" },
        h("dt", {}, "Job"), h("dd", { class: "mono" }, job.id),
        h("dt", {}, "Run"), h("dd", {}, h("a", { href: `#/runs/${encodeURIComponent(job.run_id)}` }, "open (metrics and logs)")),
        h("dt", {}, "Experiment / project"), h("dd", {}, `${job.experiment} / ${job.project}`),
        h("dt", {}, "State"), h("dd", {}, job.cancel_requested ? `${job.status}, cancelling` : job.status),
        h("dt", {}, "Queue / agent"), h("dd", {}, `${job.queue} / ${job.agent_name || "not assigned"}`),
        h("dt", {}, "Created"), h("dd", {}, fmtTime(job.created_at)),
        h("dt", {}, "Started on agent"), h("dd", {}, fmtTime(job.assigned_at)),
        h("dt", {}, "Finished"), h("dd", {}, fmtTime(job.finished_at)),
        h("dt", {}, "Result"), h("dd", {}, resultText(job) || "–"),
        spec ? specRows(spec) : [h("dt", {}, "Spec"), h("dd", { class: "muted" }, "Loading…")]),
      spec ? h("h3", {}, "Parameters") : null,
      spec ? (Object.keys(spec.params).length
        ? h("dl", { class: "kv" }, Object.entries(spec.params).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, paramText(v))]))
        : h("p", { class: "muted" }, "None")) : null);
  }

  async function showDetail(id) {
    editing = false;
    state.selected = id;
    paintDetail();
    try {
      await specOf(id);
      ctx.render(() => paintDetail());
    } catch (error) {
      ctx.render(() => panel.replaceChildren(h("p", { class: "error", role: "alert" }, `Could not load the job: ${error.message}`)));
    }
  }

  async function openEditor(id) {
    let spec;
    try {
      spec = await specOf(id);
    } catch (error) {
      state.banner = h("p", { class: "error", role: "alert" }, `Could not open the copy: ${error.message}`);
      ctx.render(() => renderList());
      return;
    }
    ctx.render(() => buildEditor(id, spec));
  }

  function buildEditor(id, spec) {
    editing = true;
    state.selected = id;
    const original = {
      name: spec.name, queue: spec.queue, resources: spec.resources, params: spec.params, env: spec.env,
      timeout_s: spec.timeout_s ?? null,
    };
    const field = (label, input) => h("label", { class: "control" }, label, " ", input);
    const numberInput = (value, label, min, step) => {
      const input = h("input", { type: "number", value, "aria-label": label });
      input.min = String(min); // min and step are set as properties, since h() does not allowlist them
      if (step) input.step = step;
      return input;
    };
    const name = h("input", { value: spec.name, "aria-label": "name" });
    const queue = h("input", { value: spec.queue, "aria-label": "queue" });
    const cpu = numberInput(spec.resources.cpu, "cpu", 1);
    const memory = numberInput(spec.resources.memory_gb, "memory GB", 0.1, "any");
    const gpu = numberInput(spec.resources.gpu, "gpu", 0);
    const labels = h("input", { value: spec.resources.labels.join(", "), "aria-label": "labels" });
    const timeout = numberInput(spec.timeout_s ?? "", "timeout seconds", 60);
    timeout.placeholder = "none";
    const params = pairEditor("parameter", Object.entries(spec.params), true);
    // The server stores environment values as strings, so they are not parsed.
    const env = pairEditor("env", Object.entries(spec.env), false);
    const feedback = h("p", { class: "muted", role: "status" });
    const submitButton = h("button", { type: "submit" }, "Dispatch copy");

    async function submit(event) {
      event.preventDefault();
      feedback.className = "muted";
      let overrides;
      try {
        overrides = buildOverrides(original, {
          name: name.value, queue: queue.value,
          resources: {
            cpu: Number(cpu.value), memory_gb: Number(memory.value), gpu: Number(gpu.value),
            labels: labels.value.split(",").map((s) => s.trim()).filter(Boolean),
          },
          params: params.read(), env: env.read(),
          // An empty timeout keeps the original one. The server cannot clear a timeout.
          timeout_s: timeout.value === "" ? NaN : Number(timeout.value),
        });
      } catch (error) {
        feedback.className = "error";
        feedback.textContent = `Could not queue the copy: ${error.message}`;
        return;
      }
      submitButton.disabled = true;
      feedback.textContent = "Queueing…";
      let created;
      try {
        created = await writes.rescheduleJob(id, overrides);
      } catch (error) {
        submitButton.disabled = false;
        feedback.className = "error";
        feedback.textContent = `Could not queue the copy: ${error.message}`;
        return;
      }
      // The copy is queued. A failed refresh from here must not look like a failed dispatch.
      editing = false;
      state.group = "scheduled";
      state.banner = h("p", { class: "muted", role: "status" }, "Queued job ", h("span", { class: "mono" }, created.id), " (",
        h("a", { href: `#/runs/${encodeURIComponent(created.run_id)}` }, "run"), ").");
      refresh().catch(notice.show);
      showDetail(created.id);
    }

    panel.replaceChildren(
      h("h2", {}, "Copy and reschedule"),
      h("p", { class: "muted" }, `Copies "${spec.name}" with the same code, data and runtime. Change what you need, then dispatch the copy.`),
      h("form", { class: "editor", onsubmit: submit },
        field("Name", name), field("Queue", queue), field("CPU", cpu), field("Memory (GB)", memory), field("GPU", gpu),
        field("Labels", labels), field("Timeout (s)", timeout),
        h("h3", {}, "Parameters"), params.el,
        h("h3", {}, "Environment"), env.el,
        h("div", { class: "toolbar" }, submitButton,
          h("button", { type: "button", onclick: () => { editing = false; panel.replaceChildren(); } }, "Cancel")),
        feedback));
  }

  root.replaceChildren(
    h("h1", {}, "Jobs"),
    h("div", { class: "toolbar" },
      h("label", { class: "control" }, "Project", " ",
        h("select", {
          "aria-label": "project",
          onchange: (e) => { state.project = e.target.value; refresh().catch(notice.show); },
        }, ["", ...projects].map((p) => h("option", { value: p }, p || "all")))),
      tabs),
    notice.el,
    h("div", { class: "split" }, list, panel));
  renderList();
  await refresh();
  ctx.poll(refresh, 5000, notice.show);
}

import { api, writes } from "../api.js";
import { keyValues, refreshError, statusBadge, table } from "../components.js";
import { lineChart } from "../charts.js";
import { h } from "../dom.js";
import { TERMINAL_STATUSES, colorFor, commitUrl, dispatchBody, downsample, fmtDuration, fmtNumber, fmtTime, mergeLogs, shortSha } from "../lib.js";

const MAX_LOG_LINES = 2000;
const MAX_CHART_POINTS = 500;
const POLL_MS = 3000;

// Presigned download links may be http for local object stores, never another scheme.
function downloadable(url) {
  try {
    const { protocol } = new URL(url);
    return protocol === "https:" || protocol === "http:" ? url : null;
  } catch {
    return null;
  }
}

// The fields the configuration, code, data and environment sections are drawn from.
function detailKey(exp) {
  return JSON.stringify([exp.config, exp.params, exp.git, exp.datasets, exp.requirements,
    exp.argv, exp.env, exp.python_version, exp.platform, exp.script]);
}

export default async function experiment(root, route, ctx) {
  const id = decodeURIComponent(route.parts[1]);
  let exp = await api.experiment(id);
  if (!ctx.active()) return;

  const notice = refreshError();
  const header = h("div");
  const charts = h("div", { class: "chart-grid" });
  const logBox = h("pre", { class: "log", "aria-label": "logs" });
  const sections = h("div");
  const artifacts = h("div");
  const dispatchBox = h("div");

  // Metrics: the first load fetches every point; later loads fetch only points after sinceId.
  // Each series keeps all its points, and its chart is updated in place.
  let sinceId = null;
  const series = new Map();
  let placeholder = null;

  // Logs: one cursor per stream, and one fetch at a time so overlapping polls cannot append twice.
  const lastSeq = { stdout: -1, stderr: -1 };
  let logsBusy = false;
  let lines = [];

  let detailsKey = null;

  ctx.onCleanup(() => {
    for (const entry of series.values()) entry.chart.destroy();
    series.clear();
  });

  // Dispatch schedules this experiment as a job on an agent, like `mlops dispatch`. The form is built
  // once, so the polls do not reset what the user typed.
  function renderDispatch() {
    const queue = h("input", { value: "default", "aria-label": "queue" });
    const cpu = h("input", { type: "number", "aria-label": "cpu" });
    const memory = h("input", { type: "number", "aria-label": "memory GB" });
    const gpu = h("input", { type: "number", "aria-label": "gpu" });
    cpu.min = "0"; memory.min = "0"; memory.step = "any"; gpu.min = "0"; // set as properties, like jobs.js
    const labels = h("input", { "aria-label": "labels", placeholder: "comma separated" });
    const feedback = h("p", { class: "muted", role: "status" });
    const submit = h("button", { type: "submit" }, "Dispatch as job");

    async function onsubmit(event) {
      event.preventDefault();
      let body;
      try {
        body = dispatchBody({
          queue: queue.value, cpu: cpu.value, memory_gb: memory.value, gpu: gpu.value, labels: labels.value,
        });
      } catch (error) {
        feedback.className = "error";
        feedback.textContent = `Could not dispatch: ${error.message}`;
        return;
      }
      submit.disabled = true;
      feedback.className = "muted";
      feedback.textContent = "Queueing…";
      try {
        const job = await writes.dispatchExperiment(id, body);
        feedback.replaceChildren("Queued job ", h("span", { class: "mono" }, job.id), ". Follow it in the ",
          h("a", { href: "#/jobs" }, "Jobs tab"), ".");
      } catch (error) {
        feedback.className = "error";
        feedback.textContent = `Could not dispatch: ${error.message}`;
      }
      submit.disabled = false;
    }

    dispatchBox.replaceChildren(h("form", { class: "editor", onsubmit },
      h("label", {}, "Queue ", queue), " ",
      h("label", {}, "CPU ", cpu), " ",
      h("label", {}, "Memory GB ", memory), " ",
      h("label", {}, "GPU ", gpu), " ",
      h("label", {}, "Labels ", labels), " ",
      submit), feedback);
  }

  function renderHeader() {
    ctx.render(() => header.replaceChildren(
      h("h1", {}, exp.name, " ", statusBadge(exp.status)),
      h("p", { class: "muted" },
        `${exp.project} · ${exp.owner} · ${exp.source} · started ${fmtTime(exp.started_at || exp.created_at)} · ${fmtDuration(exp.started_at, exp.finished_at)}`),
      exp.notes ? h("p", {}, exp.notes) : null));
  }

  function renderDetails() {
    const git = exp.git;
    const link = commitUrl(git);
    let commitCell = shortSha(git && git.commit);
    if (link) {
      // The remote URL is never shown: it can carry credentials. Only the commit link uses it.
      const anchor = h("a", { href: link }, shortSha(git.commit));
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      commitCell = anchor;
    }
    const code = git
      ? h("dl", { class: "kv" },
        h("dt", {}, "Repository"), h("dd", {}, git.repo || "–"),
        h("dt", {}, "Branch"), h("dd", {}, git.branch || "–"),
        h("dt", {}, "Commit"), h("dd", { class: "mono" }, commitCell),
        h("dt", {}, "Uncommitted changes"),
        h("dd", {}, git.dirty ? `yes (patch ${git.patch_key ? git.patch_key.split("/").pop() : "not stored"})` : "no"),
        h("dt", {}, "Script"), h("dd", { class: "mono" }, `${exp.script || "–"} (in ${git.cwd || "."})`))
      : h("p", { class: "muted" }, `Not in a git repository. Script: ${exp.script || "–"}`);
    ctx.render(() => sections.replaceChildren(
      h("h2", {}, "Configuration"), keyValues({ ...exp.config, ...exp.params }),
      h("h2", {}, "Code"), code,
      h("h2", {}, "Data"),
      table([
        { title: "Path", class: "mono", render: (d) => d.path },
        { title: "DVC hash", class: "mono", render: (d) => d.dvc_hash || "–" },
        { title: "Repo", render: (d) => d.repo || "–" },
        { title: "Commit", class: "mono", render: (d) => shortSha(d.commit) },
      ], exp.datasets, "No datasets recorded."),
      h("h2", {}, "Environment"),
      keyValues({ python: exp.python_version, platform: exp.platform, arguments: (exp.argv || []).join(" "), ...exp.env }),
      h("details", {},
        h("summary", {}, `Installed packages (${exp.requirements.length})`),
        h("pre", { class: "log" }, exp.requirements.join("\n")))));
    detailsKey = detailKey(exp);
  }

  async function renderMetrics() {
    const incremental = sinceId !== null;
    const data = await api.metrics(id, incremental ? sinceId : undefined);
    ctx.render(() => {
      let maxId = sinceId ?? 0;
      for (const name of Object.keys(data).sort()) {
        const fresh = data[name];
        if (!fresh.length) continue;
        let entry = series.get(name);
        if (!entry) {
          const last = h("span", { class: "muted" });
          const canvas = h("canvas", { "aria-label": `chart ${name}` });
          if (placeholder) { placeholder.remove(); placeholder = null; }
          charts.append(h("section", { class: "chart-box" }, h("h3", {}, name, " ", last), canvas));
          entry = { points: [], canvas, last, chart: null, color: colorFor(series.size) };
          series.set(name, entry);
        }
        let disordered = false;
        for (const p of fresh) {
          const x = p.step ?? entry.points.length + 1;
          if (entry.points.length && x < entry.points.at(-1)[0]) disordered = true;
          entry.points.push([x, p.value]);
          maxId = Math.max(maxId, p.id);
        }
        if (disordered) entry.points.sort((a, b) => a[0] - b[0]);
        const shown = downsample(entry.points, MAX_CHART_POINTS);
        if (!entry.chart) {
          entry.chart = lineChart(entry.canvas, [{ label: name, points: shown, color: entry.color }]);
        } else {
          entry.chart.data.datasets[0].data = shown.map(([x, y]) => ({ x, y }));
          entry.chart.update("none");
        }
        entry.last.textContent = `last ${fmtNumber(entry.points.at(-1)[1])}`;
      }
      sinceId = maxId;
      if (!series.size && !placeholder) {
        placeholder = h("p", { class: "muted" }, "No metrics yet.");
        charts.append(placeholder);
      }
    });
  }

  async function renderLogs() {
    if (logsBusy) return;
    logsBusy = true;
    try {
      const fresh = [];
      for (const stream of ["stdout", "stderr"]) {
        fresh.push(...await api.logs(id, stream, lastSeq[stream]));
      }
      ctx.render(() => {
        for (const chunk of fresh) lastSeq[chunk.stream] = Math.max(lastSeq[chunk.stream], chunk.seq);
        if (!fresh.length && lines.length) return;
        lines = lines.concat(mergeLogs(fresh)).sort((a, b) => a.ts - b.ts).slice(-MAX_LOG_LINES);
        const stick = logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 20;
        logBox.replaceChildren(...lines.map((l) => h("div", { class: l.stream === "stderr" ? "stderr" : null }, l.text)));
        if (!lines.length) logBox.append(h("span", { class: "muted" }, "No output yet."));
        if (stick) logBox.scrollTop = logBox.scrollHeight;
      });
    } finally {
      logsBusy = false;
    }
  }

  function downloadButton(artifact) {
    const status = h("span", { class: "error", role: "alert" });
    const button = h("button", { type: "button" }, "Download");
    button.addEventListener("click", async () => {
      status.replaceChildren();
      try {
        const { url } = await api.artifactUrl(id, artifact.id);
        const safe = downloadable(url);
        if (!safe) throw new Error("the download link has an unsupported scheme");
        window.open(safe, "_blank", "noopener");
      } catch (error) {
        status.replaceChildren(`Download failed: ${error.message}`);
      }
    });
    return h("span", {}, button, " ", status);
  }

  async function renderArtifacts() {
    const rows = await api.artifacts(id);
    ctx.render(() => artifacts.replaceChildren(table([
      { title: "Name", render: (a) => a.name },
      { title: "Kind", render: (a) => a.kind },
      { title: "Size", render: (a) => `${a.size} B` },
      { title: "", render: (a) => downloadButton(a) },
    ], rows, "No artifacts.")));
  }

  renderHeader();
  renderDetails();
  ctx.render(() => root.replaceChildren(
    notice.el,
    header,
    h("h2", {}, "Run on an agent"), dispatchBox,
    h("h2", {}, "Metrics"), charts,
    h("h2", {}, "Logs"), logBox,
    sections,
    h("h2", {}, "Artifacts"), artifacts));
  renderDispatch();
  await Promise.all([renderMetrics(), renderLogs(), renderArtifacts()]);

  // Once the run is finished the poll keeps its timer but makes no requests.
  let finished = TERMINAL_STATUSES.has(exp.status);
  ctx.poll(async () => {
    if (finished) return;
    const next = await api.experiment(id);
    if (!ctx.active()) return;
    exp = next;
    renderHeader();
    // Details are redrawn only when their data changed, so an open "Installed packages" stays open.
    if (detailKey(exp) !== detailsKey) renderDetails();
    await Promise.all([renderMetrics(), renderLogs(), renderArtifacts()]);
    finished = TERMINAL_STATUSES.has(exp.status);
    notice.clear();
  }, POLL_MS, notice.show);
}

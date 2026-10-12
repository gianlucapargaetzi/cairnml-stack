import { api } from "../api.js";
import { keyValues, statusBadge, table } from "../components.js";
import { lineChart } from "../charts.js";
import { h } from "../dom.js";
import { colorFor, commitUrl, downsample, fmtDuration, fmtNumber, fmtTime, mergeLogs, shortSha } from "../lib.js";

const LIVE = new Set(["running", "queued"]);
const MAX_LOG_LINES = 2000;
const MAX_CHART_POINTS = 500;

// Presigned download links may be http for local object stores, never another scheme.
function downloadable(url) {
  try {
    const { protocol } = new URL(url);
    return protocol === "https:" || protocol === "http:" ? url : null;
  } catch {
    return null;
  }
}

export default async function experiment(root, route, ctx) {
  const id = decodeURIComponent(route.parts[1]);
  let exp = await api.experiment(id);

  const header = h("div");
  const charts = h("div", { class: "chart-grid" });
  const logBox = h("pre", { class: "log", "aria-label": "logs" });
  const artifacts = h("div");
  const lastSeq = { stdout: -1, stderr: -1 };
  let lines = [];
  let chartInstances = [];
  ctx.onCleanup(() => {
    chartInstances.forEach((c) => c.destroy());
    chartInstances = [];
  });

  function renderHeader() {
    header.replaceChildren(
      h("h1", {}, exp.name, " ", statusBadge(exp.status)),
      h("p", { class: "muted" },
        `${exp.project} · ${exp.owner} · ${exp.source} · started ${fmtTime(exp.started_at || exp.created_at)} · ${fmtDuration(exp.started_at, exp.finished_at)}`),
      exp.notes ? h("p", {}, exp.notes) : null);
  }

  async function renderMetrics() {
    const metrics = await api.metrics(id);
    if (!ctx.active()) return;
    chartInstances.forEach((c) => c.destroy());
    chartInstances = [];
    charts.replaceChildren();
    const names = Object.keys(metrics).sort();
    if (!names.length) {
      charts.append(h("p", { class: "muted" }, "No metrics yet."));
      return;
    }
    names.forEach((name, i) => {
      const series = metrics[name];
      if (!series.length) return;
      const points = downsample(series.map((p, n) => [p.step ?? n + 1, p.value]), MAX_CHART_POINTS);
      const canvas = h("canvas", { "aria-label": `chart ${name}` });
      charts.append(h("section", { class: "chart-box" },
        h("h3", {}, name, " ", h("span", { class: "muted" }, `last ${fmtNumber(points.at(-1)[1])}`)),
        canvas));
      chartInstances.push(lineChart(canvas, [{ label: name, points, color: colorFor(i) }]));
    });
  }

  async function renderLogs() {
    const fresh = [];
    for (const stream of ["stdout", "stderr"]) {
      const chunks = await api.logs(id, stream, lastSeq[stream]);
      for (const chunk of chunks) {
        lastSeq[stream] = Math.max(lastSeq[stream], chunk.seq);
        fresh.push(chunk);
      }
    }
    if (!ctx.active()) return;
    if (!fresh.length && lines.length) return;
    lines = lines.concat(mergeLogs(fresh)).sort((a, b) => a.ts - b.ts).slice(-MAX_LOG_LINES);
    const stick = logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 20;
    logBox.replaceChildren(...lines.map((l) => h("div", { class: l.stream === "stderr" ? "stderr" : null }, l.text)));
    if (!lines.length) logBox.append(h("span", { class: "muted" }, "No output yet."));
    if (stick) logBox.scrollTop = logBox.scrollHeight;
  }

  function downloadButton(artifact) {
    const status = h("span", { class: "error", role: "alert" });
    const button = h("button", { type: "button" }, "Download");
    button.addEventListener("click", async () => {
      status.textContent = "";
      try {
        const { url } = await api.artifactUrl(id, artifact.id);
        const safe = downloadable(url);
        if (!safe) throw new Error("the download link has an unsupported scheme");
        window.open(safe, "_blank", "noopener");
      } catch (error) {
        status.textContent = `Download failed: ${error.message}`;
      }
    });
    return h("span", {}, button, " ", status);
  }

  async function renderArtifacts() {
    const rows = await api.artifacts(id);
    if (!ctx.active()) return;
    artifacts.replaceChildren(table([
      { title: "Name", render: (a) => a.name },
      { title: "Kind", render: (a) => a.kind },
      { title: "Size", render: (a) => `${a.size} B` },
      { title: "", render: (a) => downloadButton(a) },
    ], rows, "No artifacts."));
  }

  const git = exp.git;
  const link = commitUrl(git);
  let commitCell = shortSha(git && git.commit);
  if (link) {
    // The repository's remote URL is never shown: it can carry credentials. Only the commit link is built from it.
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

  root.replaceChildren(
    header,
    h("h2", {}, "Metrics"), charts,
    h("h2", {}, "Logs"), logBox,
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
      h("pre", { class: "log" }, exp.requirements.join("\n"))),
    h("h2", {}, "Artifacts"), artifacts);

  renderHeader();
  await Promise.all([renderMetrics(), renderLogs(), renderArtifacts()]);

  let wasLive = LIVE.has(exp.status);
  ctx.poll(async () => {
    const next = await api.experiment(id);
    if (!ctx.active()) return;
    exp = next;
    renderHeader();
    const live = LIVE.has(exp.status);
    // Refresh once more after the run ends, so the last output and metrics are shown.
    if (live || wasLive) await Promise.all([renderMetrics(), renderLogs(), renderArtifacts()]);
    wasLive = live;
  }, 3000);
}

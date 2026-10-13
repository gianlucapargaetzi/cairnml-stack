import { api } from "../api.js";
import { refreshError, table } from "../components.js";
import { h } from "../dom.js";
import { barPercent, fmtDuration, fmtTime, queueState, usageLabel } from "../lib.js";

// One bar. The width is set through the CSSOM, never a style attribute, so the CSP stays strict.
function bar(label, used, total, unit, kind) {
  const fill = h("div", { class: `fill ${kind}` });
  fill.style.width = `${barPercent(used, total)}%`;
  return h("div", { class: "meter" },
    h("div", { class: "meter-label" }, `${label}: ${usageLabel(used, total, unit)}`),
    h("div", { class: "track" }, fill));
}

function capabilityText(caps) {
  const gpus = caps.gpus
    ? ` · ${caps.gpus} gpu${caps.gpu_models.length ? ` (${[...new Set(caps.gpu_models)].join(", ")})` : ""}`
    : "";
  return `${caps.cpu} cpu · ${caps.memory_gb} GB memory${gpus}`;
}

function agentCard(agent) {
  const caps = agent.capabilities;
  const free = agent.free;
  const usage = agent.usage;
  const sampled = agent.usage_at ? `sampled ${fmtDuration(agent.usage_at, null)} ago` : null;
  const labels = caps.labels.length ? ` · labels: ${caps.labels.join(", ")}` : "";
  const docker = caps.docker ? "" : " · no docker";
  return h("section", { class: "agent-card" },
    h("h2", {},
      h("span", { class: `dot ${agent.online ? "on" : "off"}`, role: "img", "aria-label": agent.online ? "online" : "offline" }),
      ` ${agent.name} `,
      h("span", { class: "muted" }, agent.online ? "online" : `offline, last seen ${fmtTime(agent.last_seen)}`)),
    h("p", { class: "muted" },
      `queues: ${agent.queues.join(", ") || "none"} · runtimes: ${caps.runtimes.join(", ") || "none"}${labels}${docker}`),
    h("p", {}, capabilityText(caps)),
    h("h3", {}, "Allocated to jobs"),
    bar("CPU", caps.cpu - free.cpu, caps.cpu, "cpu", "allocated"),
    bar("Memory", caps.memory_gb - free.memory_gb, caps.memory_gb, "GB", "allocated"),
    caps.gpus ? bar("GPU", caps.gpus - free.gpu, caps.gpus, "gpu", "allocated") : null,
    h("h3", {}, "Actually in use", sampled ? h("span", { class: "muted" }, ` (${sampled})`) : null),
    usage
      ? [
        bar("CPU", usage.cpu_percent, 100, "%", "actual"),
        bar("Memory", usage.mem_used_gb, usage.mem_total_gb, "GB", "actual"),
        usage.gpus.map((g) => [
          bar(`GPU ${g.index} compute`, g.util_percent, 100, "%", "actual"),
          bar(`GPU ${g.index} memory`, g.mem_used_gb, g.mem_total_gb, "GB", "actual"),
        ]),
      ]
      : h("p", { class: "muted" }, "No usage reported yet."),
    h("h3", {}, "Running jobs"),
    agent.running_jobs.length
      ? h("ul", {}, agent.running_jobs.map((j) =>
        h("li", {}, h("a", { href: "#/jobs" }, j.run_name), ` (${j.project})`)))
      : h("p", { class: "muted" }, "Idle."),
    agent.other_running_jobs ? h("p", { class: "muted" }, `${agent.other_running_jobs} more in projects you are not in.`) : null);
}

const STATE_LABEL = { stuck: "stuck: no online agent serves this queue", busy: "busy", idle: "idle" };
const STATE_CLASS = { stuck: "failed", busy: "running", idle: "finished" };

function queueWait(seconds) {
  return seconds === null || seconds === undefined ? "–" : fmtDuration(new Date(Date.now() - seconds * 1000).toISOString(), null);
}

export default async function resources(root, route, ctx) {
  const notice = refreshError();
  const content = h("div", { class: "resources" });
  root.replaceChildren(h("h1", {}, "Resources"), notice.el, content);

  async function refresh() {
    const { agents, queues } = await api.resources();
    notice.clear();
    content.replaceChildren(
      agents.length
        ? h("div", { class: "agent-grid" }, agents.map(agentCard))
        : h("p", { class: "muted" }, "No agents are registered. An administrator creates a token with `mlops admin agent-token` and starts an agent."),
      h("h2", {}, "Queues"),
      table([
        { title: "Queue", render: (q) => q.name },
        { title: "Queued", render: (q) => q.queued },
        { title: "Running", render: (q) => q.running },
        { title: "Serving agents", render: (q) => q.agents },
        { title: "Oldest wait", render: (q) => queueWait(q.oldest_wait_s) },
        {
          title: "State",
          render: (q) => {
            const state = queueState(q);
            return h("span", { class: `status status-${STATE_CLASS[state]}` }, STATE_LABEL[state]);
          },
        },
      ], queues, "No queues yet."));
  }

  await refresh().catch(notice.show);
  ctx.poll(refresh, 5000, notice.show);
}

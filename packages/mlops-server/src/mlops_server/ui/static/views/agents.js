import { api } from "../api.js";
import { table } from "../components.js";
import { h } from "../dom.js";
import { fmtTime } from "../lib.js";

export default async function agents(root, route, ctx) {
  async function render() {
    const rows = await api.agentsStatus();
    root.replaceChildren(
      h("h1", {}, "Agents"),
      table([
        { title: "Agent", render: (a) => a.name },
        { title: "State", render: (a) => h("span", { class: `status status-${a.online ? "running" : "failed"}` }, a.online ? "online" : "offline") },
        { title: "Queues", render: (a) => a.queues.join(", ") },
        { title: "Capacity", render: (a) => `${a.capabilities.cpu} cpu · ${a.capabilities.memory_gb} GB · ${a.capabilities.gpus} gpu` },
        { title: "Free", render: (a) => `${a.free.cpu} cpu · ${a.free.memory_gb} GB · ${a.free.gpu} gpu` },
        { title: "Runtimes", render: (a) => (a.capabilities.runtimes || []).join(", ") },
        { title: "Running", render: (a) => a.running_jobs.map((j) => `${j.experiment_name} (${j.project})`).join(", ") || "–" },
        { title: "Last seen", render: (a) => fmtTime(a.last_seen) },
      ], rows, "No agents are enrolled."));
  }
  await render();
  ctx.poll(render, 5000);
}

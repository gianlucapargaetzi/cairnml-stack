import { api } from "../api.js";
import { table } from "../components.js";
import { h } from "../dom.js";
import { fmtTime } from "../lib.js";

export default async function admin(root, route, ctx) {
  let users, agents, clients;
  try {
    [users, agents, clients] = await Promise.all([api.adminUsers(), api.adminAgents(), api.adminClients()]);
  } catch (error) {
    if (error.status === 403) { ctx.render(() => root.replaceChildren(h("p", {}, "Administrators only."))); return; }
    throw error;
  }
  ctx.render(() => root.replaceChildren(
    h("h1", {}, "Administration"),
    h("p", { class: "muted" }, "Read-only view. Use the mlops CLI to revoke clients or agents and to create agent tokens."),
    h("h2", {}, "Users"),
    table([
      { title: "User", render: (u) => u.username },
      { title: "Roles", render: (u) => u.roles.join(", ") || "–" },
      { title: "Status", render: (u) => h("span", { class: `status status-${u.disabled ? "failed" : "finished"}` }, u.disabled ? "disabled" : "active") },
      { title: "Active client keys", render: (u) => u.clients_active },
    ], users),
    h("h2", {}, "Agents"),
    table([
      { title: "Id", class: "mono", render: (a) => a.id },
      { title: "Name", render: (a) => a.name },
      { title: "Queues", render: (a) => a.queues.join(", ") },
      { title: "State", render: (a) => (a.revoked ? "revoked" : "active") },
      { title: "Last seen", render: (a) => fmtTime(a.last_seen) },
    ], agents),
    h("h2", {}, "Client keys"),
    table([
      { title: "Id", class: "mono", render: (c) => c.id },
      { title: "Machine", render: (c) => c.name },
      { title: "User", class: "mono", render: (c) => c.user_id },
      { title: "State", render: (c) => (c.revoked ? "revoked" : "active") },
    ], clients)));
}
import { api, logout } from "./api.js";
import { h } from "./dom.js";
import { parseHash } from "./lib.js";

const ROUTES = [
  ["", () => import("./views/overview.js"), "Overview"],
  ["projects", () => import("./views/projects.js"), "Projects"],
  ["jobs", () => import("./views/jobs.js"), "Jobs"],
  ["experiments", () => import("./views/experiments.js"), "Experiments"],
  ["agents", () => import("./views/agents.js"), "Agents"],
  ["compare", () => import("./views/compare.js"), null],
  ["admin", () => import("./views/admin.js"), "Admin"],
];

const main = document.getElementById("main");
let cleanups = [];
let renderToken = 0;

function newContext() {
  const timers = [];
  const ctx = {
    poll(fn, ms) {
      const tick = () => { if (!document.hidden) Promise.resolve().then(fn).catch(showError); };
      timers.push(setInterval(tick, ms));
    },
    onCleanup(fn) { cleanups.push(fn); },
  };
  cleanups.push(() => timers.forEach(clearInterval));
  return ctx;
}

function showError(error) {
  if (error && error.message === "login required") return;
  main.replaceChildren(h("p", { class: "error" }, `Something went wrong: ${error && error.message}`));
}

async function render() {
  const mine = ++renderToken;
  cleanups.forEach((fn) => { try { fn(); } catch { /* ignore */ } });
  cleanups = [];
  const { parts, params } = parseHash(window.location.hash);
  const route = parts[0] || "";
  const entry = ROUTES.find(([name]) => name === route);
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === route));
  if (!entry) { main.replaceChildren(h("p", {}, "Page not found.")); return; }
  try {
    const module = await entry[1]();
    if (mine !== renderToken) return;
    main.replaceChildren();
    await module.default(main, { parts, params }, newContext());
  } catch (error) {
    if (mine === renderToken) showError(error);
  }
}

async function start() {
  const me = await api.me();
  const nav = document.getElementById("nav");
  for (const [name, , title] of ROUTES) {
    if (!title || (name === "admin" && !me.is_admin)) continue;
    nav.append(h("a", { href: `#/${name}`, dataset: { route: name } }, title));
  }
  document.getElementById("user").textContent = me.username || "";
  const button = document.getElementById("logout");
  button.hidden = false;
  button.addEventListener("click", async () => { window.location.href = await logout(me.csrf); });
  window.addEventListener("hashchange", render);
  await render();
}

start().catch(showError);

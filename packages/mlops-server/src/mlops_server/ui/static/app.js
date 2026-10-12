import { api, logout } from "./api.js";
import { h } from "./dom.js";
import { createScope, parseHash } from "./lib.js";

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
let current = null;
let renderToken = 0;

// The context a view receives. Everything it starts is tied to the page scope, which is
// disposed when the route changes, so a stale view cannot poll or write after that.
function newContext(scope) {
  return {
    poll(fn, ms) {
      if (!scope.canRun()) return;
      const id = setInterval(() => {
        if (document.hidden || !scope.canRun()) return;
        Promise.resolve().then(fn).catch((error) => { if (scope.canRun()) showError(error); });
      }, ms);
      scope.onCleanup(() => clearInterval(id));
    },
    onCleanup(fn) { scope.onCleanup(fn); },
    active: () => scope.canRun(),
  };
}

function showError(error) {
  if (error && error.message === "login required") return;
  main.replaceChildren(h("p", { class: "error" }, `Something went wrong: ${error && error.message}`));
}

async function render() {
  const mine = ++renderToken;
  if (current) current.dispose();
  const scope = createScope();
  current = scope;
  const { parts, params } = parseHash(window.location.hash);
  const route = parts[0] || "";
  const entry = ROUTES.find(([name]) => name === route);
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === route));
  if (!entry) { main.replaceChildren(h("p", {}, "Page not found.")); return; }
  try {
    const module = await entry[1]();
    if (mine !== renderToken || !scope.canRun()) return;
    main.replaceChildren();
    await module.default(main, { parts, params }, newContext(scope));
  } catch (error) {
    if (mine === renderToken && scope.canRun()) showError(error);
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
  const header = document.querySelector("header.top");
  const notice = h("span", { class: "error", role: "alert" });
  header.append(notice);
  const button = document.getElementById("logout");
  button.hidden = false;
  button.addEventListener("click", async () => {
    notice.replaceChildren();
    try {
      window.location.href = await logout(me.csrf);
    } catch (error) {
      notice.replaceChildren(`Log out failed (${error.message}). Try again.`);
    }
  });
  window.addEventListener("hashchange", render);
  await render();
}

start().catch(showError);

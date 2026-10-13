import { api, logout, setCsrf } from "./api.js";
import { h } from "./dom.js";
import { createPageScope, parseHash } from "./lib.js";

// [route name, loader, navigation label or null]. The brand link goes to the overview.
const ROUTES = [
  ["", () => import("./views/overview.js"), null],
  ["projects", () => import("./views/projects.js"), "Projects"],
  ["datasets", () => import("./views/datasets.js"), "Datasets"],
  ["jobs", () => import("./views/jobs.js"), "Jobs"],
  ["resources", () => import("./views/resources.js"), "Resources"],
  ["experiment", () => import("./views/experiment.js"), null],
  ["runs", () => import("./views/runs.js"), null],
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
    // Runs fn every ms while the page is open and visible. A tick is skipped while the previous
    // one is still in flight, so responses cannot pile up or land out of order. A failed tick
    // goes to onError (the view keeps its last good content); without one, the error page shows.
    poll(fn, ms, onError) {
      if (!scope.canRun()) return;
      let busy = false;
      const id = setInterval(() => {
        if (document.hidden || !scope.canRun() || busy) return;
        busy = true;
        Promise.resolve().then(fn).then(
          () => { busy = false; },
          (error) => {
            busy = false;
            if (!scope.canRun() || isLoginError(error)) return;
            if (onError) onError(error); else showError(error);
          });
      }, ms);
      scope.onCleanup(() => clearInterval(id));
    },
    // Every write a view makes after an await goes through here, so a stale page never paints.
    render: (fn) => scope.run(fn),
    onCleanup(fn) { scope.onCleanup(fn); },
    active: () => scope.canRun(),
  };
}

function isLoginError(error) {
  return Boolean(error && error.message === "login required");
}

function showError(error) {
  if (isLoginError(error)) return;
  main.replaceChildren(h("p", { class: "error" }, `Something went wrong: ${error && error.message}`));
}

async function render() {
  const mine = ++renderToken;
  if (current) current.dispose();
  const scope = createPageScope();
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
  setCsrf(me.csrf);
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

import { shouldRedirectToLogin } from "./lib.js";

// Once per page load: a session the login page cannot establish must not loop forever.
let redirectedToLogin = false;

async function request(path, params = {}, init = {}) {
  const url = new URL("/api/v1" + path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" }, ...init });
  if (response.status === 401) {
    if (shouldRedirectToLogin(window.location.pathname, redirectedToLogin)) {
      redirectedToLogin = true;
      window.location.href = "/ui/auth/login";
    }
    throw new Error("login required");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch { /* keep status text */ }
    const error = new Error(String(detail));
    error.status = response.status;
    throw error;
  }
  return { json: await response.json(), total: Number(response.headers.get("X-Total-Count") || 0) };
}

const get = async (path, params) => (await request(path, params)).json;

export const api = {
  me: () => get("/me"),
  overview: () => get("/overview"),
  projects: () => get("/projects"),
  jobs: (params) => get("/jobs", params),
  projectOverview: (slug) => get("/projects/overview", { project: slug }),
  projectGraph: (slug, repo, limit = 60) => get("/projects/graph", { project: slug, repo, limit }),
  datasets: (project) => get("/datasets", { project }),
  datasetDetail: (project, repo, path, ref) => get("/datasets/detail", { project, repo, path, ref }),
  experimentSummary: (id) => get(`/experiments/${encodeURIComponent(id)}/summary`),
  resources: () => get("/resources"),
  jobSpec: (id) => get(`/jobs/${encodeURIComponent(id)}/spec`),
  runs: (params) => request("/runs", params),
  run: (id) => get(`/runs/${encodeURIComponent(id)}`),
  metrics: (id, sinceId) => get(`/runs/${encodeURIComponent(id)}/metrics`, { since_id: sinceId }),
  logs: (id, stream, afterSeq) => get(`/runs/${encodeURIComponent(id)}/logs`, { stream, after_seq: afterSeq }),
  artifacts: (id) => get(`/runs/${encodeURIComponent(id)}/artifacts`),
  artifactUrl: (id, aid) => get(`/runs/${encodeURIComponent(id)}/artifacts/${encodeURIComponent(aid)}/download`),
  compare: (ids) => get("/runs/compare", { ids: ids.join(",") }),
  adminAgents: () => get("/admin/agents"),
  adminClients: () => get("/admin/clients"),
  adminUsers: () => get("/admin/users"),
};

let csrfToken = "";
export const setCsrf = (value) => { csrfToken = value; };

// Writes carry the CSRF token from /me. A 401 sends the user to the login page, like reads do.
async function send(method, path, body) {
  const response = await fetch("/api/v1" + path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": csrfToken },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    window.location.href = "/ui/auth/login";
    throw new Error("login required");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch { /* keep status text */ }
    const error = new Error(String(detail));
    error.status = response.status;
    throw error;
  }
  return response.json();
}

const enc = encodeURIComponent;
export const writes = {
  cancelJob: (id) => send("POST", `/jobs/${enc(id)}/cancel`),
  rescheduleJob: (id, overrides) => send("POST", `/jobs/${enc(id)}/reschedule`, overrides),
  dispatchRun: (id, body) => send("POST", `/runs/${enc(id)}/dispatch`, body),
  patchExperiment: (id, body) => send("PATCH", `/experiments/${enc(id)}`, body),
};

export async function logout(csrf) {
  const response = await fetch("/ui/auth/logout", {
    method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrf },
  });
  if (!response.ok) throw new Error("logout failed");
  return (await response.json()).logout_url;
}

async function request(path, params = {}, init = {}) {
  const url = new URL("/api/v1" + path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" }, ...init });
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
  return { json: await response.json(), total: Number(response.headers.get("X-Total-Count") || 0) };
}

const get = async (path, params) => (await request(path, params)).json;

export const api = {
  me: () => get("/me"),
  overview: () => get("/overview"),
  projects: () => get("/projects"),
  jobs: (params) => get("/jobs", params),
  agentsStatus: () => get("/agents/status"),
  experiments: (params) => request("/experiments", params),
  experiment: (id) => get(`/experiments/${encodeURIComponent(id)}`),
  metrics: (id) => get(`/experiments/${encodeURIComponent(id)}/metrics`),
  logs: (id, stream, afterSeq) => get(`/experiments/${encodeURIComponent(id)}/logs`, { stream, after_seq: afterSeq }),
  artifacts: (id) => get(`/experiments/${encodeURIComponent(id)}/artifacts`),
  artifactUrl: (id, aid) => get(`/experiments/${encodeURIComponent(id)}/artifacts/${encodeURIComponent(aid)}/download`),
  compare: (ids) => get("/experiments/compare", { ids: ids.join(",") }),
  adminAgents: () => get("/admin/agents"),
  adminClients: () => get("/admin/clients"),
  adminUsers: () => get("/admin/users"),
};

export async function logout(csrf) {
  const response = await fetch("/ui/auth/logout", {
    method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrf },
  });
  if (!response.ok) throw new Error("logout failed");
  return (await response.json()).logout_url;
}

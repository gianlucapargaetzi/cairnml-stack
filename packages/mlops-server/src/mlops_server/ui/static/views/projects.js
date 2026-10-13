import { api } from "../api.js";
import { bestCell, runColumns, table } from "../components.js";
import { h } from "../dom.js";
import { renderGraph } from "../graph.js";
import { buildProjectTree, commitUrl, fmtTime, shortSha } from "../lib.js";

const projectHref = (slug) => `#/projects?project=${encodeURIComponent(slug)}`;

// Opens in a new tab; rel and target are set as properties because h() allows only a fixed set of attributes.
function githubLink(url) {
  if (!url) return null;
  const link = h("a", { href: url }, "view on GitHub");
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function treeView(nodes) {
  return h("ul", { class: "tree" }, nodes.map((node) => {
    const own = node.project
      ? h("a", { href: projectHref(node.project.slug) }, node.project.name || node.project.slug)
      : null;
    if (!node.children.length) return h("li", {}, own || node.name);
    return h("li", {}, h("details", { open: true },
      h("summary", {}, node.name, own ? " · " : "", own), treeView(node.children)));
  }));
}

export default async function projects(root, route, ctx) {
  if (route.params.project) return projectPage(root, route.params.project, ctx);
  const [list, overview] = await Promise.all([api.projects(), api.overview()]);
  const stats = new Map(overview.projects.map((p) => [p.slug, p]));
  ctx.render(() => root.replaceChildren(
    h("h1", {}, "Projects"),
    list.length
      ? treeView(buildProjectTree(list.map((p) => ({ ...p, ...stats.get(p.slug) }))))
      : h("p", { class: "muted" }, "You are not a member of any project yet. Ask an administrator."),
    table([
      { title: "Project", render: (p) => h("a", { href: projectHref(p.slug) }, p.slug) },
      { title: "Runs", render: (p) => (stats.get(p.slug) || {}).runs ?? 0 },
      { title: "Running", render: (p) => (stats.get(p.slug) || {}).running ?? 0 },
      { title: "Last activity", render: (p) => fmtTime((stats.get(p.slug) || {}).last_activity) },
    ], list, "")));
}

async function projectPage(root, slug, ctx) {
  const [overview, datasets] = await Promise.all([
    api.projectOverview(slug),
    api.datasets(slug).catch(() => []),
  ]);
  const graphBox = h("div", { class: "graph-box" });
  const detail = h("div", { class: "graph-detail muted" }, "Click a commit to see the runs that ran on it.");
  const repoSummary = h("p", { class: "muted" });
  const repoSelect = h("select", {
    "aria-label": "repository",
    onchange: (e) => loadGraph(e.target.value),
  }, overview.repos.map((r) => h("option", { value: r.repo }, `${r.repo} (${r.role})`)));

  // Each load drops its result when a newer load (or a route change) has started since.
  let loadSeq = 0;
  async function loadGraph(repo) {
    const mine = ++loadSeq;
    graphBox.replaceChildren(h("p", { class: "muted" }, "Loading history…"));
    detail.replaceChildren("Click a commit to see the runs that ran on it.");
    try {
      const data = await api.projectGraph(slug, repo);
      if (mine !== loadSeq) return;
      ctx.render(() => {
        const head = data.commits.find((c) => c.sha === data.head);
        repoSummary.replaceChildren(
          `default branch ${data.default_branch} · head `,
          h("code", {}, shortSha(data.head)),
          head ? ` ${head.message}` : "",
          ` · ${data.branches.length} branches${data.truncated ? " · history truncated" : ""}`);
        renderGraph(graphBox, data, ({ commit, runs }) => {
          const url = commitUrl({ remote_url: `https://github.com/${repo}`, commit: commit.sha });
          detail.replaceChildren(
            h("strong", {}, commit.message),
            h("div", { class: "muted" }, `${commit.author} · ${fmtTime(commit.date)} · `,
              h("code", {}, shortSha(commit.sha)), url ? " · " : "", githubLink(url)),
            runs.length
              ? h("ul", {}, runs.map((e) => h("li", {},
                h("a", { href: `#/runs/${encodeURIComponent(e.id)}` }, e.name), ` (${e.experiment}, ${e.status})`)))
              : h("p", { class: "muted" }, "No run recorded on this commit."));
        });
      });
    } catch (error) {
      if (mine !== loadSeq) return;
      ctx.render(() => graphBox.replaceChildren(h("p", { class: "error" }, `Could not load the repository history: ${error.message}`)));
    }
  }

  const jobs = Object.entries(overview.counts.jobs).map(([k, v]) => `${v} ${k}`).join(", ") || "none";
  ctx.render(() => root.replaceChildren(
    h("h1", {}, overview.project.name || overview.project.slug),
    h("p", { class: "muted" }, `${overview.project.slug} · ${overview.counts.runs} runs (${overview.counts.running} running) · jobs: ${jobs}`),
    h("h2", {}, "Experiments"),
    table([
      { title: "Experiment", render: (t) => h("a", { href: `#/experiment?id=${encodeURIComponent(t.id)}` }, t.name) },
      { title: "Kind", render: (t) => t.kind },
      { title: "Runs", render: (t) => t.runs },
      { title: "Running", render: (t) => t.running },
      { title: "Best result", render: (t) => bestCell(t) },
      { title: "Last activity", render: (t) => fmtTime(t.last_activity) },
    ], overview.experiments, "No experiments yet. Pass experiment=\"training\" to mlops.init(), or dispatch a job."),
    h("h2", {}, "Repository"),
    overview.repos.length
      ? [h("div", { class: "toolbar" }, repoSelect), repoSummary, h("div", { class: "graph-panel" }, graphBox, detail)]
      : h("p", { class: "muted" }, `No repository linked: run \`mlops repo link --project ${slug} --repo owner/name\`.`),
    h("h2", {}, "Datasets"),
    table([
      { title: "Dataset", render: (d) => h("a", { href: `#/datasets?project=${encodeURIComponent(d.project)}&repo=${encodeURIComponent(d.repo)}&path=${encodeURIComponent(d.path)}` }, d.path) },
      { title: "Type", render: (d) => d.type || "–" },
      { title: "License", render: (d) => d.license || "–" },
      { title: "Card", render: (d) => (d.has_card ? "yes" : "missing") },
    ], datasets, "No datasets found in the linked repositories."),
    h("h2", {}, "Containers and environments"),
    table([
      { title: "Name", render: (c) => c.name },
      { title: "Kind", render: (c) => c.kind },
      { title: "Jobs", render: (c) => c.jobs },
      { title: "Last used", render: (c) => fmtTime(c.last_used) },
      { title: "Last status", render: (c) => c.last_status },
    ], overview.containers, "No jobs have run in this project yet."),
    h("h2", {}, "Recent runs"),
    table(runColumns(), overview.recent, "No runs yet.")));
  if (overview.repos.length) await loadGraph(overview.repos[0].repo);
}

// MLOps framework: system architecture (5 physical machines)
// Compile: typst compile mlops-architecture.typ
// Needs the @preview/cetz package (fetched automatically on first compile).
//
// Layout is absolute: every box is placed by its centre (x, y) on a grid.
// Units are canvas units (0.9 cm each). Node size: W x H.

#import "@preview/cetz:0.4.2": canvas, draw

#set page(width: 400mm, height: auto, margin: 12mm, fill: white)
#set text(font: ("Liberation Sans", "DejaVu Sans"), size: 9pt, fill: rgb("#1f2937"))

// ---------- Palette per physical machine ----------
#let ext = (fill: rgb("#f3f4f6"), stroke: rgb("#6b7280"))
#let srv = (fill: rgb("#dbeafe"), stroke: rgb("#2563eb"))
#let cli = (fill: rgb("#dcfce7"), stroke: rgb("#16a34a"))
#let agt = (fill: rgb("#fef3c7"), stroke: rgb("#d97706"))
#let nas = (fill: rgb("#ede9fe"), stroke: rgb("#7c3aed"))
#let ink = rgb("#374151")

#let W = 4.4 // node width
#let H = 1.2 // node height

// ---------- Helpers ----------
#let node(x, y, title, sub, c) = {
  draw.rect(
    (x - W / 2, y - H / 2), (x + W / 2, y + H / 2),
    fill: c.fill, stroke: 0.8pt + c.stroke, radius: 3pt,
  )
  draw.content(
    (x, y), width: W - 0.2,
    align(center)[
      #text(weight: "bold", size: 8.5pt)[#title] \
      #text(size: 7pt, fill: ink)[#sub]
    ],
  )
}

#let frame(x0, y0, x1, y1, c, title) = {
  draw.rect(
    (x0, y0), (x1, y1),
    fill: c.fill.transparentize(55%),
    stroke: (paint: c.stroke, thickness: 0.6pt, dash: "dashed"),
    radius: 5pt,
  )
  draw.content(
    (x0 + 0.3, y1 - 0.45), anchor: "west",
    text(weight: "bold", size: 9pt, fill: c.stroke)[#title],
  )
}

// Orthogonal wire through the given points
#let wire(pts, dash: false, both: false) = draw.line(
  ..pts,
  stroke: if dash {
    (paint: ink, thickness: 0.7pt, dash: "dashed")
  } else {
    0.7pt + ink
  },
  mark: if both { (start: ">", end: ">") } else { (end: ">") },
)

// Small label with white background so it stays readable over lines
#let tag(x, y, body) = draw.content(
  (x, y),
  box(fill: white, inset: 1.5pt, text(size: 6.8pt, fill: ink)[#body]),
)

#align(center)[
  #text(size: 16pt, weight: "bold")[MLOps Framework: System Architecture]
  #linebreak()
  #text(size: 9pt, fill: rgb("#6b7280"))[Five physical machines. Datasets and artifacts live in object storage; the server stores their metadata and references, never the files in its databases.]
]
#v(4mm)

#canvas(length: 0.9cm, {
  // ============ Machine frames ============
  // Row 1: Client | Server | Agents
  frame(0, 10.4, 5.8, 18.0, cli, "1 · Client")
  frame(7.0, 10.4, 23.2, 18.0, srv, "2 · Server")
  frame(24.8, 10.4, 41.2, 18.0, agt, "4 · Agents")
  draw.content(
    (25.1, 17.1), anchor: "west",
    text(size: 6.8pt, fill: ink)[auth: device key → agent token · per-job token · GitHub token · presigned S3 URLs],
  )
  // Row 2: External | NAS
  frame(0, 2.6, 23.2, 8.0, ext, "5 · External services")
  frame(24.8, 4.8, 35.8, 8.0, nas, "3 · NAS")

  // ============ Client (column x = 2.9) ============
  node(2.9, 16.1, "CLI / Python SDK", "REST + device key (clearml-init)", cli)
  node(2.9, 13.9, "Dispatch jobs", "enqueue tasks with requirements", cli)
  node(2.9, 11.7, "Local runner", "auto-logged, git", cli)

  // ============ Server ============
  node(9.9, 16.1, "API server", "clients + agents, REST", srv)
  node(15.1, 16.1, "Experiment Tracking", "runs, metrics, artifacts", srv)
  node(9.9, 13.9, "Job Scheduler", "resource matching", srv)
  node(9.9, 11.7, "Job queue", "queued tasks, in MongoDB", srv)
  node(15.1, 11.7, "Metadata DB", "MongoDB · Redis · Elasticsearch", srv)
  node(20.3, 11.7, "Auth middleware", "token check, admin role", srv)
  node(20.3, 16.1, "Web app", "projects, runs, jobs, workers", srv)

  // ============ Agents ============
  node(32.9, 16.1, "Resource inventory", "CPU, RAM, GPU, labels", agt)
  node(27.7, 13.9, "Agent daemon", "clearml-agent --managed", agt)
  node(32.9, 13.9, "Python runner", "venv per job", agt)
  node(38.1, 13.9, "Container runner", "Docker: host or dind", agt)

  // ============ External ============
  node(2.9, 6.1, "GitHub", "source repos, read by GitHub App", ext)
  node(20.3, 6.1, "Identity Provider", "Keycloak: OIDC, mlops realm", ext)
  node(20.3, 3.9, "Dockerhub", "container images", ext)

  // ============ NAS ============
  node(27.7, 6.1, "Dataset store", "S3 buckets: dataset, model", nas)
  node(32.9, 6.1, "Artifact store", "S3 buckets: artifact, debug", nas)

  // ============ Wires: client ============
  wire(((5.1, 16.1), (7.7, 16.1)))
  tag(6.4, 16.6, [REST])
  wire(((5.1, 13.9), (6.4, 13.9), (6.4, 15.6), (7.7, 15.6)))
  wire(((2.9, 11.1), (2.9, 6.7)))
  tag(2.9, 9.2, [git clone / push])
  wire(((5.1, 11.7), (6.4, 11.7), (6.4, 9.2), (26.0, 9.2), (26.0, 6.7)))
  tag(14.0, 9.2, [dataset and artifact transfer, presigned S3 URLs])

  // ============ Wires: server ============
  wire(((12.1, 16.1), (12.9, 16.1)))
  wire(((9.9, 15.5), (9.9, 14.5)))
  wire(((15.1, 15.5), (15.1, 12.3)))
  wire(((9.9, 13.3), (9.9, 12.3)))
  wire(((20.3, 11.1), (20.3, 6.7)), dash: true)
  tag(21.7, 10.7, [OIDC: login, user sync])

  // Server -> GitHub: read-only GitHub App (fetch remote status)
  wire(((7.6, 10.4), (7.6, 8.6), (5.0, 8.6), (5.0, 6.7)), dash: true)
  tag(6.4, 8.2, [server: GitHub App, read])

  // ============ Wires: scheduler -> agents ============
  wire(((12.1, 13.9), (24.0, 13.9), (24.0, 16.1), (30.7, 16.1)), both: true)
  tag(18.0, 14.3, [REST: register, poll, logs, job tokens])

  // ============ Wires: agents -> NAS / Dockerhub ============
  wire(((27.7, 13.3), (27.7, 6.7)))
  tag(29.0, 9.2, [dataset pull, S3 URLs])
  wire(((32.9, 13.3), (32.9, 6.7)))
  tag(33.6, 9.2, [upload artifacts])
  wire(((38.1, 13.3), (38.1, 3.9), (22.5, 3.9)))
  tag(30.5, 4.3, [pull images])
})

#v(5mm)

// ---------- Legend and notes ----------
#grid(
  columns: (1fr, 1fr),
  gutter: 10mm,
  [
    #text(weight: "bold")[Machine rules]
    - *Client* talks to the Server (REST), to GitHub (git) and to the object store on the NAS (datasets and artifacts, through presigned S3 URLs).
    - *Server* runs the API, the web app, the scheduler and the stores: MongoDB for tasks and metadata, Redis and Elasticsearch for caches and events. It also runs the sign-in service (Keycloak) and the object store (RustFS) in the same deploy stack.
    - *NAS* holds the four buckets of the object store: dataset, model, artifact and debug.
    - *Agents* are enrolled by an admin with a device key. They get a token per job, a short-lived GitHub token for the job's one repository, and presigned S3 URLs for transfers. Jobs run in containers (Docker on the host, or a Docker daemon in a `dind` container). They pull images from Dockerhub.
  ],
  [
    #text(weight: "bold")[Data and identity]
    - Datasets and artifacts are ClearML datasets and artifacts. A run stores their ids and hashes, not the files.
    - Source repositories are on GitHub. The server reads them with a read-only GitHub App and gives each job a token for its one repository.
    - Clients enroll once through a Keycloak login, then use their device key only. Agents are enrolled by an admin only.
    - Presigned S3 URLs name the object store's public address, so clients must be able to reach it.
    - Dashed arrows: identity and authentication checks.
    - Browsers use the web app after the same Keycloak login. Users are synced from Keycloak.
  ],
)

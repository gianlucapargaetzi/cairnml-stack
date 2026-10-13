import { svg } from "./dom.js";
import { layoutGraph } from "./graph-layout.js";
import { colorFor } from "./lib.js";

const ROW = 30;
const LANE = 20;
const PAD = 20;
const TEXT_GAP = 16;
const TEXT_WIDTH = 560;
const ZOOM_STEP = 0.85;

function edgePath(e, x, y) {
  const x1 = x(e.fromLane), y1 = y(e.fromRow), x2 = x(e.toLane), y2 = y(e.toRow);
  if (x1 === x2) return `M ${x1} ${y1} L ${x2} ${y2}`;
  const bend = ROW * 0.6;
  return `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
}

// Draws the commit graph into container. data: {commits, branches, default_branch, experiments}
// where experiments maps a sha to the experiments that ran on it. onSelect({commit, experiments})
// runs when a commit is clicked or activated with Enter.
export function renderGraph(container, data, onSelect) {
  const { nodes, edges, laneCount } = layoutGraph(data.commits, data.branches);
  const x = (lane) => PAD + lane * LANE;
  const y = (row) => PAD + row * ROW;
  const textStart = x(laneCount) + TEXT_GAP;
  const width = textStart + TEXT_WIDTH;
  const height = PAD * 2 + Math.max(1, nodes.length) * ROW;
  const root = svg("svg", {
    class: "graph", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "commit graph",
  });
  const stage = svg("g");
  root.append(stage);

  for (const e of edges) {
    const lane = e.fromLane === e.toLane ? e.fromLane : Math.max(e.fromLane, e.toLane);
    stage.append(svg("path", { d: edgePath(e, x, y), fill: "none", stroke: colorFor(lane), "stroke-width": 2 }));
  }

  for (const node of nodes) {
    const runs = (data.experiments || {})[node.sha] || [];
    const cx = x(node.lane), cy = y(node.row);
    const group = svg("g", { class: "commit", tabindex: 0, "data-sha": node.sha });
    group.append(svg("title", {}, `${node.commit.message}\n${node.commit.author} · ${node.commit.date}`));
    if (runs.length) group.append(svg("circle", { cx, cy, r: 9, fill: "none", stroke: "currentColor", "stroke-width": 2 }));
    group.append(svg("circle", { cx, cy, r: 5, fill: colorFor(node.lane) }));
    let cursor = textStart;
    for (const name of node.branches) {
      const isDefault = name === data.default_branch;
      group.append(svg("text", { x: cursor, y: cy + 4, class: isDefault ? "graph-chip graph-chip-default" : "graph-chip" }, name));
      cursor += name.length * 7 + 14;
    }
    const message = String(node.commit.message || "").split("\n")[0].slice(0, 70);
    const count = runs.length ? `  (${runs.length} experiment${runs.length === 1 ? "" : "s"})` : "";
    group.append(svg("text", { x: cursor, y: cy + 4, class: "commit-label" }, `${node.sha.slice(0, 8)}  ${message}${count}`));
    const select = () => onSelect({ commit: node.commit, experiments: runs });
    group.addEventListener("click", select);
    group.addEventListener("keydown", (ev) => { if (ev.key === "Enter") select(); });
    stage.append(group);
  }

  // Wheel zooms around the pointer and dragging pans, both by changing the viewBox.
  let view = { x: 0, y: 0, w: width, h: height };
  const apply = () => root.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
  root.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const factor = ev.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
    const rect = root.getBoundingClientRect();
    const px = view.x + ((ev.clientX - rect.left) / rect.width) * view.w;
    const py = view.y + ((ev.clientY - rect.top) / rect.height) * view.h;
    view = { x: px - (px - view.x) * factor, y: py - (py - view.y) * factor, w: view.w * factor, h: view.h * factor };
    apply();
  }, { passive: false });

  let drag = null;
  root.addEventListener("pointerdown", (ev) => {
    drag = { x: ev.clientX, y: ev.clientY, view: { ...view } };
    root.setPointerCapture(ev.pointerId);
  });
  root.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    const rect = root.getBoundingClientRect();
    view = {
      ...drag.view,
      x: drag.view.x - ((ev.clientX - drag.x) / rect.width) * drag.view.w,
      y: drag.view.y - ((ev.clientY - drag.y) / rect.height) * drag.view.h,
    };
    apply();
  });
  root.addEventListener("pointerup", () => { drag = null; });
  root.addEventListener("pointercancel", () => { drag = null; });

  container.replaceChildren(root);
}

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { Dropdown, Text } from 'components/kit';

import projectPagesService, {
  IRepoGraph,
} from 'services/api/projectPages/projectPagesService';

import {
  colorFor,
  IGraphEdge,
  IGraphNode,
  layoutGraph,
} from 'utils/graph/layout';

const ROW = 30;
const LANE = 20;
const PAD = 20;
const TEXT_GAP = 16;
const TEXT_WIDTH = 560;
const ZOOM_STEP = 0.85;

// A curve between two commits: straight when they share a lane, bent otherwise.
function edgePath(edge: IGraphEdge): string {
  const x = (lane: number) => PAD + lane * LANE;
  const y = (row: number) => PAD + row * ROW;
  const x1 = x(edge.fromLane);
  const y1 = y(edge.fromRow);
  const x2 = x(edge.toLane);
  const y2 = y(edge.toRow);
  if (x1 === x2) {
    return `M ${x1} ${y1} L ${x2} ${y2}`;
  }
  const bend = ROW * 0.6;
  return `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
}

interface IProps {
  repos: { repo: string; role: string }[];
  project: string;
}

// The commit history of one linked repository. A click on a commit shows the runs on it.
function RepoGraph({ repos, project }: IProps) {
  const [repoMenuOpen, setRepoMenuOpen] = useState(false);
  const [repo, setRepo] = useState(repos[0]?.repo ?? '');
  const [graph, setGraph] = useState<IRepoGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (!repo) {
      return undefined;
    }
    setGraph(null);
    setError(null);
    setSelected(null);
    const request = projectPagesService.getRepoGraph(project, repo);
    request
      .call()
      .then((data) => setGraph(data))
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(
            `Could not load the repository history: ${requestError.message}`,
          );
        }
      });
    return () => request.abort();
  }, [project, repo]);

  const layout = useMemo(
    () => (graph ? layoutGraph(graph.commits, graph.branches) : null),
    [graph],
  );
  const selectedNode: IGraphNode | undefined = layout?.nodes.find(
    (n) => n.sha === selected,
  );
  const selectedRuns =
    selectedNode && graph ? graph.runs[selectedNode.sha] ?? [] : [];
  const width = layout
    ? PAD + layout.laneCount * LANE + TEXT_GAP + TEXT_WIDTH
    : 0;
  const height = layout ? PAD * 2 + Math.max(1, layout.nodes.length) * ROW : 0;
  const textStart = layout ? PAD + layout.laneCount * LANE + TEXT_GAP : 0;

  // The visible window of the graph: the wheel zooms around the pointer, dragging pans.
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, w: 0, h: 0 });
  const drag = useRef<{ x: number; y: number; view: typeof view } | null>(null);
  useEffect(() => {
    setView({ x: 0, y: 0, w: width, h: height });
  }, [width, height]);
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) {
      return undefined;
    }
    // A native listener, so the page does not scroll while the graph zooms.
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const factor = event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      const rect = svg.getBoundingClientRect();
      setView((current) => {
        const px =
          current.x + ((event.clientX - rect.left) / rect.width) * current.w;
        const py =
          current.y + ((event.clientY - rect.top) / rect.height) * current.h;
        return {
          x: px - (px - current.x) * factor,
          y: py - (py - current.y) * factor,
          w: current.w * factor,
          h: current.h * factor,
        };
      });
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, [layout]);
  function startDrag(event: React.PointerEvent<SVGSVGElement>) {
    drag.current = { x: event.clientX, y: event.clientY, view };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function moveDrag(event: React.PointerEvent<SVGSVGElement>) {
    const start = drag.current;
    if (!start || !svgRef.current) {
      return;
    }
    const rect = svgRef.current.getBoundingClientRect();
    setView({
      ...start.view,
      x: start.view.x - ((event.clientX - start.x) / rect.width) * start.view.w,
      y:
        start.view.y - ((event.clientY - start.y) / rect.height) * start.view.h,
    });
  }
  function endDrag() {
    drag.current = null;
  }

  return (
    <div className='RepoGraph'>
      <Dropdown
        label='Repository'
        size='medium'
        value={repo || null}
        options={repos.map((item) => ({
          value: item.repo,
          label: `${item.repo} (${item.role})`,
        }))}
        onChange={(option) => setRepo(option?.value ?? repo)}
        onMenuOpen={() => setRepoMenuOpen(true)}
        onMenuClose={() => setRepoMenuOpen(false)}
        open={repoMenuOpen}
        withPortal
      />
      {graph && (
        <Text size={12} tint={50}>
          {`default branch ${graph.default_branch} · head ${graph.head.slice(
            0,
            8,
          )} · ${graph.branches.length} branches${
            graph.truncated ? ' · history truncated' : ''
          }`}
        </Text>
      )}
      {error && (
        <Text size={12} color='error' role='alert'>
          {error}
        </Text>
      )}
      {!graph && !error && (
        <Text size={12} tint={50}>
          Loading history
        </Text>
      )}
      {layout && (
        <div className='RepoGraph__panel'>
          <svg
            ref={svgRef}
            className='RepoGraph__svg'
            viewBox={`${view.x} ${view.y} ${view.w || width} ${
              view.h || height
            }`}
            role='img'
            aria-label='commit graph'
            onPointerDown={startDrag}
            onPointerMove={moveDrag}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          >
            {layout.edges.map((edge) => (
              <path
                key={`${edge.from}-${edge.to}`}
                d={edgePath(edge)}
                fill='none'
                stroke={colorFor(Math.max(edge.fromLane, edge.toLane))}
                strokeWidth={2}
              />
            ))}
            {layout.nodes.map((node) => {
              const cx = PAD + node.lane * LANE;
              const cy = PAD + node.row * ROW;
              const runs = graph?.runs[node.sha] ?? [];
              const message = String(node.commit.message || '')
                .split('\n')[0]
                .slice(0, 70);
              return (
                <g
                  key={node.sha}
                  className={`RepoGraph__commit${
                    selected === node.sha ? ' RepoGraph__commit--selected' : ''
                  }`}
                  tabIndex={0}
                  onClick={() => setSelected(node.sha)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      setSelected(node.sha);
                    }
                  }}
                >
                  <title>{`${node.commit.message}\n${node.commit.author} · ${node.commit.date}`}</title>
                  {runs.length > 0 && (
                    <circle
                      cx={cx}
                      cy={cy}
                      r={9}
                      fill='none'
                      stroke='currentColor'
                      strokeWidth={2}
                    />
                  )}
                  <circle cx={cx} cy={cy} r={5} fill={colorFor(node.lane)} />
                  {node.branches.map((name, index) => {
                    const chipX =
                      textStart +
                      node.branches
                        .slice(0, index)
                        .reduce((sum, b) => sum + b.length * 7 + 14, 0);
                    return (
                      <text
                        key={name}
                        x={chipX}
                        y={cy + 4}
                        className={`RepoGraph__chip${
                          name === graph?.default_branch
                            ? ' RepoGraph__chip--default'
                            : ''
                        }`}
                      >
                        {name}
                      </text>
                    );
                  })}
                  <text
                    x={
                      textStart +
                      node.branches.reduce(
                        (sum, b) => sum + b.length * 7 + 14,
                        0,
                      )
                    }
                    y={cy + 4}
                    className='RepoGraph__label'
                  >
                    {`${node.sha.slice(0, 8)}  ${message}${
                      runs.length
                        ? `  (${runs.length} run${
                            runs.length === 1 ? '' : 's'
                          })`
                        : ''
                    }`}
                  </text>
                </g>
              );
            })}
          </svg>
          <div className='RepoGraph__detail'>
            {selectedNode ? (
              <>
                <strong>{selectedNode.commit.message}</strong>
                <Text size={12} tint={50}>
                  {`${selectedNode.commit.author} · ${new Date(
                    selectedNode.commit.date,
                  ).toLocaleString()} · ${selectedNode.sha.slice(0, 10)}`}
                </Text>
                {selectedRuns.length ? (
                  <ul>
                    {selectedRuns.map((run) => (
                      <li key={run.id}>
                        <Link to={`/runs/${encodeURIComponent(run.id)}`}>
                          {run.name}
                        </Link>{' '}
                        ({run.experiment}, {run.status})
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Text size={12} tint={50}>
                    No run recorded on this commit.
                  </Text>
                )}
              </>
            ) : (
              <Text size={12} tint={50}>
                Click a commit to see the runs that ran on it.
              </Text>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default RepoGraph;

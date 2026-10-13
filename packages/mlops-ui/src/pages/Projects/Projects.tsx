import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import datasetsService from 'services/api/datasets/datasetsService';
import projectPagesService, {
  IProjectOverview,
  IProjectSummary,
} from 'services/api/projectPages/projectPagesService';

import { IDatasetRow } from 'utils/datasets/datasets';
import {
  bestLabel,
  buildProjectTree,
  IProjectRef,
  IProjectTreeNode,
} from 'utils/projects/projects';

import RepoGraph from './RepoGraph';

import './Projects.scss';

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '–';
}

function duration(run: {
  started_at: string | null;
  finished_at: string | null;
}): string {
  if (!run.started_at) {
    return '–';
  }
  const end = run.finished_at ? Date.parse(run.finished_at) : Date.now();
  const seconds = Math.max(
    0,
    Math.round((end - Date.parse(run.started_at)) / 1000),
  );
  if (seconds < 60) {
    return `${seconds}s`;
  }
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function TreeView({ nodes }: { nodes: IProjectTreeNode[] }) {
  return (
    <ul className='Projects__tree'>
      {nodes.map((node) => {
        const own = node.project ? (
          <Link
            to={`/projects?project=${encodeURIComponent(node.project.slug)}`}
          >
            {node.project.name || node.project.slug}
          </Link>
        ) : null;
        if (!node.children.length) {
          return <li key={node.name}>{own ?? node.name}</li>;
        }
        return (
          <li key={node.name}>
            <details open>
              <summary>
                {node.name}
                {own ? ' · ' : ''}
                {own}
              </summary>
              <TreeView nodes={node.children} />
            </details>
          </li>
        );
      })}
    </ul>
  );
}

function ProjectList() {
  const [projects, setProjects] = useState<IProjectRef[] | null>(null);
  const [stats, setStats] = useState<Map<string, IProjectSummary>>(new Map());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const list = projectPagesService.getProjects();
    const overview = projectPagesService.getOverview();
    Promise.all([list.call(), overview.call()])
      .then(([loaded, summary]) => {
        setProjects(loaded);
        setStats(new Map(summary.projects.map((p) => [p.slug, p])));
      })
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`Projects could not be loaded: ${requestError.message}`);
        }
      });
    return () => {
      list.abort();
      overview.abort();
    };
  }, []);

  if (error) {
    return (
      <p className='Projects__error' role='alert'>
        {error}
      </p>
    );
  }
  if (!projects) {
    return <p className='Projects__muted'>Loading…</p>;
  }
  const merged = projects.map((p) => ({ ...p, ...(stats.get(p.slug) ?? {}) }));
  return (
    <>
      <h1>Projects</h1>
      {projects.length ? (
        <TreeView nodes={buildProjectTree(merged)} />
      ) : (
        <p className='Projects__muted'>
          You are not a member of any project yet. Ask an administrator.
        </p>
      )}
      <table className='Projects__table'>
        <thead>
          <tr>
            <th>Project</th>
            <th>Runs</th>
            <th>Running</th>
            <th>Last activity</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => {
            const summary = stats.get(project.slug);
            return (
              <tr key={project.id}>
                <td>
                  <Link
                    to={`/projects?project=${encodeURIComponent(project.slug)}`}
                  >
                    {project.slug}
                  </Link>
                </td>
                <td>{summary?.runs ?? 0}</td>
                <td>{summary?.running ?? 0}</td>
                <td>{formatTime(summary?.last_activity ?? null)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

function ProjectDetail({ slug }: { slug: string }) {
  const [overview, setOverview] = useState<IProjectOverview | null>(null);
  const [datasets, setDatasets] = useState<IDatasetRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOverview(null);
    setError(null);
    const request = projectPagesService.getProjectOverview(slug);
    request
      .call()
      .then((data) => setOverview(data))
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`The project could not be loaded: ${requestError.message}`);
        }
      });
    // Datasets come from the linked repositories; a failure leaves the section empty.
    const listing = datasetsService.getDatasets();
    listing
      .call()
      .then((rows) => setDatasets(rows.filter((row) => row.project === slug)))
      .catch(() => setDatasets([]));
    return () => {
      request.abort();
      listing.abort();
    };
  }, [slug]);

  if (error) {
    return (
      <p className='Projects__error' role='alert'>
        {error}
      </p>
    );
  }
  if (!overview) {
    return <p className='Projects__muted'>Loading…</p>;
  }
  const jobs =
    Object.entries(overview.counts.jobs)
      .map(([k, v]) => `${v} ${k}`)
      .join(', ') || 'none';
  return (
    <>
      <p>
        <Link to='/projects'>← all projects</Link>
      </p>
      <h1>{overview.project.name || overview.project.slug}</h1>
      <p className='Projects__muted'>
        {overview.project.slug} · {overview.counts.runs} runs (
        {overview.counts.running} running) · jobs: {jobs}
      </p>

      <h2>Experiments</h2>
      <table className='Projects__table'>
        <thead>
          <tr>
            <th>Experiment</th>
            <th>Kind</th>
            <th>Runs</th>
            <th>Running</th>
            <th>Best result</th>
            <th>Last activity</th>
          </tr>
        </thead>
        <tbody>
          {overview.experiments.map((experiment) => {
            const best = bestLabel(experiment);
            return (
              <tr key={experiment.id}>
                <td>
                  <Link
                    to={`/experiment?id=${encodeURIComponent(experiment.id)}`}
                  >
                    {experiment.name}
                  </Link>
                </td>
                <td>{experiment.kind}</td>
                <td>{experiment.runs}</td>
                <td>{experiment.running}</td>
                <td>
                  {best.runId ? (
                    <Link to={`/runs/${encodeURIComponent(best.runId)}`}>
                      {best.text}
                    </Link>
                  ) : (
                    best.text
                  )}
                </td>
                <td>{formatTime(experiment.last_activity)}</td>
              </tr>
            );
          })}
          {overview.experiments.length === 0 && (
            <tr>
              <td colSpan={6} className='Projects__muted'>
                No experiments yet. Pass experiment=&quot;training&quot; to
                mlops.init(), or dispatch a job.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2>Repository</h2>
      {overview.repos.length ? (
        <RepoGraph repos={overview.repos} project={slug} />
      ) : (
        <p className='Projects__muted'>
          No repository linked: run{' '}
          <code>mlops repo link --project {slug} --repo owner/name</code>.
        </p>
      )}

      <h2>Datasets</h2>
      <table className='Projects__table'>
        <thead>
          <tr>
            <th>Dataset</th>
            <th>Type</th>
            <th>License</th>
            <th>Card</th>
          </tr>
        </thead>
        <tbody>
          {datasets.map((row) => (
            <tr key={`${row.repo}/${row.path}`}>
              <td>
                <Link
                  to={`/datasets?${new URLSearchParams({
                    project: row.project,
                    repo: row.repo,
                    path: row.path,
                  }).toString()}`}
                >
                  {row.path}
                </Link>
              </td>
              <td>{row.type ?? '–'}</td>
              <td>{row.license ?? '–'}</td>
              <td>{row.has_card ? 'yes' : 'missing'}</td>
            </tr>
          ))}
          {datasets.length === 0 && (
            <tr>
              <td colSpan={4} className='Projects__muted'>
                No datasets found in the linked repositories.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2>Containers and environments</h2>
      <table className='Projects__table'>
        <thead>
          <tr>
            <th>Name</th>
            <th>Kind</th>
            <th>Jobs</th>
            <th>Last used</th>
            <th>Last status</th>
          </tr>
        </thead>
        <tbody>
          {overview.containers.map((container) => (
            <tr key={`${container.kind}:${container.name}`}>
              <td className='Projects__mono'>{container.name}</td>
              <td>{container.kind}</td>
              <td>{container.jobs}</td>
              <td>{formatTime(container.last_used)}</td>
              <td>{container.last_status}</td>
            </tr>
          ))}
          {overview.containers.length === 0 && (
            <tr>
              <td colSpan={5} className='Projects__muted'>
                No jobs have run in this project yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h2>Recent runs</h2>
      <table className='Projects__table'>
        <thead>
          <tr>
            <th>Name</th>
            <th>Status</th>
            <th>Experiment</th>
            <th>Owner</th>
            <th>Started</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          {overview.recent.map((run) => (
            <tr key={run.id}>
              <td>
                <Link to={`/runs/${encodeURIComponent(run.id)}`}>
                  {run.name}
                </Link>
              </td>
              <td>{run.status}</td>
              <td>{run.experiment}</td>
              <td>{run.owner}</td>
              <td>{formatTime(run.started_at ?? run.created_at)}</td>
              <td>{duration(run)}</td>
            </tr>
          ))}
          {overview.recent.length === 0 && (
            <tr>
              <td colSpan={6} className='Projects__muted'>
                No runs yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}

// The list, or the overview of one project when the query names it.
function Projects(): React.FunctionComponentElement<React.ReactNode> {
  const location = useLocation();
  const slug = new URLSearchParams(location.search).get('project');
  return (
    <ErrorBoundary>
      <section className='Projects'>
        {slug ? <ProjectDetail key={slug} slug={slug} /> : <ProjectList />}
      </section>
    </ErrorBoundary>
  );
}

export default Projects;

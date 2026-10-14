import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { Card, Table, Text } from 'components/kit';
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
            className='Projects__link'
            to={`/projects?project=${encodeURIComponent(node.project.slug)}`}
          >
            {node.project.name || node.project.slug}
          </Link>
        ) : null;
        if (!node.children.length) {
          return (
            <li key={node.name}>
              <Text size={12}>{own ?? node.name}</Text>
            </li>
          );
        }
        return (
          <li key={node.name}>
            <details open>
              <summary>
                <Text size={12} component='span' weight={600}>
                  {node.name}
                </Text>
                {own ? (
                  <Text size={12} component='span' tint={50}>
                    {' · '}
                  </Text>
                ) : null}
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

function ErrorText({ message }: { message: string }) {
  return (
    <Text size={12} color='error' role='alert'>
      {message}
    </Text>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return (
    <Text size={12} tint={50}>
      {children}
    </Text>
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
    return <ErrorText message={error} />;
  }
  if (!projects) {
    return <Muted>Loading</Muted>;
  }
  const merged = projects.map((p) => ({ ...p, ...(stats.get(p.slug) ?? {}) }));
  return (
    <>
      <header className='Projects__header'>
        <Text component='h1' size={18} weight={600} tint={100}>
          Projects
        </Text>
        <Text size={12} tint={50}>
          Projects you are a member of, with their runs.
        </Text>
      </header>
      <Card title='Hierarchy'>
        {projects.length ? (
          <TreeView nodes={buildProjectTree(merged)} />
        ) : (
          <Muted>
            You are not a member of any project yet. Ask an administrator.
          </Muted>
        )}
      </Card>
      <Card title='All projects'>
        <Table
          columns={[
            { key: 'project', label: 'Project' },
            { key: 'runs', label: 'Runs' },
            { key: 'running', label: 'Running' },
            { key: 'activity', label: 'Last activity' },
          ]}
          rows={projects.map((project) => {
            const summary = stats.get(project.slug);
            return {
              id: project.id,
              project: (
                <Link
                  className='Projects__link'
                  to={`/projects?project=${encodeURIComponent(project.slug)}`}
                >
                  {project.slug}
                </Link>
              ),
              runs: summary?.runs ?? 0,
              running: summary?.running ?? 0,
              activity: formatTime(summary?.last_activity ?? null),
            };
          })}
          rowKey='id'
          emptyText='No projects yet.'
        />
      </Card>
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
    return <ErrorText message={error} />;
  }
  if (!overview) {
    return <Muted>Loading</Muted>;
  }
  const jobs =
    Object.entries(overview.counts.jobs)
      .map(([k, v]) => `${v} ${k}`)
      .join(', ') || 'none';
  return (
    <section className='Projects__detail'>
      <Link className='Projects__link' to='/projects'>
        ← All projects
      </Link>
      <header className='Projects__header'>
        <Text component='h1' size={18} weight={600} tint={100}>
          {overview.project.name || overview.project.slug}
        </Text>
        <Text size={12} tint={50}>
          {`${overview.project.slug} · ${overview.counts.runs} runs (${overview.counts.running} running) · jobs: ${jobs}`}
        </Text>
      </header>

      <Card title='Experiments'>
        <Table
          columns={[
            { key: 'experiment', label: 'Experiment' },
            { key: 'kind', label: 'Kind' },
            { key: 'runs', label: 'Runs' },
            { key: 'running', label: 'Running' },
            { key: 'best', label: 'Best result' },
            { key: 'activity', label: 'Last activity' },
          ]}
          rows={overview.experiments.map((experiment) => {
            const best = bestLabel(experiment);
            return {
              id: experiment.id,
              experiment: (
                <Link
                  className='Projects__link'
                  to={`/experiment?id=${encodeURIComponent(experiment.id)}`}
                >
                  {experiment.name}
                </Link>
              ),
              kind: experiment.kind,
              runs: experiment.runs,
              running: experiment.running,
              best: best.runId ? (
                <Link
                  className='Projects__link'
                  to={`/runs/${encodeURIComponent(best.runId)}`}
                >
                  {best.text}
                </Link>
              ) : (
                best.text
              ),
              activity: formatTime(experiment.last_activity),
            };
          })}
          rowKey='id'
          emptyText='No experiments yet. Pass experiment="training" to mlops.init(), or dispatch a job.'
        />
      </Card>

      <Card title='Repository'>
        {overview.repos.length ? (
          <RepoGraph repos={overview.repos} project={slug} />
        ) : (
          <Muted>
            {`No repository linked. Run mlops repo link --project ${slug} --repo owner/name.`}
          </Muted>
        )}
      </Card>

      <Card title='Datasets'>
        <Table
          columns={[
            { key: 'dataset', label: 'Dataset' },
            { key: 'type', label: 'Type' },
            { key: 'license', label: 'License' },
            { key: 'card', label: 'Card' },
          ]}
          rows={datasets.map((row) => ({
            id: `${row.repo}/${row.path}`,
            dataset: (
              <Link
                className='Projects__link'
                to={`/datasets?${new URLSearchParams({
                  project: row.project,
                  repo: row.repo,
                  path: row.path,
                }).toString()}`}
              >
                {row.path}
              </Link>
            ),
            type: row.type ?? '–',
            license: row.license ?? '–',
            card: row.has_card ? 'Yes' : 'Missing',
          }))}
          rowKey='id'
          emptyText='No datasets found in the linked repositories.'
        />
      </Card>

      <Card title='Containers and environments'>
        <Table
          columns={[
            { key: 'name', label: 'Name' },
            { key: 'kind', label: 'Kind' },
            { key: 'jobs', label: 'Jobs' },
            { key: 'last_used', label: 'Last used' },
            { key: 'status', label: 'Last status' },
          ]}
          rows={overview.containers.map((container) => ({
            id: `${container.kind}:${container.name}`,
            name: <span className='Projects__mono'>{container.name}</span>,
            kind: container.kind,
            jobs: container.jobs,
            last_used: formatTime(container.last_used),
            status: container.last_status,
          }))}
          rowKey='id'
          emptyText='No jobs have run in this project yet.'
        />
      </Card>

      <Card title='Recent runs'>
        <Table
          columns={[
            { key: 'name', label: 'Name' },
            { key: 'status', label: 'Status' },
            { key: 'experiment', label: 'Experiment' },
            { key: 'owner', label: 'Owner' },
            { key: 'started', label: 'Started' },
            { key: 'duration', label: 'Duration' },
          ]}
          rows={overview.recent.map((run) => ({
            id: run.id,
            name: (
              <Link
                className='Projects__link'
                to={`/runs/${encodeURIComponent(run.id)}`}
              >
                {run.name}
              </Link>
            ),
            status: run.status,
            experiment: run.experiment,
            owner: run.owner,
            started: formatTime(run.started_at ?? run.created_at),
            duration: duration(run),
          }))}
          rowKey='id'
          emptyText='No runs yet.'
        />
      </Card>
    </section>
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

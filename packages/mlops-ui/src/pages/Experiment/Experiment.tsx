import React, { useEffect, useMemo, useState } from 'react';
import { Link, useHistory, useLocation } from 'react-router-dom';

import { MenuItem } from '@material-ui/core';

import { Badge, Button, Card, Table, Text } from 'components/kit';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';
import OutlinedField from 'components/OutlinedField/OutlinedField';

import { STATUS_COLORS } from 'config/colors/colors';

import experimentPagesService, {
  IExperimentSummary,
} from 'services/api/experimentPages/experimentPagesService';

import {
  bestId,
  DIRECTIONS,
  EXPERIMENT_KINDS,
  explainSaveError,
  paramText,
  sortRows,
  varyingKeys,
} from 'utils/experiments/experiments';
import { MAX_COMPARE } from 'utils/compare/compare';
import { fmtNumber } from 'utils/projects/projects';

import './Experiment.scss';

const POLL_MS = 10000;
const TOP = 3;

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
  return seconds < 60
    ? `${seconds}s`
    : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

// The primary value of each run, oldest first, as a line.
function ValueChart({ values, label }: { values: number[]; label: string }) {
  const width = 640;
  const height = 180;
  const pad = 24;
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const x = (i: number) =>
    pad +
    (values.length === 1 ? 0 : (i / (values.length - 1)) * (width - 2 * pad));
  const y = (v: number) =>
    height - pad - ((v - low) / span) * (height - 2 * pad);
  const points = values.map((v, i) => `${x(i)},${y(v)}`).join(' ');
  return (
    <svg
      className='Experiment__chart'
      viewBox={`0 0 ${width} ${height}`}
      role='img'
      aria-label={`${label} by run`}
    >
      <polyline points={points} />
      {values.map((v, i) => (
        <circle key={i} cx={x(i)} cy={y(v)} r={3} />
      ))}
    </svg>
  );
}

function SettingsForm({
  summary,
  onSaved,
}: {
  summary: IExperimentSummary;
  onSaved: () => void;
}) {
  const { experiment } = summary;
  const [kind, setKind] = useState(experiment.kind);
  const [description, setDescription] = useState(experiment.description ?? '');
  const [metric, setMetric] = useState(experiment.primary_metric ?? '');
  const [direction, setDirection] = useState(experiment.direction ?? 'min');
  const [message, setMessage] = useState('');

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setMessage('Saving…');
    experimentPagesService
      .patchSettings(experiment.id, {
        kind,
        description: description || null,
        primary_metric: metric || null,
        direction: metric ? direction : null,
      })
      .call()
      .then(() => {
        setMessage('Saved.');
        onSaved();
      })
      .catch((error) => setMessage(explainSaveError(error)));
  }

  return (
    <form className='Experiment__settings' onSubmit={submit}>
      <div className='Experiment__fields'>
        <OutlinedField
          id='experiment-kind'
          label='Kind'
          select
          value={kind}
          onValueChange={setKind}
        >
          {EXPERIMENT_KINDS.map((k) => (
            <MenuItem key={k} value={k}>
              {k}
            </MenuItem>
          ))}
        </OutlinedField>
        <OutlinedField
          id='experiment-metric'
          label='Primary metric'
          placeholder='e.g. val_loss'
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
        />
        <OutlinedField
          id='experiment-direction'
          label='Better is'
          select
          value={direction}
          onValueChange={setDirection}
        >
          {DIRECTIONS.map((d) => (
            <MenuItem key={d} value={d}>
              {d}
            </MenuItem>
          ))}
        </OutlinedField>
      </div>
      <OutlinedField
        id='experiment-description'
        label='Description'
        multiline
        rows={3}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className='Experiment__actions'>
        <Button variant='contained' type='submit'>
          Save settings
        </Button>
        {message && (
          <Text size={12} tint={70} role='status'>
            {message}
          </Text>
        )}
      </div>
    </form>
  );
}

function ExperimentDetail({ id }: { id: string }) {
  const [summary, setSummary] = useState<IExperimentSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState('created_at:desc');
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const history = useHistory();

  useEffect(() => {
    const request = experimentPagesService.getSummary(id);
    request
      .call()
      .then((data) => {
        setSummary(data);
        setError(null);
      })
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(
            `The experiment could not be loaded: ${requestError.message}`,
          );
        }
      });
    return () => request.abort();
  }, [id, reload]);

  useEffect(() => {
    const timer = window.setInterval(() => setReload((n) => n + 1), POLL_MS);
    return () => window.clearInterval(timer);
  }, []);

  const rows = useMemo(() => {
    if (!summary) {
      return [];
    }
    const [by, direction] = sort.split(':');
    return sortRows(
      summary.runs,
      by,
      direction === 'best' ? summary.experiment.direction ?? 'min' : direction,
    );
  }, [summary, sort]);

  if (error) {
    return (
      <Text size={12} color='error' role='alert'>
        {error}
      </Text>
    );
  }
  if (!summary) {
    return (
      <Text size={12} tint={50}>
        Loading…
      </Text>
    );
  }
  const { experiment, stats } = summary;
  const direction = experiment.direction ?? 'min';
  const best = bestId(summary.runs, direction);
  const keys = varyingKeys(summary.runs);
  const valued = summary.runs
    .filter((r) => typeof r.primary_value === 'number')
    .map((r) => r.primary_value as number)
    .reverse();
  const ranked = sortRows(
    summary.runs.filter((r) => typeof r.primary_value === 'number'),
    'primary_value',
    direction,
  );
  const compareUrl = (ids: string[]) =>
    `/compare?ids=${encodeURIComponent(ids.join(','))}`;
  const toggle = (id: string, on: boolean) =>
    setSelected((current) =>
      on ? [...current, id] : current.filter((x) => x !== id),
    );

  return (
    <>
      <header className='Experiment__header'>
        <Link
          className='Experiment__link'
          to={`/projects?project=${encodeURIComponent(experiment.project)}`}
        >
          ← {experiment.project}
        </Link>
        <div className='Experiment__title'>
          <Text component='h1' size={18} weight={600} tint={100}>
            {experiment.name}
          </Text>
          <Badge
            label={experiment.kind}
            color={STATUS_COLORS.neutral}
            size='small'
          />
        </div>
        {experiment.description && (
          <Text size={12} tint={50}>
            {experiment.description}
          </Text>
        )}
      </header>

      <Card
        title='Settings'
        subtitle='How this experiment is described and judged.'
      >
        <SettingsForm
          summary={summary}
          onSaved={() => setReload((n) => n + 1)}
        />
      </Card>

      <div className='Experiment__stats'>
        <Card
          title={stats.best ? fmtNumber(stats.best.value) : '–'}
          subtitle={
            stats.best
              ? `best ${experiment.primary_metric} (${direction})`
              : 'Set a primary metric to see the best result'
          }
        >
          {stats.best && (
            <Link
              className='Experiment__link'
              to={`/runs/${encodeURIComponent(stats.best.run_id)}`}
            >
              {stats.best.name}
            </Link>
          )}
        </Card>
        <Card
          title={`${stats.runs}`}
          subtitle={`runs (${stats.running} running)`}
        />
      </div>

      <Card title='Runs' subtitle='Select runs to compare them side by side.'>
        <div className='Experiment__toolbar'>
          <div className='Experiment__sort'>
            <OutlinedField
              id='experiment-sort'
              label='Sort'
              select
              value={sort}
              onValueChange={setSort}
            >
              <MenuItem value='created_at:desc'>newest first</MenuItem>
              <MenuItem value='created_at:asc'>oldest first</MenuItem>
              <MenuItem value='primary_value:best'>best first</MenuItem>
            </OutlinedField>
          </div>
          <Button
            variant={selected.length ? 'contained' : 'outlined'}
            disabled={selected.length < 2 || selected.length > MAX_COMPARE}
            onClick={() => history.push(compareUrl(selected))}
          >
            {selected.length
              ? `Compare selected (${selected.length})`
              : 'Compare selected'}
          </Button>
          <Button
            variant='outlined'
            disabled={ranked.length < 2}
            onClick={() =>
              history.push(compareUrl(ranked.slice(0, TOP).map((r) => r.id)))
            }
          >
            {`Compare top ${Math.min(TOP, ranked.length)}`}
          </Button>
        </div>
        <Table
          columns={[
            { key: 'select', label: '' },
            { key: 'run', label: 'Run' },
            { key: 'status', label: 'Status' },
            {
              key: 'value',
              label: experiment.primary_metric || 'Primary value',
            },
            ...keys.map((key) => ({ key: `param:${key}`, label: key })),
            { key: 'started', label: 'Started' },
            { key: 'duration', label: 'Duration' },
            { key: 'commit', label: 'Commit' },
          ]}
          rows={rows.map((run) => {
            const cells: Record<string, React.ReactNode> = {
              id: run.id,
              select: (
                <input
                  type='checkbox'
                  className='Experiment__checkbox'
                  aria-label={`select ${run.name}`}
                  checked={selected.includes(run.id)}
                  onChange={(event) => toggle(run.id, event.target.checked)}
                />
              ),
              run: (
                <Link
                  className='Experiment__link'
                  to={`/runs/${encodeURIComponent(run.id)}`}
                >
                  {run.name}
                </Link>
              ),
              status: run.status,
              value: (
                <span
                  className={run.id === best ? 'Experiment__best' : undefined}
                >
                  {fmtNumber(run.primary_value)}
                </span>
              ),
              started: formatTime(run.started_at ?? run.created_at),
              duration: duration(run),
              commit: (
                <span className='Experiment__mono'>
                  {run.commit ? run.commit.slice(0, 8) : '–'}
                  {run.dirty ? ' +changes' : ''}
                </span>
              ),
            };
            keys.forEach((key) => {
              cells[`param:${key}`] =
                run.params && key in run.params ? (
                  <span className='Experiment__mono'>
                    {paramText(run.params[key])}
                  </span>
                ) : (
                  '–'
                );
            });
            return cells;
          })}
          rowKey='id'
          emptyText='No runs in this experiment yet.'
        />
      </Card>

      {valued.length > 0 && (
        <Card
          title={`${experiment.primary_metric} by run`}
          subtitle='Oldest run on the left.'
        >
          <ValueChart
            values={valued}
            label={experiment.primary_metric ?? 'primary metric'}
          />
        </Card>
      )}
    </>
  );
}

// The experiment named by the id query parameter.
function Experiment(): React.FunctionComponentElement<React.ReactNode> {
  const location = useLocation();
  const id = new URLSearchParams(location.search).get('id');
  return (
    <ErrorBoundary>
      <section className='Experiment'>
        {id ? (
          <ExperimentDetail key={id} id={id} />
        ) : (
          <Text size={12} color='error'>
            No experiment was given. Open an experiment from its project.
          </Text>
        )}
      </section>
    </ErrorBoundary>
  );
}

export default Experiment;

import React, { useEffect, useMemo, useState } from 'react';
import { Link, useHistory, useLocation } from 'react-router-dom';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

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
      <polyline points={points} fill='none' stroke='#2563eb' strokeWidth={2} />
      {values.map((v, i) => (
        <circle key={i} cx={x(i)} cy={y(v)} r={3} fill='#2563eb' />
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
      <label>
        Kind
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {EXPERIMENT_KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      <label>
        Description
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <label>
        Primary metric
        <input
          value={metric}
          placeholder='e.g. val_loss'
          onChange={(e) => setMetric(e.target.value)}
        />
      </label>
      <label>
        Better is
        <select
          value={direction}
          onChange={(e) => setDirection(e.target.value)}
        >
          {DIRECTIONS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </label>
      <div>
        <button type='submit'>Save</button>
      </div>
      <p className='Experiment__muted' role='status'>
        {message}
      </p>
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
      <p className='Experiment__error' role='alert'>
        {error}
      </p>
    );
  }
  if (!summary) {
    return <p className='Experiment__muted'>Loading…</p>;
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
      <p>
        <Link
          to={`/projects?project=${encodeURIComponent(experiment.project)}`}
        >
          ← {experiment.project}
        </Link>
      </p>
      <h1>
        {experiment.name}{' '}
        <span className='Experiment__kind'>{experiment.kind}</span>
      </h1>
      {experiment.description && (
        <p className='Experiment__muted'>{experiment.description}</p>
      )}

      <details className='Experiment__settings-box'>
        <summary>Settings</summary>
        <SettingsForm
          summary={summary}
          onSaved={() => setReload((n) => n + 1)}
        />
      </details>

      <div className='Experiment__cards'>
        <div className='Experiment__card'>
          <div className='Experiment__card-value'>
            {stats.best ? fmtNumber(stats.best.value) : '–'}
          </div>
          <div className='Experiment__muted'>
            {stats.best ? (
              <>
                best {experiment.primary_metric} ({direction}) ·{' '}
                <Link to={`/runs/${encodeURIComponent(stats.best.run_id)}`}>
                  {stats.best.name}
                </Link>
              </>
            ) : (
              'Set a primary metric to see the best result'
            )}
          </div>
        </div>
        <div className='Experiment__card'>
          <div className='Experiment__card-value'>{stats.runs}</div>
          <div className='Experiment__muted'>
            runs ({stats.running} running)
          </div>
        </div>
      </div>

      <h2>Runs</h2>
      <div className='Experiment__toolbar'>
        <label>
          Sort{' '}
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value='created_at:desc'>newest first</option>
            <option value='created_at:asc'>oldest first</option>
            <option value='primary_value:best'>best first</option>
          </select>
        </label>{' '}
        <button
          type='button'
          disabled={selected.length < 2 || selected.length > MAX_COMPARE}
          onClick={() => history.push(compareUrl(selected))}
        >
          {selected.length
            ? `Compare selected (${selected.length})`
            : 'Compare selected'}
        </button>{' '}
        <button
          type='button'
          disabled={ranked.length < 2}
          onClick={() =>
            history.push(compareUrl(ranked.slice(0, TOP).map((r) => r.id)))
          }
        >
          {`Compare top ${Math.min(TOP, ranked.length)}`}
        </button>
      </div>
      <table className='Experiment__table'>
        <thead>
          <tr>
            <th />
            <th>Run</th>
            <th>Status</th>
            <th>{experiment.primary_metric || 'Primary value'}</th>
            {keys.map((key) => (
              <th key={key}>{key}</th>
            ))}
            <th>Started</th>
            <th>Duration</th>
            <th>Commit</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((run) => (
            <tr key={run.id}>
              <td>
                <input
                  type='checkbox'
                  aria-label={`select ${run.name}`}
                  checked={selected.includes(run.id)}
                  onChange={(event) => toggle(run.id, event.target.checked)}
                />
              </td>
              <td>
                <Link to={`/runs/${encodeURIComponent(run.id)}`}>
                  {run.name}
                </Link>
              </td>
              <td>{run.status}</td>
              <td className={run.id === best ? 'Experiment__best' : undefined}>
                {fmtNumber(run.primary_value)}
              </td>
              {keys.map((key) => (
                <td key={key} className='Experiment__mono'>
                  {run.params && key in run.params
                    ? paramText(run.params[key])
                    : '–'}
                </td>
              ))}
              <td>{formatTime(run.started_at ?? run.created_at)}</td>
              <td>{duration(run)}</td>
              <td className='Experiment__mono'>
                {run.commit ? run.commit.slice(0, 8) : '–'}
                {run.dirty ? ' +changes' : ''}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7 + keys.length} className='Experiment__muted'>
                No runs in this experiment yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {valued.length > 0 && (
        <>
          <h3>{experiment.primary_metric} by run</h3>
          <ValueChart
            values={valued}
            label={experiment.primary_metric ?? 'primary metric'}
          />
        </>
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
          <p className='Experiment__error'>
            No experiment was given. Open an experiment from its project.
          </p>
        )}
      </section>
    </ErrorBoundary>
  );
}

export default Experiment;

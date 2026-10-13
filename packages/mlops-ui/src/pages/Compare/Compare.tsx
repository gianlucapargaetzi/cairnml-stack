import React, { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import compareService, {
  ICompareRun,
} from 'services/api/compare/compareService';

import {
  diffRows,
  MAX_COMPARE,
  metricWinner,
  parseCompareIds,
  setDiff,
} from 'utils/compare/compare';
import { colorFor } from 'utils/graph/layout';
import { fmtNumber } from 'utils/projects/projects';

import MultiLineChart from './MultiLineChart';

import './Compare.scss';

const cell = (value: unknown): string =>
  value === undefined || value === null
    ? '–'
    : typeof value === 'object'
    ? JSON.stringify(value)
    : String(value);

function CompareView({ ids }: { ids: string[] }) {
  const [runs, setRuns] = useState<ICompareRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyDiffs, setOnlyDiffs] = useState(true);

  useEffect(() => {
    const request = compareService.getCompare(ids);
    request
      .call()
      .then((data) => setRuns(data.runs))
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`The runs could not be compared: ${requestError.message}`);
        }
      });
    return () => request.abort();
  }, [ids.join(',')]);

  const names = useMemo(
    () =>
      runs
        ? [...new Set(runs.flatMap((run) => Object.keys(run.metrics)))].sort()
        : [],
    [runs],
  );
  const params = useMemo(
    () =>
      runs ? diffRows(runs, (run) => ({ ...run.config, ...run.params })) : [],
    [runs],
  );
  const code = useMemo(
    () =>
      runs
        ? diffRows(runs, (run) => ({
            repository: run.git?.repo,
            branch: run.git?.branch,
            commit: run.git?.commit?.slice(0, 8),
            'uncommitted changes': run.git
              ? run.git.dirty
                ? 'yes'
                : 'no'
              : undefined,
            script: run.script,
            python: run.python_version,
            platform: run.platform,
            ...Object.fromEntries(
              run.datasets.map((d) => [
                `data ${d.path}`,
                d.dvc_hash || 'unversioned',
              ]),
            ),
          }))
        : [],
    [runs],
  );

  if (error) {
    return (
      <p className='Compare__error' role='alert'>
        {error}
      </p>
    );
  }
  if (!runs) {
    return <p className='Compare__muted'>Loading…</p>;
  }
  const base = runs[0];
  const colored = runs.map((run, index) => ({
    ...run,
    color: colorFor(index),
  }));
  const shownParams = params.filter((row) => !onlyDiffs || row.differs);

  return (
    <>
      <p>
        <Link to='/runs'>← runs</Link>
      </p>
      <h1>Compare runs</h1>
      {ids.length > MAX_COMPARE && (
        <p className='Compare__muted'>
          Only the first {MAX_COMPARE} runs are compared.
        </p>
      )}
      <div className='Compare__chips'>
        {colored.map((run) => (
          <span key={run.id} className='Compare__chip'>
            <span
              className='Compare__swatch'
              style={{ background: run.color }}
            />
            <Link to={`/runs/${encodeURIComponent(run.id)}`}>{run.name}</Link>{' '}
            {run.status}
            {runs.length > 2 && (
              <>
                {' '}
                <Link
                  className='Compare__muted'
                  to={`/compare?ids=${encodeURIComponent(
                    ids.filter((x) => x !== run.id).join(','),
                  )}`}
                >
                  remove
                </Link>
              </>
            )}
          </span>
        ))}
      </div>

      <h2>Metrics</h2>
      {names.length === 0 && (
        <p className='Compare__muted'>None of these runs logged metrics.</p>
      )}
      <div className='Compare__charts'>
        {names.map((name) => (
          <section key={name} className='Compare__chart-box'>
            <h3>{name}</h3>
            <MultiLineChart
              label={`compare ${name}`}
              series={colored
                .filter((run) => run.metrics[name])
                .map((run) => ({
                  name: run.name,
                  color: run.color,
                  points: run.metrics[name].series,
                }))}
            />
          </section>
        ))}
      </div>
      {names.length > 0 && (
        <table className='Compare__table'>
          <thead>
            <tr>
              <th>Metric</th>
              {runs.map((run) => (
                <th key={run.id}>{run.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {names.map((name) => {
              const winner = metricWinner(runs, name);
              return (
                <tr key={name}>
                  <th>{name}</th>
                  {runs.map((run) => {
                    const m = run.metrics[name];
                    return (
                      <td
                        key={run.id}
                        className={
                          m && winner === run.id ? 'Compare__best' : undefined
                        }
                      >
                        {m
                          ? `${fmtNumber(m.last)} (${fmtNumber(
                              m.min,
                            )} – ${fmtNumber(m.max)})`
                          : '–'}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <h2>Parameters</h2>
      <label className='Compare__muted'>
        <input
          type='checkbox'
          checked={onlyDiffs}
          onChange={(e) => setOnlyDiffs(e.target.checked)}
        />{' '}
        only differences
      </label>
      {shownParams.length ? (
        <table className='Compare__table'>
          <thead>
            <tr>
              <th>Parameter</th>
              {runs.map((run) => (
                <th key={run.id}>{run.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shownParams.map((row) => (
              <tr
                key={row.key}
                className={row.differs ? 'Compare__differs' : undefined}
              >
                <th>{row.key}</th>
                {row.values.map((value, index) => (
                  <td key={index} className='Compare__mono'>
                    {cell(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className='Compare__muted'>
          {onlyDiffs
            ? 'All parameters are identical.'
            : 'No parameters recorded.'}
        </p>
      )}

      <h2>Code and data</h2>
      <table className='Compare__table'>
        <thead>
          <tr>
            <th />
            {runs.map((run) => (
              <th key={run.id}>{run.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {code.map((row) => (
            <tr
              key={row.key}
              className={row.differs ? 'Compare__differs' : undefined}
            >
              <th>{row.key}</th>
              {row.values.map((value, index) => (
                <td key={index} className='Compare__mono'>
                  {cell(value)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {runs.slice(1).map((run) => {
        const diff = setDiff(base.requirements, run.requirements);
        const lines = [
          ...diff.added.map((x) => `+ ${x}`),
          ...diff.removed.map((x) => `- ${x}`),
        ];
        return (
          <details key={run.id} className='Compare__packages'>
            <summary>
              {run.name} vs {base.name}: +{diff.added.length} added, −
              {diff.removed.length} removed
            </summary>
            <pre>{lines.join('\n') || 'identical'}</pre>
          </details>
        );
      })}
    </>
  );
}

// The runs named by the ids query parameter, compared side by side.
function Compare(): React.FunctionComponentElement<React.ReactNode> {
  const location = useLocation();
  const ids = parseCompareIds(
    new URLSearchParams(location.search).get('ids') ?? '',
  );
  return (
    <ErrorBoundary>
      <section className='Compare'>
        {ids.length >= 2 ? (
          <CompareView key={ids.join(',')} ids={ids} />
        ) : (
          <>
            <h1>Compare runs</h1>
            <p className='Compare__muted'>
              Select two or more runs in the list and press “Compare selected”.
            </p>
            <Link to='/runs'>Go to runs</Link>
          </>
        )}
      </section>
    </ErrorBoundary>
  );
}

export default Compare;

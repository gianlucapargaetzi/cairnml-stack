import React, { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';
import { Badge, Card, Table, Text } from 'components/kit';

import { STATUS_COLORS } from 'config/colors/colors';

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
      <header className='Compare__header'>
        <Link className='Compare__link' to='/runs'>
          ← Runs
        </Link>
        <Text component='h1' size={18} weight={600} tint={100}>
          Compare runs
        </Text>
        {ids.length > MAX_COMPARE && (
          <Text size={12} tint={50}>
            {`Only the first ${MAX_COMPARE} runs are compared.`}
          </Text>
        )}
      </header>

      <Card
        title='Runs'
        subtitle='Each run keeps its colour in the charts below.'
      >
        <div className='Compare__chips'>
          {colored.map((run) => (
            <div key={run.id} className='Compare__chip'>
              <span
                className='Compare__swatch'
                style={{ background: run.color }}
              />
              <Link
                className='Compare__link'
                to={`/runs/${encodeURIComponent(run.id)}`}
              >
                {run.name}
              </Link>
              <Badge
                label={run.status}
                size='small'
                color={STATUS_COLORS.neutral}
              />
              {runs.length > 2 && (
                <Link
                  className='Compare__muted-link'
                  to={`/compare?ids=${encodeURIComponent(
                    ids.filter((x) => x !== run.id).join(','),
                  )}`}
                >
                  Remove
                </Link>
              )}
            </div>
          ))}
        </div>
      </Card>

      <Card title='Metrics'>
        {names.length === 0 && (
          <Text size={12} tint={50}>
            None of these runs logged metrics.
          </Text>
        )}
        <div className='Compare__charts'>
          {names.map((name) => (
            <section key={name} className='Compare__chart-box'>
              <Text component='h3' size={14} weight={600} tint={100}>
                {name}
              </Text>
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
          <Table
            columns={[
              { key: 'metric', label: 'Metric' },
              ...runs.map((run) => ({ key: run.id, label: run.name })),
            ]}
            rows={names.map((name) => {
              const winner = metricWinner(runs, name);
              const row: { [key: string]: React.ReactNode } = {
                id: name,
                metric: name,
              };
              runs.forEach((run) => {
                const m = run.metrics[name];
                const text = m
                  ? `${fmtNumber(m.last)} (${fmtNumber(m.min)} – ${fmtNumber(
                      m.max,
                    )})`
                  : '–';
                row[run.id] =
                  m && winner === run.id ? (
                    <span className='Compare__best'>{text}</span>
                  ) : (
                    text
                  );
              });
              return row;
            })}
            rowKey='id'
          />
        )}
      </Card>

      <Card title='Parameters'>
        <label className='Compare__toggle'>
          <input
            type='checkbox'
            checked={onlyDiffs}
            onChange={(e) => setOnlyDiffs(e.target.checked)}
          />
          <Text size={12} tint={50}>
            Only differences
          </Text>
        </label>
        {shownParams.length ? (
          <Table
            columns={[
              { key: 'parameter', label: 'Parameter' },
              ...runs.map((run) => ({ key: run.id, label: run.name })),
            ]}
            rows={shownParams.map((row) => {
              const out: { [key: string]: React.ReactNode } = {
                id: row.key,
                parameter: row.differs ? (
                  <span className='Compare__differs'>{row.key}</span>
                ) : (
                  row.key
                ),
              };
              row.values.forEach((value, index) => {
                out[runs[index].id] = (
                  <span className='Compare__mono'>{cell(value)}</span>
                );
              });
              return out;
            })}
            rowKey='id'
          />
        ) : (
          <Text size={12} tint={50}>
            {onlyDiffs
              ? 'All parameters are identical.'
              : 'No parameters recorded.'}
          </Text>
        )}
      </Card>

      <Card title='Code and data'>
        <Table
          columns={[
            { key: 'field', label: '' },
            ...runs.map((run) => ({ key: run.id, label: run.name })),
          ]}
          rows={code.map((row) => {
            const out: { [key: string]: React.ReactNode } = {
              id: row.key,
              field: row.differs ? (
                <span className='Compare__differs'>{row.key}</span>
              ) : (
                row.key
              ),
            };
            row.values.forEach((value, index) => {
              out[runs[index].id] = (
                <span className='Compare__mono'>{cell(value)}</span>
              );
            });
            return out;
          })}
          rowKey='id'
        />
        {runs.slice(1).map((run) => {
          const diff = setDiff(base.requirements, run.requirements);
          const lines = [
            ...diff.added.map((x) => `+ ${x}`),
            ...diff.removed.map((x) => `- ${x}`),
          ];
          return (
            <details key={run.id} className='Compare__packages'>
              <summary>
                <Text size={12} component='span'>
                  {`${run.name} vs ${base.name}: +${diff.added.length} added, −${diff.removed.length} removed`}
                </Text>
              </summary>
              <pre className='Compare__mono'>
                {lines.join('\n') || 'identical'}
              </pre>
            </details>
          );
        })}
      </Card>
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
          <Card
            title='Compare runs'
            subtitle='Select two or more runs in the list and press “Compare selected”.'
          >
            <Link className='Compare__link' to='/runs'>
              Go to runs
            </Link>
          </Card>
        )}
      </section>
    </ErrorBoundary>
  );
}

export default Compare;

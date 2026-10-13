import React, { useCallback, useEffect, useState } from 'react';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import resourcesService, {
  IResourceAgent,
  IResources,
} from 'services/api/resources/resourcesService';

import {
  barPercent,
  capabilityText,
  fmtDuration,
  queueState,
  QueueState,
  usageLabel,
} from 'utils/resources/resources';

import './Resources.scss';

const REFRESH_MS = 5000;

const STATE_LABEL: Record<QueueState, string> = {
  stuck: 'stuck: no online agent serves this queue',
  busy: 'busy',
  idle: 'idle',
};

function Meter({
  label,
  used,
  total,
  unit,
}: {
  label: string;
  used: number;
  total: number;
  unit: string;
}) {
  return (
    <div className='Resources__meter'>
      <div className='Resources__meter-label'>
        {label}: {usageLabel(used, total, unit)}
      </div>
      <div className='Resources__track'>
        <div
          className='Resources__fill'
          style={{ width: `${barPercent(used, total)}%` }}
        />
      </div>
    </div>
  );
}

function AgentCard({ agent }: { agent: IResourceAgent }) {
  const caps = agent.capabilities;
  const free = agent.free;
  const usage = agent.usage;
  return (
    <section className='Resources__agent'>
      <h2>
        <span
          className={`Resources__dot ${
            agent.online ? 'Resources__dot--on' : ''
          }`}
          role='img'
          aria-label={agent.online ? 'online' : 'offline'}
        />{' '}
        {agent.name}{' '}
        <span className='Resources__muted'>
          {agent.online
            ? 'online'
            : `offline, last seen ${
                agent.last_seen
                  ? new Date(agent.last_seen).toLocaleString()
                  : '–'
              }`}
        </span>
      </h2>
      <p className='Resources__muted'>
        queues: {agent.queues.join(', ') || 'none'} · runtimes:{' '}
        {caps.runtimes.join(', ') || 'none'}
        {caps.labels.length ? ` · labels: ${caps.labels.join(', ')}` : ''}
        {caps.docker ? '' : ' · no docker'}
      </p>
      <p>{capabilityText(caps)}</p>
      <h3>Allocated to jobs</h3>
      <Meter
        label='CPU'
        used={caps.cpu - free.cpu}
        total={caps.cpu}
        unit='cpu'
      />
      <Meter
        label='Memory'
        used={caps.memory_gb - free.memory_gb}
        total={caps.memory_gb}
        unit='GB'
      />
      {caps.gpus > 0 && (
        <Meter
          label='GPU'
          used={caps.gpus - free.gpu}
          total={caps.gpus}
          unit='gpu'
        />
      )}
      <h3>
        Actually in use{' '}
        {agent.usage_at && (
          <span className='Resources__muted'>
            (sampled {fmtDuration(agent.usage_at, null)} ago)
          </span>
        )}
      </h3>
      {usage ? (
        <>
          <Meter label='CPU' used={usage.cpu_percent} total={100} unit='%' />
          <Meter
            label='Memory'
            used={usage.mem_used_gb}
            total={usage.mem_total_gb}
            unit='GB'
          />
          {usage.gpus.map((gpu) => (
            <React.Fragment key={gpu.index}>
              <Meter
                label={`GPU ${gpu.index} compute`}
                used={gpu.util_percent}
                total={100}
                unit='%'
              />
              <Meter
                label={`GPU ${gpu.index} memory`}
                used={gpu.mem_used_gb}
                total={gpu.mem_total_gb}
                unit='GB'
              />
            </React.Fragment>
          ))}
        </>
      ) : (
        <p className='Resources__muted'>No usage reported yet.</p>
      )}
      <h3>Running jobs</h3>
      {agent.running_jobs.length ? (
        <ul>
          {agent.running_jobs.map((job, index) => (
            <li key={index}>
              {job.run_name} ({job.project})
            </li>
          ))}
        </ul>
      ) : (
        <p className='Resources__muted'>Idle.</p>
      )}
      {agent.other_running_jobs > 0 && (
        <p className='Resources__muted'>
          {agent.other_running_jobs} more in projects you are not in.
        </p>
      )}
    </section>
  );
}

function queueWait(seconds: number | null): string {
  return seconds === null
    ? '–'
    : fmtDuration(new Date(Date.now() - seconds * 1000).toISOString(), null);
}

function Resources(): React.FunctionComponentElement<React.ReactNode> {
  const [data, setData] = useState<IResources | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    const request = resourcesService.getResources();
    request
      .call()
      .then((next) => {
        setData(next);
        setError(null);
      })
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`Resources could not be loaded: ${requestError.message}`);
        }
      });
    return request;
  }, []);

  useEffect(() => {
    let request = refresh();
    const timer = window.setInterval(() => {
      request.abort();
      request = refresh();
    }, REFRESH_MS);
    return () => {
      window.clearInterval(timer);
      request.abort();
    };
  }, [refresh]);

  return (
    <ErrorBoundary>
      <section className='Resources'>
        <h1>Resources</h1>
        {error && (
          <p className='Resources__error' role='alert'>
            {error}
          </p>
        )}
        {data && data.agents.length > 0 && (
          <div className='Resources__grid'>
            {data.agents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}
        {data && data.agents.length === 0 && (
          <p className='Resources__muted'>
            No agents are registered. An administrator creates a token with{' '}
            <code>mlops admin agent-token</code> and starts an agent.
          </p>
        )}
        <h2>Queues</h2>
        <table className='Resources__table'>
          <thead>
            <tr>
              <th>Queue</th>
              <th>Queued</th>
              <th>Running</th>
              <th>Serving agents</th>
              <th>Oldest wait</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {(data?.queues ?? []).map((queue) => {
              const state = queueState(queue);
              return (
                <tr key={queue.name}>
                  <td>{queue.name}</td>
                  <td>{queue.queued}</td>
                  <td>{queue.running}</td>
                  <td>{queue.agents}</td>
                  <td>{queueWait(queue.oldest_wait_s)}</td>
                  <td className={`Resources__state Resources__state--${state}`}>
                    {STATE_LABEL[state]}
                  </td>
                </tr>
              );
            })}
            {data && data.queues.length === 0 && (
              <tr>
                <td colSpan={6} className='Resources__muted'>
                  No queues yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </ErrorBoundary>
  );
}

export default Resources;

import React, { useCallback, useEffect, useState } from 'react';

import { Badge, Card, DefinitionList, Table, Text } from 'components/kit';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import { STATUS_COLORS } from 'config/colors/colors';

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

const STATE_COLOR: Record<QueueState, string> = {
  stuck: STATUS_COLORS.error,
  busy: STATUS_COLORS.warning,
  idle: STATUS_COLORS.success,
};

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
        <Text size={12} weight={600} tint={60}>
          {label}: {usageLabel(used, total, unit)}
        </Text>
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
  const status = agent.online
    ? 'Online'
    : `Offline, last seen ${
        agent.last_seen ? new Date(agent.last_seen).toLocaleString() : '–'
      }`;
  return (
    <Card title={agent.name} subtitle={status}>
      <div className='Resources__status'>
        <Badge
          label={agent.online ? 'Online' : 'Offline'}
          color={agent.online ? STATUS_COLORS.success : STATUS_COLORS.error}
          size='small'
        />
      </div>
      <DefinitionList
        items={[
          { label: 'Queues', value: agent.queues.join(', ') || 'none' },
          { label: 'Runtimes', value: caps.runtimes.join(', ') || 'none' },
          { label: 'Labels', value: caps.labels.join(', ') || 'none' },
          { label: 'Docker', value: caps.docker ? 'Yes' : 'No' },
        ]}
      />
      <Text size={12}>{capabilityText(caps)}</Text>

      <Text component='h3' size={14} weight={600} tint={100}>
        Allocated to jobs
      </Text>
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

      <Text component='h3' size={14} weight={600} tint={100}>
        Actually in use
      </Text>
      {agent.usage_at && (
        <Text size={12} tint={50}>
          {`Sampled ${fmtDuration(agent.usage_at, null)} ago`}
        </Text>
      )}
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
        <Text size={12} tint={50}>
          No usage reported yet.
        </Text>
      )}

      <Text component='h3' size={14} weight={600} tint={100}>
        Running jobs
      </Text>
      {agent.running_jobs.length ? (
        agent.running_jobs.map((job, index) => (
          <Text key={index} size={12}>
            {`${job.run_name} (${job.project})`}
          </Text>
        ))
      ) : (
        <Text size={12} tint={50}>
          Idle.
        </Text>
      )}
      {agent.other_running_jobs > 0 && (
        <Text size={12} tint={50}>
          {`${agent.other_running_jobs} more in projects you are not in.`}
        </Text>
      )}
    </Card>
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
        <header className='Resources__header'>
          <Text component='h1' size={18} weight={600} tint={100}>
            Resources
          </Text>
          <Text size={12} tint={50}>
            Agents, what they run, and the queues waiting for them. Refreshes
            every few seconds.
          </Text>
        </header>
        {error && (
          <Text size={12} color='error' role='alert'>
            {error}
          </Text>
        )}
        {data && data.agents.length > 0 && (
          <div className='Resources__grid'>
            {data.agents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}
        {data && data.agents.length === 0 && (
          <Text size={12} tint={50}>
            No agents are registered. An administrator creates a token with
            mlops admin agent-token and starts an agent.
          </Text>
        )}
        <Card title='Queues' subtitle='Jobs waiting or running, per queue.'>
          <Table
            columns={[
              { key: 'queue', label: 'Queue' },
              { key: 'queued', label: 'Queued' },
              { key: 'running', label: 'Running' },
              { key: 'agents', label: 'Serving agents' },
              { key: 'wait', label: 'Oldest wait' },
              { key: 'state', label: 'State' },
            ]}
            rows={(data?.queues ?? []).map((queue) => {
              const state = queueState(queue);
              return {
                id: queue.name,
                queue: queue.name,
                queued: queue.queued,
                running: queue.running,
                agents: queue.agents,
                wait: queueWait(queue.oldest_wait_s),
                state: (
                  <Badge
                    label={STATE_LABEL[state]}
                    color={STATE_COLOR[state]}
                    size='small'
                  />
                ),
              };
            })}
            rowKey='id'
            emptyText='No queues yet.'
          />
        </Card>
      </section>
    </ErrorBoundary>
  );
}

export default Resources;

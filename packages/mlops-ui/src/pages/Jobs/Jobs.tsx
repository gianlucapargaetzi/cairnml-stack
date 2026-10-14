import React, { useCallback, useEffect, useState } from 'react';

import {
  Badge,
  Button,
  Card,
  DefinitionList,
  Table,
  Text,
} from 'components/kit';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import { STATUS_COLORS } from 'config/colors/colors';

import jobsService, { IJobRow, IJobSpec } from 'services/api/jobs/jobsService';

import { canCancel, JOB_GROUPS, JobGroup, jobGroup } from 'utils/jobs/jobs';

import JobRescheduleForm from './JobRescheduleForm';

import './Jobs.scss';

const REFRESH_MS = 5000;

// Badge colour for a job status. Failures are red, finished jobs green, cancelled jobs amber.
function statusColor(status: string): string {
  if (status === 'failed' || status === 'error') {
    return STATUS_COLORS.error;
  }
  if (status === 'finished' || status === 'succeeded') {
    return STATUS_COLORS.success;
  }
  if (status === 'cancelled' || status === 'canceled') {
    return STATUS_COLORS.warning;
  }
  return STATUS_COLORS.primary;
}

function formatTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '–';
}

function Jobs(): React.FunctionComponentElement<React.ReactNode> {
  const [rows, setRows] = useState<IJobRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [group, setGroup] = useState<JobGroup>('active');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [spec, setSpec] = useState<IJobSpec | null>(null);
  const [copying, setCopying] = useState(false);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);

  const refresh = useCallback(() => {
    const request = jobsService.getJobs();
    request
      .call()
      .then((data) => {
        setRows(data);
        setError(null);
        setRefreshedAt(new Date());
      })
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`Jobs could not be loaded: ${requestError.message}`);
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

  // A spec never changes, so it is fetched once per selected job.
  useEffect(() => {
    setSpec(null);
    setCopying(false);
    if (!selectedId) {
      return undefined;
    }
    const request = jobsService.getJobSpec(selectedId);
    request
      .call()
      .then((data) => setSpec(data))
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`The job spec could not be loaded: ${requestError.message}`);
        }
      });
    return () => request.abort();
  }, [selectedId]);

  const counts = Object.fromEntries(
    JOB_GROUPS.map(({ key }) => [
      key,
      rows.filter((job) => jobGroup(job.status) === key).length,
    ]),
  );
  const shown = rows.filter((job) => jobGroup(job.status) === group);
  const selected = rows.find((job) => job.id === selectedId) ?? null;

  function cancel(job: IJobRow) {
    jobsService
      .cancelJob(job.id)
      .call()
      .then(() => {
        setBanner(`Cancel requested for ${job.id}.`);
        refresh();
      })
      .catch((requestError) =>
        setBanner(`Could not cancel: ${requestError.message}`),
      );
  }

  return (
    <ErrorBoundary>
      <section className='Jobs'>
        <header className='Jobs__header'>
          <div className='Jobs__title'>
            <Text component='h1' size={18} weight={600} tint={100}>
              Jobs
            </Text>
            <Text size={12} tint={50}>
              {refreshedAt
                ? `Updated ${refreshedAt.toLocaleTimeString()}`
                : 'Loading'}
            </Text>
          </div>
          <Button variant='outlined' size='small' onClick={refresh}>
            Refresh
          </Button>
        </header>

        {banner && (
          <Text size={12} color='success' role='status'>
            {banner}
          </Text>
        )}
        {error && (
          <Text size={12} color='error' role='alert'>
            {error}
          </Text>
        )}

        <div className='Jobs__body'>
          <Card
            title='Jobs'
            subtitle='Runs dispatched to agents. Select a job to see its spec.'
          >
            <div className='Jobs__groups' role='group' aria-label='Job groups'>
              {JOB_GROUPS.map(({ key, label }) => (
                <Button
                  key={key}
                  size='small'
                  variant={group === key ? 'contained' : 'outlined'}
                  color={group === key ? 'secondary' : 'primary'}
                  aria-pressed={group === key}
                  onClick={() => setGroup(key)}
                >
                  {label} ({counts[key]})
                </Button>
              ))}
            </div>
            <Table
              columns={[
                { key: 'run', label: 'Run' },
                { key: 'project', label: 'Project' },
                { key: 'status', label: 'Status' },
                { key: 'queue', label: 'Queue' },
                { key: 'agent', label: 'Agent' },
                { key: 'created', label: 'Created' },
                { key: 'action', label: '' },
              ]}
              rows={shown.map((job) => ({
                id: job.id,
                run: job.run_name,
                project: job.project,
                status: (
                  <Badge
                    label={
                      job.cancel_requested
                        ? `${job.status}, cancelling`
                        : job.status
                    }
                    color={statusColor(job.status)}
                    size='small'
                  />
                ),
                queue: job.queue,
                agent: job.agent_name ?? '–',
                created: formatTime(job.created_at),
                action:
                  canCancel(job) && !job.cancel_requested ? (
                    <Button
                      variant='outlined'
                      size='small'
                      onClick={(event: React.MouseEvent) => {
                        event.stopPropagation();
                        cancel(job);
                      }}
                    >
                      Cancel
                    </Button>
                  ) : null,
              }))}
              rowKey='id'
              onRowClick={setSelectedId}
              selectedRowKey={selectedId ?? undefined}
              emptyText='No jobs in this group.'
            />
          </Card>

          <aside className='Jobs__detail' aria-label='Job detail'>
            {!selected && (
              <Card title='Job detail'>
                <Text size={12} tint={50}>
                  Select a job to see its spec.
                </Text>
              </Card>
            )}
            {selected && (
              <Card title={selected.run_name} subtitle={selected.id}>
                <DefinitionList
                  items={[
                    { label: 'Job', value: selected.id, mono: true },
                    { label: 'Run', value: selected.run_id, mono: true },
                    { label: 'Status', value: selected.status },
                    { label: 'Agent', value: selected.agent_name ?? '–' },
                    { label: 'Exit code', value: selected.exit_code ?? '–' },
                    { label: 'Message', value: selected.message ?? '–' },
                    {
                      label: 'Assigned',
                      value: formatTime(selected.assigned_at),
                    },
                    {
                      label: 'Finished',
                      value: formatTime(selected.finished_at),
                    },
                  ]}
                />
                {spec && (
                  <DefinitionList
                    items={[
                      { label: 'Project', value: spec.project },
                      { label: 'Experiment', value: spec.experiment },
                      {
                        label: 'Resources',
                        value: `${spec.resources.cpu} cpu, ${spec.resources.memory_gb} GB, ${spec.resources.gpu} gpu`,
                      },
                      {
                        label: 'Labels',
                        value: spec.resources.labels.join(', ') || '–',
                      },
                      {
                        label: 'Timeout',
                        value: spec.timeout_s ? `${spec.timeout_s} s` : 'none',
                      },
                      {
                        label: 'Code',
                        value: spec.code
                          ? `${spec.code.repo} @ ${spec.code.commit.slice(
                              0,
                              10,
                            )}`
                          : 'none',
                        mono: true,
                      },
                      {
                        label: 'Parameters',
                        value: Object.keys(spec.params).length
                          ? Object.entries(spec.params)
                              .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                              .join(', ')
                          : 'none',
                        mono: true,
                      },
                      {
                        label: 'Env keys',
                        value: Object.keys(spec.env).join(', ') || 'none',
                        mono: true,
                      },
                    ]}
                  />
                )}
                <div className='Jobs__actions'>
                  {canCancel(selected) && !selected.cancel_requested && (
                    <Button variant='outlined' onClick={() => cancel(selected)}>
                      Cancel job
                    </Button>
                  )}
                  {spec && !copying && (
                    <Button variant='outlined' onClick={() => setCopying(true)}>
                      Copy and reschedule
                    </Button>
                  )}
                </div>
                {spec && copying && (
                  <JobRescheduleForm
                    job={selected}
                    spec={spec}
                    onClose={() => setCopying(false)}
                    onCreated={(created) => {
                      setBanner(
                        `Queued job ${created.id} as a copy of ${selected.id}.`,
                      );
                      setCopying(false);
                      setSelectedId(created.id);
                      refresh();
                    }}
                  />
                )}
              </Card>
            )}
          </aside>
        </div>
      </section>
    </ErrorBoundary>
  );
}

export default Jobs;

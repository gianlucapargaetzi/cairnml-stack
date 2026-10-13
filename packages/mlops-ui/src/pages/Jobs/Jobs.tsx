import React, { useCallback, useEffect, useState } from 'react';

import Button from 'components/kit_v2/Button';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import jobsService, { IJobRow, IJobSpec } from 'services/api/jobs/jobsService';

import { canCancel, JOB_GROUPS, JobGroup, jobGroup } from 'utils/jobs/jobs';

import JobRescheduleForm from './JobRescheduleForm';

import './Jobs.scss';

const REFRESH_MS = 5000;

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
          <h1>Jobs</h1>
          <span className='Jobs__muted'>
            {refreshedAt
              ? `Updated ${refreshedAt.toLocaleTimeString()}`
              : 'Loading…'}
          </span>
          <Button onClick={refresh}>Refresh</Button>
        </header>
        {banner && (
          <p className='Jobs__banner' role='status'>
            {banner}
          </p>
        )}
        {error && (
          <p className='Jobs__error' role='alert'>
            {error}
          </p>
        )}
        <div className='Jobs__body'>
          <div className='Jobs__list'>
            <nav className='Jobs__groups' aria-label='Job groups'>
              {JOB_GROUPS.map(({ key, label }) => (
                <button
                  key={key}
                  type='button'
                  className={
                    group === key
                      ? 'Jobs__group Jobs__group--active'
                      : 'Jobs__group'
                  }
                  onClick={() => setGroup(key)}
                >
                  {label} ({counts[key]})
                </button>
              ))}
            </nav>
            <table className='Jobs__table'>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Project</th>
                  <th>Status</th>
                  <th>Queue</th>
                  <th>Agent</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {shown.map((job) => (
                  <tr
                    key={job.id}
                    className={
                      job.id === selectedId
                        ? 'Jobs__row Jobs__row--selected'
                        : 'Jobs__row'
                    }
                    onClick={() => setSelectedId(job.id)}
                  >
                    <td>{job.run_name}</td>
                    <td>{job.project}</td>
                    <td>
                      {job.cancel_requested
                        ? `${job.status}, cancelling`
                        : job.status}
                    </td>
                    <td>{job.queue}</td>
                    <td>{job.agent_name ?? '–'}</td>
                    <td>{formatTime(job.created_at)}</td>
                    <td>
                      {canCancel(job) && !job.cancel_requested && (
                        <Button
                          onClick={(event: React.MouseEvent) => {
                            event.stopPropagation();
                            cancel(job);
                          }}
                        >
                          Cancel
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
                {shown.length === 0 && (
                  <tr>
                    <td colSpan={7} className='Jobs__muted'>
                      No jobs in this group.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <aside className='Jobs__detail' aria-label='Job detail'>
            {!selected && (
              <p className='Jobs__muted'>Select a job to see its spec.</p>
            )}
            {selected && (
              <>
                <h2>{selected.run_name}</h2>
                <dl className='Jobs__facts'>
                  <dt>Job</dt>
                  <dd className='mono'>{selected.id}</dd>
                  <dt>Run</dt>
                  <dd className='mono'>{selected.run_id}</dd>
                  <dt>Status</dt>
                  <dd>{selected.status}</dd>
                  <dt>Agent</dt>
                  <dd>{selected.agent_name ?? '–'}</dd>
                  <dt>Exit code</dt>
                  <dd>{selected.exit_code ?? '–'}</dd>
                  <dt>Message</dt>
                  <dd>{selected.message ?? '–'}</dd>
                  <dt>Assigned</dt>
                  <dd>{formatTime(selected.assigned_at)}</dd>
                  <dt>Finished</dt>
                  <dd>{formatTime(selected.finished_at)}</dd>
                </dl>
                {spec && (
                  <dl className='Jobs__facts'>
                    <dt>Project</dt>
                    <dd>{spec.project}</dd>
                    <dt>Experiment</dt>
                    <dd>{spec.experiment}</dd>
                    <dt>Resources</dt>
                    <dd>
                      {spec.resources.cpu} cpu, {spec.resources.memory_gb} GB,{' '}
                      {spec.resources.gpu} gpu
                    </dd>
                    <dt>Labels</dt>
                    <dd>{spec.resources.labels.join(', ') || '–'}</dd>
                    <dt>Timeout</dt>
                    <dd>{spec.timeout_s ? `${spec.timeout_s} s` : 'none'}</dd>
                    <dt>Code</dt>
                    <dd className='mono'>
                      {spec.code
                        ? `${spec.code.repo} @ ${spec.code.commit.slice(0, 10)}`
                        : 'none'}
                    </dd>
                    <dt>Parameters</dt>
                    <dd className='mono'>
                      {Object.keys(spec.params).length
                        ? Object.entries(spec.params)
                            .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                            .join(', ')
                        : 'none'}
                    </dd>
                    <dt>Env keys</dt>
                    <dd className='mono'>
                      {Object.keys(spec.env).join(', ') || 'none'}
                    </dd>
                  </dl>
                )}
                <div className='Jobs__detail-actions'>
                  {canCancel(selected) && !selected.cancel_requested && (
                    <Button onClick={() => cancel(selected)}>Cancel job</Button>
                  )}
                  {spec && !copying && (
                    <Button onClick={() => setCopying(true)}>
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
              </>
            )}
          </aside>
        </div>
      </section>
    </ErrorBoundary>
  );
}

export default Jobs;

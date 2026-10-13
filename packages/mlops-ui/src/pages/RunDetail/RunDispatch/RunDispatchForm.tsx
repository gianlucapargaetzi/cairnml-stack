import React, { useState } from 'react';
import { Link } from 'react-router-dom';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import jobsService from 'services/api/jobs/jobsService';

import { dispatchBody } from 'utils/jobs/dispatch';

import './RunDispatch.scss';

// Schedules this run as a job on an agent, as `mlops dispatch` does. The job appears on the jobs
// page; a copy with other resources is made there.
function RunDispatchForm({ runId }: { runId: string }) {
  const [form, setForm] = useState({
    queue: 'default',
    cpu: '',
    memory_gb: '',
    gpu: '',
    labels: '',
  });
  const [message, setMessage] = useState<React.ReactNode>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function set(field: keyof typeof form) {
    return (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [field]: event.target.value }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    let body;
    try {
      body = dispatchBody(form);
    } catch (parseError) {
      setError(`Could not dispatch: ${(parseError as Error).message}`);
      return;
    }
    setBusy(true);
    setError(null);
    setMessage('Queueing…');
    jobsService
      .dispatchRun(runId, body)
      .call()
      .then((job) =>
        setMessage(
          <>
            Queued job <span className='RunDispatch__mono'>{job.id}</span>.
            Follow it in the <Link to='/jobs'>Jobs page</Link>.
          </>,
        ),
      )
      .catch((requestError) => {
        setMessage(null);
        setError(`Could not dispatch: ${requestError.message}`);
      })
      .finally(() => setBusy(false));
  }

  return (
    <ErrorBoundary>
      <form
        className='RunDispatch'
        onSubmit={submit}
        aria-label='Run on an agent'
      >
        <h3>Run on an agent</h3>
        <label>
          Queue
          <input value={form.queue} onChange={set('queue')} />
        </label>
        <label>
          CPU
          <input type='number' min={0} value={form.cpu} onChange={set('cpu')} />
        </label>
        <label>
          Memory GB
          <input
            type='number'
            min={0}
            step='any'
            value={form.memory_gb}
            onChange={set('memory_gb')}
          />
        </label>
        <label>
          GPU
          <input type='number' min={0} value={form.gpu} onChange={set('gpu')} />
        </label>
        <label>
          Labels
          <input
            placeholder='comma separated'
            value={form.labels}
            onChange={set('labels')}
          />
        </label>
        <button type='submit' disabled={busy}>
          Dispatch as job
        </button>
        {error && (
          <p className='RunDispatch__error' role='alert'>
            {error}
          </p>
        )}
        {message && (
          <p className='RunDispatch__muted' role='status'>
            {message}
          </p>
        )}
      </form>
    </ErrorBoundary>
  );
}

export default RunDispatchForm;

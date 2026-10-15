import React, { useState } from 'react';
import { Link } from 'react-router-dom';

import { Button, Card, Text } from 'components/kit';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';
import OutlinedField from 'components/OutlinedField/OutlinedField';

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
    return (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
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
      <Card
        title='Run on an agent'
        subtitle='Schedules this run as a job on an agent, as mlops dispatch does.'
        className='RunDispatch'
      >
        <form onSubmit={submit} aria-label='Run on an agent'>
          <div className='RunDispatch__fields'>
            <OutlinedField
              id='dispatch-queue'
              label='Queue'
              value={form.queue}
              onChange={set('queue')}
            />
            <OutlinedField
              id='dispatch-cpu'
              label='CPU'
              numeric
              value={form.cpu}
              onChange={set('cpu')}
            />
            <OutlinedField
              id='dispatch-memory-gb'
              label='Memory GB'
              numeric
              value={form.memory_gb}
              onChange={set('memory_gb')}
            />
            <OutlinedField
              id='dispatch-gpu'
              label='GPU'
              numeric
              value={form.gpu}
              onChange={set('gpu')}
            />
            <div className='RunDispatch__wide'>
              <OutlinedField
                id='dispatch-labels'
                label='Labels'
                placeholder='comma separated'
                value={form.labels}
                onChange={set('labels')}
              />
            </div>
          </div>
          <div className='RunDispatch__actions'>
            <Button variant='contained' type='submit' disabled={busy}>
              Dispatch as job
            </Button>
          </div>
          {error && (
            <Text size={12} color='error' role='alert'>
              {error}
            </Text>
          )}
          {message && (
            <Text size={12} tint={70} role='status'>
              {message}
            </Text>
          )}
        </form>
      </Card>
    </ErrorBoundary>
  );
}

export default RunDispatchForm;

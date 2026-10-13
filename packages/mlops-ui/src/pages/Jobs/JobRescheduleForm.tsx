import React, { useState } from 'react';

import Button from 'components/kit_v2/Button';

import jobsService, { IJobRow, IJobSpec } from 'services/api/jobs/jobsService';

import { buildJobOverrides, IJobForm, parseLabels } from 'utils/jobs/jobs';

interface IProps {
  job: IJobRow;
  spec: IJobSpec;
  onCreated: (created: IJobRow) => void;
  onClose: () => void;
}

// Params are written one per line as key=value. A value that parses as JSON keeps its type
// (numbers, booleans, lists); any other value is a string.
function paramsToText(params: { [key: string]: unknown }): string {
  return Object.entries(params)
    .map(
      ([key, value]) =>
        `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`,
    )
    .join('\n');
}

function textToParams(text: string): { [key: string]: unknown } {
  const params: { [key: string]: unknown } = {};
  for (const line of text.split('\n').filter((l) => l.trim())) {
    const index = line.indexOf('=');
    if (index <= 0) {
      throw new Error(`"${line}" is not key=value`);
    }
    const key = line.slice(0, index).trim();
    const raw = line.slice(index + 1).trim();
    try {
      params[key] = JSON.parse(raw);
    } catch {
      params[key] = raw;
    }
  }
  return params;
}

function envToText(env: { [key: string]: string }): string {
  return Object.entries(env)
    .map(([key, value]) => `${key}=${value}`)
    .join('\n');
}

function textToEnv(text: string): { [key: string]: string } {
  const env: { [key: string]: string } = {};
  for (const line of text.split('\n').filter((l) => l.trim())) {
    const index = line.indexOf('=');
    if (index <= 0) {
      throw new Error(`"${line}" is not KEY=value`);
    }
    env[line.slice(0, index).trim()] = line.slice(index + 1);
  }
  return env;
}

function JobRescheduleForm({ job, spec, onCreated, onClose }: IProps) {
  const [name, setName] = useState(spec.name);
  const [queue, setQueue] = useState(spec.queue);
  const [cpu, setCpu] = useState(String(spec.resources.cpu));
  const [memory, setMemory] = useState(String(spec.resources.memory_gb));
  const [gpu, setGpu] = useState(String(spec.resources.gpu));
  const [labels, setLabels] = useState(spec.resources.labels.join(', '));
  const [timeoutText, setTimeoutText] = useState(
    spec.timeout_s ? String(spec.timeout_s) : '',
  );
  const [params, setParams] = useState(paramsToText(spec.params));
  const [env, setEnv] = useState(envToText(spec.env));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    let form: IJobForm;
    try {
      form = {
        name,
        queue,
        resources: {
          cpu: Number(cpu),
          memory_gb: Number(memory),
          gpu: Number(gpu),
          labels: parseLabels(labels),
        },
        params: textToParams(params),
        env: textToEnv(env),
        timeout_s: timeoutText.trim() === '' ? '' : Number(timeoutText),
      };
    } catch (parseError) {
      setError((parseError as Error).message);
      return;
    }
    const overrides = buildJobOverrides(spec, form);
    setBusy(true);
    setError(null);
    jobsService
      .rescheduleJob(job.id, overrides)
      .call()
      .then((created) => onCreated(created))
      .catch((requestError) =>
        setError(`Could not queue the copy: ${requestError.message}`),
      )
      .finally(() => setBusy(false));
  }

  return (
    <form
      className='JobReschedule'
      onSubmit={submit}
      aria-label='Copy and reschedule'
    >
      <h3>Copy and reschedule</h3>
      <p className='Jobs__muted'>
        Copies &quot;{spec.name}&quot; with the same code, data and runtime.
        Change what you need, then dispatch the copy.
      </p>
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Queue
        <input value={queue} onChange={(e) => setQueue(e.target.value)} />
      </label>
      <label>
        CPU
        <input
          type='number'
          min={1}
          value={cpu}
          onChange={(e) => setCpu(e.target.value)}
        />
      </label>
      <label>
        Memory GB
        <input
          type='number'
          min={0.1}
          step='any'
          value={memory}
          onChange={(e) => setMemory(e.target.value)}
        />
      </label>
      <label>
        GPU
        <input
          type='number'
          min={0}
          value={gpu}
          onChange={(e) => setGpu(e.target.value)}
        />
      </label>
      <label>
        Labels
        <input value={labels} onChange={(e) => setLabels(e.target.value)} />
      </label>
      <label>
        Timeout seconds
        <input
          type='number'
          min={60}
          placeholder='keep'
          value={timeoutText}
          onChange={(e) => setTimeoutText(e.target.value)}
        />
      </label>
      <label>
        Parameters (key=value per line)
        <textarea
          rows={4}
          value={params}
          onChange={(e) => setParams(e.target.value)}
        />
      </label>
      <label>
        Environment (KEY=value per line)
        <textarea
          rows={3}
          value={env}
          onChange={(e) => setEnv(e.target.value)}
        />
      </label>
      {error && (
        <p className='Jobs__error' role='alert'>
          {error}
        </p>
      )}
      <div className='JobReschedule__actions'>
        <Button type='submit' disabled={busy}>
          Dispatch copy
        </Button>
        <Button onClick={onClose}>Close</Button>
      </div>
      <span className='Jobs__muted'>
        Copy of {job.id} from {job.run_id}
      </span>
    </form>
  );
}

export default JobRescheduleForm;

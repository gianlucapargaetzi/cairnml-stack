import {
  buildJobOverrides,
  IJobForm,
  canCancel,
  jobGroup,
  mapDiff,
  parseLabels,
} from './jobs';

const original = {
  name: 'train',
  queue: 'default',
  resources: { cpu: 4, memory_gb: 8, gpu: 1, labels: ['a100'] },
  params: { lr: 0.1, epochs: 3 },
  env: { HF_HOME: '/cache' },
  timeout_s: 3600,
};

const unchanged: IJobForm = {
  name: 'train',
  queue: 'default',
  resources: { cpu: 4, memory_gb: 8, gpu: 1, labels: ['a100'] },
  params: { lr: 0.1, epochs: 3 },
  env: { HF_HOME: '/cache' },
  timeout_s: '',
};

describe('jobGroup and canCancel', () => {
  it('groups the six statuses into four lists', () => {
    expect(jobGroup('queued')).toBe('active');
    expect(jobGroup('assigned')).toBe('active');
    expect(jobGroup('running')).toBe('active');
    expect(jobGroup('finished')).toBe('finished');
    expect(jobGroup('failed')).toBe('failed');
    expect(jobGroup('cancelled')).toBe('cancelled');
  });

  it('allows cancelling only jobs that are still active', () => {
    expect(canCancel({ status: 'running', cancel_requested: false })).toBe(
      true,
    );
    expect(canCancel({ status: 'queued', cancel_requested: false })).toBe(true);
    expect(canCancel({ status: 'finished', cancel_requested: false })).toBe(
      false,
    );
  });
});

describe('buildJobOverrides', () => {
  it('sends nothing for an unchanged form', () => {
    expect(buildJobOverrides(original, { ...unchanged })).toEqual({});
  });

  it('sends only the fields that changed, in the shape of JobOverrides', () => {
    const overrides = buildJobOverrides(original, {
      ...unchanged,
      name: 'train again',
      resources: { cpu: 8, memory_gb: 8, gpu: 1, labels: ['a100'] },
      params: { lr: 0.01, epochs: 3 },
    });
    expect(overrides).toEqual({
      name: 'train again',
      resources: { cpu: 8, memory_gb: 8, gpu: 1, labels: ['a100'] },
      params: { lr: 0.01 },
    });
  });

  it('removes a param or env key that the form dropped, with null', () => {
    const overrides = buildJobOverrides(original, {
      ...unchanged,
      params: { lr: 0.1 },
      env: {},
    });
    expect(overrides).toEqual({
      params: { epochs: null },
      env: { HF_HOME: null },
    });
  });

  it('keeps the original timeout when the field is empty', () => {
    expect(
      buildJobOverrides(original, { ...unchanged, timeout_s: '' }),
    ).toEqual({});
    expect(
      buildJobOverrides(original, { ...unchanged, timeout_s: 7200 }),
    ).toEqual({
      timeout_s: 7200,
    });
  });
});

describe('helpers', () => {
  it('parses a comma list of labels and drops blanks', () => {
    expect(parseLabels(' a100, ,v100 ')).toEqual(['a100', 'v100']);
    expect(parseLabels('')).toEqual([]);
  });

  it('diffs maps by key, keeping values that did not change out of the result', () => {
    expect(mapDiff({ a: 1, b: 2 }, { a: 1, b: 3, c: 4 })).toEqual({
      b: 3,
      c: 4,
    });
  });
});

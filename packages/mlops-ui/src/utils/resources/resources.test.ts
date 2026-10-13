import {
  barPercent,
  capabilityText,
  fmtDuration,
  queueState,
  usageLabel,
} from './resources';

describe('barPercent and usageLabel', () => {
  it('clamps a bar to 0 to 100 and gives 0 for a missing or zero total', () => {
    expect(barPercent(2, 8)).toBe(25);
    expect(barPercent(12, 8)).toBe(100);
    expect(barPercent(-1, 8)).toBe(0);
    expect(barPercent(2, 0)).toBe(0);
    expect(barPercent(undefined as unknown as number, 8)).toBe(0);
  });

  it('shows used over total with the unit, and a dash when used is missing', () => {
    expect(usageLabel(2.25, 8, 'cpu')).toBe('2.3 / 8 cpu');
    expect(usageLabel(undefined as unknown as number, 8, 'GB')).toBe(
      '– / 8 GB',
    );
  });
});

describe('queueState', () => {
  it('is stuck when jobs wait and no agent serves the queue', () => {
    expect(queueState({ queued: 2, agents: 0 })).toBe('stuck');
  });

  it('is busy when jobs wait and an agent serves it, idle otherwise', () => {
    expect(queueState({ queued: 2, agents: 1 })).toBe('busy');
    expect(queueState({ queued: 0, agents: 0 })).toBe('idle');
  });
});

describe('capabilityText and fmtDuration', () => {
  it('lists cpu, memory and gpus with their distinct models', () => {
    expect(
      capabilityText({
        cpu: 16,
        memory_gb: 64,
        gpus: 2,
        gpu_models: ['A100', 'A100'],
      }),
    ).toBe('16 cpu · 64 GB memory · 2 gpu (A100)');
    expect(
      capabilityText({ cpu: 4, memory_gb: 8, gpus: 0, gpu_models: [] }),
    ).toBe('4 cpu · 8 GB memory');
  });

  it('formats a span in the largest two units', () => {
    const start = '2026-10-13T10:00:00Z';
    expect(fmtDuration(start, '2026-10-13T10:00:42Z')).toBe('42s');
    expect(fmtDuration(start, '2026-10-13T10:03:05Z')).toBe('3m 5s');
    expect(fmtDuration(start, '2026-10-13T12:10:00Z')).toBe('2h 10m');
    expect(fmtDuration(start, '2026-10-15T11:00:00Z')).toBe('2d 1h');
    expect(fmtDuration(null, null)).toBe('–');
  });
});

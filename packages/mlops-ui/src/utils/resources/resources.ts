// Helpers for the resources page: bars, queue states and the capability text of an agent.

export function barPercent(used: number, total: number): number {
  if (typeof used !== 'number' || typeof total !== 'number' || total <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, (used / total) * 100));
}

export function usageLabel(used: number, total: number, unit: string): string {
  const shown =
    typeof used === 'number' ? String(Math.round(used * 10) / 10) : '–';
  return `${shown} / ${total} ${unit}`;
}

export type QueueState = 'stuck' | 'busy' | 'idle';

export interface IQueueStats {
  name: string;
  queued: number;
  running: number;
  agents: number;
  oldest_wait_s: number | null;
}

export function queueState(
  queue: Pick<IQueueStats, 'queued' | 'agents'>,
): QueueState {
  if (queue.queued > 0 && queue.agents === 0) {
    return 'stuck';
  }
  return queue.queued > 0 ? 'busy' : 'idle';
}

export interface IAgentCapabilities {
  cpu: number;
  memory_gb: number;
  gpus: number;
  gpu_models: string[];
}

export function capabilityText(caps: IAgentCapabilities): string {
  const models = [...new Set(caps.gpu_models)];
  const gpus = caps.gpus
    ? ` · ${caps.gpus} gpu${models.length ? ` (${models.join(', ')})` : ''}`
    : '';
  return `${caps.cpu} cpu · ${caps.memory_gb} GB memory${gpus}`;
}

// A duration between two ISO times (the end defaults to now), in the largest two units.
export function fmtDuration(start: string | null, end: string | null): string {
  if (!start) {
    return '–';
  }
  const startMs = Date.parse(start);
  const endMs = end ? Date.parse(end) : Date.now();
  let seconds = Math.max(0, Math.round((endMs - startMs) / 1000));
  const days = Math.floor(seconds / 86400);
  seconds %= 86400;
  const hours = Math.floor(seconds / 3600);
  seconds %= 3600;
  const minutes = Math.floor(seconds / 60);
  seconds %= 60;
  if (days) {
    return `${days}d ${hours}h`;
  }
  if (hours) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

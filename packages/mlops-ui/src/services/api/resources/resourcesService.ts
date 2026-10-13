import { IAgentCapabilities, IQueueStats } from 'utils/resources/resources';

import API from '../api';

// Agents and queues, with the load of each agent. Visible to every reader; running jobs are
// named only for projects the caller is in.
export interface IResourceAgent {
  id: string;
  name: string;
  online: boolean;
  last_seen: string | null;
  queues: string[];
  capabilities: IAgentCapabilities & {
    labels: string[];
    runtimes: string[];
    docker: boolean;
  };
  free: { cpu: number; memory_gb: number; gpu: number };
  usage: {
    cpu_percent: number;
    mem_used_gb: number;
    mem_total_gb: number;
    gpus: {
      index: number;
      util_percent: number;
      mem_used_gb: number;
      mem_total_gb: number;
    }[];
  } | null;
  usage_at: string | null;
  running_jobs: { run_name: string; project: string }[];
  other_running_jobs: number;
}

export interface IResources {
  agents: IResourceAgent[];
  queues: IQueueStats[];
}

function getResources() {
  return API.get<IResources>('v1/resources');
}

const resourcesService = { getResources };

export default resourcesService;

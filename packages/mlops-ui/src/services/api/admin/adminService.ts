import API from '../api';

// Read-only administration data. Revocation and agent tokens are done with the mlops CLI.
export interface IAdminUser {
  id: string;
  username: string;
  roles: string[];
  disabled: boolean;
  clients_active: number;
}

export interface IAdminAgent {
  id: string;
  name: string;
  queues: string[];
  revoked: boolean;
  last_seen: string | null;
}

export interface IAdminClient {
  id: string;
  name: string;
  user_id: string;
  revoked: boolean;
}

function getUsers() {
  return API.get<IAdminUser[]>('v1/admin/users');
}

function getAgents() {
  return API.get<IAdminAgent[]>('v1/admin/agents');
}

function getClients() {
  return API.get<IAdminClient[]>('v1/admin/clients');
}

const adminService = { getUsers, getAgents, getClients };

export default adminService;

import API from '../api';

// Read-only data of the signed-in user. Changes go through the identity provider or the mlops CLI.
export interface IAccountClient {
  id: string;
  name: string;
  created_at: string;
  revoked_at: string | null;
}

export interface IAccountProject {
  id: string;
  slug: string;
  name: string;
}

export interface IPublicConfig {
  server_url: string;
  oidc_issuer: string;
  oidc_client_id: string;
}

function getMyClients() {
  return API.get<IAccountClient[]>('v1/me/clients');
}

function getProjects() {
  return API.get<IAccountProject[]>('v1/projects');
}

function getConfig() {
  return API.get<IPublicConfig>('v1/config');
}

const accountService = { getMyClients, getProjects, getConfig };

export default accountService;

import React, { useEffect, useState } from 'react';

import { Card, Table, Text } from 'components/kit';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import adminService, {
  IAdminAgent,
  IAdminClient,
  IAdminUser,
} from 'services/api/admin/adminService';

import { activeLabel, isForbidden, userStatus } from 'utils/admin/admin';

import './Admin.scss';

interface IAdminData {
  users: IAdminUser[];
  agents: IAdminAgent[];
  clients: IAdminClient[];
}

function Admin(): React.FunctionComponentElement<React.ReactNode> {
  const [data, setData] = useState<IAdminData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    const users = adminService.getUsers();
    const agents = adminService.getAgents();
    const clients = adminService.getClients();
    Promise.all([users.call(), agents.call(), clients.call()])
      .then(([loadedUsers, loadedAgents, loadedClients]) =>
        setData({
          users: loadedUsers,
          agents: loadedAgents,
          clients: loadedClients,
        }),
      )
      .catch((requestError) => {
        if (isForbidden(requestError)) {
          setForbidden(true);
        } else if (requestError?.name !== 'AbortError') {
          setError(
            `Administration data could not be loaded: ${requestError.message}`,
          );
        }
      });
    return () => {
      users.abort();
      agents.abort();
      clients.abort();
    };
  }, []);

  return (
    <ErrorBoundary>
      <section className='Admin'>
        <header className='Admin__header'>
          <Text component='h1' size={18} weight={600} tint={100}>
            Administration
          </Text>
          <Text size={12} tint={50}>
            Read-only view. Use the mlops CLI to revoke clients or agents and to
            create agent tokens.
          </Text>
        </header>

        {forbidden && (
          <Text size={12} tint={50}>
            Administrators only.
          </Text>
        )}
        {error && (
          <Text size={12} color='error' role='alert'>
            {error}
          </Text>
        )}

        {data && (
          <>
            <Card
              title='Users'
              subtitle='Accounts that have signed in or been synced.'
            >
              <Table
                columns={[
                  { key: 'user', label: 'User' },
                  { key: 'roles', label: 'Roles' },
                  { key: 'status', label: 'Status' },
                  { key: 'keys', label: 'Active client keys' },
                ]}
                rows={data.users.map((user) => ({
                  id: user.id,
                  user: user.username,
                  roles: user.roles.join(', ') || '–',
                  status: userStatus(user),
                  keys: user.clients_active,
                }))}
                rowKey='id'
                emptyText='No users yet.'
              />
            </Card>

            <Card title='Agents' subtitle='Machines that run jobs.'>
              <Table
                columns={[
                  { key: 'id', label: 'Id' },
                  { key: 'name', label: 'Name' },
                  { key: 'queues', label: 'Queues' },
                  { key: 'state', label: 'State' },
                  { key: 'seen', label: 'Last seen' },
                ]}
                rows={data.agents.map((agent) => ({
                  id: agent.id,
                  name: agent.name,
                  queues: agent.queues.join(', '),
                  state: activeLabel(agent.revoked),
                  seen: agent.last_seen
                    ? new Date(agent.last_seen).toLocaleString()
                    : '–',
                }))}
                rowKey='id'
                emptyText='No agents enrolled.'
              />
            </Card>

            <Card title='Client keys' subtitle='Machines enrolled for a user.'>
              <Table
                columns={[
                  { key: 'id', label: 'Id' },
                  { key: 'name', label: 'Machine' },
                  { key: 'user', label: 'User' },
                  { key: 'state', label: 'State' },
                ]}
                rows={data.clients.map((client) => ({
                  id: client.id,
                  name: client.name,
                  user: client.user_id,
                  state: activeLabel(client.revoked),
                }))}
                rowKey='id'
                emptyText='No machines enrolled.'
              />
            </Card>
          </>
        )}
      </section>
    </ErrorBoundary>
  );
}

export default Admin;

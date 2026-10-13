import React, { useEffect, useState } from 'react';

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
        <h1>Administration</h1>
        {forbidden && <p className='Admin__muted'>Administrators only.</p>}
        {error && (
          <p className='Admin__error' role='alert'>
            {error}
          </p>
        )}
        {data && (
          <>
            <p className='Admin__muted'>
              Read-only view. Use the mlops CLI to revoke clients or agents and
              to create agent tokens.
            </p>
            <h2>Users</h2>
            <table className='Admin__table'>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Roles</th>
                  <th>Status</th>
                  <th>Active client keys</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.username}</td>
                    <td>{user.roles.join(', ') || '–'}</td>
                    <td>{userStatus(user)}</td>
                    <td>{user.clients_active}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h2>Agents</h2>
            <table className='Admin__table'>
              <thead>
                <tr>
                  <th>Id</th>
                  <th>Name</th>
                  <th>Queues</th>
                  <th>State</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {data.agents.map((agent) => (
                  <tr key={agent.id}>
                    <td className='Admin__mono'>{agent.id}</td>
                    <td>{agent.name}</td>
                    <td>{agent.queues.join(', ')}</td>
                    <td>{activeLabel(agent.revoked)}</td>
                    <td>
                      {agent.last_seen
                        ? new Date(agent.last_seen).toLocaleString()
                        : '–'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h2>Client keys</h2>
            <table className='Admin__table'>
              <thead>
                <tr>
                  <th>Id</th>
                  <th>Machine</th>
                  <th>User</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {data.clients.map((client) => (
                  <tr key={client.id}>
                    <td className='Admin__mono'>{client.id}</td>
                    <td>{client.name}</td>
                    <td className='Admin__mono'>{client.user_id}</td>
                    <td>{activeLabel(client.revoked)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </ErrorBoundary>
  );
}

export default Admin;

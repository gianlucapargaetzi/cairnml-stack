import React, { useEffect, useState } from 'react';

import {
  Badge,
  Button,
  Card,
  DefinitionList,
  Table,
  Text,
} from 'components/kit';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import { STATUS_COLORS } from 'config/colors/colors';

import accountService, {
  IAccountClient,
  IAccountProject,
} from 'services/api/account/accountService';
import { getSession } from 'services/session/session';

import './Settings.scss';

interface ISettingsData {
  clients: IAccountClient[];
  projects: IAccountProject[];
  issuer: string;
}

// The identity provider's account console. Name, email and username are read-only there;
// the password is changed on its "Signing in" page.
function openAccountConsole(issuer: string, path: string = ''): void {
  const url = `${issuer.replace(/\/$/, '')}/account/${path}`;
  window.open(url, '_blank', 'noopener,noreferrer');
}

function Settings(): React.FunctionComponentElement<React.ReactNode> {
  const session = getSession();
  const [data, setData] = useState<ISettingsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const clients = accountService.getMyClients();
    const projects = accountService.getProjects();
    const config = accountService.getConfig();
    Promise.all([clients.call(), projects.call(), config.call()])
      .then(([loadedClients, loadedProjects, loadedConfig]) =>
        setData({
          clients: loadedClients,
          projects: loadedProjects,
          issuer: loadedConfig.oidc_issuer,
        }),
      )
      .catch((requestError) => {
        if (requestError?.name !== 'AbortError') {
          setError(`Settings could not be loaded: ${requestError.message}`);
        }
      });
    return () => {
      clients.abort();
      projects.abort();
      config.abort();
    };
  }, []);

  return (
    <ErrorBoundary>
      <section className='Settings'>
        <header className='Settings__header'>
          <Text component='h1' size={18} weight={600} tint={100}>
            Settings
          </Text>
          <Text size={12} tint={50}>
            Your account. Name, email and username are managed by an
            administrator.
          </Text>
        </header>

        {error && (
          <Text size={12} color='error' role='alert'>
            {error}
          </Text>
        )}

        <Card title='Profile' subtitle='Read-only.'>
          <DefinitionList
            items={[
              {
                label: 'Username',
                value: session?.username ?? 'Not available',
              },
              {
                label: 'Roles',
                value: session?.roles.length
                  ? session.roles.join(', ')
                  : 'None',
              },
              {
                label: 'Administrator',
                value: (
                  <Badge
                    label={session?.is_admin ? 'Yes' : 'No'}
                    color={
                      session?.is_admin
                        ? STATUS_COLORS.primary
                        : STATUS_COLORS.neutral
                    }
                    size='small'
                  />
                ),
              },
              {
                label: 'Name and email',
                value: data ? (
                  <Button
                    variant='text'
                    size='small'
                    onClick={() => openAccountConsole(data.issuer)}
                  >
                    View in your identity provider
                  </Button>
                ) : (
                  <Text size={12} tint={50}>
                    Loading
                  </Text>
                ),
              },
            ]}
          />
        </Card>

        <Card
          title='Password'
          subtitle='The identity provider checks your password, so it is changed there.'
        >
          <div>
            {data ? (
              <Button
                variant='contained'
                onClick={() =>
                  openAccountConsole(data.issuer, 'account-security/signing-in')
                }
              >
                Change password
              </Button>
            ) : (
              <Text size={12} tint={50}>
                Loading
              </Text>
            )}
          </div>
        </Card>

        <Card title='Projects' subtitle='Projects you are a member of.'>
          <Table
            columns={[
              { key: 'name', label: 'Name' },
              { key: 'slug', label: 'Identifier' },
            ]}
            rows={(data?.projects ?? []).map((project) => ({
              id: project.id,
              name: project.name,
              slug: project.slug,
            }))}
            rowKey='id'
            emptyText={
              data
                ? 'You are not a member of any project yet. Ask an administrator.'
                : 'Loading'
            }
          />
        </Card>

        <Card
          title='Enrolled machines'
          subtitle='Machines that can submit runs as you.'
        >
          <Table
            columns={[
              { key: 'name', label: 'Name' },
              { key: 'enrolled', label: 'Enrolled' },
              { key: 'status', label: 'Status' },
            ]}
            rows={(data?.clients ?? []).map((client) => ({
              id: client.id,
              name: client.name,
              enrolled: new Date(client.created_at).toLocaleString(),
              status: (
                <Badge
                  label={client.revoked_at ? 'Revoked' : 'Active'}
                  color={
                    client.revoked_at
                      ? STATUS_COLORS.error
                      : STATUS_COLORS.success
                  }
                  size='small'
                />
              ),
            }))}
            rowKey='id'
            emptyText={
              data
                ? 'No machine is enrolled for your account. Run mlops enroll on the machine.'
                : 'Loading'
            }
          />
        </Card>
      </section>
    </ErrorBoundary>
  );
}

export default Settings;

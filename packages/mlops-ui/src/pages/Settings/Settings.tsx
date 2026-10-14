import React, { useEffect, useState } from 'react';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import accountService, {
  IAccountClient,
  IAccountProject,
} from 'services/api/account/accountService';
import { getSession, signOut } from 'services/session/session';

import './Account.scss';

interface IAccountData {
  clients: IAccountClient[];
  projects: IAccountProject[];
  issuer: string;
}

function Account(): React.FunctionComponentElement<React.ReactNode> {
  const session = getSession();
  const [data, setData] = useState<IAccountData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

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
          setError(`Account data could not be loaded: ${requestError.message}`);
        }
      });
    return () => {
      clients.abort();
      projects.abort();
      config.abort();
    };
  }, []);

  function handleSignOut() {
    setSigningOut(true);
    setError(null);
    signOut().catch((signOutError) => {
      setSigningOut(false);
      setError(`Sign out failed: ${signOutError.message}`);
    });
  }

  // Keycloak's account console, on the password page. Passwords are changed there, not here.
  const passwordUrl = data
    ? `${data.issuer}/account/#/security/signingin`
    : null;

  return (
    <ErrorBoundary>
      <section className='Account'>
        <h1>Account</h1>
        <p className='Account__muted'>
          Your account. Everything on this page is read-only, except the
          password and sign-out actions.
        </p>
        {error && (
          <p className='Account__error' role='alert'>
            {error}
          </p>
        )}

        <h2>Profile</h2>
        <dl className='Account__profile'>
          <dt>Username</dt>
          <dd>{session?.username ?? 'Not available'}</dd>
          <dt>Roles</dt>
          <dd>{session?.roles.length ? session.roles.join(', ') : 'None'}</dd>
          <dt>Administrator</dt>
          <dd>{session?.is_admin ? 'Yes' : 'No'}</dd>
        </dl>

        <h2>Password</h2>
        <p className='Account__muted'>
          Passwords are managed by the identity provider. Change yours there.
        </p>
        {passwordUrl ? (
          <a
            className='Account__button'
            href={passwordUrl}
            target='_blank'
            rel='noopener noreferrer'
          >
            Change password
          </a>
        ) : (
          <span className='Account__muted'>Loading</span>
        )}

        <h2>Projects</h2>
        {data && data.projects.length === 0 && (
          <p className='Account__muted'>You are not a member of any project.</p>
        )}
        {data && data.projects.length > 0 && (
          <ul className='Account__list'>
            {data.projects.map((project) => (
              <li key={project.id}>
                <span>{project.name}</span>{' '}
                <span className='Account__mono'>{project.slug}</span>
              </li>
            ))}
          </ul>
        )}

        <h2>Enrolled machines</h2>
        {data && data.clients.length === 0 && (
          <p className='Account__muted'>
            No machine is enrolled for your account. Run{' '}
            <code>mlops enroll</code> on the machine.
          </p>
        )}
        {data && data.clients.length > 0 && (
          <table className='Account__table'>
            <thead>
              <tr>
                <th>Name</th>
                <th>Enrolled</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.clients.map((client) => (
                <tr key={client.id}>
                  <td>{client.name}</td>
                  <td>{new Date(client.created_at).toLocaleString()}</td>
                  <td>{client.revoked_at ? 'Revoked' : 'Active'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h2>Session</h2>
        <button
          type='button'
          className='Account__button Account__button--secondary'
          onClick={handleSignOut}
          disabled={signingOut}
        >
          {signingOut ? 'Signing out' : 'Sign out'}
        </button>
      </section>
    </ErrorBoundary>
  );
}

export default Account;

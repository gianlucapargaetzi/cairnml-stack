import API, { getCsrfToken, setCsrfToken } from 'services/api/api';

export interface ISession {
  id: string;
  kind: string;
  user_id: string | null;
  username: string | null;
  roles: string[];
  is_admin: boolean;
  csrf: string | null;
}

let currentSession: ISession | null = null;

// The session loaded at startup, or null before it is loaded.
export function getSession(): ISession | null {
  return currentSession;
}

// Reads who is signed in. A missing session sends the browser to sign-in (see api.ts).
export async function loadSession(): Promise<ISession> {
  const session = await API.get<ISession>('v1/me').call();
  setCsrfToken(session.csrf ?? '');
  currentSession = session;
  return session;
}

// Ends the server session, then the IdP session, so the next sign-in asks for credentials.
export async function signOut(): Promise<void> {
  const response = await fetch('/ui/auth/logout', {
    method: 'POST',
    headers: { 'X-CSRF-Token': getCsrfToken() },
  });
  if (!response.ok) {
    throw new Error(`sign-out failed (HTTP ${response.status})`);
  }
  const { logout_url: logoutUrl } = (await response.json()) as {
    logout_url: string;
  };
  window.location.assign(logoutUrl);
}

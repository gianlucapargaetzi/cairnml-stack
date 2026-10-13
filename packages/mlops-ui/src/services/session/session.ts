import API, { setCsrfToken } from 'services/api/api';

export interface ISession {
  id: string;
  kind: string;
  user_id: string | null;
  username: string | null;
  roles: string[];
  is_admin: boolean;
  csrf: string | null;
}

// Reads who is signed in. A missing session sends the browser to sign-in (see api.ts).
export async function loadSession(): Promise<ISession> {
  const session = await API.get<ISession>('v1/me').call();
  setCsrfToken(session.csrf ?? '');
  return session;
}

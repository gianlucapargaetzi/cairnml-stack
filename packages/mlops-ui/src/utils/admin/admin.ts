// Helpers for the admin page.

// The API answers 403 to anyone who is not an administrator.
export function isForbidden(error: unknown): boolean {
  return (error as { status?: number } | null)?.status === 403;
}

export function activeLabel(revoked: boolean): string {
  return revoked ? 'revoked' : 'active';
}

export function userStatus(user: Pick<IUserStatus, 'disabled'>): string {
  return user.disabled ? 'disabled' : 'active';
}

interface IUserStatus {
  disabled: boolean;
}

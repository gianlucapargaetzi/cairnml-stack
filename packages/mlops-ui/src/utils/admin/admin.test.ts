import { activeLabel, isForbidden, userStatus } from './admin';

describe('admin helpers', () => {
  it('recognises a 403 from the API, and nothing else', () => {
    expect(
      isForbidden(Object.assign(new Error('forbidden'), { status: 403 })),
    ).toBe(true);
    expect(
      isForbidden(Object.assign(new Error('server'), { status: 500 })),
    ).toBe(false);
    expect(isForbidden(new Error('network'))).toBe(false);
    expect(isForbidden(null)).toBe(false);
  });

  it('labels revoked and disabled rows', () => {
    expect(activeLabel(true)).toBe('revoked');
    expect(activeLabel(false)).toBe('active');
    expect(userStatus({ disabled: true })).toBe('disabled');
    expect(userStatus({ disabled: false })).toBe('active');
  });
});

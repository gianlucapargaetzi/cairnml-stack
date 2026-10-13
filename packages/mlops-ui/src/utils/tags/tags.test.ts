import { normalizeColor, validateTag } from './tags';

describe('validateTag', () => {
  it('needs a name of 1 to 64 characters and a description of at most 2000', () => {
    expect(
      validateTag({ name: 'baseline', color: null, description: '' }),
    ).toBeNull();
    expect(validateTag({ name: '   ', color: null, description: '' })).toBe(
      'A tag needs a name.',
    );
    expect(
      validateTag({ name: 'x'.repeat(65), color: null, description: '' }),
    ).toMatch(/64/);
    expect(
      validateTag({ name: 'a', color: null, description: 'x'.repeat(2001) }),
    ).toMatch(/2000/);
  });
});

describe('normalizeColor', () => {
  it('accepts a six-digit hex colour, in lower case, and nothing else', () => {
    expect(normalizeColor('#A1B2C3')).toBe('#a1b2c3');
    expect(normalizeColor('  #123456 ')).toBe('#123456');
    expect(normalizeColor('')).toBeNull();
    expect(normalizeColor('blue')).toBeUndefined();
    expect(normalizeColor('#abc')).toBeUndefined();
  });
});

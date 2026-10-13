import { mergeParams } from './projectsService';

describe('mergeParams', () => {
  it('merges the sequence names of every project, with their context keys, per kind', () => {
    const merged = mergeParams([
      {
        params: ['lr'],
        metric: {},
        images: { pred: ['subset'] },
        texts: { log: [] },
      },
      {
        params: ['batch'],
        metric: {},
        images: { pred: [], mask: [] },
      },
    ]);

    expect(merged.params).toEqual({ lr: '', batch: '' });
    expect(merged.images).toEqual({
      pred: [{ subset: '' }, {}],
      mask: [{}],
    });
    expect(merged.texts).toEqual({ log: [{}] });
    expect(merged.audios).toEqual({});
  });
});

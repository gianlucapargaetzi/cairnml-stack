import { dispatchBody } from './dispatch';

describe('dispatchBody', () => {
  it('defaults the queue, splits the labels and leaves empty resource fields to the server', () => {
    expect(
      dispatchBody({
        queue: '  ',
        cpu: '',
        memory_gb: '',
        gpu: '',
        labels: 'a100, v100 ,',
      }),
    ).toEqual({ queue: 'default', labels: ['a100', 'v100'] });
  });

  it('sends the resources that were given as numbers', () => {
    expect(
      dispatchBody({
        queue: 'gpu',
        cpu: '4',
        memory_gb: '8.5',
        gpu: '1',
        labels: '',
      }),
    ).toEqual({ queue: 'gpu', labels: [], cpu: 4, memory_gb: 8.5, gpu: 1 });
  });

  it('refuses a resource that is negative or not a number', () => {
    expect(() =>
      dispatchBody({
        queue: 'default',
        cpu: '-1',
        memory_gb: '',
        gpu: '',
        labels: '',
      }),
    ).toThrow('cpu must be a number of 0 or more');
    expect(() =>
      dispatchBody({
        queue: 'default',
        cpu: '',
        memory_gb: 'lots',
        gpu: '',
        labels: '',
      }),
    ).toThrow('memory_gb must be a number of 0 or more');
  });
});

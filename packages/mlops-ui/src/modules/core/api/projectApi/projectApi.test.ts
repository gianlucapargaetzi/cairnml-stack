import projectsService from 'services/api/projects/projectsService';

import { getParams } from './index';

jest.mock('services/api/projects/projectsService', () => ({
  __esModule: true,
  default: {
    getProjectParams: jest.fn(),
  },
}));

const listing = {
  params: { lr: 0.1 },
  metric: { loss: [{}] },
  images: {},
};

describe('getParams', () => {
  beforeEach(() => {
    (projectsService.getProjectParams as jest.Mock).mockReturnValue({
      call: async () => listing,
      abort: () => undefined,
    });
  });

  it('reads the params and metric names from the explorer listings', async () => {
    const result = await getParams({ sequence: 'metric' });

    expect(projectsService.getProjectParams).toHaveBeenCalled();
    expect(result.params).toEqual({ lr: 0.1 });
    expect(result.metric).toEqual({ loss: [{}] });
  });

  it('drops params when exclude_params is set, as the dashboard asks', async () => {
    const result = await getParams({
      sequence: ['metric', 'images'],
      exclude_params: true,
    });

    expect(result.params).toBeUndefined();
    expect(result.metric).toEqual({ loss: [{}] });
  });
});

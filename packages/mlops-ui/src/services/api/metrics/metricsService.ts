import { IApiRequest } from 'types/services/services';
import { IAlignMetricsDataParams } from 'types/services/models/metrics/metricsAppModel';

import API from '../api';

const endpoints = {
  GET_METRICS: 'v1/explorer/runs/search/metric',
};

// `p` is the point density (50, 250 or 500). The explorer API takes it as `points`.
function getMetricsData(params: { q?: string; p?: number }): IApiRequest<any> {
  return API.get<any>(endpoints.GET_METRICS, {
    q: params.q || '',
    ...(params.p ? { points: params.p } : {}),
  });
}

// Aligning metric traces on a shared x axis needs the align endpoint, which is not built yet.
function fetchAlignedMetricsData(
  _params: IAlignMetricsDataParams,
): IApiRequest<any> {
  throw new Error('Metric alignment is not supported yet.');
}

const metricsService = {
  endpoints,
  getMetricsData,
  fetchAlignedMetricsData,
};

export default metricsService;

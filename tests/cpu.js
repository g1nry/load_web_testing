import http from 'k6/http';
import { check } from 'k6';
import { appendCacheBuster, buildUrl, getEnvEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { cpuThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const endpoints = getEnvEndpoints('CPU_ENDPOINTS', __ENV.LOAD_ENDPOINTS || '/');
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';

export const options = {
  scenarios: {
    cpu_pressure: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.CPU_RATE || '500'),
      timeUnit: '1s',
      duration: __ENV.CPU_DURATION || '5m',
      preAllocatedVUs: Number(__ENV.CPU_PRE_ALLOCATED_VUS || '100'),
      maxVUs: Number(__ENV.CPU_MAX_VUS || '1000'),
    },
  },
  noConnectionReuse: (__ENV.CPU_NO_CONNECTION_REUSE || 'true') === 'true',
  thresholds: cpuThresholds,
};

export default function () {
  const endpoint = appendCacheBuster(pickEndpoint(endpoints));
  const response = http.get(buildUrl(targetUrl, endpoint), {
    timeout: requestTimeout,
    tags: { endpoint: endpoint.split('?')[0] },
  });

  check(response, {
    'server responded': (res) => res.status > 0,
    'status is not 5xx': (res) => res.status < 500,
  });
}

export function handleSummary(data) {
  return buildSummary(data);
}

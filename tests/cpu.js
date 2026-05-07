import http from 'k6/http';
import { check } from 'k6';
import { appendCacheBuster, buildUrl, getEnvEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { cpuThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const endpoints = getEnvEndpoints('CPU_ENDPOINTS', __ENV.LOAD_ENDPOINTS || '/');
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const noConnectionReuse = (__ENV.CPU_NO_CONNECTION_REUSE || 'false') === 'true';

function getStages() {
  const rates = (__ENV.CPU_RATE_STEPS || __ENV.CPU_RATE || '25,50,100,200')
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value) && value > 0);
  const rampDuration = __ENV.CPU_RAMP_DURATION || '30s';
  const holdDuration = __ENV.CPU_HOLD_DURATION || '1m';
  const stages = [];

  for (const rate of rates) {
    stages.push({ duration: rampDuration, target: rate });
    stages.push({ duration: holdDuration, target: rate });
  }

  stages.push({ duration: __ENV.CPU_RAMP_DOWN_DURATION || '30s', target: 0 });
  return stages;
}

if (noConnectionReuse) {
  console.warn('CPU_NO_CONNECTION_REUSE=true creates many new TCP connections and can overload the runner network/NAT before the service CPU limit is reached.');
}

export const options = {
  scenarios: {
    cpu_pressure: {
      executor: 'ramping-arrival-rate',
      timeUnit: '1s',
      stages: getStages(),
      preAllocatedVUs: Number(__ENV.CPU_PRE_ALLOCATED_VUS || '100'),
      maxVUs: Number(__ENV.CPU_MAX_VUS || '1000'),
    },
  },
  noConnectionReuse,
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
    'status is 2xx or 3xx': (res) => res.status >= 200 && res.status < 400,
  });
}

export function handleSummary(data) {
  return buildSummary(data);
}

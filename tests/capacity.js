import http from 'k6/http';
import { check } from 'k6';
import { appendCacheBuster, buildUrl, getEnvEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { capacityThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const endpoints = getEnvEndpoints('CAPACITY_ENDPOINTS', __ENV.LOAD_ENDPOINTS || '/');
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const preAllocatedVUs = Number(__ENV.CAPACITY_PRE_ALLOCATED_VUS || '100');
const maxVUs = Number(__ENV.CAPACITY_MAX_VUS || '2000');

function getCapacityStages() {
  const stepRates = (__ENV.CAPACITY_RATE_STEPS || '50,100,200,400,800')
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value) && value > 0);

  const rampDuration = __ENV.CAPACITY_RAMP_DURATION || '30s';
  const holdDuration = __ENV.CAPACITY_HOLD_DURATION || '1m';
  const rampDownDuration = __ENV.CAPACITY_RAMP_DOWN_DURATION || '1m';
  const stages = [];

  for (const rate of stepRates) {
    stages.push({ duration: rampDuration, target: rate });
    stages.push({ duration: holdDuration, target: rate });
  }

  stages.push({ duration: rampDownDuration, target: 0 });
  return stages;
}

export const options = {
  scenarios: {
    capacity_search: {
      executor: 'ramping-arrival-rate',
      timeUnit: '1s',
      preAllocatedVUs,
      maxVUs,
      stages: getCapacityStages(),
    },
  },
  thresholds: capacityThresholds,
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

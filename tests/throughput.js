import http from 'k6/http';
import { check } from 'k6';
import { appendCacheBuster, buildUrl, getEnvEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { throughputThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const endpoints = getEnvEndpoints('THROUGHPUT_ENDPOINTS', __ENV.LOAD_ENDPOINTS || '/');
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const preAllocatedVUs = Number(__ENV.THROUGHPUT_PRE_ALLOCATED_VUS || '50');
const maxVUs = Number(__ENV.THROUGHPUT_MAX_VUS || '500');

function getStages() {
  const rates = (__ENV.THROUGHPUT_RATE_STEPS || '50,100,200,400')
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value) && value > 0);
  const rampDuration = __ENV.THROUGHPUT_RAMP_DURATION || '30s';
  const holdDuration = __ENV.THROUGHPUT_HOLD_DURATION || '1m';
  const stages = [];

  for (const rate of rates) {
    stages.push({ duration: rampDuration, target: rate });
    stages.push({ duration: holdDuration, target: rate });
  }

  stages.push({ duration: __ENV.THROUGHPUT_RAMP_DOWN_DURATION || '30s', target: 0 });
  return stages;
}

export const options = {
  scenarios: {
    throughput: {
      executor: 'ramping-arrival-rate',
      timeUnit: '1s',
      preAllocatedVUs,
      maxVUs,
      stages: getStages(),
    },
  },
  thresholds: throughputThresholds,
};

export default function () {
  const endpoint = appendCacheBuster(pickEndpoint(endpoints));
  const response = http.get(buildUrl(targetUrl, endpoint), {
    timeout: requestTimeout,
    tags: { endpoint: endpoint.split('?')[0] },
  });

  check(response, {
    'status is not 5xx': (res) => res.status < 500,
  });
}

export function handleSummary(data) {
  return buildSummary(data);
}

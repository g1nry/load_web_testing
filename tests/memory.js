import http from 'k6/http';
import { check, sleep } from 'k6';
import { appendCacheBuster, buildUrl, getEnvEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { memoryThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const memoryEndpointsConfigured = Boolean(__ENV.MEMORY_ENDPOINTS);
const endpoints = getEnvEndpoints('MEMORY_ENDPOINTS', __ENV.LOAD_ENDPOINTS || '/');
const requestTimeout = __ENV.MEMORY_REQUEST_TIMEOUT || __ENV.REQUEST_TIMEOUT || '15s';
const sleepSeconds = Number(__ENV.MEMORY_SLEEP_SECONDS || '0');
const minResponseBytes = Number(__ENV.MEMORY_MIN_RESPONSE_BYTES || '0');

if (!memoryEndpointsConfigured) {
  console.warn('MEMORY_ENDPOINTS is not set. Memory profile is running against LOAD_ENDPOINTS fallback and may not create useful RAM pressure.');
}

export const options = {
  scenarios: {
    memory_pressure: {
      executor: 'constant-vus',
      vus: Number(__ENV.MEMORY_VUS || '300'),
      duration: __ENV.MEMORY_DURATION || '10m',
    },
  },
  thresholds: memoryThresholds,
};

export default function () {
  const endpoint = appendCacheBuster(pickEndpoint(endpoints));
  const response = http.get(buildUrl(targetUrl, endpoint), {
    timeout: requestTimeout,
    tags: { endpoint: endpoint.split('?')[0] },
  });
  const bodyLength = response.body ? response.body.length : 0;

  if (minResponseBytes > 0 && __VU === 1 && __ITER < 3 && bodyLength < minResponseBytes) {
    console.warn(`Memory endpoint response is only ${bodyLength} bytes. Configure MEMORY_ENDPOINTS to hit RAM-heavy endpoints.`);
  }

  check(response, {
    'server responded': (res) => res.status > 0,
    'status is 2xx or 3xx': (res) => res.status >= 200 && res.status < 400,
    'response is large enough for memory pressure': () => minResponseBytes === 0 || bodyLength >= minResponseBytes,
  });

  if (sleepSeconds > 0) {
    sleep(sleepSeconds);
  }
}

export function handleSummary(data) {
  return buildSummary(data);
}

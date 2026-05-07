import http from 'k6/http';
import { check } from 'k6';
import { appendCacheBuster, buildUrl, getEnvEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { networkThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const networkEndpointsConfigured = Boolean(__ENV.NETWORK_ENDPOINTS);
const endpoints = getEnvEndpoints('NETWORK_ENDPOINTS', __ENV.LOAD_ENDPOINTS || '/');
const requestTimeout = __ENV.NETWORK_REQUEST_TIMEOUT || __ENV.REQUEST_TIMEOUT || '15s';
const minResponseBytes = Number(__ENV.NETWORK_MIN_RESPONSE_BYTES || '10240');

if (!networkEndpointsConfigured) {
  console.warn('NETWORK_ENDPOINTS is not set. Network profile is running against LOAD_ENDPOINTS fallback and may not create useful bandwidth pressure.');
}

export const options = {
  scenarios: {
    network_pressure: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.NETWORK_RATE || '200'),
      timeUnit: '1s',
      duration: __ENV.NETWORK_DURATION || '5m',
      preAllocatedVUs: Number(__ENV.NETWORK_PRE_ALLOCATED_VUS || '100'),
      maxVUs: Number(__ENV.NETWORK_MAX_VUS || '1000'),
    },
  },
  thresholds: networkThresholds,
};

export default function () {
  const endpoint = appendCacheBuster(pickEndpoint(endpoints));
  const response = http.get(buildUrl(targetUrl, endpoint), {
    timeout: requestTimeout,
    tags: { endpoint: endpoint.split('?')[0] },
  });
  const bodyLength = response.body ? response.body.length : 0;

  if (__VU === 1 && __ITER < 3 && bodyLength < minResponseBytes) {
    console.warn(`Network endpoint response is only ${bodyLength} bytes. Configure NETWORK_ENDPOINTS to hit large-response endpoints.`);
  }

  check(response, {
    'server responded': (res) => res.status > 0,
    'status is not 5xx': (res) => res.status < 500,
    'response is large enough for network pressure': () => bodyLength >= minResponseBytes,
  });
}

export function handleSummary(data) {
  return buildSummary(data);
}

import http from 'k6/http';
import { check, sleep } from 'k6';
import { buildUrl, getLoadEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { spikeThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const endpoints = getLoadEndpoints();
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const sleepSeconds = Number(__ENV.SLEEP_SECONDS || '1');

export const options = {
  stages: [
    { duration: __ENV.SPIKE_LOW_DURATION || '1m', target: Number(__ENV.SPIKE_LOW_VUS || '10') },
    { duration: __ENV.SPIKE_HIGH_DURATION || '1m', target: Number(__ENV.SPIKE_HIGH_VUS || '100') },
    { duration: __ENV.SPIKE_RECOVERY_DURATION || '2m', target: Number(__ENV.SPIKE_LOW_VUS || '10') },
    { duration: '30s', target: 0 },
  ],
  thresholds: spikeThresholds,
};

export default function () {
  const endpoint = pickEndpoint(endpoints);

  const response = http.get(buildUrl(targetUrl, endpoint), {
    timeout: requestTimeout,
    tags: { endpoint },
  });

  check(response, {
    'server responded': (res) => res.status > 0,
    'status is not 5xx': (res) => res.status < 500,
  });

  sleep(sleepSeconds);
}

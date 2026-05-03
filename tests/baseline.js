import http from 'k6/http';
import { check, sleep } from 'k6';
import { buildUrl, getLoadEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { baselineThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const endpoints = getLoadEndpoints();
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const sleepSeconds = Number(__ENV.SLEEP_SECONDS || '1');

export const options = {
  vus: Number(__ENV.BASELINE_VUS || '10'),
  duration: __ENV.BASELINE_DURATION || '3m',
  thresholds: baselineThresholds,
};

export default function () {
  const endpoint = pickEndpoint(endpoints);

  const response = http.get(buildUrl(targetUrl, endpoint), {
    timeout: requestTimeout,
    tags: { endpoint },
  });

  check(response, {
    'status is 2xx or 3xx': (res) => res.status >= 200 && res.status < 400,
  });

  sleep(sleepSeconds);
}

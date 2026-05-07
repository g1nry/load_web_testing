import http from 'k6/http';
import { check, sleep } from 'k6';
import { getTargetUrl, buildUrl } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { smokeThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const sleepSeconds = Number(__ENV.SLEEP_SECONDS || '1');

export const options = {
  vus: Number(__ENV.SMOKE_VUS || '1'),
  duration: __ENV.SMOKE_DURATION || '30s',
  thresholds: smokeThresholds,
};

export default function () {
  const response = http.get(buildUrl(targetUrl, '/'), {
    timeout: requestTimeout,
  });

  check(response, {
    'root endpoint returns 2xx or 3xx': (res) => res.status >= 200 && res.status < 400,
  });

  sleep(sleepSeconds);
}

export function handleSummary(data) {
  return buildSummary(data);
}

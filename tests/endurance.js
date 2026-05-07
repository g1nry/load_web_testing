import http from 'k6/http';
import { check, sleep } from 'k6';
import { buildUrl, getLoadEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { enduranceThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const endpoints = getLoadEndpoints();
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const sleepSeconds = Number(__ENV.SLEEP_SECONDS || '1');

export const options = {
  vus: Number(__ENV.ENDURANCE_VUS || '20'),
  duration: __ENV.ENDURANCE_DURATION || '30m',
  thresholds: enduranceThresholds,
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

export function handleSummary(data) {
  return buildSummary(data);
}

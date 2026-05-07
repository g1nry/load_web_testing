import http from 'k6/http';
import { check, sleep } from 'k6';
import { buildUrl, getLoadEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { stressThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const endpoints = getLoadEndpoints();
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const sleepSeconds = Number(__ENV.SLEEP_SECONDS || '1');

export const options = {
  stages: [
    { duration: __ENV.STRESS_STAGE_1_DURATION || '2m', target: Number(__ENV.STRESS_STAGE_1_VUS || '10') },
    { duration: __ENV.STRESS_STAGE_2_DURATION || '3m', target: Number(__ENV.STRESS_STAGE_2_VUS || '50') },
    { duration: __ENV.STRESS_STAGE_3_DURATION || '3m', target: Number(__ENV.STRESS_STAGE_3_VUS || '100') },
    { duration: __ENV.STRESS_RAMP_DOWN_DURATION || '2m', target: 0 },
  ],
  thresholds: stressThresholds,
};

export default function () {
  const endpoint = pickEndpoint(endpoints);

  const response = http.get(buildUrl(targetUrl, endpoint), {
    timeout: requestTimeout,
    tags: { endpoint },
  });

  check(response, {
    'server responded': (res) => res.status > 0,
  });

  sleep(sleepSeconds);
}

export function handleSummary(data) {
  return buildSummary(data);
}

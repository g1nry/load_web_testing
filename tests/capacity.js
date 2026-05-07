import http from 'k6/http';
import { check, sleep } from 'k6';
import { buildUrl, getLoadEndpoints, getTargetUrl, pickEndpoint } from '../config/endpoints.js';
import { buildSummary } from '../config/report.js';
import { capacityThresholds } from '../config/thresholds.js';

const targetUrl = getTargetUrl();
const endpoints = getLoadEndpoints();
const requestTimeout = __ENV.REQUEST_TIMEOUT || '5s';
const sleepSeconds = Number(__ENV.SLEEP_SECONDS || '1');

function getCapacityStages() {
  const stepVus = (__ENV.CAPACITY_STEP_VUS || '5,10,20,40,60,80,100')
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value) && value >= 0);

  const rampDuration = __ENV.CAPACITY_RAMP_DURATION || '30s';
  const holdDuration = __ENV.CAPACITY_HOLD_DURATION || '1m';
  const rampDownDuration = __ENV.CAPACITY_RAMP_DOWN_DURATION || '1m';
  const stages = [];

  for (const vus of stepVus) {
    stages.push({ duration: rampDuration, target: vus });
    stages.push({ duration: holdDuration, target: vus });
  }

  stages.push({ duration: rampDownDuration, target: 0 });
  return stages;
}

export const options = {
  stages: getCapacityStages(),
  thresholds: capacityThresholds,
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

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
const stepDuration = __ENV.CAPACITY_STEP_DURATION || __ENV.CAPACITY_HOLD_DURATION || '1m';
const gracefulStop = __ENV.CAPACITY_GRACEFUL_STOP || '30s';
const failureRateLimit = __ENV.CAPACITY_FAILURE_RATE_LIMIT || '0.05';
const p95LimitMs = __ENV.CAPACITY_P95_LIMIT_MS || '1000';

function getStepRates() {
  return (__ENV.CAPACITY_RATE_STEPS || '50,100,200,400,800')
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value) && value > 0);
}

function scenarioName(rate, index) {
  return `capacity_${index + 1}_${rate}_rps`;
}

function durationToSeconds(duration) {
  const normalized = String(duration).trim().toLowerCase();
  const matches = [...normalized.matchAll(/(\d+)(ms|s|m|h)/g)];

  if (matches.length === 0 && /^\d+$/.test(normalized)) {
    return Number(normalized);
  }

  return matches.reduce((total, match) => {
    const value = Number(match[1]);
    const unit = match[2];

    if (unit === 'ms') {
      return total + (value > 0 ? 1 : 0);
    }

    if (unit === 's') {
      return total + value;
    }

    if (unit === 'm') {
      return total + value * 60;
    }

    return total + value * 3600;
  }, 0);
}

function secondsToDuration(seconds) {
  if (seconds <= 0) {
    return '0s';
  }

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const restSeconds = seconds % 60;
  let output = '';

  if (hours > 0) {
    output += `${hours}h`;
  }

  if (minutes > 0) {
    output += `${minutes}m`;
  }

  if (restSeconds > 0 || output === '') {
    output += `${restSeconds}s`;
  }

  return output;
}

function getCapacityScenarios() {
  const scenarios = {};
  const stepRates = getStepRates();
  const stepSeconds = durationToSeconds(stepDuration);

  stepRates.forEach((rate, index) => {
    scenarios[scenarioName(rate, index)] = {
      executor: 'constant-arrival-rate',
      rate,
      timeUnit: '1s',
      duration: stepDuration,
      startTime: secondsToDuration(index * stepSeconds),
      preAllocatedVUs,
      maxVUs,
      gracefulStop,
      tags: {
        capacity_rate: String(rate),
      },
    };
  });

  return scenarios;
}

function getCapacityThresholds() {
  const thresholds = { ...capacityThresholds };
  const stepRates = getStepRates();

  stepRates.forEach((rate, index) => {
    const scenario = scenarioName(rate, index);
    thresholds[`http_req_failed{scenario:${scenario}}`] = [`rate<${failureRateLimit}`];
    thresholds[`http_req_duration{scenario:${scenario}}`] = [`p(95)<${p95LimitMs}`];
    thresholds[`dropped_iterations{scenario:${scenario}}`] = ['count<1'];
    thresholds[`http_reqs{scenario:${scenario}}`] = ['count>=0'];
  });

  return thresholds;
}

export const options = {
  scenarios: getCapacityScenarios(),
  thresholds: getCapacityThresholds(),
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

export const smokeThresholds = {
  http_req_failed: ['rate<0.05'],
  http_req_duration: ['p(95)<1000'],
};

export const discoveryThresholds = {
  http_req_duration: ['p(95)<3000'],
};

export const throughputThresholds = {
  http_req_failed: ['rate<0.10'],
  http_req_duration: ['p(95)<2000'],
};

export const cpuThresholds = {
  http_req_failed: ['rate<0.20'],
  http_req_duration: ['p(95)<3000'],
};

export const memoryThresholds = {
  http_req_failed: ['rate<0.20'],
  http_req_duration: ['p(95)<5000'],
};

export const networkThresholds = {
  http_req_failed: ['rate<0.20'],
  http_req_duration: ['p(95)<5000'],
};

export const capacityThresholds = {
  http_req_failed: ['rate<0.30'],
  http_req_duration: ['p(95)<5000'],
};

// Abort thresholds are cumulative since test start; k6 evaluates them periodically.
export function withStopThresholds(thresholds) {
  const failure = Number(__ENV.STOP_FAILURE_RATE || '0.10');
  const latency = Number(__ENV.STOP_P95_MS || '2000');
  const delay = __ENV.STOP_DELAY || '30s';
  if (!Number.isFinite(failure) || failure <= 0 || failure > 1 || !Number.isFinite(latency) || latency <= 0) {
    throw new Error('STOP_FAILURE_RATE must be in (0, 1] and STOP_P95_MS must be positive');
  }
  return {
    ...thresholds,
    http_req_failed: [
      ...(thresholds.http_req_failed || []),
      { threshold: `rate<${failure}`, abortOnFail: true, delayAbortEval: delay },
    ],
    http_req_duration: [
      ...(thresholds.http_req_duration || []),
      { threshold: `p(95)<${latency}`, abortOnFail: true, delayAbortEval: delay },
    ],
  };
}

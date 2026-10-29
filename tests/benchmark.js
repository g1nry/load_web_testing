import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { getBenchmarkConfig, phaseAt } from '../config/benchmark.js';
import { buildUrl } from '../config/endpoints.js';
import { diagnosticOptions, recordResponseSize } from '../config/diagnostics.js';
import { buildSummary } from '../config/report.js';
import { withStopThresholds } from '../config/thresholds.js';

const config = getBenchmarkConfig();
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }));

export const options = {
  ...diagnosticOptions,
  maxRedirects: 0,
  scenarios: {
    local_benchmark: {
      executor: 'ramping-arrival-rate', timeUnit: '1s', startRate: config.startRate,
      preAllocatedVUs: config.preAllocatedVUs, maxVUs: config.maxVUs,
      gracefulStop: config.gracefulStop,
      stages: config.phases.map((phase) => ({ duration: phase.duration, target: phase.targetRate })),
    },
  },
  thresholds: withStopThresholds({ checks: ['rate==1'] }),
};

export default function () {
  // A repeatable round-robin mix; duplicate paths provide simple integer weights.
  const endpoint = config.endpoints[exec.scenario.iterationInTest % config.endpoints.length];
  const phase = phaseAt(config, (Date.now() - exec.scenario.startTime) / 1000);
  const tags = { benchmark_phase: phase.name };
  const response = http.get(buildUrl(config.target, endpoint), {
    timeout: config.requestTimeout, responseType: 'binary', redirects: 0,
    tags: { ...tags, endpoint: endpoint.split('?')[0] },
  });
  recordResponseSize(response, endpoint, 'GET', tags);
  check(response, { 'local endpoint returns 2xx': (res) => res.status >= 200 && res.status < 300 }, tags);
}

export function handleSummary(data) {
  return buildSummary(data, config);
}

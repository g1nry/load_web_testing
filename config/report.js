function metric(data, name) {
  return data.metrics && data.metrics[name] && data.metrics[name].values
    ? data.metrics[name].values
    : {};
}

function value(data, name, field, fallback = 0) {
  const rawValue = metric(data, name)[field];
  return typeof rawValue === 'number' && Number.isFinite(rawValue) ? rawValue : fallback;
}

function formatNumber(number, digits = 2) {
  return Number.isFinite(number) ? number.toFixed(digits) : 'n/a';
}

function formatCount(number) {
  return Number.isFinite(number) ? String(Math.round(number)) : 'n/a';
}

function formatPercent(rate) {
  return Number.isFinite(rate) ? `${(rate * 100).toFixed(2)}%` : 'n/a';
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) {
    return 'n/a';
  }

  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${formatNumber(value, unitIndex === 0 ? 0 : 2)} ${units[unitIndex]}`;
}

function formatMs(ms) {
  return Number.isFinite(ms) ? `${formatNumber(ms, 2)} ms` : 'n/a';
}

function formatMbps(bytesPerSecond) {
  return Number.isFinite(bytesPerSecond) ? `${formatNumber((bytesPerSecond * 8) / 1000000, 3)} Mbps` : 'n/a';
}

function durationSeconds(data) {
  if (data.state && Number.isFinite(data.state.testRunDurationMs)) {
    return data.state.testRunDurationMs / 1000;
  }
  const httpRate = value(data, 'http_reqs', 'rate');
  const httpCount = value(data, 'http_reqs', 'count');

  if (httpRate > 0 && httpCount > 0) {
    return httpCount / httpRate;
  }

  const iterationRate = value(data, 'iterations', 'rate');
  const iterationCount = value(data, 'iterations', 'count');

  if (iterationRate > 0 && iterationCount > 0) {
    return iterationCount / iterationRate;
  }

  return 0;
}

function thresholdsStatus(data) {
  const failed = [];

  for (const [metricName, metricData] of Object.entries(data.metrics || {})) {
    for (const [thresholdName, thresholdData] of Object.entries(metricData.thresholds || {})) {
      if (!thresholdData.ok) {
        failed.push(`${metricName}: ${thresholdName}`);
      }
    }
  }

  return failed;
}

function thresholdOk(data, metricName) {
  const thresholds = (data.metrics && data.metrics[metricName] && data.metrics[metricName].thresholds) || {};
  const entries = Object.values(thresholds);

  if (entries.length === 0) {
    return null;
  }

  return entries.every((threshold) => threshold.ok);
}

function metricByScenarioName(baseMetric, scenario) {
  return `${baseMetric}{scenario:${scenario}}`;
}

function capacitySteps(data) {
  const steps = [];
  const seen = new Set();

  for (const metricName of Object.keys(data.metrics || {})) {
    const match = metricName.match(/\{scenario:(capacity_(\d+)_(\d+)_rps)\}/);

    if (!match) {
      continue;
    }

    const scenario = match[1];
    if (seen.has(scenario)) {
      continue;
    }

    seen.add(scenario);
    steps.push({
      scenario,
      index: Number(match[2]),
      rateTarget: Number(match[3]),
    });
  }

  return steps
    .sort((left, right) => left.index - right.index)
    .map((step) => {
      const failedMetric = metricByScenarioName('http_req_failed', step.scenario);
      const durationMetric = metricByScenarioName('http_req_duration', step.scenario);
      const droppedMetric = metricByScenarioName('dropped_iterations', step.scenario);
      const requestsMetric = metricByScenarioName('http_reqs', step.scenario);
      const failureRate = value(data, failedMetric, 'rate', NaN);
      const p95 = value(data, durationMetric, 'p(95)', NaN);
      const dropped = value(data, droppedMetric, 'count', 0);
      const requestCount = value(data, requestsMetric, 'count', NaN);
      // k6 summary rates use the entire test duration, not the scenario duration.
      // Do not present this value as a per-step throughput.
      const failedOk = thresholdOk(data, failedMetric);
      const p95Ok = thresholdOk(data, durationMetric);
      const droppedOk = thresholdOk(data, droppedMetric);

      return {
        ...step,
        failureRate,
        p95,
        dropped,
        requestCount,
        stable: requestCount > 0 && Number.isFinite(failureRate) && Number.isFinite(p95)
          && failedOk !== null && p95Ok !== null && droppedOk !== null
          ? failedOk && p95Ok && droppedOk : null,
      };
    });
}

function buildCapacityAnalysis(data) {
  const profile = __ENV.K6_PROFILE || '';

  if (profile !== 'capacity') {
    return '';
  }

  const steps = capacitySteps(data);

  if (steps.length === 0) {
    return `## Capacity / Failure Threshold Notes

- Last stable load: not detected
- First failing load: not detected
- Failure criterion: per-step thresholds were not found in the k6 summary
- Evidence: check capacity scenario configuration and summary JSON
`;
  }

  let lastStable = null;
  let firstFailing = null;

  for (const step of steps) {
    if (step.stable === null) {
      break;
    }
    if (step.stable) {
      lastStable = step;
      continue;
    }

    firstFailing = step;
    break;
  }

  const rows = steps
    .map((step) => `| ${step.rateTarget} | ${formatCount(step.requestCount)} | ${formatPercent(step.failureRate)} | ${formatMs(step.p95)} | ${formatCount(step.dropped)} | ${step.stable === null ? 'no data' : step.stable ? 'stable' : 'unstable'} |`)
    .join('\n');

  return `## Capacity / Failure Threshold Notes

- Last stable load: ${lastStable ? `${lastStable.rateTarget} RPS` : 'none'}
- First failing load: ${firstFailing ? `${firstFailing.rateTarget} RPS` : steps.some((step) => step.stable === null) ? 'undetermined (missing samples)' : 'not reached'}
- Failure criterion: per-step http failure rate, p95 latency and dropped iterations thresholds
- Evidence: see per-step table below. Target RPS is scheduled iterations, not measured peak throughput.
- Dropped iterations indicate the generator could not start all scheduled work; this alone does not prove a server failure.
- Overlapping graceful stops can mix traffic from adjacent steps.

| Target RPS | Requests | Failure rate | p95 latency | Dropped iterations | Status |
| ---: | ---: | ---: | ---: | ---: | --- |
${rows}
`;
}

function endpointList() {
  const profile = __ENV.K6_PROFILE || '';
  const endpointEnvByProfile = {
    throughput: 'THROUGHPUT_ENDPOINTS',
    cpu: 'CPU_ENDPOINTS',
    memory: 'MEMORY_ENDPOINTS',
    network: 'NETWORK_ENDPOINTS',
    capacity: 'CAPACITY_ENDPOINTS',
  };
  const endpointEnv = endpointEnvByProfile[profile] || 'LOAD_ENDPOINTS';
  const rawEndpoints = __ENV[endpointEnv] || __ENV.LOAD_ENDPOINTS || '/';

  return rawEndpoints
    .split(',')
    .map((endpoint) => endpoint.trim())
    .filter(Boolean)
    .join(', ');
}

function scenarioSummary(data) {
  const options = data.options || {};
  const scenarioNames = Object.keys(options.scenarios || {});

  if (scenarioNames.length > 0) {
    return scenarioNames.join(', ');
  }

  return __ENV.K6_PROFILE || 'default';
}

function markdownValue(raw) {
  return String(raw).replace(/\|/g, '\\|').replace(/[\r\n]/g, ' ');
}

function benchmarkPlan(config) {
  if (!config || config.profile !== 'benchmark') return '';
  const rows = config.phases.map((phase) => `| ${phase.name} | ${phase.kind} | ${phase.duration} | ${phase.startRate} | ${phase.targetRate} |`).join('\n');
  return `## Local Benchmark Configuration

| Field | Value |
| --- | --- |
| Run label | ${markdownValue(config.labels.run)} |
| Server CPU label | ${markdownValue(config.labels.serverCPU)} |
| Server memory label | ${markdownValue(config.labels.serverMemory)} |
| Server configuration label | ${markdownValue(config.labels.serverConfig)} |
| Generator location label | ${markdownValue(config.labels.generatorLocation)} |
| Planned duration | ${config.plannedDurationSeconds} s plus graceful stop |
| Preallocated / maximum VUs | ${config.preAllocatedVUs} / ${config.maxVUs} |
| Stop failure rate / p95 / evaluation delay | ${config.stopCriteria.failureRate} / ${config.stopCriteria.p95Ms} ms / ${config.stopCriteria.delay} |

Resource labels are supplied by the operator; this runner does not apply or verify server resource limits. A separate generator avoids competing with the server for CPU and network resources. Endpoint order is repeated round-robin; duplicate paths act as integer weights. Redirects are not followed.

| Phase | Kind | Duration | From target RPS | To target RPS |
| --- | --- | --- | ---: | ---: |
${rows}
`;
}

function buildMarkdown(data, config) {
  const profile = (config && config.profile) || __ENV.K6_PROFILE || 'unknown';
  const script = __ENV.K6_SCRIPT || 'unknown';
  const startedAt = __ENV.K6_STARTED_AT || 'unknown';
  const summaryJson = __ENV.K6_SUMMARY_JSON || 'unknown';
  const summaryMarkdown = __ENV.K6_SUMMARY_MARKDOWN || 'unknown';
  const grafanaUrl = __ENV.GRAFANA_DASHBOARD_URL || 'not provided';
  const duration = durationSeconds(data);
  const sentRate = value(data, 'data_sent', 'rate');
  const receivedRate = value(data, 'data_received', 'rate');
  const totalNetworkRate = sentRate + receivedRate;
  const failedThresholds = thresholdsStatus(data);

  return `# k6 Test Report: ${profile}

## Run Metadata

| Field | Value |
| --- | --- |
| Profile | ${profile} |
| Run ID | ${__ENV.K6_RUN_ID || 'not configured'} |
| Script | ${script} |
| Started at | ${startedAt} |
| Target URL | ${(config && config.target) || __ENV.TARGET_URL || 'not provided'} |
| Endpoints | ${config ? markdownValue(config.endpoints.join(', ')) : endpointList()} |
| Request timeout | ${(config && config.requestTimeout) || (profile === 'network' ? __ENV.NETWORK_REQUEST_TIMEOUT : profile === 'memory' ? __ENV.MEMORY_REQUEST_TIMEOUT : '') || __ENV.REQUEST_TIMEOUT || 'default'} |
| Sleep between iterations | ${config ? 'arrival-rate paced' : __ENV.SLEEP_SECONDS || 'default'} |
| Scenarios | ${scenarioSummary(data)} |
| JSON summary | ${summaryJson} |
| Markdown report | ${summaryMarkdown} |
| Grafana dashboard | ${grafanaUrl} |

## Client-Side Load

| Metric | Value |
| --- | ---: |
| Duration | ${formatNumber(duration, 2)} s |
| HTTP requests | ${formatCount(value(data, 'http_reqs', 'count'))} |
| Average completed HTTP requests/s (whole run) | ${formatNumber(value(data, 'http_reqs', 'rate', NaN))} |
| Peak RPS | Not available from summary; requires time-series data |
| Dropped iterations | ${formatCount(value(data, 'dropped_iterations', 'count', 0))} |
| Iterations | ${formatCount(value(data, 'iterations', 'count'))} |
| Checks passed | ${formatCount(value(data, 'checks', 'passes'))} |
| Checks failed | ${formatCount(value(data, 'checks', 'fails'))} |
| HTTP failure rate | ${formatPercent(value(data, 'http_req_failed', 'rate'))} |

## Latency

| Metric | Value |
| --- | ---: |
| Average | ${formatMs(value(data, 'http_req_duration', 'avg', NaN))} |
| Median | ${formatMs(value(data, 'http_req_duration', 'med', NaN))} |
| p90 | ${formatMs(value(data, 'http_req_duration', 'p(90)', NaN))} |
| p95 | ${formatMs(value(data, 'http_req_duration', 'p(95)', NaN))} |
| p99 | ${formatMs(value(data, 'http_req_duration', 'p(99)', NaN))} |
| Max | ${formatMs(value(data, 'http_req_duration', 'max', NaN))} |

## Network From k6 Runner

| Metric | Value |
| --- | ---: |
| Data sent | ${formatBytes(value(data, 'data_sent', 'count'))} |
| Data received | ${formatBytes(value(data, 'data_received', 'count'))} |
| Avg send rate | ${formatBytes(sentRate)}/s (${formatMbps(sentRate)}) |
| Avg receive rate | ${formatBytes(receivedRate)}/s (${formatMbps(receivedRate)}) |
| Combined avg network rate | ${formatBytes(totalNetworkRate)}/s (${formatMbps(totalNetworkRate)}) |

Counts include HTTP requests from redirects; average RPS covers the entire run, including ramp-down and graceful stop. A failure threshold is not proof of a site outage.

Network totals are k6 client-side transfer counters, not response body sizes or server interface counters.

## Thresholds

${failedThresholds.length === 0 ? '- All configured thresholds passed.' : failedThresholds.map((item) => `- Failed: ${item}`).join('\n')}

${buildCapacityAnalysis(data)}

${benchmarkPlan(config)}
`;
}

function buildStdoutSummary(data) {
  const failedThresholds = thresholdsStatus(data);
  const sentRate = value(data, 'data_sent', 'rate');
  const receivedRate = value(data, 'data_received', 'rate');

  return `
Readable report: ${__ENV.K6_SUMMARY_MARKDOWN || 'not configured'}

Client-side summary:
  http_reqs:        ${formatCount(value(data, 'http_reqs', 'count'))}
  avg_rps:          ${formatNumber(value(data, 'http_reqs', 'rate'))}
  failure_rate:     ${formatPercent(value(data, 'http_req_failed', 'rate'))}
  p95_latency:      ${formatMs(value(data, 'http_req_duration', 'p(95)'))}
  sent:             ${formatBytes(value(data, 'data_sent', 'count'))}
  received:         ${formatBytes(value(data, 'data_received', 'count'))}
  avg_network_rate: ${formatMbps(sentRate + receivedRate)}
  thresholds:       ${failedThresholds.length === 0 ? 'passed' : `failed (${failedThresholds.length})`}
`;
}

export function buildSummary(data, config) {
  const markdown = buildMarkdown(data, config);
  const output = {
    stdout: buildStdoutSummary(data),
  };

  if (__ENV.K6_SUMMARY_MARKDOWN) {
    output[__ENV.K6_SUMMARY_MARKDOWN] = markdown;
  }

  if (config && __ENV.K6_RUN_CONFIG_JSON) {
    output[__ENV.K6_RUN_CONFIG_JSON] = JSON.stringify(config, null, 2);
  }

  return output;
}

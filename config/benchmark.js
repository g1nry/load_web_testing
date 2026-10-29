// Pure configuration helpers; shared by the local profile and offline checks.
export function assertLocalTarget(raw) {
  const match = String(raw).match(/^https?:\/\/([^/?#]+)(\/[^?#]*)?$/i);
  if (!match || match[1].includes('@')) {
    throw new Error('BENCHMARK_TARGET_URL must be an HTTP(S) loopback or private-IP URL without credentials, query or fragment');
  }
  const authority = match[1].toLowerCase();
  const parts = authority.startsWith('[')
    ? authority.match(/^\[([a-f0-9:]+)\](?::(\d+))?$/)
    : authority.match(/^([^:]+)(?::(\d+))?$/);
  if (!parts || (parts[2] && (Number(parts[2]) < 1 || Number(parts[2]) > 65535))) {
    throw new Error('Invalid local benchmark host or port');
  }
  const host = parts[1];
  const ipv4 = host.split('.');
  const canonicalIPv4 = ipv4.length === 4 && ipv4.every((part) => /^\d+$/.test(part)
    && Number(part) <= 255 && String(Number(part)) === part);
  const octets = ipv4.map(Number);
  const privateIPv4 = canonicalIPv4 && (octets[0] === 127 || octets[0] === 10
    || (octets[0] === 192 && octets[1] === 168)
    || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31));
  // ULA IPv6 literals and ::1; DNS aliases and public addresses are excluded.
  const localIPv6 = host === '::1' || /^f[cd][a-f0-9]{2}:[a-f0-9:]+$/.test(host);
  if (host !== 'localhost' && !privateIPv4 && !localIPv6) {
    throw new Error('Benchmark target must be localhost, loopback, RFC1918 IPv4 or ULA IPv6; public targets and DNS aliases are not accepted');
  }
  return String(raw).replace(/\/+$/, '');
}

export function durationSeconds(raw, name, allowZero = false) {
  const normalized = String(raw).trim();
  const pieces = [...normalized.matchAll(/(\d+(?:\.\d+)?)(ms|s|m|h)/g)];
  if (!pieces.length || pieces.map((piece) => piece[0]).join('') !== normalized) {
    throw new Error(`${name} must be a duration such as 20s, 2m or 1m30s`);
  }
  const factors = { ms: .001, s: 1, m: 60, h: 3600 };
  const seconds = pieces.reduce((sum, piece) => sum + Number(piece[1]) * factors[piece[2]], 0);
  if (!Number.isFinite(seconds) || seconds < 0 || (!allowZero && seconds === 0)) {
    throw new Error(`${name} must be ${allowZero ? 'nonnegative' : 'positive'}`);
  }
  return seconds;
}

function positiveInteger(raw, name) {
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

export function getBenchmarkConfig(env = __ENV) {
  const target = assertLocalTarget(env.BENCHMARK_TARGET_URL || 'http://127.0.0.1:8080');
  const endpoints = (env.BENCHMARK_ENDPOINTS || '/').split(',').map((path) => path.trim());
  if (endpoints.some((path) => !path.startsWith('/') || path.startsWith('//') || path.includes('#'))) {
    throw new Error('BENCHMARK_ENDPOINTS must contain nonempty same-origin paths starting with /');
  }
  const rates = (env.BENCHMARK_RATE_STEPS || '50,100,200,400,600').split(',')
    .map((raw) => positiveInteger(raw.trim(), 'BENCHMARK_RATE_STEPS'));
  if (rates.some((rate, index) => index > 0 && rate <= rates[index - 1])) {
    throw new Error('BENCHMARK_RATE_STEPS must be strictly increasing');
  }
  const startRate = positiveInteger(env.BENCHMARK_START_RATE || '10', 'BENCHMARK_START_RATE');
  if (startRate > rates[0]) {
    throw new Error('BENCHMARK_START_RATE must not exceed the first step');
  }
  const preAllocatedVUs = positiveInteger(env.BENCHMARK_PRE_ALLOCATED_VUS || '50', 'BENCHMARK_PRE_ALLOCATED_VUS');
  const maxVUs = positiveInteger(env.BENCHMARK_MAX_VUS || '500', 'BENCHMARK_MAX_VUS');
  if (maxVUs < preAllocatedVUs) {
    throw new Error('BENCHMARK_MAX_VUS must be >= BENCHMARK_PRE_ALLOCATED_VUS');
  }
  const requestTimeout = env.BENCHMARK_REQUEST_TIMEOUT || '5s';
  const gracefulStop = env.BENCHMARK_GRACEFUL_STOP || '30s';
  const stopCriteria = {
    failureRate: Number(env.STOP_FAILURE_RATE || '0.10'),
    p95Ms: Number(env.STOP_P95_MS || '2000'),
    delay: env.STOP_DELAY || '30s',
  };
  durationSeconds(requestTimeout, 'BENCHMARK_REQUEST_TIMEOUT');
  durationSeconds(gracefulStop, 'BENCHMARK_GRACEFUL_STOP', true);
  durationSeconds(stopCriteria.delay, 'STOP_DELAY', true);
  const phases = [];
  let elapsed = 0;
  let previousRate = startRate;
  const add = (name, kind, duration, targetRate, allowZero = false) => {
    const seconds = durationSeconds(duration, name, allowZero);
    if (!seconds) return;
    phases.push({ name, kind, duration, startSeconds: elapsed, endSeconds: elapsed + seconds,
      startRate: previousRate, targetRate });
    elapsed += seconds;
    previousRate = targetRate;
  };
  add('warmup', 'warmup', env.BENCHMARK_WARMUP_DURATION || '20s', startRate);
  rates.forEach((rate, index) => {
    add(`ramp_${index + 1}`, 'ramp', env.BENCHMARK_RAMP_DURATION || '20s', rate);
    add(`hold_${index + 1}`, 'hold', env.BENCHMARK_HOLD_DURATION || '2m', rate);
  });
  add('soak', 'soak', env.BENCHMARK_SOAK_DURATION || '5m', rates[rates.length - 1], true);
  add('ramp_down', 'ramp_down', env.BENCHMARK_RAMP_DOWN_DURATION || '30s', 0);
  return {
    profile: 'benchmark', target, endpoints, startRate, rates, preAllocatedVUs, maxVUs,
    requestTimeout, gracefulStop, stopCriteria, phases, plannedDurationSeconds: elapsed,
    labels: {
      run: env.BENCHMARK_RUN_LABEL || 'unlabelled',
      serverCPU: env.BENCHMARK_SERVER_CPU || 'not recorded',
      serverMemory: env.BENCHMARK_SERVER_MEMORY || 'not recorded',
      serverConfig: env.BENCHMARK_SERVER_CONFIG || 'not recorded',
      generatorLocation: env.BENCHMARK_GENERATOR_LOCATION || 'not recorded',
    },
  };
}

export function phaseAt(config, elapsedSeconds) {
  return config.phases.find((phase) => elapsedSeconds < phase.endSeconds)
    || config.phases[config.phases.length - 1];
}

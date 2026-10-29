#!/usr/bin/env bash
# Full wrapper check against a loopback fixture. Does not read the project's .env.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
k6_binary="$(realpath "${1:?Pass the path to a Linux k6 binary}")"
work="$(mktemp -d /tmp/load-web-wrapper.XXXXXXXX)"
server_pid=""
cleanup() {
  if [ -n "${server_pid}" ]; then
    kill "${server_pid}" 2>/dev/null || true
    wait "${server_pid}" 2>/dev/null || true
  fi
  # Only remove this test's freshly created, absolute temporary directory.
  if [[ "${work}" == /tmp/load-web-wrapper.* ]]; then
    rm -rf -- "${work}"
  fi
}
trap cleanup EXIT
ln -s "${root}/scripts" "${work}/scripts"
python3 - "${work}/port" <<'PY' &
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'local diagnostic fixture'
        self.send_response(500 if self.path.startswith('/fail') else 200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
Path(sys.argv[1]).write_text(str(server.server_port))
server.serve_forever()
PY
server_pid=$!
for attempt in {1..50}; do
  if [ -s "${work}/port" ]; then break; fi
  sleep 0.1
done
port="$(cat "${work}/port")"
(
  cd "${work}"
  export PATH="$(dirname "${k6_binary}"):${PATH}"
  . "${root}/scripts/lib.sh"
  load_env() {
    export TARGET_URL="http://127.0.0.1:${port}${fixture_suffix:-}"
    export SMOKE_DURATION=1s SMOKE_VUS=1 SLEEP_SECONDS=0.2
    export K6_NO_USAGE_REPORT=true K6_AUTO_EXTENSION_RESOLUTION=false
    export ENABLE_DIAGNOSTIC_PROBE=true DIAGNOSTIC_PROBE_ENDPOINT=/
    export DIAGNOSTIC_PROBE_INTERVAL_SECONDS=5 DIAGNOSTIC_PROBE_TIMEOUT_SECONDS=1
    export RECOVERY_HEALTHY_SAMPLES=1
    if [ -n "${fixture_suffix:-}" ]; then
      export RECOVERY_OBSERVATION_SECONDS=2
    else
      export RECOVERY_OBSERVATION_SECONDS=10
    fi
    export PROMETHEUS_URL= REPORT_INTERVAL_SECONDS=1
  }
  run_k6_profile smoke "${root}/tests/smoke.js"
  fixture_suffix=/fail
  if run_k6_profile smoke "${root}/tests/smoke.js"; then
    printf 'Expected the failing local fixture to produce a nonzero exit status.\n' >&2
    exit 1
  fi
  fixture_suffix=""
  export BENCHMARK_TARGET_URL="http://127.0.0.1:${port}"
  export BENCHMARK_ENDPOINTS=/ BENCHMARK_START_RATE=2 BENCHMARK_RATE_STEPS=2
  export BENCHMARK_WARMUP_DURATION=1s BENCHMARK_RAMP_DURATION=1s BENCHMARK_HOLD_DURATION=1s
  export BENCHMARK_SOAK_DURATION=0s BENCHMARK_RAMP_DOWN_DURATION=1s
  export BENCHMARK_PRE_ALLOCATED_VUS=1 BENCHMARK_MAX_VUS=2
  export BENCHMARK_RUN_LABEL=wrapper-local BENCHMARK_SERVER_CPU=4 BENCHMARK_SERVER_MEMORY=8GiB
  run_k6_profile benchmark "${root}/tests/benchmark.js"
  export BENCHMARK_TARGET_URL=https://example.invalid
  curl() { touch "${work}/unexpected-preflight"; return 23; }
  if run_k6_profile benchmark "${root}/tests/benchmark.js"; then
    printf 'Expected a public benchmark target to be rejected.\n' >&2
    exit 1
  fi
  test ! -f "${work}/unexpected-preflight"
)
python3 - "${work}" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]) / 'results' / 'smoke'
assert {path.name for path in root.iterdir()} == {'json', 'jsonl', 'csv', 'md', 'log'}
assert len(list((root / 'json').glob('*.json'))) == 6
assert len(list((root / 'jsonl').glob('*.jsonl'))) == 6
assert len(list((root / 'csv').glob('*.csv'))) == 6
assert len(list((root / 'md').glob('*.md'))) == 2
assert len(list((root / 'log').glob('*.log'))) == 2
runs = [json.loads(path.read_text()) for path in sorted((root / 'json').glob('*.diagnostics.json'))]
data, failing = runs
assert data['run']['k6_exit_code'] == 0
assert data['http']['requests'] > 0
assert data['runner']['available']
assert data['runner']['rss_bytes_peak'] > 0
assert data['recovery']['status'] == 'healthy sequence confirmed'
assert failing['run']['k6_exit_code'] != 0
assert failing['http']['failure_rate'] == 1
assert failing['recovery']['status'] == 'not confirmed within observation window'
benchmark = root.parent / 'benchmark'
data = json.loads(next((benchmark / 'json').glob('*.diagnostics.json')).read_text())
assert data['benchmark_config']['labels']['serverCPU'] == '4'
assert data['benchmark_config']['target'].startswith('http://127.0.0.1:')
assert data['benchmark_phases']
assert len(list((benchmark / 'csv').glob('*.phases.csv'))) == 1
assert len(list((benchmark / 'json').glob('*.json'))) == 4
print('Wrapper integration passed: successful/failing runs, benchmark phases/labels, local-scope preflight and nested artifacts.')
PY

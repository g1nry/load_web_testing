"""Optional real-k6 checks: K6_BINARY must point to a local k6 executable."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('analyzer', ROOT / 'scripts' / 'analyze-metrics.py')
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)
BODY = ('Привет! ' * 1000).encode('utf-8')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = gzip.compress(BODY)
        self.send_response(500 if self.path == '/fail' else 200)
        self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@unittest.skipUnless(os.environ.get('K6_BINARY'), 'Set K6_BINARY for local k6 integration checks')
class K6LocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.target = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def run_network(self, directory, endpoint, duration, stop_delay):
        report = directory / 'md' / 'local.md'
        report.parent.mkdir()
        raw, summary = directory / 'local.points.jsonl', directory / 'local.summary.json'
        env = dict(os.environ, TARGET_URL=self.target, NETWORK_ENDPOINTS=endpoint,
                   NETWORK_METHOD='GET', NETWORK_PAYLOAD_BYTES='0', NETWORK_MIN_RESPONSE_BYTES='1',
                   NETWORK_RATE='1', NETWORK_DURATION=duration, NETWORK_PRE_ALLOCATED_VUS='1',
                   NETWORK_MAX_VUS='2', STOP_DELAY=stop_delay, STOP_FAILURE_RATE='0.10',
                   STOP_P95_MS='2000', K6_PROFILE='network', K6_SUMMARY_MARKDOWN=str(report),
                   K6_NO_USAGE_REPORT='true', K6_AUTO_EXTENSION_RESOLUTION='false')
        result = subprocess.run([
            os.environ['K6_BINARY'], 'run', '--address', '127.0.0.1:0', '--quiet',
            '--summary-export', str(summary), '--out', f'json={raw}', str(ROOT / 'tests' / 'network.js'),
        ], cwd=directory, env=env, capture_output=True, text=True, timeout=20)
        return result, raw, summary, report

    def test_real_gzip_body_size_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result, raw, summary, report = self.run_network(directory, '/ok', '2s', '30s')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            diagnostic = directory / 'json' / 'local.diagnostics.json'
            analyzer.analyze(raw, directory / 'csv' / 'local.intervals.csv', report, 1,
                             diagnostics_json=diagnostic, summary_json=summary)
            data = json.loads(diagnostic.read_text(encoding='utf-8'))
            self.assertGreater(data['http']['requests'], 0)
            self.assertEqual(data['http']['final_response_body_bytes']['avg'], len(BODY))
            self.assertEqual(data['endpoints'][0]['endpoint'], '/ok')
            self.assertIsNotNone(data['average_rps'])
            self.assertIn('### HTTP diagnostics', report.read_text(encoding='utf-8'))

    def test_abort_threshold_stops_local_failing_endpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, raw, summary, report = self.run_network(Path(temporary), '/fail', '6s', '0s')
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(raw.exists())
            self.assertTrue(report.exists(), result.stdout + result.stderr)
            self.assertIn('threshold', (result.stdout + result.stderr).lower())

    def inspect_benchmark(self, target, **overrides):
        env = dict(os.environ, BENCHMARK_TARGET_URL=target, K6_NO_USAGE_REPORT='true', **overrides)
        return subprocess.run([os.environ['K6_BINARY'], 'inspect', '--include-system-env-vars', str(ROOT / 'tests' / 'benchmark.js')],
                              env=env, capture_output=True, text=True, timeout=10)

    def test_benchmark_accepts_private_literals_and_rejects_public_targets(self):
        for target in ('http://127.0.0.1:8080', 'http://10.0.0.2', 'https://172.16.1.3:443/app',
                       'http://192.168.0.10', 'http://[fd00::1]:8080', 'http://[::1]', 'http://localhost:8080'):
            with self.subTest(target=target):
                result = self.inspect_benchmark(target)
                self.assertEqual(result.returncode, 0, result.stderr)
        for target in ('https://example.com', 'http://8.8.8.8', 'http://localhost.example.com',
                       'http://127.0.0.1@8.8.8.8', 'http://2130706433', 'http://169.254.169.254',
                       'http://192.168.1.1.example.com', 'http://010.0.0.1', 'http://127.0.0.1:0'):
            with self.subTest(target=target):
                self.assertNotEqual(self.inspect_benchmark(target).returncode, 0)

    def test_benchmark_validates_schedule_and_scope_before_requests(self):
        for overrides in (
            {'BENCHMARK_RATE_STEPS': '50,20'}, {'BENCHMARK_RATE_STEPS': '50,50'},
            {'BENCHMARK_RAMP_DURATION': '1mjunk'}, {'BENCHMARK_ENDPOINTS': '//example.com'},
            {'BENCHMARK_PRE_ALLOCATED_VUS': '20', 'BENCHMARK_MAX_VUS': '10'},
        ):
            with self.subTest(overrides=overrides):
                self.assertNotEqual(self.inspect_benchmark(self.target, **overrides).returncode, 0)
        result = self.inspect_benchmark(self.target)
        options = json.loads(result.stdout)
        self.assertEqual(options['maxRedirects'], 0)
        scenario = options['scenarios']['local_benchmark']
        self.assertEqual(max(stage['target'] for stage in scenario['stages']), 600)
        self.assertEqual(scenario['stages'][-1]['target'], 0)

    def test_benchmark_mix_phase_tags_and_resource_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report, raw = directory / 'local.md', directory / 'local.points.jsonl'
            summary, config = directory / 'local.summary.json', directory / 'local.config.json'
            env = dict(os.environ, TARGET_URL='https://example.invalid', BENCHMARK_TARGET_URL=self.target,
                       BENCHMARK_ENDPOINTS='/ok,/ok,/other', BENCHMARK_START_RATE='4', BENCHMARK_RATE_STEPS='4,8',
                       BENCHMARK_WARMUP_DURATION='0.25s', BENCHMARK_RAMP_DURATION='0.25s',
                       BENCHMARK_HOLD_DURATION='0.25s', BENCHMARK_SOAK_DURATION='0.5s', BENCHMARK_RAMP_DOWN_DURATION='0.25s',
                       BENCHMARK_PRE_ALLOCATED_VUS='2', BENCHMARK_MAX_VUS='8', BENCHMARK_SERVER_CPU='4',
                       BENCHMARK_SERVER_MEMORY='8GiB', BENCHMARK_RUN_LABEL='test-label', K6_RUN_CONFIG_JSON=str(config),
                       K6_PROFILE='benchmark', K6_SUMMARY_MARKDOWN=str(report), STOP_DELAY='30s',
                       STOP_FAILURE_RATE='0.10', STOP_P95_MS='2000', K6_NO_USAGE_REPORT='true')
            result = subprocess.run([
                os.environ['K6_BINARY'], 'run', '--address', '127.0.0.1:0', '--quiet',
                '--summary-export', str(summary), '--out', f'json={raw}', str(ROOT / 'tests' / 'benchmark.js'),
            ], cwd=directory, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            diagnostic = directory / 'diagnostics.json'
            analyzer.analyze(raw, directory / 'local.intervals.csv', report, 1,
                             diagnostics_json=diagnostic, summary_json=summary, benchmark_config=config)
            data = json.loads(diagnostic.read_text(encoding='utf-8'))
            self.assertEqual(data['benchmark_config']['target'], self.target)
            self.assertEqual(data['benchmark_config']['labels']['serverCPU'], '4')
            self.assertEqual(data['benchmark_config']['plannedDurationSeconds'], 2)
            counts = {item['endpoint']: item['requests'] for item in data['endpoints']}
            self.assertLessEqual(abs(counts['/ok'] - 2 * counts['/other']), 2)
            phases = {phase['phase']: phase for phase in data['benchmark_phases']}
            self.assertGreater(phases['soak']['requests'], 0)
            self.assertEqual(sum(phase['requests'] for phase in phases.values()), data['http']['requests'])
            self.assertIn('test-label', report.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

"""Offline regression checks for the k6 time-series analyzer."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'analyzer', Path(__file__).resolve().parents[1] / 'scripts' / 'analyze-metrics.py',
)
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)


def point(metric, value, second=1, tags=None):
    return json.dumps({'type': 'Point', 'metric': metric, 'data': {
        'time': f'2026-01-01T00:00:{second:02d}Z', 'value': value, 'tags': tags,
    }}) + '\n'


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / 'points.jsonl'
        self.output = self.directory / 'intervals.csv'
        self.report = self.directory / 'report.md'
        self.environment = patch.dict(os.environ, {
            'STOP_FAILURE_RATE': '0.10', 'STOP_P95_MS': '2000',
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_analysis(self, text):
        self.source.write_text(text, encoding='utf-8')
        return analyzer.analyze(self.source, self.output, self.report, 10)

    def test_gaps_and_missing_samples_are_preserved(self):
        rows = self.run_analysis(point('http_reqs', 1) + point('http_reqs', 1, 21))
        self.assertEqual([row['completed_rps'] for row in rows], [.1, 0, .1])
        self.assertIsNone(rows[1]['failure_rate'])
        with self.output.open(encoding='utf-8', newline='') as stream:
            saved = list(csv.DictReader(stream))
        self.assertEqual(saved[1]['p95_ms'], '')
        self.assertEqual(saved[1]['failure_rate'], '')

    def test_latency_bytes_status_and_failure_counts(self):
        rows = self.run_analysis(
            point('http_reqs', 1, tags={'status': '0', 'error_code': '1050'})
            + point('http_req_failed', 1) + point('http_req_failed', 0)
            + point('http_req_duration', 100) + point('http_req_duration', 300)
            + point('data_sent', 42) + point('data_received', 500)
            + point('dropped_iterations', 3)
        )
        row = rows[0]
        self.assertEqual((row['p95_ms'], row['p99_ms']), (290, 298))
        self.assertEqual(row['failure_rate'], .5)
        self.assertEqual((row['sent_bytes'], row['received_bytes']), (42, 500))
        self.assertEqual(row['dropped_iterations'], 3)
        self.assertEqual(row['request_timeouts'], 1)
        self.assertEqual(json.loads(row['error_codes']), {'1050': 1})

    def test_truncated_final_record_is_reported(self):
        with self.assertWarns(UserWarning):
            rows = self.run_analysis(point('http_reqs', 1) + '{"type":')
        self.assertEqual(rows[0]['requests'], 1)
        self.assertIn('Incomplete input', self.report.read_text(encoding='utf-8'))

    def test_malformed_middle_record_fails(self):
        with self.assertRaisesRegex(ValueError, 'line 2'):
            self.run_analysis(point('http_reqs', 1) + 'broken\n' + point('http_reqs', 1))

    def test_reanalysis_replaces_section_and_keeps_following_sections(self):
        sample = point('http_reqs', 1) + point('http_req_failed', 1)
        self.run_analysis(sample)
        with self.report.open('a', encoding='utf-8') as stream:
            stream.write('\n## Prometheus\n\nExisting metrics.\n')
        self.run_analysis(sample)
        report = self.report.read_text(encoding='utf-8')
        self.assertEqual(report.count('## Client time-series'), 1)
        self.assertEqual(report.count('## Prometheus'), 1)
        self.assertNotIn('None ms', report)
        self.assertIn('p95 n/a', report)

    def test_threshold_uses_unrounded_values(self):
        os.environ['STOP_FAILURE_RATE'] = '0.333332'
        sample = point('http_req_failed', 1) + point('http_req_failed', 0) * 2
        self.run_analysis(sample)
        self.assertIn('First interval exceeding', self.report.read_text(encoding='utf-8'))

    def test_empty_input_and_bom(self):
        self.assertEqual(self.run_analysis(''), [])
        self.assertIn('No supported point samples', self.report.read_text(encoding='utf-8'))
        rows = self.run_analysis('\ufeff' + point('http_reqs', 1))
        self.assertEqual(rows[0]['requests'], 1)

    def test_endpoint_grouping_timings_and_body_size(self):
        first = {'method': 'GET', 'endpoint': '/items?q=one', 'status': '200'}
        second = {'method': 'POST', 'url': 'https://example.invalid/items?secret=removed', 'status': '429'}
        self.run_analysis(
            point('http_reqs', 1, tags=first) + point('http_req_failed', 0, tags=first)
            + point('http_req_waiting', 120, tags=first)
            + point('response_body_bytes', 9000, tags=first)
            + point('http_reqs', 1, tags=second) + point('http_req_failed', 1, tags=second)
        )
        with self.output.with_suffix('.endpoints.csv').open(encoding='utf-8', newline='') as stream:
            endpoints = list(csv.DictReader(stream))
        self.assertEqual([(item['method'], item['endpoint']) for item in endpoints], [('GET', '/items'), ('POST', '/items')])
        self.assertEqual(endpoints[0]['http_req_waiting_p95_ms'], '120.0')
        self.assertEqual(endpoints[0]['response_body_avg_bytes'], '9000.0')
        self.assertEqual(endpoints[1]['failure_rate'], '1.0')
        self.assertNotIn('secret', self.report.read_text(encoding='utf-8'))

    def test_machine_diagnostics_support_legacy_summary_export(self):
        summary = self.directory / 'summary.json'
        summary.write_text(json.dumps({'metrics': {'http_reqs': {'count': 5, 'rate': 2.5}}}))
        diagnostic = self.directory / 'json' / 'diagnostics.json'
        self.source.write_text(point('http_reqs', 1), encoding='utf-8')
        analyzer.analyze(self.source, self.output, self.report, 10,
                         diagnostics_json=diagnostic, summary_json=summary)
        saved = json.loads(diagnostic.read_text(encoding='utf-8'))
        self.assertEqual(saved['average_rps'], 2.5)
        self.assertEqual(saved['peak_window']['completed_rps'], .1)
        self.assertFalse(saved['runner']['available'])
        self.assertTrue(saved['incomplete_input'])
        self.assertFalse(saved['raw_request_count_matches_summary'])

    def test_benchmark_keeps_unobserved_phases_after_early_stop(self):
        config = self.directory / 'config.json'
        config.write_text(json.dumps({'profile': 'benchmark', 'labels': {'serverCPU': '4'}, 'phases': [
            {'name': 'warmup', 'kind': 'warmup', 'startSeconds': 0, 'endSeconds': 10, 'targetRate': 2},
            {'name': 'hold_1', 'kind': 'hold', 'startSeconds': 10, 'endSeconds': 20, 'targetRate': 4},
        ]}))
        tags = {'method': 'GET', 'endpoint': '/', 'benchmark_phase': 'warmup'}
        self.source.write_text(point('http_reqs', 1, tags=tags) + point('http_req_duration', 300, tags=tags), encoding='utf-8')
        diagnostic = self.directory / 'diagnostics.json'
        analyzer.analyze(self.source, self.output, self.report, 10,
                         benchmark_config=config, diagnostics_json=diagnostic)
        saved = json.loads(diagnostic.read_text(encoding='utf-8'))
        phases = saved['benchmark_phases']
        self.assertEqual(phases[0]['requests'], 1)
        self.assertEqual(phases[1]['requests'], 0)
        self.assertIsNone(phases[1]['latency_ms']['p95'])
        self.assertTrue(self.output.with_suffix('.phases.csv').exists())


if __name__ == '__main__':
    unittest.main()

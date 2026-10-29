import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    'comparison', Path(__file__).resolve().parents[1] / 'scripts' / 'compare-benchmarks.py',
)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonTests(unittest.TestCase):
    def test_resource_labels_share_workload_but_schedule_changes_do_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = dict(benchmark_config=dict(profile='benchmark', target='http://127.0.0.1:8080',
                            phases=[dict(name='hold_1', targetRate=100)], labels=dict(run='baseline', serverCPU='2')),
                            run=dict(run_id='one'), average_rps=90, http=dict(requests=900, latency_ms=dict(p95=200)),
                            peak_window=dict(completed_rps=100, window_seconds=10))
            second = copy.deepcopy(original)
            second['benchmark_config']['labels'] = dict(run='larger', serverCPU='4')
            third = copy.deepcopy(second)
            third['benchmark_config']['phases'][0]['targetRate'] = 200
            for index, data in enumerate((original, second, third)):
                (root / f'{index}.diagnostics.json').write_text(json.dumps(data))
            (root / 'smoke.diagnostics.json').write_text('{}')
            rows = comparison.compare([root], root / 'csv' / 'comparison.csv')
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]['workload_id'], rows[1]['workload_id'])
            self.assertNotEqual(rows[1]['workload_id'], rows[2]['workload_id'])
            self.assertEqual(rows[1]['server_cpu_label'], '4')

    def test_non_benchmark_results_do_not_look_like_benchmarks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'smoke.diagnostics.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'No local benchmark'):
                comparison.compare([root], root / 'comparison.csv')

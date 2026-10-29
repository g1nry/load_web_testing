"""Probe integration checks use a loopback HTTP server exclusively."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'observer', Path(__file__).resolve().parents[1] / 'scripts' / 'observe-run.py',
)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class Handler(BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        self.seen.append(self.path)
        if self.path == '/slow':
            time.sleep(.05)
        self.send_response(500 if self.path == '/fail' else 302 if self.path == '/redirect' else 200)
        if self.path == '/redirect':
            self.send_header('Location', '/must-not-follow')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def log_message(self, *args):
        pass


class ObserverTests(unittest.TestCase):
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

    def test_probe_status_latency_and_redirect_handling(self):
        Handler.seen.clear()
        self.assertTrue(observer.probe(self.target + '/ok', 1, 1000)['healthy'])
        self.assertFalse(observer.probe(self.target + '/fail', 1, 1000)['healthy'])
        redirect = observer.probe(self.target + '/redirect', 1, 1000)
        self.assertEqual(redirect['status'], 302)
        self.assertNotIn('/must-not-follow', Handler.seen)
        self.assertFalse(observer.probe(self.target + '/slow', 1, 1)['healthy'])

    def test_cross_origin_probe_paths_are_rejected(self):
        for endpoint in ('//example.invalid/', 'https://example.invalid/', '/#fragment'):
            with self.assertRaises(ValueError):
                observer.probe_url(self.target, endpoint)

    def test_recovery_deadline_and_disabled_probe(self):
        for endpoint, expected in (('/fail', 'not confirmed within observation window'), ('', 'disabled')):
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                finished = root / 'run.json'
                finished.write_text(json.dumps({'load_ended_at': observer.now()}))
                clock = [0]

                def advance(seconds):
                    clock[0] += seconds

                failed = dict(time=observer.now(), status=500, headers_ms=1, healthy=False, error=None)
                with patch.object(observer.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(observer.time, 'sleep', side_effect=advance), patch.object(observer, 'probe', return_value=failed):
                    observer.observe(0, finished, root / 'runner.jsonl', root / 'probes.jsonl',
                                     self.target, endpoint, recovery_seconds=1)
                records = [json.loads(line) for line in (root / 'probes.jsonl').read_text().splitlines()]
                self.assertEqual(records[-1]['recovery_status'], expected)

    def test_recovery_confirmation_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            finished = root / 'run.json'
            finished.write_text(json.dumps({'load_ended_at': observer.now()}))
            observer.observe(0, finished, root / 'runner.jsonl', root / 'probes.jsonl',
                             self.target, '/ok', healthy_count=1)
            records = [json.loads(line) for line in (root / 'probes.jsonl').read_text().splitlines()]
            self.assertEqual(records[0]['phase'], 'recovery')
            self.assertEqual(records[-1]['recovery_status'], 'healthy sequence confirmed')
            self.assertGreaterEqual(records[-1]['healthy_after_load_seconds'], 0)

    def test_linux_sampler_uses_deltas_and_process_identity(self):
        stats = ['0'] * 20
        stats[11], stats[12], stats[19] = '10', '5', '99'
        files = {
            '/proc/stat': 'cpu 100 0 0 100 0 0 0 0\n',
            '/proc/net/dev': 'header\nheader\n eth0: 100 0 0 0 0 0 0 0 200 0 0 0 0 0 0 0\n',
            '/proc/meminfo': 'MemAvailable: 4096 kB\n',
            '/proc/123/stat': '123 (k6 worker) ' + ' '.join(stats),
            '/proc/123/status': 'VmRSS: 512 kB\n',
        }

        def read(path, *args, **kwargs):
            return files[path.as_posix()]

        with patch.object(Path, 'read_text', read), patch.object(observer.time, 'monotonic', side_effect=[1, 2]), patch.object(observer.os, 'sysconf', return_value=100, create=True):
            sampler = observer.RunnerSampler(123)
            sampler.sample()
            stats[11] = '20'
            files['/proc/123/stat'] = '123 (k6 worker) ' + ' '.join(stats)
            files['/proc/stat'] = 'cpu 120 0 0 180 0 0 0 0\n'
            sample = sampler.sample()
        self.assertEqual(sample['k6_cpu_percent'], 10)
        self.assertAlmostEqual(sample['host_cpu_busy_percent'], 20)
        self.assertEqual(sample['rss_bytes'], 512 * 1024)


if __name__ == '__main__':
    unittest.main()

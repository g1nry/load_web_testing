#!/usr/bin/env python3
"""Sample local runner resources and low-frequency HTTP availability independently of k6."""
import argparse
import json
import math
import os
from pathlib import Path
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(stream, item):
    stream.write(json.dumps(item, allow_nan=False) + '\n')
    stream.flush()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def probe_url(target, endpoint):
    base, path = urlsplit(target), urlsplit(endpoint)
    if base.scheme not in ('http', 'https') or not base.hostname or base.username or base.password or base.query or base.fragment:
        raise ValueError('Probe target must be an HTTP(S) URL without credentials, query or fragment')
    if not endpoint.startswith('/') or endpoint.startswith('//') or path.scheme or path.netloc or path.fragment:
        raise ValueError('Probe endpoint must be a same-origin absolute path')
    return target.rstrip('/') + endpoint


def probe(url, timeout, limit_ms):
    start = time.monotonic()
    status, error = 0, None
    try:
        request = Request(url, headers={'User-Agent': 'k6-independent-probe/1.0'}, method='GET')
        # Measure response headers only. Never follow redirects or download the body.
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            status = response.status
    except HTTPError as response:
        status = response.code
        response.close()
    except (URLError, OSError, TimeoutError) as exception:
        error = type(exception).__name__
    elapsed = (time.monotonic() - start) * 1000
    return dict(time=now(), status=status, headers_ms=elapsed,
                healthy=200 <= status < 400 and elapsed < limit_ms, error=error)


class RunnerSampler:
    def __init__(self, pid):
        self.pid = pid
        self.previous = None
        self.identity = None

    def sample(self):
        record = dict(type='runner', time=now(), supported=False)
        try:
            raw = Path('/proc/stat').read_text().splitlines()[0].split()[1:]
            cpu = [int(value) for value in raw[:8]]
            host = dict(cpu_total=sum(cpu), cpu_idle=cpu[3] + cpu[4], rx=0, tx=0)
            for line in Path('/proc/net/dev').read_text().splitlines()[2:]:
                device, counters = line.split(':', 1)
                if device.strip() != 'lo':
                    values = counters.split()
                    host['rx'] += int(values[0])
                    host['tx'] += int(values[8])
            mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
            record['host_available_bytes'] = int(mem['MemAvailable'].split()[0]) * 1024
            record['supported'] = True
        except (OSError, ValueError, KeyError, IndexError):
            return record
        process_ticks = None
        try:
            fields = Path(f'/proc/{self.pid}/stat').read_text().rsplit(')', 1)[1].split()
            identity = fields[19]
            if self.identity is None:
                self.identity = identity
            if self.identity == identity:
                process_ticks = int(fields[11]) + int(fields[12])
                status = dict(line.split(':', 1) for line in Path(f'/proc/{self.pid}/status').read_text().splitlines())
                record['rss_bytes'] = int(status['VmRSS'].split()[0]) * 1024
        except (OSError, ValueError, KeyError, IndexError):
            pass
        current = dict(time=time.monotonic(), process_ticks=process_ticks, **host)
        if self.previous:
            previous = self.previous
            elapsed = current['time'] - previous['time']
            total_delta = host['cpu_total'] - previous['cpu_total']
            if total_delta > 0:
                record['host_cpu_busy_percent'] = 100 * (1 - (host['cpu_idle'] - previous['cpu_idle']) / total_delta)
            if elapsed > 0:
                for name in ('rx', 'tx'):
                    delta = host[name] - previous[name]
                    record[f'host_{name}_bytes_per_second'] = delta / elapsed if delta >= 0 else None
                if process_ticks is not None and previous['process_ticks'] is not None:
                    delta = process_ticks - previous['process_ticks']
                    record['k6_cpu_percent'] = 100 * delta / os.sysconf('SC_CLK_TCK') / elapsed if delta >= 0 else None
        self.previous = current
        return record


def completion(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def validate(target, endpoint, interval, timeout, limit_ms, recovery_seconds, healthy_count, max_seconds):
    if not all(math.isfinite(value) for value in (interval, timeout, limit_ms, recovery_seconds, max_seconds)):
        raise ValueError('Observer settings must be finite')
    if interval < 5 or not 0 < timeout <= 10 or not 0 < recovery_seconds <= 600 or healthy_count < 1:
        raise ValueError('Probe interval >= 5s, timeout in (0, 10], recovery in (0, 600], healthy count >= 1 required')
    if limit_ms <= 0 or max_seconds <= 0:
        raise ValueError('Probe latency limit and observer lifetime must be positive')
    return probe_url(target, endpoint) if endpoint else None


def observe(pid, finished_file, runner_file, probe_file, target, endpoint, *,
            interval=5, timeout=3, limit_ms=2000, recovery_seconds=60, healthy_count=3,
            max_seconds=3600):
    url = validate(target, endpoint, interval, timeout, limit_ms, recovery_seconds, healthy_count, max_seconds)
    for path in (runner_file, probe_file):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    sampler = RunnerSampler(pid)
    started = time.monotonic()
    next_probe = started
    recovery_started = None
    load_ended_timestamp = None
    healthy = 0
    with open(runner_file, 'w', encoding='utf-8') as runner, open(probe_file, 'w', encoding='utf-8') as probes:
        while True:
            clock = time.monotonic()
            finished = completion(finished_file)
            if finished and recovery_started is None:
                recovery_started = clock
                load_ended_timestamp = datetime.fromisoformat(finished['load_ended_at']).timestamp()
            if recovery_started is None:
                emit(runner, sampler.sample())
            if clock - started >= max_seconds:
                emit(probes, dict(type='observer_end', time=now(), recovery_status='observer lifetime exceeded'))
                return
            if recovery_started is not None and not url:
                emit(probes, dict(type='observer_end', time=now(), recovery_status='disabled'))
                return
            if recovery_started is not None and clock - recovery_started >= recovery_seconds:
                emit(probes, dict(type='observer_end', time=now(), recovery_status='not confirmed within observation window'))
                return
            if url and clock >= next_probe:
                phase = 'recovery' if recovery_started is not None else 'load'
                result = probe(url, timeout, limit_ms)
                emit(probes, dict(type='probe', phase=phase, **result))
                # Schedule after completion; never overlap probes or catch up missed ones.
                next_probe = time.monotonic() + interval
                if phase == 'recovery':
                    healthy = healthy + 1 if result['healthy'] else 0
                    if healthy >= healthy_count:
                        elapsed = max(0, time.time() - load_ended_timestamp)
                        emit(probes, dict(type='observer_end', time=now(), recovery_status='healthy sequence confirmed',
                                          healthy_after_load_seconds=elapsed))
                        return
            if recovery_started is not None and time.monotonic() - recovery_started >= recovery_seconds:
                emit(probes, dict(type='observer_end', time=now(), recovery_status='not confirmed within observation window'))
                return
            time.sleep(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    for name in ('finished-file', 'runner-file', 'probe-file', 'target'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--endpoint', default='')
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--timeout', type=float, default=3)
    parser.add_argument('--limit-ms', type=float, default=2000)
    parser.add_argument('--recovery-seconds', type=float, default=60)
    parser.add_argument('--healthy-count', type=int, default=3)
    parser.add_argument('--max-seconds', type=float, default=3600)
    parser.add_argument('--validate-only', action='store_true')
    args = vars(parser.parse_args())
    validate_only = args.pop('validate_only')
    if validate_only:
        validate(**{name: args[name] for name in ('target', 'endpoint', 'interval', 'timeout', 'limit_ms', 'recovery_seconds', 'healthy_count', 'max_seconds')})
    else:
        observe(**args)

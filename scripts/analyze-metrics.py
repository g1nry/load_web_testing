#!/usr/bin/env python3
"""Aggregate k6 JSON point samples into fixed UTC windows."""
import csv
import argparse
import json
import math
import os
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


TIMINGS = (
    'http_req_blocked', 'http_req_connecting', 'http_req_tls_handshaking',
    'http_req_sending', 'http_req_waiting', 'http_req_receiving',
)
METRICS = {
    'http_reqs', 'http_req_failed', 'http_req_duration',
    'data_sent', 'data_received', 'dropped_iterations', 'iterations',
    'vus', 'vus_max', 'checks', 'response_body_bytes', *TIMINGS,
}


def empty_bucket():
    return {
        'requests': 0, 'failed': 0, 'failure_samples': 0,
        'sent': 0, 'received': 0, 'dropped': 0,
        'latencies': [], 'statuses': Counter(), 'errors': Counter(),
        'timings': defaultdict(list), 'vus': None, 'vus_max': None,
        'iterations': 0, 'checks_failed': 0, 'check_samples': 0,
        'body_bytes': [],
    }


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def read_points(source):
    """Read JSONL, flagging an incomplete final record instead of losing the run."""
    with open(source, encoding='utf-8-sig') as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                if not line.endswith('\n'):
                    warnings.warn(f'Ignoring truncated final JSONL line {line_number}', stacklevel=2)
                    yield {'type': 'Truncated'}
                    return
                raise ValueError(f'Invalid JSONL at line {line_number}') from error


def add_sample(bucket, name, number, tags):
    if name == 'http_reqs':
        bucket['requests'] += number
        bucket['statuses'][str(tags.get('status', 'unknown'))] += number
        if tags.get('error_code') and str(tags['error_code']) != '0':
            bucket['errors'][str(tags['error_code'])] += number
    elif name == 'http_req_failed':
        bucket['failed'] += bool(number)
        bucket['failure_samples'] += 1
    elif name == 'http_req_duration':
        bucket['latencies'].append(number)
    elif name == 'response_body_bytes':
        bucket['body_bytes'].append(number)
    elif name in TIMINGS:
        bucket['timings'][name].append(number)
    elif name in ('vus', 'vus_max'):
        bucket[name] = max(bucket[name] or 0, number)
    elif name == 'checks':
        bucket['check_samples'] += 1
        bucket['checks_failed'] += not bool(number)
    else:
        field = {'data_sent': 'sent', 'data_received': 'received',
                 'dropped_iterations': 'dropped', 'iterations': 'iterations'}[name]
        bucket[field] += number


def endpoint_key(tags):
    raw = str(tags.get('endpoint') or tags.get('url') or 'unknown')
    path = urlsplit(raw).path if raw != 'unknown' else raw
    return str(tags.get('method') or 'unknown'), path or '/'


def stats(values):
    return dict(samples=len(values), avg=sum(values) / len(values) if values else None,
                p95=percentile(values, .95), p99=percentile(values, .99),
                max=max(values) if values else None)


def error_categories(errors):
    return dict(
        request_timeouts=errors.get('1050', 0), dial_timeouts=errors.get('1211', 0),
        connection_refused=errors.get('1212', 0), connection_reset=errors.get('1220', 0),
        dns_errors=sum(count for code, count in errors.items() if code.isdigit() and 1100 <= int(code) < 1200),
        tls_errors=sum(count for code, count in errors.items() if code.isdigit() and 1300 <= int(code) < 1400),
    )


def bucket_summary(bucket):
    return {
        'requests': bucket['requests'],
        'failure_rate': bucket['failed'] / bucket['failure_samples'] if bucket['failure_samples'] else None,
        'failure_samples': bucket['failure_samples'],
        'latency_ms': stats(bucket['latencies']),
        'timings_ms': {name: stats(values) for name, values in bucket['timings'].items()},
        'status_counts': dict(bucket['statuses']), 'error_codes': dict(bucket['errors']),
        'final_response_body_bytes': stats(bucket['body_bytes']),
        'error_categories': error_categories(bucket['errors']),
    }


def write_csv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def format_value(value, suffix=''):
    return f'{value:.3f}{suffix}' if value is not None else 'n/a'


def markdown_cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')


def summarize_runner(path):
    if not path or not Path(path).exists():
        return {'available': False, 'reason': 'Runner samples were not collected.'}
    samples = [item for item in read_points(path) if item.get('type') == 'runner']
    result = {'available': any(item.get('supported') for item in samples), 'samples': len(samples)}
    for field in ('k6_cpu_percent', 'rss_bytes', 'host_cpu_busy_percent',
                  'host_rx_bytes_per_second', 'host_tx_bytes_per_second'):
        values = [item[field] for item in samples if item.get(field) is not None]
        result[field + '_peak'] = max(values) if values else None
    values = [item['host_available_bytes'] for item in samples if item.get('host_available_bytes') is not None]
    result['host_available_bytes_min'] = min(values) if values else None
    return result


def summarize_probes(path):
    if not path or not Path(path).exists():
        return {'available': False, 'status': 'not collected'}
    points = list(read_points(path))
    samples = [item for item in points if item.get('type') == 'probe']
    final = next((item for item in reversed(points) if item.get('type') == 'observer_end'), {})
    return {
        'available': bool(samples), 'samples': len(samples),
        'failed_samples': sum(not item['healthy'] for item in samples),
        'failed_during_load': sum(not item['healthy'] for item in samples if item['phase'] == 'load'),
        'status_counts': dict(Counter(str(item['status']) for item in samples)),
        'status': final.get('recovery_status', 'incomplete'),
        'healthy_after_load_seconds': final.get('healthy_after_load_seconds'),
        'last_probe_at': samples[-1]['time'] if samples else None,
    }


def analyze(source, output, report, width, *, endpoints_csv=None, endpoint_intervals_csv=None,
            diagnostics_json=None, runner_samples=None, probe_samples=None, run_metadata=None,
            summary_json=None, benchmark_config=None, phases_csv=None):
    if not isinstance(width, int) or width <= 0:
        raise ValueError('interval must be a positive integer')
    failure_limit = float(os.environ.get('STOP_FAILURE_RATE') or '0.10')
    latency_limit = float(os.environ.get('STOP_P95_MS') or '2000')
    if not 0 < failure_limit <= 1 or not math.isfinite(latency_limit) or latency_limit <= 0:
        raise ValueError('invalid STOP_FAILURE_RATE or STOP_P95_MS')
    buckets = defaultdict(empty_bucket)
    endpoints = defaultdict(empty_bucket)
    endpoint_windows = defaultdict(empty_bucket)
    phase_buckets = defaultdict(empty_bucket)
    total = empty_bucket()
    truncated = False
    first_failure_at = last_failure_at = None
    for item in read_points(source):
        if item.get('type') == 'Truncated':
            truncated = True
            continue
        if item.get('type') != 'Point':
            continue
        name, point = item.get('metric'), item.get('data', {})
        if name not in METRICS:
            continue
        timestamp = datetime.fromisoformat(point['time'].replace('Z', '+00:00')).timestamp()
        bucket = buckets[math.floor(timestamp / width) * width]
        number, tags = point['value'], point.get('tags') or {}
        if not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError('Invalid metric value')
        add_sample(bucket, name, number, tags)
        add_sample(total, name, number, tags)
        if tags.get('benchmark_phase'):
            add_sample(phase_buckets[tags['benchmark_phase']], name, number, tags)
        if name == 'http_req_failed' and number:
            first_failure_at = min(first_failure_at, timestamp) if first_failure_at is not None else timestamp
            last_failure_at = max(last_failure_at, timestamp) if last_failure_at is not None else timestamp
        if name.startswith('http_') or name == 'response_body_bytes':
            key = endpoint_key(tags)
            add_sample(endpoints[key], name, number, tags)
            add_sample(endpoint_windows[(math.floor(timestamp / width) * width, *key)], name, number, tags)
    fields = [
        'window_start_utc', 'window_seconds', 'requests', 'completed_rps',
        'failure_rate', 'p95_ms', 'p99_ms', 'sent_bytes', 'received_bytes',
        'dropped_iterations', 'status_counts', 'error_codes',
        'successful_rps', 'iterations', 'vus_peak', 'vus_max_peak', 'checks_failed',
        'sent_bytes_per_second', 'received_bytes_per_second',
        'response_body_samples', 'response_body_avg_bytes', 'response_body_p95_bytes',
        'latency_samples', 'failure_samples', 'request_timeouts', 'dial_timeouts',
        *[name + '_p95_ms' for name in TIMINGS],
    ]
    rows = []
    starts = range(min(buckets), max(buckets) + width, width) if buckets else []
    for start in starts:
        b = buckets.get(start, empty_bucket())
        rows.append(dict(
            window_start_utc=datetime.fromtimestamp(start, timezone.utc).isoformat(),
            window_seconds=width,
            requests=b['requests'],
            completed_rps=b['requests'] / width,
            failure_rate=b['failed'] / b['failure_samples'] if b['failure_samples'] else None,
            p95_ms=percentile(b['latencies'], .95),
            p99_ms=percentile(b['latencies'], .99),
            sent_bytes=b['sent'], received_bytes=b['received'],
            dropped_iterations=b['dropped'],
            status_counts=json.dumps(b['statuses'], sort_keys=True),
            error_codes=json.dumps(b['errors'], sort_keys=True),
            successful_rps=(b['failure_samples'] - b['failed']) / width if b['failure_samples'] else None,
            iterations=b['iterations'], vus_peak=b['vus'], vus_max_peak=b['vus_max'],
            checks_failed=b['checks_failed'],
            sent_bytes_per_second=b['sent'] / width,
            received_bytes_per_second=b['received'] / width,
            response_body_samples=len(b['body_bytes']),
            response_body_avg_bytes=sum(b['body_bytes']) / len(b['body_bytes']) if b['body_bytes'] else None,
            response_body_p95_bytes=percentile(b['body_bytes'], .95),
            latency_samples=len(b['latencies']), failure_samples=b['failure_samples'],
            request_timeouts=b['errors'].get('1050', 0), dial_timeouts=b['errors'].get('1211', 0),
            **{name + '_p95_ms': percentile(b['timings'][name], .95) for name in TIMINGS},
        ))
    write_csv(output, rows, fields)
    endpoints_csv = Path(endpoints_csv or Path(output).with_suffix('.endpoints.csv'))
    endpoint_intervals_csv = Path(endpoint_intervals_csv or Path(output).with_suffix('.endpoint-intervals.csv'))
    endpoint_fields = ['method', 'endpoint', 'requests', 'failure_rate', 'latency_samples',
                       'avg_ms', 'p95_ms', 'p99_ms', 'max_ms', 'status_counts', 'error_codes',
                       'response_body_samples', 'response_body_avg_bytes', 'response_body_max_bytes',
                       *[name + '_p95_ms' for name in TIMINGS]]

    def endpoint_row(key, bucket):
        return dict(method=key[0], endpoint=key[1], requests=bucket['requests'],
                    failure_rate=bucket['failed'] / bucket['failure_samples'] if bucket['failure_samples'] else None,
                    latency_samples=len(bucket['latencies']),
                    avg_ms=sum(bucket['latencies']) / len(bucket['latencies']) if bucket['latencies'] else None,
                    p95_ms=percentile(bucket['latencies'], .95), p99_ms=percentile(bucket['latencies'], .99),
                    max_ms=max(bucket['latencies']) if bucket['latencies'] else None,
                    status_counts=json.dumps(bucket['statuses'], sort_keys=True),
                    error_codes=json.dumps(bucket['errors'], sort_keys=True),
                    response_body_samples=len(bucket['body_bytes']),
                    response_body_avg_bytes=sum(bucket['body_bytes']) / len(bucket['body_bytes']) if bucket['body_bytes'] else None,
                    response_body_max_bytes=max(bucket['body_bytes']) if bucket['body_bytes'] else None,
                    **{name + '_p95_ms': percentile(bucket['timings'][name], .95) for name in TIMINGS})

    endpoint_rows = [endpoint_row(key, bucket) for key, bucket in sorted(endpoints.items())]
    write_csv(endpoints_csv, endpoint_rows, endpoint_fields)
    write_csv(endpoint_intervals_csv, [dict(
        window_start_utc=datetime.fromtimestamp(key[0], timezone.utc).isoformat(),
        completed_rps=bucket['requests'] / width,
        **endpoint_row(key[1:], bucket),
    ) for key, bucket in sorted(endpoint_windows.items())],
        ['window_start_utc', 'completed_rps', *endpoint_fields])
    metadata = json.loads(Path(run_metadata).read_text(encoding='utf-8')) if run_metadata and Path(run_metadata).exists() else {}
    runner = summarize_runner(runner_samples)
    recovery = summarize_probes(probe_samples)
    summary = json.loads(Path(summary_json).read_text(encoding='utf-8')) if summary_json and Path(summary_json).exists() else {}
    request_metric = summary.get('metrics', {}).get('http_reqs', {})
    request_values = request_metric.get('values', request_metric)
    peak = max(rows, key=lambda row: row['completed_rps']) if rows else None
    breach = next((row for row in rows if
                   (row['failure_rate'] is not None and row['failure_rate'] >= failure_limit)
                   or (row['p95_ms'] is not None and row['p95_ms'] >= latency_limit)), None)
    counts_match = request_values['count'] == total['requests'] if 'count' in request_values else None
    config = json.loads(Path(benchmark_config).read_text(encoding='utf-8')) if benchmark_config and Path(benchmark_config).exists() else None
    planned_phases = {phase['name']: phase for phase in config.get('phases', [])} if config else {}
    phase_names = list(dict.fromkeys([*planned_phases, *phase_buckets]))
    phase_summaries = []
    for name in phase_names:
        phase = planned_phases.get(name, {})
        bucket = phase_buckets.get(name, empty_bucket())
        phase_summaries.append(dict(
            phase=name, kind=phase.get('kind'),
            planned_seconds=phase['endSeconds'] - phase['startSeconds'] if phase else None,
            planned_target_rps=phase.get('targetRate'),
            **bucket_summary(bucket),
        ))
    if phase_summaries:
        phases_csv = Path(phases_csv or Path(output).with_suffix('.phases.csv'))
        phase_rows = [dict(
            phase=phase['phase'], kind=phase['kind'], planned_seconds=phase['planned_seconds'],
            planned_target_rps=phase['planned_target_rps'], requests=phase['requests'],
            failure_rate=phase['failure_rate'], latency_samples=phase['latency_ms']['samples'],
            p95_ms=phase['latency_ms']['p95'], p99_ms=phase['latency_ms']['p99'],
        ) for phase in phase_summaries]
        write_csv(phases_csv, phase_rows, list(phase_rows[0]))
    diagnostics = dict(
        schema_version=1, incomplete_input=truncated or counts_match is False, run=metadata,
        http=bucket_summary(total), data_sent_bytes=total['sent'], data_received_bytes=total['received'],
        dropped_iterations=total['dropped'], checks_failed=total['checks_failed'],
        vus_peak=total['vus'], vus_max_peak=total['vus_max'],
        endpoints=[dict(method=key[0], endpoint=key[1], **bucket_summary(bucket)) for key, bucket in sorted(endpoints.items())],
        runner=runner, recovery=recovery,
        windows=rows,
        average_rps=request_values.get('rate'),
        peak_window=peak,
        first_breaching_window=breach,
        first_http_failure_at=datetime.fromtimestamp(first_failure_at, timezone.utc).isoformat() if first_failure_at is not None else None,
        last_http_failure_at=datetime.fromtimestamp(last_failure_at, timezone.utc).isoformat() if last_failure_at is not None else None,
        raw_request_count_matches_summary=counts_match,
        interval_criteria=dict(failure_rate=failure_limit, p95_ms=latency_limit),
        benchmark_config=config, benchmark_phases=phase_summaries,
    )
    if diagnostics_json:
        Path(diagnostics_json).parent.mkdir(parents=True, exist_ok=True)
        Path(diagnostics_json).write_text(json.dumps(diagnostics, indent=2, allow_nan=False), encoding='utf-8')
    section = [
        '## Client time-series', '',
        f'- CSV: `{output}`; UTC-aligned windows of {width} seconds.',
        f'- Interval criteria: failure rate >= {failure_limit:.2%} or p95 >= {latency_limit:g} ms.',
        f"- Average whole-run RPS from k6 summary: {format_value(request_values.get('rate'))}.",
        f"- k6 exit code: {metadata.get('k6_exit_code', 'unknown')}; run ID: {metadata.get('run_id', 'unknown')}.",
    ]
    if rows:
        peak = max(rows, key=lambda row: row['completed_rps'])
        section.append(f"- Peak completed RPS in one window: {peak['completed_rps']:.3f} at {peak['window_start_utc']}.")
        if breach:
            failure = f"{breach['failure_rate']:.2%}" if breach['failure_rate'] is not None else 'n/a'
            latency = f"{breach['p95_ms']:.2f} ms" if breach['p95_ms'] is not None else 'n/a'
            section.append(
                f"- First interval exceeding configured thresholds: {breach['window_start_utc']} "
                f"(RPS {breach['completed_rps']:.3f}, failure rate {failure}, p95 {latency}). "
                'This is an interval observation, not the k6 cumulative abort decision.'
            )
        else:
            section.append('- No threshold breach found in available interval samples; missing samples are not evidence of success.')
    else:
        section.append('- No supported point samples found.')
    if truncated:
        section.append('- Incomplete input: truncated final JSONL line was ignored. Statistics cover available samples only.')
    if counts_match is False:
        section.append(f"- Raw request count ({total['requests']}) differs from k6 summary ({request_values['count']}); interval results may be incomplete.")
    section.extend([
        '- First and last windows may be partial; RPS uses the full window width. Empty windows between samples are included. Requests are counted on completion and include redirects.',
        '- Missing latency/failure samples are blank in CSV. Data counters are client-side transfer bytes; latency excludes connection setup.',
    ])
    section.extend([
        '', '### HTTP diagnostics', '',
        f"- HTTP status counts: `{json.dumps(total['statuses'], sort_keys=True)}`.",
        f"- k6 error codes: `{json.dumps(total['errors'], sort_keys=True)}`.",
        f"- Error categories: `{json.dumps(error_categories(total['errors']), sort_keys=True)}`.",
        f"- First / last HTTP failure sample: {diagnostics['first_http_failure_at'] or 'n/a'} / {diagnostics['last_http_failure_at'] or 'n/a'}.",
        f"- Failed checks: {total['checks_failed']}; dropped iterations: {total['dropped']}.",
        f"- Peak active / allocated VUs: {format_value(total['vus'])} / {format_value(total['vus_max'])}.",
        f"- Bytes sent / received: {total['sent']} / {total['received']}.",
        f"- Average transfer bytes sent / received per HTTP request: {format_value(total['sent'] / total['requests'] if total['requests'] else None)} / {format_value(total['received'] / total['requests'] if total['requests'] else None)}. Includes protocol overhead; not decoded body size.",
        '', '| HTTP phase | Samples | Average ms | p95 ms | p99 ms |',
        '| --- | ---: | ---: | ---: | ---: |',
    ])
    for name in TIMINGS:
        phase = stats(total['timings'][name])
        section.append(f"| {name} | {phase['samples']} | {format_value(phase['avg'])} | {format_value(phase['p95'])} | {format_value(phase['p99'])} |")
    section.extend([
        '', '### Endpoints', '',
        f'- Totals: `{endpoints_csv}`; per-window detail: `{endpoint_intervals_csv}`.',
        '- Endpoints are grouped by method and path with query strings removed. Redirect hops retain k6 request tags. Byte counters are run-wide and are not attributed to endpoints.',
        '', '| Method | Endpoint | Requests | Failure rate | Latency samples | p95 ms | p99 ms | Avg body B |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |',
    ])
    for row in endpoint_rows:
        failure = format_value(row['failure_rate'] * 100, '%') if row['failure_rate'] is not None else 'n/a'
        section.append(f"| {markdown_cell(row['method'])} | {markdown_cell(row['endpoint'])} | {row['requests']} | {failure} | {row['latency_samples']} | {format_value(row['p95_ms'])} | {format_value(row['p99_ms'])} | {format_value(row['response_body_avg_bytes'])} |")
    section.append('- Body-size samples are decoded final-response bodies returned to the script; redirect bodies are not sampled. Sample counts are in CSV. Transfer bytes include a different scope and must not be compared as identical quantities.')
    if phase_summaries:
        section.extend([
            '', '### Local benchmark phases', '',
            f'- Phase detail: `{phases_csv}`. Requests are attributed to their start phase even if they complete later. Planned target RPS is not measured throughput; phases without samples were not observed.',
            '', '| Phase | Planned target RPS | Requests | Failure rate | p95 ms | p99 ms |',
            '| --- | ---: | ---: | ---: | ---: | ---: |',
        ])
        for phase in phase_summaries:
            rate = format_value(phase['failure_rate'] * 100, '%') if phase['failure_rate'] is not None else 'n/a'
            section.append(f"| {markdown_cell(phase['phase'])} | {format_value(phase['planned_target_rps'])} | {phase['requests']} | {rate} | {format_value(phase['latency_ms']['p95'])} | {format_value(phase['latency_ms']['p99'])} |")
    section.extend(['', '### Generator observations', ''])
    if runner['available']:
        section.extend([
            f"- k6 process CPU peak: {format_value(runner['k6_cpu_percent_peak'], '% of one logical core')}; RSS peak: {format_value(runner['rss_bytes_peak'], ' B')}.",
            f"- Host busy CPU peak: {format_value(runner['host_cpu_busy_percent_peak'], '%')}; minimum available host memory: {format_value(runner['host_available_bytes_min'], ' B')}.",
            f"- Host network RX / TX peak: {format_value(runner['host_rx_bytes_per_second_peak'], ' B/s')} / {format_value(runner['host_tx_bytes_per_second_peak'], ' B/s')} (all non-loopback interfaces, may include unrelated traffic).",
        ])
    else:
        section.append('- OS runner metrics unavailable. Linux /proc is required for these samples.')
    if total['dropped']:
        section.append('- The generator did not start all scheduled iterations. Slow responses, VU limits or local resource pressure can contribute; this is not a server-capacity measurement.')
    if total['statuses'].get('429', 0):
        section.append('- HTTP 429 was observed: requests were rate-limited somewhere on the HTTP path.')
    if any(status.startswith('5') and count for status, count in total['statuses'].items()):
        section.append('- HTTP 5xx responses were observed. Client measurements cannot identify the failing backend or proxy.')
    section.extend(['', '### Independent availability and recovery', ''])
    if recovery['available']:
        section.extend([
            f"- Probe samples: {recovery['samples']}; failed: {recovery['failed_samples']}; failed during load: {recovery['failed_during_load']}.",
            f"- Post-load status: {recovery['status']}; time to confirmed healthy sequence: {format_value(recovery['healthy_after_load_seconds'], ' s')}.",
            '- Probe health uses HTTP 2xx/3xx and response-header time within the configured limit. Redirects are not followed; response bodies are not validated. Confirmation time has probe-interval resolution and does not prove recovery of all endpoints.',
        ])
    else:
        section.append('- Independent probes were not collected; recovery is unknown.')
    section.extend(['', '- Quantiles with few samples are unstable. HTTP timings and status codes describe observations, not a server-side diagnosis.'])
    report_path = Path(report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    existing = report_path.read_text(encoding='utf-8') if report_path.exists() else ''
    heading = '\n## Client time-series\n'
    prefix, found, tail = ('\n' + existing).partition(heading)
    suffix = ''
    if found:
        next_heading = tail.find('\n## ')
        if next_heading >= 0:
            suffix = tail[next_heading:]
        existing = prefix.lstrip('\n')
    report_path.write_text(existing.rstrip() + '\n\n' + '\n'.join(section) + '\n' + suffix, encoding='utf-8')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    parser.add_argument('report')
    parser.add_argument('width', type=int)
    for name in ('endpoints-csv', 'endpoint-intervals-csv', 'diagnostics-json',
                 'runner-samples', 'probe-samples', 'run-metadata', 'summary-json',
                 'benchmark-config', 'phases-csv'):
        parser.add_argument('--' + name)
    args = vars(parser.parse_args())
    analyze(**args)

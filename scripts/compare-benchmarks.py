#!/usr/bin/env python3
"""Compare local benchmark diagnostics while retaining workload and resource labels."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def comparison_row(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    config = data.get('benchmark_config')
    if not config or config.get('profile') != 'benchmark':
        return None
    labels = config.get('labels', {})
    run, http = data.get('run', {}), data.get('http', {})
    peak, breach = data.get('peak_window') or {}, data.get('first_breaching_window') or {}
    # Different hardware/address labels can share a workload. Different schedules,
    # mixes, generator limits, SLOs or reporting windows remain distinguishable.
    workload = {name: value for name, value in config.items() if name not in ('target', 'labels')}
    workload['interval_criteria'] = data.get('interval_criteria')
    workload['report_interval_seconds'] = peak.get('window_seconds')
    workload_id = hashlib.sha256(json.dumps(workload, sort_keys=True).encode()).hexdigest()[:12]
    latency = http.get('latency_ms', {})
    return dict(
        run_id=run.get('run_id', Path(path).stem), started_at=run.get('load_started_at'),
        label=labels.get('run'), server_cpu_label=labels.get('serverCPU'),
        server_memory_label=labels.get('serverMemory'), server_config_label=labels.get('serverConfig'),
        generator_location=labels.get('generatorLocation'), workload_id=workload_id,
        target=config.get('target'), k6_exit_code=run.get('k6_exit_code'),
        incomplete_input=data.get('incomplete_input'), requests=http.get('requests'),
        average_rps=data.get('average_rps'), peak_window_rps=peak.get('completed_rps'),
        failure_rate=http.get('failure_rate'), p95_ms=latency.get('p95'), p99_ms=latency.get('p99'),
        first_breaching_window_rps=breach.get('completed_rps'),
        request_timeouts=http.get('error_categories', {}).get('request_timeouts'),
        dropped_iterations=data.get('dropped_iterations'),
        sent_bytes=data.get('data_sent_bytes'), received_bytes=data.get('data_received_bytes'),
        recovery_status=data.get('recovery', {}).get('status'),
        healthy_after_load_seconds=data.get('recovery', {}).get('healthy_after_load_seconds'),
        diagnostics=str(path),
    )


def compare(inputs, output):
    paths = set()
    for raw in inputs:
        path = Path(raw)
        paths.update(path.rglob('*.diagnostics.json') if path.is_dir() else [path])
    rows = [row for path in sorted(paths) if (row := comparison_row(path)) is not None]
    if not rows:
        raise ValueError('No local benchmark diagnostics found')
    rows.sort(key=lambda row: (row['started_at'] or '', row['run_id']))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', nargs='+', help='Diagnostic files or result directories')
    parser.add_argument('--output', default='results/benchmark/csv/comparison.csv')
    args = parser.parse_args()
    rows = compare(args.inputs, args.output)
    print(f'Compared {len(rows)} runs: {args.output}. Compare results within the same workload_id.')

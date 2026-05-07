#!/usr/bin/env bash
set -euo pipefail

started_at="${1:-}"
ended_at="${2:-}"

if [ -z "${PROMETHEUS_URL:-}" ]; then
  exit 0
fi

if ! command -v curl >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
  echo "curl and jq are required to fetch Prometheus metrics" >&2
  exit 1
fi

start_epoch="$(date -d "${started_at}" +%s)"
end_epoch="$(date -d "${ended_at}" +%s)"
duration_seconds="$((end_epoch - start_epoch))"

if [ "${duration_seconds}" -lt 60 ]; then
  duration_seconds=60
fi

step="${PROMETHEUS_QUERY_STEP:-30s}"
instance_filter=""
device_filter='device!="lo"'

if [ -n "${PROMETHEUS_INSTANCE:-}" ]; then
  instance_filter=",instance=\"${PROMETHEUS_INSTANCE}\""
fi

if [ -n "${PROMETHEUS_NET_DEVICE:-}" ]; then
  device_filter="device=\"${PROMETHEUS_NET_DEVICE}\""
fi

prom_query() {
  local query="$1"

  curl -fsS --get "${PROMETHEUS_URL%/}/api/v1/query" \
    --data-urlencode "query=${query}" \
    --data-urlencode "time=${end_epoch}" \
    | jq -r '.data.result[0].value[1] // "nan"'
}

fmt_percent() {
  local value="$1"
  awk -v value="${value}" 'BEGIN { if (value == "nan" || value == "") print "n/a"; else printf "%.2f%%", value }'
}

fmt_mbps() {
  local value="$1"
  awk -v value="${value}" 'BEGIN { if (value == "nan" || value == "") print "n/a"; else printf "%.3f Mbps", value }'
}

cpu_avg="$(prom_query "avg_over_time((100 * (1 - avg(rate(node_cpu_seconds_total{mode=\"idle\"${instance_filter}}[1m]))))[${duration_seconds}s:${step}])")"
cpu_max="$(prom_query "max_over_time((100 * (1 - avg(rate(node_cpu_seconds_total{mode=\"idle\"${instance_filter}}[1m]))))[${duration_seconds}s:${step}])")"
mem_avg="$(prom_query "avg_over_time((100 * (1 - (node_memory_MemAvailable_bytes{${instance_filter#,}} / node_memory_MemTotal_bytes{${instance_filter#,}})))[${duration_seconds}s:${step}])")"
mem_max="$(prom_query "max_over_time((100 * (1 - (node_memory_MemAvailable_bytes{${instance_filter#,}} / node_memory_MemTotal_bytes{${instance_filter#,}})))[${duration_seconds}s:${step}])")"
rx_avg="$(prom_query "avg_over_time(((rate(node_network_receive_bytes_total{${device_filter}${instance_filter}}[1m]) * 8) / 1000000)[${duration_seconds}s:${step}])")"
rx_max="$(prom_query "max_over_time(((rate(node_network_receive_bytes_total{${device_filter}${instance_filter}}[1m]) * 8) / 1000000)[${duration_seconds}s:${step}])")"
tx_avg="$(prom_query "avg_over_time(((rate(node_network_transmit_bytes_total{${device_filter}${instance_filter}}[1m]) * 8) / 1000000)[${duration_seconds}s:${step}])")"
tx_max="$(prom_query "max_over_time(((rate(node_network_transmit_bytes_total{${device_filter}${instance_filter}}[1m]) * 8) / 1000000)[${duration_seconds}s:${step}])")"

cat <<EOF

## Server-Side Metrics From Prometheus

| Metric | Avg | Max |
| --- | ---: | ---: |
| CPU usage | $(fmt_percent "${cpu_avg}") | $(fmt_percent "${cpu_max}") |
| Memory usage | $(fmt_percent "${mem_avg}") | $(fmt_percent "${mem_max}") |
| Network RX | $(fmt_mbps "${rx_avg}") | $(fmt_mbps "${rx_max}") |
| Network TX | $(fmt_mbps "${tx_avg}") | $(fmt_mbps "${tx_max}") |

Prometheus range: ${started_at} - ${ended_at}
Prometheus URL: ${PROMETHEUS_URL}
Instance filter: ${PROMETHEUS_INSTANCE:-all}
Network device filter: ${PROMETHEUS_NET_DEVICE:-non-loopback devices}
EOF

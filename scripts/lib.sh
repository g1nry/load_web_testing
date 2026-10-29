#!/usr/bin/env bash

load_env() {
  if [ -f .env ]; then
    set -a
    . ./.env
    set +a
  fi
}

print_banner() {
  local profile="$1"
  local script="$2"
  local result_file="$3"
  local report_file="$4"
  local reset="\033[0m"
  local blue="\033[34m"
  local dim="\033[2m"

  printf "%b" "${blue}"
  cat <<'EOF'
                         _
     /\_/\         __ _ | |
    ( o.o )       / _  || |
     > ^ <       | (_| || |
     /   \        \__  ||_|
    (\   /)       |___/ Reversed
     ^^ ^^
EOF
  printf "%b" "${reset}"

  printf "\n%b Authorized black-box HTTP load testing%b\n\n" "${dim}" "${reset}"
  printf "     execution: local\n"
  printf "        script: %s\n" "${script}"
  printf "        output: -\n"
  printf "     scenarios: configured by %s\n\n" "${script}"
  printf "       profile: %s\n" "${profile}"
  printf "       summary: %s\n" "${result_file}"
  printf "        report: %s\n" "${report_file}"
  printf "%s\n\n" "                            "
}

duration_to_seconds() {
  local duration="${1:-0s}"
  local rest
  local total=0

  duration="${duration// /}"
  duration="${duration,,}"
  rest="${duration}"

  if [[ "${rest}" =~ ^[0-9]+$ ]]; then
    printf "%s\n" "${rest}"
    return
  fi

  while [[ "${rest}" =~ ^([0-9]+)(ms|s|m|h)(.*)$ ]]; do
    local value="${BASH_REMATCH[1]}"
    local unit="${BASH_REMATCH[2]}"
    rest="${BASH_REMATCH[3]}"

    case "${unit}" in
      ms)
        if [ "${value}" -gt 0 ]; then
          total=$((total + 1))
        fi
        ;;
      s)
        total=$((total + value))
        ;;
      m)
        total=$((total + value * 60))
        ;;
      h)
        total=$((total + value * 3600))
        ;;
    esac
  done

  printf "%s\n" "${total}"
}

format_seconds() {
  local seconds="$1"
  printf "%02d:%02d" "$((seconds / 60))" "$((seconds % 60))"
}

repeat_char() {
  local char="$1"
  local count="$2"
  local output=""

  while [ "${count}" -gt 0 ]; do
    output="${output}${char}"
    count=$((count - 1))
  done

  printf "%s" "${output}"
}

capacity_steps_count() {
  local raw_steps="${1:-}"
  local count=0
  local step

  IFS=',' read -ra steps <<< "${raw_steps}"

  for step in "${steps[@]}"; do
    step="${step// /}"
    if [ -n "${step}" ]; then
      count=$((count + 1))
    fi
  done

  printf "%s\n" "${count}"
}

profile_duration_seconds() {
  local profile="$1"

  case "${profile}" in
    smoke)
      duration_to_seconds "${SMOKE_DURATION:-30s}"
      ;;
    discovery)
      duration_to_seconds "${DISCOVERY_DURATION:-10s}"
      ;;
    throughput)
      local steps ramp hold ramp_down
      steps="$(capacity_steps_count "${THROUGHPUT_RATE_STEPS:-50,100,200,400}")"
      ramp="$(duration_to_seconds "${THROUGHPUT_RAMP_DURATION:-30s}")"
      hold="$(duration_to_seconds "${THROUGHPUT_HOLD_DURATION:-1m}")"
      ramp_down="$(duration_to_seconds "${THROUGHPUT_RAMP_DOWN_DURATION:-30s}")"
      printf "%s\n" "$((steps * (ramp + hold) + ramp_down))"
      ;;
    cpu)
      local steps ramp hold ramp_down
      steps="$(capacity_steps_count "${CPU_RATE_STEPS:-${CPU_RATE:-25,50,100,200}}")"
      ramp="$(duration_to_seconds "${CPU_RAMP_DURATION:-30s}")"
      hold="$(duration_to_seconds "${CPU_HOLD_DURATION:-1m}")"
      ramp_down="$(duration_to_seconds "${CPU_RAMP_DOWN_DURATION:-30s}")"
      printf "%s\n" "$((steps * (ramp + hold) + ramp_down))"
      ;;
    memory)
      duration_to_seconds "${MEMORY_DURATION:-10m}"
      ;;
    network)
      duration_to_seconds "${NETWORK_DURATION:-5m}"
      ;;
    capacity)
      local steps step_duration
      steps="$(capacity_steps_count "${CAPACITY_RATE_STEPS:-50,100,200,400,800}")"
      step_duration="$(duration_to_seconds "${CAPACITY_STEP_DURATION:-${CAPACITY_HOLD_DURATION:-1m}}")"
      printf "%s\n" "$((steps * step_duration))"
      ;;
    benchmark)
      local steps ramp hold warmup soak down
      steps="$(capacity_steps_count "${BENCHMARK_RATE_STEPS:-50,100,200,400,600}")"
      ramp="$(duration_to_seconds "${BENCHMARK_RAMP_DURATION:-20s}")"
      hold="$(duration_to_seconds "${BENCHMARK_HOLD_DURATION:-2m}")"
      warmup="$(duration_to_seconds "${BENCHMARK_WARMUP_DURATION:-20s}")"
      soak="$(duration_to_seconds "${BENCHMARK_SOAK_DURATION:-5m}")"
      down="$(duration_to_seconds "${BENCHMARK_RAMP_DOWN_DURATION:-30s}")"
      printf "%s\n" "$((warmup + steps * (ramp + hold) + soak + down))"
      ;;
    *)
      printf "0\n"
      ;;
  esac
}

append_prometheus_metrics() {
  local report_file="$1"
  local started_at="$2"
  local ended_at="$3"

  if [ -z "${PROMETHEUS_URL:-}" ]; then
    return
  fi

  if [ ! -x "./scripts/fetch-prometheus-metrics.sh" ]; then
    return
  fi

  ./scripts/fetch-prometheus-metrics.sh "${started_at}" "${ended_at}" >> "${report_file}" || {
    {
      printf "\n## Server-Side Metrics From Prometheus\n\n"
      printf "- Failed to fetch Prometheus metrics. Check PROMETHEUS_URL, PROMETHEUS_INSTANCE, PROMETHEUS_NET_DEVICE and curl/jq availability.\n"
    } >> "${report_file}"
  }
}

profile_endpoints_var() {
  local profile="$1"

  case "${profile}" in
    throughput)
      printf "THROUGHPUT_ENDPOINTS\n"
      ;;
    cpu)
      printf "CPU_ENDPOINTS\n"
      ;;
    memory)
      printf "MEMORY_ENDPOINTS\n"
      ;;
    network)
      printf "NETWORK_ENDPOINTS\n"
      ;;
    capacity)
      printf "CAPACITY_ENDPOINTS\n"
      ;;
    benchmark)
      printf "BENCHMARK_ENDPOINTS\n"
      ;;
    *)
      printf "LOAD_ENDPOINTS\n"
      ;;
  esac
}

profile_endpoints() {
  local profile="$1"
  local var_name
  local value

  if [ "${profile}" = "benchmark" ]; then
    printf "%s\n" "${BENCHMARK_ENDPOINTS:-/}"
    return
  fi

  var_name="$(profile_endpoints_var "${profile}")"
  value="${!var_name:-}"

  if [ -z "${value}" ]; then
    value="${LOAD_ENDPOINTS:-/}"
  fi

  printf "%s\n" "${value}"
}

profile_request_timeout() {
  local profile="$1"

  case "${profile}" in
    memory)
      printf "%s\n" "${MEMORY_REQUEST_TIMEOUT:-${REQUEST_TIMEOUT:-10s}}"
      ;;
    network)
      printf "%s\n" "${NETWORK_REQUEST_TIMEOUT:-${REQUEST_TIMEOUT:-10s}}"
      ;;
    benchmark)
      printf "%s\n" "${BENCHMARK_REQUEST_TIMEOUT:-5s}"
      ;;
    *)
      printf "%s\n" "${REQUEST_TIMEOUT:-10s}"
      ;;
  esac
}

is_control_endpoint() {
  local endpoint="$1"
  local clean_endpoint="${endpoint%%\?*}"

  case "${clean_endpoint}" in
    /ping|/healthz|/readyz|/version|/metrics)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_light_cpu_endpoint() {
  local endpoint="$1"
  local clean_endpoint="${endpoint%%\?*}"

  case "${clean_endpoint}" in
    /|/ping|/healthz|/readyz|/version)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_forbidden_network_endpoint() {
  local endpoint="$1"
  local clean_endpoint="${endpoint%%\?*}"

  case "${clean_endpoint}" in
    /ping|/healthz|/readyz|/version|/metrics)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

endpoint_audit_should_fail_on_status() {
  local profile="$1"

  case "${profile}" in
    throughput|cpu|memory|network|capacity|benchmark)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

audit_profile_endpoints() {
  local profile="$1"
  local target_url="${TARGET_URL:-}"
  local raw_endpoints
  local normalized_target
  local endpoint
  local clean_endpoint
  local url
  local tmp_file
  local curl_output
  local http_code
  local size_download
  local time_total
  local bad_status_count=0
  local control_count=0
  local light_cpu_count=0
  local forbidden_network_count=0
  local small_network_count=0
  local endpoint_count=0
  local min_network_bytes="${NETWORK_MIN_RESPONSE_BYTES:-10240}"
  local curl_timeout
  local network_method="${NETWORK_METHOD:-GET}"
  local network_payload_bytes="${NETWORK_PAYLOAD_BYTES:-0}"
  local payload_file=""
  local audit_retries="${ENDPOINT_AUDIT_RETRIES:-1}"
  local redirect_args=(-L)

  if [ "${profile}" = "benchmark" ]; then
    redirect_args=()
  fi

  if [ -z "${target_url}" ]; then
    return
  fi

  case "${profile}" in
    throughput|cpu|memory|network|capacity|benchmark)
      ;;
    *)
      return
      ;;
  esac

  raw_endpoints="$(profile_endpoints "${profile}")"
  normalized_target="${target_url%/}"
  curl_timeout="$(duration_to_seconds "$(profile_request_timeout "${profile}")")"
  if [ "${curl_timeout}" -le 0 ]; then
    curl_timeout="10"
  fi
  if [ "${profile}" = "memory" ] && [ "${ENDPOINT_AUDIT_RETRIES:-}" = "" ]; then
    audit_retries=3
  fi

  printf "endpoint audit:\n"
  printf "  %-22s %-6s %-10s %-8s %s\n" "endpoint" "status" "bytes" "attempt" "time"

  if [ "${profile}" = "network" ] && [ "${network_method^^}" = "POST" ] && [ "${network_payload_bytes}" -gt 0 ]; then
    payload_file="$(mktemp)"
    head -c "${network_payload_bytes}" /dev/zero | tr '\0' 'x' > "${payload_file}"
  fi

  IFS=',' read -ra endpoints <<< "${raw_endpoints}"
  for endpoint in "${endpoints[@]}"; do
    endpoint="${endpoint// /}"
    if [ -z "${endpoint}" ]; then
      continue
    fi

    endpoint_count=$((endpoint_count + 1))
    clean_endpoint="${endpoint%%\?*}"

    if [[ "${endpoint}" == /* ]]; then
      url="${normalized_target}${endpoint}"
    else
      url="${normalized_target}/${endpoint}"
    fi

    local attempt=1
    while [ "${attempt}" -le "${audit_retries}" ]; do
      tmp_file="$(mktemp)"
      set +e
      if [ -n "${payload_file}" ]; then
        curl_output="$(curl -sS "${redirect_args[@]}" -X POST --data-binary "@${payload_file}" -H "Content-Type: ${NETWORK_CONTENT_TYPE:-text/plain}" -o "${tmp_file}" -w "%{http_code} %{size_download} %{time_total}" --max-time "${curl_timeout}" "${url}" 2>/dev/null)"
      else
        curl_output="$(curl -sS "${redirect_args[@]}" -o "${tmp_file}" -w "%{http_code} %{size_download} %{time_total}" --max-time "${curl_timeout}" "${url}" 2>/dev/null)"
      fi
      local curl_status=$?
      set -e

      if [ "${curl_status}" -ne 0 ] || [ -z "${curl_output}" ]; then
        http_code="000"
        size_download="0"
        time_total="-"
      else
        read -r http_code size_download time_total <<< "${curl_output}"
      fi

      rm -f "${tmp_file}"

      if [ "${http_code}" -ge 200 ] && [ "${http_code}" -lt 400 ] && { [ "${profile}" != "benchmark" ] || [ "${http_code}" -lt 300 ]; }; then
        break
      fi

      attempt=$((attempt + 1))
    done

    if [ "${attempt}" -gt "${audit_retries}" ]; then
      attempt="${audit_retries}"
    fi

    printf "  %-22s %-6s %-10s %-8s %s\n" "${endpoint}" "${http_code}" "${size_download}" "${attempt}/${audit_retries}" "${time_total}s"

    if [ "${http_code}" -lt 200 ] || [ "${http_code}" -ge 400 ] || { [ "${profile}" = "benchmark" ] && [ "${http_code}" -ge 300 ]; }; then
      bad_status_count=$((bad_status_count + 1))
    fi

    if is_control_endpoint "${clean_endpoint}"; then
      control_count=$((control_count + 1))
    fi

    if is_light_cpu_endpoint "${clean_endpoint}"; then
      light_cpu_count=$((light_cpu_count + 1))
    fi

    if is_forbidden_network_endpoint "${clean_endpoint}"; then
      forbidden_network_count=$((forbidden_network_count + 1))
    fi

    if [ "${profile}" = "network" ] && [ "${size_download}" -lt "${min_network_bytes}" ]; then
      small_network_count=$((small_network_count + 1))
    fi
  done

  if [ -n "${payload_file}" ]; then
    rm -f "${payload_file}"
  fi

  printf "\n"

  if [ "${endpoint_count}" -eq 0 ]; then
    printf "endpoint audit failed: no endpoints configured for %s.\n\n" "${profile}" >&2
    return 1
  fi

  if endpoint_audit_should_fail_on_status "${profile}" && [ "${bad_status_count}" -gt 0 ]; then
    printf "endpoint audit failed: %s endpoint(s) returned non-2xx/3xx status. Remove them from this pressure profile before running it.\n\n" "${bad_status_count}" >&2
    return 1
  fi

  if [ "${profile}" = "cpu" ] && [ "${light_cpu_count}" -eq "${endpoint_count}" ]; then
    printf "endpoint audit warning: CPU profile uses only light/control endpoints. It will mostly test routing and HTTP overhead, not service CPU saturation.\n\n" >&2
  fi

  if [ "${profile}" = "network" ]; then
    if [ "${forbidden_network_count}" -gt 0 ]; then
      printf "endpoint audit failed: network profile includes control endpoints such as /metrics, /ping, /healthz, /readyz or /version. Use /api/echo or another large-response endpoint instead.\n\n" >&2
      return 1
    fi

    if [ "${small_network_count}" -gt 0 ]; then
      printf "endpoint audit failed: %s network endpoint(s) returned less than NETWORK_MIN_RESPONSE_BYTES=%s bytes.\n\n" "${small_network_count}" "${min_network_bytes}" >&2
      return 1
    fi
  fi
}

show_progress() {
  local pid="$1"
  local total_seconds="$2"
  local width=28
  local elapsed=0
  local percent=0
  local filled=0
  local empty=0
  local bar=""
  local final_elapsed=0

  if [ "${total_seconds}" -le 0 ]; then
    printf "progress: running...\n"
    while kill -0 "${pid}" 2>/dev/null; do
      sleep 1
    done
    return
  fi

  while kill -0 "${pid}" 2>/dev/null; do
    if [ "${elapsed}" -gt "${total_seconds}" ]; then
      percent=99
    else
      percent=$((elapsed * 100 / total_seconds))
    fi

    filled=$((percent * width / 100))
    empty=$((width - filled))
    bar="$(repeat_char "#" "${filled}")"
    bar="${bar}$(repeat_char "-" "${empty}")"

    printf "\rprogress: [%s] %3d%% %s/%s" \
      "${bar}" \
      "${percent}" \
      "$(format_seconds "${elapsed}")" \
      "$(format_seconds "${total_seconds}")"

    sleep 1
    elapsed=$((elapsed + 1))
  done

  final_elapsed="${elapsed}"
  if [ "${final_elapsed}" -gt "${total_seconds}" ]; then
    final_elapsed="${total_seconds}"
  fi

  percent=$((final_elapsed * 100 / total_seconds))
  filled=$((percent * width / 100))
  empty=$((width - filled))
  bar="$(repeat_char "#" "${filled}")"
  bar="${bar}$(repeat_char "-" "${empty}")"

  printf "\rprogress: [%s] %3d%% %s/%s finished\n\n" \
    "${bar}" \
    "${percent}" \
    "$(format_seconds "${final_elapsed}")" \
    "$(format_seconds "${total_seconds}")"
}

run_k6_profile() {
  local profile="$1"
  local script="$2"
  local timestamp
  local started_at
  local ended_at
  local result_file
  local report_file
  local log_file
  local expected_duration
  local metrics_file
  local intervals_file
  local endpoints_file
  local endpoint_intervals_file
  local diagnostics_file
  local config_file
  local phases_file
  local runner_file
  local probe_file
  local run_file
  local result_base
  local run_id
  local observer_pid=""
  local probe_endpoint=""
  local observer_args=()
  local python_bin=""
  local k6_pid
  local k6_status
  local log_start_line

  load_env

  if [ "${profile}" = "benchmark" ]; then
    export BENCHMARK_TARGET_URL="${BENCHMARK_TARGET_URL:-http://127.0.0.1:8080}"
    export TARGET_URL="${BENCHMARK_TARGET_URL}"
  fi

  case "${profile}" in
    smoke|discovery|throughput|cpu|memory|network|capacity|benchmark) ;;
    *) printf "Unknown profile: %s\n" "${profile}" >&2; return 1 ;;
  esac

  if ! [[ "${REPORT_INTERVAL_SECONDS:-10}" =~ ^[1-9][0-9]*$ ]]; then
    printf "REPORT_INTERVAL_SECONDS must be a positive integer.\n" >&2
    return 1
  fi
  if command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
  elif command -v python >/dev/null 2>&1; then
    python_bin="python"
  fi

  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  run_id="${profile}-${timestamp}-$$"
  result_base="results/${profile}"
  mkdir -p "${result_base}/json" "${result_base}/jsonl" "${result_base}/csv" "${result_base}/md" "${result_base}/log"
  result_file="${result_base}/json/${run_id}.summary.json"
  diagnostics_file="${result_base}/json/${run_id}.diagnostics.json"
  config_file="${result_base}/json/${run_id}.config.json"
  phases_file="${result_base}/csv/${run_id}.phases.csv"
  run_file="${result_base}/json/${run_id}.run.json"
  report_file="${result_base}/md/${run_id}.md"
  log_file="${result_base}/log/${run_id}.log"
  metrics_file="${result_base}/jsonl/${run_id}.points.jsonl"
  runner_file="${result_base}/jsonl/${run_id}.runner.jsonl"
  probe_file="${result_base}/jsonl/${run_id}.probes.jsonl"
  intervals_file="${result_base}/csv/${run_id}.intervals.csv"
  endpoints_file="${result_base}/csv/${run_id}.endpoints.csv"
  endpoint_intervals_file="${result_base}/csv/${run_id}.endpoint-intervals.csv"

  export K6_PROFILE="${profile}"
  export K6_SCRIPT="${script}"
  export K6_SUMMARY_JSON="${result_file}"
  export K6_SUMMARY_MARKDOWN="${report_file}"
  export K6_RUN_CONFIG_JSON="${config_file}"

  print_banner "${profile}" "${script}" "${result_file}" "${report_file}" | tee "${log_file}"
  # Validate local scope before preflight curl can issue any HTTP request.
  if [ "${profile}" = "benchmark" ] && ! k6 inspect --include-system-env-vars "${script}" > /dev/null 2>> "${log_file}"; then
    cat "${log_file}"
    return 1
  fi
  expected_duration="$(profile_duration_seconds "${profile}")"
  if [ -n "${python_bin}" ]; then
    if [ "${ENABLE_DIAGNOSTIC_PROBE:-true}" = "true" ]; then
      probe_endpoint="${DIAGNOSTIC_PROBE_ENDPOINT:-/}"
    fi
    observer_args=(
      --finished-file "${run_file}" --runner-file "${runner_file}" --probe-file "${probe_file}"
      --target "${TARGET_URL:-}" --endpoint "${probe_endpoint}"
      --interval "${DIAGNOSTIC_PROBE_INTERVAL_SECONDS:-5}"
      --timeout "${DIAGNOSTIC_PROBE_TIMEOUT_SECONDS:-3}"
      --limit-ms "${DIAGNOSTIC_PROBE_LIMIT_MS:-2000}"
      --recovery-seconds "${RECOVERY_OBSERVATION_SECONDS:-60}"
      --healthy-count "${RECOVERY_HEALTHY_SAMPLES:-3}"
      --max-seconds "$((expected_duration + 1200))"
    )
    if ! "${python_bin}" scripts/observe-run.py --pid 0 --validate-only "${observer_args[@]}" >> "${log_file}" 2>&1; then
      cat "${log_file}"
      return 1
    fi
  fi
  if ! audit_profile_endpoints "${profile}" 2>&1 | tee -a "${log_file}"; then
    printf "Endpoint audit failed. Log: %s\n" "${log_file}" >&2
    return 1
  fi

  started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  export K6_STARTED_AT="${started_at}"
  export K6_RUN_ID="${run_id}"
  export K6_RUN_METADATA="${run_file}"
  log_start_line="$(wc -l < "${log_file}")"

  k6 run \
    --address "127.0.0.1:0" \
    --quiet \
    --summary-export "${result_file}" \
    --out "json=${metrics_file}" \
    "${script}" >> "${log_file}" 2>&1 &

  k6_pid=$!
  trap 'if [ -n "${k6_pid:-}" ]; then kill "${k6_pid}" 2>/dev/null || true; fi; if [ -n "${observer_pid:-}" ]; then kill "${observer_pid}" 2>/dev/null || true; fi' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  if [ -n "${python_bin}" ]; then
    "${python_bin}" scripts/observe-run.py --pid "${k6_pid}" "${observer_args[@]}" >> "${log_file}" 2>&1 &
    observer_pid=$!
  fi
  show_progress "${k6_pid}" "${expected_duration}"

  set +e
  wait "${k6_pid}"
  k6_status=$?
  set -e
  k6_pid=""

  ended_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '{"profile":"%s","run_id":"%s","load_started_at":"%s","load_ended_at":"%s","k6_exit_code":%s}\n' \
    "${profile}" "${run_id}" "${started_at}" "${ended_at}" "${k6_status}" > "${run_file}"
  # The observer tolerates a partially written completion file and retries it.
  if [ -n "${observer_pid}" ]; then
    printf "Collecting post-load availability observations...\n"
    wait "${observer_pid}" || printf "Diagnostic observer failed; see the run log.\n" >> "${log_file}"
    observer_pid=""
  fi
  if [ ! -f "${report_file}" ]; then
    printf '# k6 Test Report: %s\n\nNo k6 summary was produced. Exit code: %s. See the run log.\n' "${profile}" "${k6_status}" > "${report_file}"
  fi
  if [ -f "${metrics_file}" ]; then
    if [ -n "${python_bin}" ]; then
      if ! "${python_bin}" scripts/analyze-metrics.py "${metrics_file}" "${intervals_file}" "${report_file}" "${REPORT_INTERVAL_SECONDS:-10}" \
        --endpoints-csv "${endpoints_file}" --endpoint-intervals-csv "${endpoint_intervals_file}" \
        --diagnostics-json "${diagnostics_file}" --runner-samples "${runner_file}" \
        --probe-samples "${probe_file}" --run-metadata "${run_file}" \
        --summary-json "${result_file}" --benchmark-config "${config_file}" \
        --phases-csv "${phases_file}" >> "${log_file}" 2>&1; then
        printf "Time-series analysis failed; raw samples remain in %s\n" "${metrics_file}" >> "${log_file}"
        printf "\n## Time-series analysis unavailable\n\nAnalysis failed; see the run log. Raw samples: %s\n" "${metrics_file}" >> "${report_file}"
      fi
    else
      printf "Python not found; raw samples remain in %s\n" "${metrics_file}" >> "${log_file}"
      printf "\n## Time-series analysis unavailable\n\nPython was not found. Raw samples: %s\n" "${metrics_file}" >> "${report_file}"
    fi
  fi
  append_prometheus_metrics "${report_file}" "${started_at}" "${ended_at}"

  tail -n "+$((log_start_line + 1))" "${log_file}"
  printf "\nRun: %s\nReport: %s\nDiagnostics: %s\n" "${run_id}" "${report_file}" "${diagnostics_file}"

  trap - EXIT INT TERM
  return "${k6_status}"
}

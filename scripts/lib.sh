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
      local steps ramp hold ramp_down
      steps="$(capacity_steps_count "${CAPACITY_RATE_STEPS:-50,100,200,400,800}")"
      ramp="$(duration_to_seconds "${CAPACITY_RAMP_DURATION:-30s}")"
      hold="$(duration_to_seconds "${CAPACITY_HOLD_DURATION:-1m}")"
      ramp_down="$(duration_to_seconds "${CAPACITY_RAMP_DOWN_DURATION:-1m}")"
      printf "%s\n" "$((steps * (ramp + hold) + ramp_down))"
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
  local k6_pid
  local k6_status

  mkdir -p results
  load_env

  timestamp="$(date +%Y%m%d-%H%M%S)"
  started_at="$(date +%Y-%m-%dT%H:%M:%S%z)"
  result_file="results/${profile}-${timestamp}.json"
  report_file="results/${profile}-${timestamp}.md"
  log_file="results/${profile}-${timestamp}.log"

  export K6_PROFILE="${profile}"
  export K6_SCRIPT="${script}"
  export K6_STARTED_AT="${started_at}"
  export K6_SUMMARY_JSON="${result_file}"
  export K6_SUMMARY_MARKDOWN="${report_file}"

  print_banner "${profile}" "${script}" "${result_file}" "${report_file}"

  expected_duration="$(profile_duration_seconds "${profile}")"

  k6 run \
    --address "127.0.0.1:0" \
    --quiet \
    --summary-export "${result_file}" \
    "${script}" > "${log_file}" 2>&1 &

  k6_pid=$!
  show_progress "${k6_pid}" "${expected_duration}"

  set +e
  wait "${k6_pid}"
  k6_status=$?
  set -e

  ended_at="$(date +%Y-%m-%dT%H:%M:%S%z)"
  append_prometheus_metrics "${report_file}" "${started_at}" "${ended_at}"

  cat "${log_file}"

  return "${k6_status}"
}

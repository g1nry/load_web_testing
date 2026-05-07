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

run_k6_profile() {
  local profile="$1"
  local script="$2"
  local timestamp
  local started_at
  local result_file
  local report_file

  mkdir -p results
  load_env

  timestamp="$(date +%Y%m%d-%H%M%S)"
  started_at="$(date +%Y-%m-%dT%H:%M:%S%z)"
  result_file="results/${profile}-${timestamp}.json"
  report_file="results/${profile}-${timestamp}.md"

  export K6_PROFILE="${profile}"
  export K6_SCRIPT="${script}"
  export K6_STARTED_AT="${started_at}"
  export K6_SUMMARY_JSON="${result_file}"
  export K6_SUMMARY_MARKDOWN="${report_file}"

  print_banner "${profile}" "${script}" "${result_file}" "${report_file}"

  k6 run \
    --quiet \
    --summary-export "${result_file}" \
    "${script}"
}

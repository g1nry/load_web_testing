#!/usr/bin/env bash
set -euo pipefail

mkdir -p results

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
result_file="results/endurance-${timestamp}.json"

k6 run \
  --summary-export "${result_file}" \
  tests/endurance.js

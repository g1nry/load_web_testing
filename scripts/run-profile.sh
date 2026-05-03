#!/usr/bin/env bash
set -euo pipefail

profile="${1:-}"

if [ -z "${profile}" ]; then
  echo "Usage: $0 <smoke|discovery|baseline|load|stress|spike|endurance>" >&2
  exit 1
fi

case "${profile}" in
  smoke|discovery|baseline|load|stress|spike|endurance)
    "./scripts/run-${profile}.sh"
    ;;
  *)
    echo "Unknown profile: ${profile}" >&2
    echo "Allowed profiles: smoke, discovery, baseline, load, stress, spike, endurance" >&2
    exit 1
    ;;
esac

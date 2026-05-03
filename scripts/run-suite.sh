#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

profiles="${TEST_PROFILES:-smoke,discovery,baseline}"
allow_high_impact="${ALLOW_HIGH_IMPACT_TESTS:-false}"

normalized_profiles="${profiles//,/ }"

for profile in ${normalized_profiles}; do
  case "${profile}" in
    stress|spike|endurance)
      if [ "${allow_high_impact}" != "true" ]; then
        echo "Skipping ${profile}: set ALLOW_HIGH_IMPACT_TESTS=true in .env to allow high-impact profiles."
        continue
      fi
      ;;
  esac

  echo "Running profile: ${profile}"
  ./scripts/run-profile.sh "${profile}"
done

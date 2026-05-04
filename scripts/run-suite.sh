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
failed_profiles=()

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
  if ./scripts/run-profile.sh "${profile}"; then
    echo "Completed profile: ${profile}"
  else
    status=$?
    echo "Failed profile: ${profile} (exit ${status})" >&2
    failed_profiles+=("${profile}")
  fi
done

if [ "${#failed_profiles[@]}" -gt 0 ]; then
  echo "Suite finished with failed profiles: ${failed_profiles[*]}" >&2
  exit 1
fi

echo "Suite finished successfully."

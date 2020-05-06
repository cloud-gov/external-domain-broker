#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

cf api "$CF_API_URL"
(set +x; cf auth "$CF_USERNAME" "$CF_PASSWORD")
cf target -o "$CF_ORGANIZATION" -s "$CF_SPACE"

if [[ -n "$(cf service "$SVC_NAME" --guid)" ]]; then
  cf create-service "$SVC_SERVICE" "$SVC_PLAN" "$SVC_NAME"
fi

echo -n "Waiting for service instance..."
while ! cf create-service-key "$SVC_NAME" temp-ci-key > /dev/null 2>&1; do
  echo -n "."
  sleep 5
done
echo
cf delete-service-key -f "$SVC_NAME" temp-ci-key || true

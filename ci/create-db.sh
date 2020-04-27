#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

cf api "$CF_API_URL"
(set +x; cf auth "$CF_USERNAME" "$CF_PASSWORD")
cf target -o "$CF_ORGANIZATION" -s "$CF_SPACE"

if [[ -n "$(cf service "$DB_NAME" --guid)" ]]; then
  cf create-service "$DB_SERVICE" "$DB_PLAN" "$DB_NAME"
fi

echo -n "Waiting for database..."
while ! cf create-service-key "$DB_NAME" temp-ci-key > /dev/null 2>&1; do
  echo -n "."
  sleep 5
done
echo
cf delete-service-key -f "$DB_NAME" temp-ci-key || true

#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

cf api "$CF_API_URL"
(set +x; cf auth "$CF_USERNAME" "$CF_PASSWORD")
cf target -o "$CF_ORGANIZATION" -s "$CF_SPACE"

for app in $APPLICATIONS; do
  if cf app "$app" > /dev/null; then
    cf stop "$app"
  fi
done

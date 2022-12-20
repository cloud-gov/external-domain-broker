#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit
set -x

cf api "$CF_API_URL"
(set +x; cf auth "$CF_USERNAME" "$CF_PASSWORD")
cf target -o "$CF_ORGANIZATION" -s "$CF_SPACE"

# dummy app so we can run a task.
cf push \
  -f src2/manifests/upgrade-schema.yml \
  -p src2 \
  -i 1 \
  --var DB_NAME="$DB_NAME" \
  --var REDIS_NAME="$REDIS_NAME" \
  --var APP_NAME="$APP_NAME" \
  --var FLASK_ENV="$FLASK_ENV" \
  --var DATABASE_ENCRYPTION_KEY="$DATABASE_ENCRYPTION_KEY" \
  --no-route \
  --health-check-type=process \
  -c "sleep 3600" \
  "$APP_NAME"

# This is just to put logs in the concourse output.
(cf logs "$APP_NAME" | grep "TASK/check-duplicate-certs") &

DUPLICATE_CERTS_OUTPUT=$(mktemp)
cmd="FLASK_APP='broker.app:create_app()' flask check-duplicate-certs $DUPLICATE_CERTS_OUTPUT"
id=$(cf run-task "$APP_NAME" --command "$cmd" --name="check-duplicate-certs" | grep "task id:" | awk '{print $3}')

set +x
status=RUNNING
while [[ "$status" == 'RUNNING' ]]; do
  sleep 5
  status=$(cf tasks "$APP_NAME" | grep "^$id " | awk '{print $3}')
done
set -x

cf delete -r -f "$APP_NAME"

[[ "$status" == 'SUCCEEDED' ]] && exit 0
exit 1

#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit
set -x

cf api "$CF_API_URL"
(set +x; cf auth "$CF_USERNAME" "$CF_PASSWORD")
cf target -o "$CF_ORGANIZATION" -s "$CF_SPACE"

# dummy app so we can run a task.
cf push \
  -f src/manifests/app.yml \
  -p src \
  -i 1 \
  --var DB_NAME="$DB_NAME" \
  --var REDIS_NAME="$REDIS_NAME" \
  --var APP_NAME="$APP_NAME" \
  --var FLASK_ENV="$FLASK_APP" \
  --no-route \
  --health-check-type=none \
  -c "sleep 3600" \
  "$APP_NAME"

cmd="FLASK_APP=broker flask db upgrade"

# This is just to put logs in the concourse output.
(cf logs "$APP_NAME" | grep "TASK/db-upgrade") &

id=$(cf run-task "$APP_NAME" "$cmd" --name="db-upgrade" | grep "task id:" | awk '{print $3}')

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

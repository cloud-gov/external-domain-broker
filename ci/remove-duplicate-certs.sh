#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit
set -x

cf api "$CF_API_URL"
(set +x; cf auth "$CF_USERNAME" "$CF_PASSWORD")
cf target -o "$CF_ORGANIZATION" -s "$CF_SPACE"

# dummy app so we can run a task.
cf push \
  -f src2/manifests/remove-duplicate-certs.yml \
  -p src2 \
  -i 1 \
  --var DB_NAME="$DB_NAME" \
  --var APP_NAME="$APP_NAME" \
  --var FLASK_ENV="$FLASK_ENV" \
  --var DATABASE_ENCRYPTION_KEY="$DATABASE_ENCRYPTION_KEY" \
  --var AWS_GOVCLOUD_REGION="$AWS_GOVCLOUD_REGION" \
  --var AWS_GOVCLOUD_SECRET_ACCESS_KEY="$AWS_GOVCLOUD_SECRET_ACCESS_KEY" \
  --var AWS_GOVCLOUD_ACCESS_KEY_ID="$AWS_GOVCLOUD_ACCESS_KEY_ID" \
  --var ALB_LISTENER_ARNS="$ALB_LISTENER_ARNS" \
  --no-route \
  --health-check-type=process \
  -c "sleep 3600" \
  "$APP_NAME"

# This is just to put logs in the concourse output.
(cf logs "$APP_NAME" | grep "TASK/remove-duplicate-certs") &

cmd="FLASK_APP='broker.app:create_app()' flask remove-duplicate-certs"
id=$(cf run-task "$APP_NAME" --command "$cmd" --name="remove-duplicate-certs" | grep "task id:" | awk '{print $3}')

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

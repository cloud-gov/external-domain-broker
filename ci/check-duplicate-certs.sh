#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

cf api "$CF_API_URL"
(set +x; cf auth "$CF_USERNAME" "$CF_PASSWORD")
cf target -o "$CF_ORGANIZATION" -s "$CF_SPACE"

# dummy app so we can run a task.
cf push \
  -f src2/manifests/check-duplicate-certs.yml \
  -p src2 \
  -i 1 \
  --var DB_NAME="$DB_NAME" \
  --var APP_NAME="$APP_NAME" \
  --var FLASK_ENV="$FLASK_ENV" \
  --var DATABASE_ENCRYPTION_KEY="$DATABASE_ENCRYPTION_KEY" \
  --var ALB_LISTENER_ARNS="$ALB_LISTENER_ARNS" \
  --no-route \
  --health-check-type=process \
  -c "sleep 3600" \
  "$APP_NAME"

# This is just to put logs in the concourse output.
(cf logs "$APP_NAME" | grep "TASK/check-duplicate-certs") &

cmd="FLASK_APP='broker.app:create_app()' flask check-duplicate-certs"
id=$(cf run-task "$APP_NAME" --command "$cmd" --name="check-duplicate-certs" | grep "task id:" | awk '{print $3}')

status=RUNNING
while [[ "$status" == 'RUNNING' ]]; do
  sleep 5
  status=$(cf tasks "$APP_NAME" | grep "^$id " | awk '{print $3}')
  echo $status
done

DUPLICATE_CERTS_OUTPUT=$(mktemp)
cf logs "$APP_NAME" --recent | grep 'service_instance_duplicate_cert_count' | awk '{print $4 " " $5}' > "$DUPLICATE_CERTS_OUTPUT"
cat "$DUPLICATE_CERTS_OUTPUT"
curl --data-binary @- "${GATEWAY_HOST}:${GATEWAY_PORT:-9091}/metrics/job/domain_broker/instance/${ENVIRONMENT}" < "$DUPLICATE_CERTS_OUTPUT"

cf delete -r -f "$APP_NAME"

[[ "$status" == 'SUCCEEDED' ]] && exit 0
exit 1

#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit
set -x

cf api "$CF_API_URL"
(set +x; cf auth "$CF_USERNAME" "$CF_PASSWORD")
cf target -o "$CF_ORGANIZATION" -s "$CF_SPACE"

cmd="flask db upgrade"

# This is just to put logs in the concourse output.
(cf logs "$APP_NAME" | grep "TASK/db-upgrade") &

id=$(cf run-task "$APP_NAME" "$cmd" --name="db-upgrade" | grep "task id:" | awk '{print $3}')

status=RUNNING
while [[ "$status" == 'RUNNING' ]]; do
  sleep 5
  status=$(cf tasks "$APP_NAME" | grep "^$id " | awk '{print $3}')
done

exit "$([[ "$status" == 'SUCCEEDED' ]])"

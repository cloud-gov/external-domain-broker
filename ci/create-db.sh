#!/usr/bin/env bash

# Credit to https://gist.github.com/kelapure/ef79419796e35a68629a4e772e4646e4

set -euo pipefail
shopt -s inherit_errexit

# If the DB doesn't exist:
  # Create the DB
  # Wait for the DB

[[ -v app ]] || (echo "Must supply \$app"; exit 1)

cmd="flask db upgrade"
name="db-upgrade"

# This is just to put logs in the concourse output.
(cf logs "$app" | grep "TASK/$name") &

id=$(cf run-task "$app" "$cmd" | grep "task id:" | awk '{print $3}')

status=RUNNING
while [[ "$status" == 'RUNNING' ]]; do
  sleep 1
  status=$(cf tasks "$app" | grep "^$id " | awk '{print $3}')
done

exit "$([ "$status" = 'SUCCEEDED' ])"

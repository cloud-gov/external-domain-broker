#!/usr/bin/env bash

if [[ ! -v PGBASE ]]; then
  echo "Expected \$PGBASE to be defined in the Dockerfile"
  exit 2
fi

if ! pg_ctl --silent --log="$PGBASE/logs" start; then
  echo "Error starting postgres"
  exit 2
fi

exec "$@"

#!/usr/bin/env bash

set -euo pipefail

LOGS=${TMPDIR:-/app/logs}

if ! pgrep -x pebble > /dev/null; then
  echo "Starting Pebble"
  (
    cd /
    pebble \
      -config="/test/config/pebble-config.json" \
      -dnsserver="127.0.0.1:8053" \
      -strict \
      > "$LOGS/pebble.log" 2>&1 &
  )
fi

if ! pgrep -x pebble-challtestsrv > /dev/null; then
  echo "Starting Pebble Challenge Test Server"
  (
    cd /app
    pebble-challtestsrv \
      > "$LOGS/pebble-challtestsrv.log" 2>&1 &
  )
fi

if ! pgrep -x redis-server > /dev/null; then
  echo "Starting Redis"
  (
    cd /app
    redis-server tests/redis.conf \
      > "$LOGS/redis.log" 2>&1 &
  )
fi

#!/usr/bin/env bash

set -euo pipefail

if ! pgrep -x redis-server > /dev/null; then
  echo "Starting Redis"
  redis-server tests/redis.conf &
fi

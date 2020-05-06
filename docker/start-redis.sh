#!/usr/bin/env bash

set -euo pipefail

echo "Starting Redis"
redis-server tests/redis.conf &

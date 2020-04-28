#!/usr/bin/env bash

redis-server tests/redis.conf &

exec "$@"

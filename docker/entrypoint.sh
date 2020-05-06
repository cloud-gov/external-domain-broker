#!/usr/bin/env bash

/app/docker/start-redis.sh

exec "$@"

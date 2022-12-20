#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

export PYTHONPATH=$(dirname "$0")/..

# send logs to dev null, since we create other log handlers elsewhere
python src2/broker/alb_checks_consumer.py "$@" broker.alb_checks_consumer.huey

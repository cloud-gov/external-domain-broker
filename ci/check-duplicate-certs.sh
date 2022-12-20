#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

python -m pip install -r src2/requirements.txt

# python src2/broker/alb_checks_consumer.py "$@" broker.alb_checks_consumer.huey
export DUPLICATE_CERT_METRICS_FILEPATH=$(mktemp)

SRCPATH=$(dirname "$0")/..
export PYTHONPATH="$PYTHONPATH:$SRCPATH"

python src2/broker/alb_checks.py

cat "$DUPLICATE_CERT_METRICS_FILEPATH"

#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

python -m venv venv
source ./venv/bin/activate

python --version

python -m pip install -r src2/requirements.txt

# python src2/broker/alb_checks_consumer.py "$@" broker.alb_checks_consumer.huey
export DUPLICATE_CERT_METRICS_FILEPATH=$(mktemp)

export PYTHONPATH=$(dirname "$0")/..

python src2/broker/alb_checks.py

cat "$DUPLICATE_CERT_METRICS_FILEPATH"

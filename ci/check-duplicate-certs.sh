#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

export PYTHONPATH
export DUPLICATE_CERT_METRICS_FILEPATH

PYTHONPATH=$(dirname "$0")/..

pushd src2
  python -m venv venv
  source ./venv/bin/activate

  python --version

  python -m pip install -r requirements.txt

  # python src2/broker/alb_checks_consumer.py "$@" broker.alb_checks_consumer.huey
  DUPLICATE_CERT_METRICS_FILEPATH=$(mktemp)

  python broker/alb_checks.py

  cat "$DUPLICATE_CERT_METRICS_FILEPATH"
popd

#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

export PYTHONPATH
export DUPLICATE_CERT_METRICS_FILEPATH

pushd src2
  PYTHONPATH=$(pwd)
  echo "$PYTHONPATH"

  python -m venv venv
  source ./venv/bin/activate

  PYTHONPATH="$PYTHONPATH:$PYTHONPATH/venv/lib/python3.8/site-packages/"
  echo "$PYTHONPATH"

  python --version

  python -m pip install -r requirements.txt

  # python src2/broker/alb_checks_consumer.py "$@" broker.alb_checks_consumer.huey
  DUPLICATE_CERT_METRICS_FILEPATH=$(mktemp)

  python broker/alb_checks.py

  cat "$DUPLICATE_CERT_METRICS_FILEPATH"
popd

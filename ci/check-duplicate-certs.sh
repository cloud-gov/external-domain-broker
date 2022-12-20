#!/usr/bin/env bash

set -euo pipefail
shopt -s inherit_errexit

export PYTHONPATH=$(dirname "$0")/..

pip install -r src2/requirements.txt

python src2/broker/alb_checks_consumer.py "$@" broker.alb_checks_consumer.huey

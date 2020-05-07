#!/usr/bin/env bash

set -euo pipefail

export CUSTOM_COMPILE_COMMAND="./dev update-requirements"
echo "Compiling requirements.txt"
pip-compile \
  --quiet \
  --output-file=requirements.txt \
  pip-tools/requirements.in

echo "Compiling dev-requirements.txt"
pip-compile \
  --quiet \
  --output-file=pip-tools/dev-requirements.txt \
  pip-tools/dev-requirements.in

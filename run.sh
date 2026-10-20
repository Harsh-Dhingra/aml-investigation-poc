#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.lock
  .venv/bin/python -m pip install -e '.[dev]'
fi
if [[ $# -eq 0 ]]; then
  set -- serve
fi
if [[ "$1" == "serve" && ! -f kyc-dashboard/dist/index.html ]]; then
  npm ci --prefix kyc-dashboard
  NODE_DISABLE_COMPILE_CACHE=1 npm run build --prefix kyc-dashboard
fi
exec .venv/bin/python -m aml_poc.cli "$@"

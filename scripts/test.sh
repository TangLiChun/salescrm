#!/usr/bin/env bash
# Run the Pi test suite locally.
#   ./scripts/test.sh           lint + format check + pytest
#   ./scripts/test.sh --live    also run the opt-in real-DeepSeek smoke test
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

ruff check .
ruff format --check .

if [[ "${1:-}" == "--live" ]]; then
  PI_LIVE_LLM=1 pytest -q
else
  pytest -q
fi

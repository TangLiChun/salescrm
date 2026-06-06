#!/usr/bin/env bash
# Run the Pi test suite locally.
#   ./scripts/test.sh           lint + format check + pytest
#   ./scripts/test.sh --live    also run opt-in real-DeepSeek smoke + Pi harness
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

ruff check .
ruff format --check .

if [[ "${1:-}" == "--live" ]]; then
  PI_LIVE_LLM=1 pytest -q
  PI_LIVE_LLM=1 python scripts/pi_agent_harness.py \
    --min-pass-rate "${PI_HARNESS_MIN_PASS_RATE:-0.75}" \
    --show-events fail
else
  pytest -q
fi

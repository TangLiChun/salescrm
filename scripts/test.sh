#!/usr/bin/env bash
# Run the Pi test suite locally.
#   ./scripts/test.sh           lint + format check + pytest
#   ./scripts/test.sh --live    also run opt-in real-DeepSeek smoke + Pi harness
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_BIN="${PYTHON_BIN:-python}"
PYTEST_BIN="${PYTEST_BIN:-pytest}"
RUFF_BIN="${RUFF_BIN:-ruff}"
if [[ -x ".venv/bin/python" ]]; then PYTHON_BIN=".venv/bin/python"; fi
if [[ -x ".venv/bin/pytest" ]]; then PYTEST_BIN=".venv/bin/pytest"; fi
if [[ -x ".venv/bin/ruff" ]]; then RUFF_BIN=".venv/bin/ruff"; fi

"${RUFF_BIN}" check .
"${RUFF_BIN}" format --check .
npm run check:frontend

if [[ "${1:-}" == "--live" ]]; then
  PI_LIVE_LLM=1 "${PYTEST_BIN}" -q
  PI_LIVE_LLM=1 "${PYTHON_BIN}" scripts/pi_agent_harness.py \
    --min-pass-rate "${PI_HARNESS_MIN_PASS_RATE:-0.75}" \
    --show-events fail
else
  "${PYTEST_BIN}" -q
fi

# Pi Agent Harness

Pi agent harness runs the real Pi agent loop against the configured LLM while
replacing CRM/enrichment tools with deterministic canned results. It is designed
to catch commercial reliability regressions before they reach users:

- model replies with an intro but never calls a tool
- wrong first tool selection
- malformed or incomplete tool arguments
- forbidden tool usage
- blocked tool attempts from runtime commercial guardrails
- retries before acting
- stream ends without a clean `done`
- timeout or upstream error

The harness is live-LLM opt-in. Running without `--live` or `PI_LIVE_LLM=1`
does not call the network.

## Commands

List built-in scenarios:

```bash
.venv/bin/python scripts/pi_agent_harness.py --list
```

Run against DeepSeek and write artifacts:

```bash
PI_LIVE_LLM=1 \
LLM_API_KEY=sk-... \
LLM_BASE_URL=https://api.deepseek.com \
LLM_MODEL=deepseek-v4-flash \
.venv/bin/python scripts/pi_agent_harness.py \
  --repeat 3 \
  --timeout-seconds 240 \
  --jsonl artifacts/pi-harness.jsonl \
  --summary-json artifacts/pi-harness-summary.json
```

Replay a prior artifact without calling the LLM:

```bash
.venv/bin/python scripts/pi_agent_harness.py \
  --replay-jsonl artifacts/pi-harness.jsonl \
  --summary-json artifacts/pi-harness-summary.json
```

Run one scenario:

```bash
.venv/bin/python scripts/pi_agent_harness.py \
  --live \
  --scenario asn-roleemail-lookup
```

## Custom Scenarios

Custom scenarios are JSON. The top level can be a list or an object with a
`scenarios` list.

```json
{
  "scenarios": [
    {
      "name": "crm-google-search",
      "message": "列出库里 Google 相关联系人",
      "expect_tools": ["list_contacts"],
      "forbid_tools": ["web_search"],
      "arg_check": "list_contacts_non_empty",
      "max_retries": 0,
      "require_immediate": true,
      "fail_on_blocked_tools": true
    }
  ]
}
```

Run with custom scenarios:

```bash
.venv/bin/python scripts/pi_agent_harness.py \
  --live \
  --scenario-file docs/examples/pi-harness-scenarios.json
```

Supported `arg_check` names:

- `asn_text`: expected tool args contain ASN-like digits in `text` or `query`
- `list_contacts_non_empty`: `list_contacts` has a non-empty `q`
- `follow_up_status`: `follow_up_status` is one of the CRM enum values

`fail_on_blocked_tools` defaults to `true`. Keep it enabled for release gates:
a blocked tool means the runtime saved the turn, but the model still attempted a
commercially unsafe plan. Set it to `false` only for diagnostic scenarios where
you intentionally want to observe guardrail behavior without failing the run.

## CI Gate

Recommended CI command:

```bash
PI_LIVE_LLM=1 \
LLM_API_KEY="$LLM_API_KEY" \
LLM_BASE_URL=https://api.deepseek.com \
LLM_MODEL=deepseek-v4-flash \
  .venv/bin/python scripts/pi_agent_harness.py \
  --repeat 2 \
  --min-pass-rate 0.95 \
  --show-events fail \
  --jsonl artifacts/pi-harness.jsonl \
  --summary-json artifacts/pi-harness-summary.json
```

Use `--fail-fast` for fast feedback while editing prompts. Prefer full repeats
for release gates because tool-calling models can be slightly nondeterministic.

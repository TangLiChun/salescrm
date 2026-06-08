# Replace External Pi Coding Agent with DeepSeek-Reasonix — Design

**Date:** 2026-06-09
**Status:** Approved (brainstorming) → ready for implementation plan

## Goal

Replace the external **Pi Coding Agent** integration (`integrations/pi/`) with
[DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix) as the VPS-side
agent that drives Sales CRM lead import/discovery. Reasonix is a DeepSeek-native Go
terminal coding agent with a built-in `bash` tool and markdown **skills** support.

## Background & Scope

There are two distinct "Pi" things in this project. **Only the external one is in scope.**

| | In scope? |
|---|---|
| **External Pi Coding Agent** (`integrations/pi/`) — a separate Node CLI on the VPS that calls *into* the CRM via the Agent API to import scraped leads | **YES — being replaced** |
| **In-app "Pi 助手"** web chat (`app/pi_*.py`, `app/agent_chat.py`, `frontend/.../pi.ts`) — the browser-embedded assistant | **NO — untouched** |

### Key insight: the backend is agent-agnostic

Sales CRM exposes a small, Bearer-authenticated **Agent API** at `/api/agent/*`. This
HTTP surface plus the Agent Token (设置 → 自动化 → Agent API) is a **stable, agent-neutral
contract**. The only Pi-specific code is the client-side adapter package
(`integrations/pi/` — a pi-mono extension + skill + deploy glue).

Therefore: **no Python backend changes.** We swap only the client-side adapter layer.

### Chosen approach (decided during brainstorming)

- **Integration mechanism:** Skill + zero-dependency helper CLI. Reasonix calls the CLI
  through its built-in `bash` tool. **No MCP server**, no long-running process. (Reasonix
  *does* support MCP, but a skill + CLI is the lightest path and mirrors the existing
  pattern.)
- **pi handling:** **Full replacement** — delete `integrations/pi/` and the pi steps in
  `scripts/deploy.sh`.
- **Deploy automation:** **Full port** of the deploy.sh pi block to Reasonix.
- **Settings label:** rename the pi-specific **"Pi Agent API"** label to a neutral
  **"外部 Agent API / External Agent API"** (the API is generic; pi is gone).

## Non-Goals

- No change to the in-app "Pi 助手" web chat or `app/pi_*.py`.
- No change to the `/api/agent/*` endpoints, `app/agent_auth.py`, or the Agent Token
  generation/storage.
- Not configuring Reasonix's own DeepSeek model/credentials in deploy (handled by
  `reasonix setup` / the user; the pi deploy likewise never configured pi's LLM).
- No MCP server (explicitly rejected in favor of skill + CLI).

## Architecture

```
Reasonix (VPS terminal/desktop)
  └─ built-in `bash` tool ──► `salescrm` CLI (Python stdlib)
                                  └─ HTTP Bearer ──► Sales CRM  /api/agent/*  (UNCHANGED)
  └─ skill: skills/salescrm/SKILL.md  (tells the agent when/how to use the CLI)
```

Env contract (written by deploy into `${APP_DIR}/.reasonix-env`, sourced in `~/.bashrc`):
- `SALESCRM_URL` (default `http://127.0.0.1:8000`)
- `SALESCRM_TOKEN` (from 设置 → 自动化 → Agent API)

## Components

### 1. `integrations/reasonix/bin/salescrm` — helper CLI

Zero-dependency Python 3 script (stdlib only: `argparse`, `json`, `os`, `sys`,
`urllib.request`). Executable (`#!/usr/bin/env python3`, `chmod +x`). Structured as an
importable module (`main(argv) -> int`, plus small pure helpers) so it is unit-testable.

**Config:** reads `SALESCRM_URL` (default `http://127.0.0.1:8000`) and `SALESCRM_TOKEN`
(required; clear error + non-zero exit if missing). Sends
`Authorization: Bearer <token>` and `Content-Type: application/json`.

**Subcommands** (mirror the 4 Agent API endpoints exactly):

| Command | Endpoint | Notes |
|---|---|---|
| `salescrm health` | `GET /api/agent/health` | connectivity check |
| `salescrm contacts [--q S] [--status all\|sent\|unsent] [--follow-up S] [--limit N] [--offset N]` | `GET /api/agent/contacts` | defaults: status=all, limit=50, offset=0 |
| `salescrm import-leads [FILE\|-] [--source S]` | `POST /api/agent/leads/import` | reads JSON from FILE or stdin; accepts a bare `[...]` rows array or `{"rows":[...]}`; `--source` default `reasonix-agent` |
| `salescrm discover "<query>" [--min-score N] [--delay F] [--auto-import]` | `POST /api/agent/leads/discover` | defaults: min_score=60, delay=0.5, auto_import=false |

**Output:** success → pretty JSON (the endpoint's response body) to stdout, exit 0.
Failure (network, non-2xx, missing token, bad input) → concise message to **stderr** with
the HTTP status + server `detail` when present, exit non-zero. Validation bounds (e.g.
`limit` 1–500, `min_score` 0–100) are enforced server-side; the CLI passes values through
and surfaces the server's 4xx detail rather than duplicating bounds.

### 2. `integrations/reasonix/skills/salescrm/SKILL.md` — Reasonix skill

Markdown with frontmatter (`name`, `description`) ported from the pi skill. Body:
- CRM runs at `$SALESCRM_URL`; auth via Agent Token (not browser login).
- Setup steps (regenerate token in UI, export env vars).
- Subcommand reference table (the CLI above) and **when to use each** (e.g. run
  `salescrm health` before a long scrape; `import-leads` after producing a rows JSON;
  `discover` for AI lead discovery).
- The lead-import workflow (scrape/produce rows → `salescrm import-leads`).

Loaded via Reasonix `[skills] paths` pointing at this directory.

### 3. `integrations/reasonix/reasonix.toml.example` — sample config

Documents the integration-relevant config:
```toml
[skills]
paths = ["/opt/salescrm/integrations/reasonix/skills"]
```
Plus commented notes: ensure the `salescrm` CLI is on `PATH` (deploy symlinks it to
`/usr/local/bin`), and that the user supplies their own DeepSeek model/credentials via
`reasonix setup` (out of scope for this integration).

### 4. `integrations/reasonix/README.md`

Setup/install guide replacing the pi README: regenerate token → export
`SALESCRM_URL`/`SALESCRM_TOKEN` → install Reasonix (`npm i -g reasonix`, prebuilt-binary
fallback) → register the skills path + CLI on PATH → verify with `salescrm health`.

### 5. `scripts/deploy.sh` — port pi block → reasonix

Replace the pi automation (currently ~L475–598, `SKIP_PI`) with Reasonix equivalents:
- Read the Agent Token from the container; write `${APP_DIR}/.reasonix-env`
  (`export SALESCRM_URL=...`, `export SALESCRM_TOKEN=...`).
- Source `.reasonix-env` from `~/.bashrc` (idempotent marker, replacing the pi marker).
- Install Reasonix: `npm i -g reasonix` (with a fallback note for prebuilt binaries).
- Symlink `${APP_DIR}/integrations/reasonix/bin/salescrm` → `/usr/local/bin/salescrm`.
- Merge/write the skills path into the Reasonix config.
- Validate with `salescrm health` (or the existing health curl).
- Rename the gate `SKIP_PI` → `SKIP_REASONIX`; update the final summary/verify lines.

### 6. Delete `integrations/pi/`

Remove the entire directory: `README.md`, `package.json`, `extensions/salescrm.ts`,
`skills/salescrm/SKILL.md`.

### 7. Settings label rename (pi → neutral)

The settings section labelled **"Pi Agent API"** (and its description/strings) now
misnames a generic API. Rename to neutral copy (e.g. **"外部 Agent API" / "External Agent
API"**, **"Agent Token"** already neutral). Touch points:
- `frontend/src/i18n.ts` (zh + en) — the relevant `settings.*` keys.
- `app/static/index.html` if any inline default text references "Pi".
- Rebuild frontend artifacts (`app/static/i18n.js`, etc.).
- **Does not** touch the in-app "Pi 助手" nav/chat strings.

### 8. Tests — `tests/test_reasonix_cli.py`

Unit tests in the repo's style (stdlib, no real network/DB): import the CLI module,
monkeypatch its HTTP call (e.g. the `urllib.request.urlopen`/opener), and assert:
- argument parsing → correct method/URL/path/query/body per subcommand;
- `Authorization: Bearer` header and base-URL/default handling;
- missing-token error path (non-zero exit, message);
- `import-leads` reads both `[...]` and `{"rows":[...]}` from file and stdin;
- HTTP-error path surfaces status + `detail`.

## Documentation touch-ups

- Top-level `README.md`: update any references to the Pi Coding Agent integration to
  point at Reasonix (`integrations/reasonix/`). Leave in-app "Pi 助手" references intact.

## Verification

Mirror CI before each commit:
```
ruff check . && ruff format --check . && pytest -q && npm run check:frontend
```
- The new CLI is covered by `tests/test_reasonix_cli.py` and adds **no runtime
  dependency** (stdlib only).
- `npm run check:frontend` + built-artifact diff apply when component 7 (label rename)
  touches the frontend; rebuild artifacts before committing TS/i18n changes.
- `scripts/deploy.sh` is shell — sanity-check with `bash -n scripts/deploy.sh` (and
  `shellcheck` if available); not exercised by pytest.

## Rollout / Rollback

- Backend unchanged → zero API/runtime risk to the running CRM.
- Rollback = `git revert` the integration commits; the Agent API/token are untouched, so
  reverting restores the pi files without data migration.

## File Structure

**Create:**
- `integrations/reasonix/bin/salescrm`
- `integrations/reasonix/skills/salescrm/SKILL.md`
- `integrations/reasonix/reasonix.toml.example`
- `integrations/reasonix/README.md`
- `tests/test_reasonix_cli.py`

**Modify:**
- `scripts/deploy.sh` (pi block → reasonix; `SKIP_PI` → `SKIP_REASONIX`)
- `frontend/src/i18n.ts` (+ rebuilt `app/static/i18n.js`) — label rename
- `app/static/index.html` (only if inline "Pi Agent API" default text exists) + rebuilt artifacts
- `README.md` (integration references)

**Delete:**
- `integrations/pi/` (entire directory)

**Unchanged (explicitly):**
- `app/agent_routes.py`, `app/agent_auth.py`, the Agent Token mechanism, all `app/pi_*.py`
  and the in-app "Pi 助手".

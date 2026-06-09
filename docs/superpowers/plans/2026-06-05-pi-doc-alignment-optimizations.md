# Pi 文档对齐优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align Sales CRM Pi agent with [how-pi-agent-works](https://how-pi-agent-works.vercel.app/) engineering practices: parallel fallback, live parallel progress, overflow compress-retry, turn-aware compaction, branch summary on fork, and fork UX.

**Architecture:** Shared helpers in `app/pi_context.py` (overflow detection, turn boundaries, branch summary). Python `agent_chat.py` mirrors TS `agentLoop.ts` for parallel batches. Overflow recovery via `POST /api/internal/pi/recover-overflow` + one retry in both runtimes. Fork stores `parent_thread_id` and optional branch-summary text.

**Tech Stack:** Python 3.13, FastAPI, TypeScript pi-agent sidecar, pytest, frontend tsc.

---

## Task 1: Shared compression & overflow helpers

**Files:**
- Modify: `app/pi_context.py`
- Create: `tests/test_pi_compression_boundaries.py`

- [x] Add `is_context_overflow_error(message)`
- [x] Add `next_compression_batch_end(history, through, batch_size, max_end)`
- [x] Add `summarize_branch_suffix(batch)`
- [x] Tests for cut boundaries and overflow patterns

## Task 2: Turn-aware compaction + fork branch summary

**Files:**
- Modify: `app/pi_chat_store.py`, `app/database.py`
- Modify: `tests/test_pi_fork.py`

- [x] Use `next_compression_batch_end` in `maybe_compress_thread_context`
- [x] `fork_pi_thread`: branch summary for `history[end:]`, set `parent_thread_id`
- [x] DB migration `parent_thread_id TEXT NULL`

## Task 3: Overflow recover internal API

**Files:**
- Modify: `app/pi_internal_routes.py`
- Modify: `services/pi-agent/src/pythonClient.ts`

- [x] `POST /recover-overflow` → compress + `prepare_pi_turn`

## Task 4: TS parallel progress + overflow retry

**Files:**
- Modify: `services/pi-agent/src/agentLoop.ts`

- [x] Parallel batch drains progress queues while `Promise.all` runs
- [x] On overflow LLM error with `threadId`, call recover once and retry stream

## Task 5: Python parallel tools + overflow retry

**Files:**
- Modify: `app/agent_chat.py`
- Create: `tests/test_agent_chat_parallel.py` (unit with mocks)

- [x] Parallel safe batch via `asyncio.gather` + ordered writeback
- [x] Overflow compress-retry when `thread_id` set

## Task 6: Fork UX + docs

**Files:**
- Modify: `frontend/src/js/modules/pi.ts`, `app/main.py` (thread list fields)
- Modify: `docs/pi-agent-ts-service.md`

- [x] Thread list shows branch marker when `parent_thread_id` or title prefix
- [x] Update sidecar/background jobs documentation

## Task 7: Verify

- [x] `uv run pytest -q`
- [x] `npm run build:frontend` + `cd services/pi-agent && npm run build`

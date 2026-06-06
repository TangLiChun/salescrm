# Pi Reliability + Test Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Pi agent reliable and regression-proof by extracting its decision logic into a pure, fully-tested state machine, replacing fake streaming with a true-streaming httpx LLM client with retries, and standing up a pytest + ruff + GitHub Actions test foundation driven by a FakeLLM.

**Architecture:** Approach B (targeted extraction). Keep `app/agent_chat.py` as the agent-loop driver + public facade (callers unchanged). Extract pure helpers and the turn-decision logic into focused `app/pi_*.py` modules. Add dependency-injection seams (`llm_client`, `tool_runner`) so the agent loop is testable without network or DB. Characterize current behavior before refactoring; keep CI green at every step.

**Tech Stack:** Python 3.12 (prod runtime), FastAPI, Postgres (psycopg), DeepSeek V4 (OpenAI-compatible), httpx (new), pytest + pytest-asyncio, ruff, GitHub Actions.

**Spec:** [docs/superpowers/specs/2026-06-06-pi-agent-reliability-test-foundation-design.md](../specs/2026-06-06-pi-agent-reliability-test-foundation-design.md)

**Conventions for this plan:**
- All commits omit a trailing co-author line here; the executor appends the repo's standard `Co-Authored-By` line.
- "Extract verbatim" = move the named function/constant unchanged to the new module, then re-import it back into `agent_chat.py` (or `llm.py`) so existing references and the public facade keep working.
- Run all test commands from repo root `/Users/tlc/Documents/salescrm`.

---

## Phase A — Test Foundation (no business-logic changes)

### Task 1: Project + dependency config

**Files:**
- Create: `pyproject.toml`
- Create: `requirements-dev.txt`
- Modify: `requirements.txt`

- [ ] **Step 1: Add httpx to production deps**

Append to `requirements.txt`:

```
httpx>=0.27.0
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
ruff>=0.6.0
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501", "B008"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["B"]
```

- [ ] **Step 4: Install dev deps**

Run: `python -m pip install -r requirements-dev.txt`
Expected: installs pytest, pytest-asyncio, ruff, httpx without errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements-dev.txt requirements.txt
git commit -m "build: add pytest/ruff/httpx tooling config"
```

---

### Task 2: Adopt ruff formatting repo-wide (isolated mechanical commit)

**Files:** all tracked `.py` files (mechanical formatting only).

> This is a one-time, large-but-mechanical diff so CI's `ruff format --check` can pass. Keep it in its own commit, separate from any logic change. Review the diff is whitespace/wrapping only.

- [ ] **Step 1: See what lint issues exist**

Run: `ruff check .`
Note any real errors (unused imports, etc.). If any are non-mechanical, fix them in a separate follow-up commit, not here.

- [ ] **Step 2: Auto-fix safe lint issues**

Run: `ruff check --fix .`
Expected: import sorting and trivially-safe fixes applied.

- [ ] **Step 3: Format the repo**

Run: `ruff format .`
Expected: reports N files reformatted.

- [ ] **Step 4: Sanity check the app still imports**

Run: `python -c "from app.agent_chat import agent_chat_stream; from app.database import init_db; print('import ok')"`
Expected: prints `import ok`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "style: adopt ruff format + import sorting repo-wide"
```

---

### Task 3: Tests scaffold + first passing test

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Create `tests/__init__.py`** (empty file)

- [ ] **Step 2: Create `tests/conftest.py`**

```python
"""Shared test fixtures and async helpers."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


async def collect_events(stream: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drain an agent event stream into a list for assertions."""
    events: list[dict[str, Any]] = []
    async for event in stream:
        events.append(event)
    return events


def event_types(events: list[dict[str, Any]]) -> list[str]:
    return [str(e.get("type")) for e in events]


def assistant_text(events: list[dict[str, Any]]) -> str:
    """Concatenate all assistant_done texts (final visible reply)."""
    return "".join(
        str(e.get("text") or "") for e in events if e.get("type") == "assistant_done"
    )
```

- [ ] **Step 3: Create `tests/test_smoke.py`**

```python
from tests.conftest import collect_events, event_types


def test_pytest_runs():
    assert True


def test_helpers_importable():
    assert callable(collect_events)
    assert callable(event_types)
```

- [ ] **Step 4: Run tests**

Run: `pytest -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: scaffold pytest with async event helpers"
```

---

### Task 4: FakeLLM test double + builders

**Files:**
- Create: `tests/fake_llm.py`
- Create: `tests/test_fake_llm.py`

- [ ] **Step 1: Write the failing test**

`tests/test_fake_llm.py`:

```python
import pytest

from tests.conftest import collect_events
from tests.fake_llm import FakeLLM, content_message, error_response, tool_call


@pytest.mark.asyncio
async def test_fake_llm_yields_scripted_text():
    fake = FakeLLM([content_message("你好")])
    events = await collect_events(fake(messages=[], tools=None))
    assert {"type": "content_delta", "text": "你好"} in events
    msg = [e for e in events if e["type"] == "message"][0]["message"]
    assert msg["content"] == "你好"
    assert "tool_calls" not in msg


@pytest.mark.asyncio
async def test_fake_llm_yields_tool_calls():
    fake = FakeLLM([content_message("查一下", tool_calls=[tool_call("list_contacts", {"q": "isp"})])])
    events = await collect_events(fake(messages=[], tools=None))
    msg = [e for e in events if e["type"] == "message"][0]["message"]
    assert msg["tool_calls"][0]["function"]["name"] == "list_contacts"


@pytest.mark.asyncio
async def test_fake_llm_advances_per_call_and_records():
    fake = FakeLLM([content_message("first"), content_message("second")])
    await collect_events(fake(messages=[{"role": "user", "content": "hi"}], tools=None))
    second = await collect_events(fake(messages=[], tools=None, tool_choice="required"))
    assert [e for e in second if e["type"] == "message"][0]["message"]["content"] == "second"
    assert len(fake.calls) == 2
    assert fake.calls[1]["tool_choice"] == "required"


@pytest.mark.asyncio
async def test_fake_llm_error_response():
    fake = FakeLLM([error_response("boom")])
    events = await collect_events(fake(messages=[], tools=None))
    assert events == [{"type": "error", "message": "boom"}]


@pytest.mark.asyncio
async def test_fake_llm_runs_out_of_script():
    fake = FakeLLM([content_message("only one")])
    await collect_events(fake(messages=[], tools=None))
    with pytest.raises(AssertionError):
        await collect_events(fake(messages=[], tools=None))
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_fake_llm.py -q`
Expected: FAIL (`ModuleNotFoundError: tests.fake_llm`).

- [ ] **Step 3: Implement `tests/fake_llm.py`**

```python
"""A scriptable stand-in for the streaming LLM client used by agent_chat_stream.

Each element passed to FakeLLM is one *response* (a list of event dicts) returned
on successive calls, mirroring app.agent_chat._iter_llm_stream's event contract:
content_delta / status / message / error.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


def tool_call(name: str, arguments: dict[str, Any], call_id: str | None = None) -> dict[str, Any]:
    return {
        "id": call_id or f"call_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


def content_message(
    text: str = "",
    *,
    tool_calls: list[dict[str, Any]] | None = None,
    reasoning: str | None = None,
    stream_text: bool = True,
) -> list[dict[str, Any]]:
    """Build one scripted response: optional streamed content + final message event."""
    events: list[dict[str, Any]] = []
    if text and stream_text:
        events.append({"type": "content_delta", "text": text})
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if reasoning:
        message["reasoning_content"] = reasoning
    if tool_calls:
        message["tool_calls"] = tool_calls
    events.append({"type": "message", "message": message})
    return events


def error_response(message: str) -> list[dict[str, Any]]:
    return [{"type": "error", "message": message}]


class FakeLLM:
    """Callable matching agent_chat's injected llm_client signature."""

    def __init__(self, responses: list[list[dict[str, Any]]]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        tool_choice: Any = None,
    ) -> AsyncIterator[dict[str, Any]]:
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        assert self._index < len(self._responses), "FakeLLM ran out of scripted responses"
        response = self._responses[self._index]
        self._index += 1

        async def _gen() -> AsyncIterator[dict[str, Any]]:
            for event in response:
                yield event

        return _gen()
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_fake_llm.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/fake_llm.py tests/test_fake_llm.py
git commit -m "test: add scriptable FakeLLM double for agent-loop tests"
```

---

### Task 5: CI workflow + local test script

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `scripts/test.sh`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: salescrm
          POSTGRES_PASSWORD: salescrm
          POSTGRES_DB: salescrm_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      DATABASE_URL: postgresql://salescrm:salescrm@localhost:5432/salescrm_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        run: python -m pip install -r requirements-dev.txt
      - name: Lint
        run: ruff check .
      - name: Format check
        run: ruff format --check .
      - name: Test
        run: pytest -q
```

- [ ] **Step 2: Create `scripts/test.sh`**

```bash
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
```

- [ ] **Step 3: Make it executable + run it**

Run: `chmod +x scripts/test.sh && ./scripts/test.sh`
Expected: ruff passes, pytest passes (7 tests so far).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml scripts/test.sh
git commit -m "ci: add GitHub Actions workflow and local test.sh"
```

---

## Phase B — Injection seam + characterization net

### Task 6: Add `llm_client` / `tool_runner` injection seams (behavior-preserving)

**Files:**
- Modify: `app/agent_chat.py` (`agent_chat_stream` signature + the two call sites; `_stream_text_reply`)

- [ ] **Step 1: Add seam parameters to `agent_chat_stream`**

In `app/agent_chat.py`, change the signature ([agent_chat.py:1950-1957](../../../app/agent_chat.py)) to add two keyword-only params with defaults that preserve current behavior:

```python
async def agent_chat_stream(
    user_id: int,
    message: str,
    history: list[dict[str, str]] | None = None,
    *,
    thread_id: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
    llm_client: Callable[..., AsyncIterator[dict[str, Any]]] | None = None,
    tool_runner: Callable[..., Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
```

Immediately after the first `yield {"type": "status", ...}` line, bind defaults:

```python
    llm_client = llm_client or _iter_llm_stream
    tool_runner = tool_runner or _run_tool
```

- [ ] **Step 2: Route the LLM call site through the seam**

Replace the call `async for event in _iter_llm_stream(messages, AGENT_TOOLS, tool_choice=tool_choice):` ([agent_chat.py:2035](../../../app/agent_chat.py)) with:

```python
            async for event in llm_client(messages, AGENT_TOOLS, tool_choice=tool_choice):
```

- [ ] **Step 3: Route the round-cap summary through the seam**

`_stream_text_reply` ([agent_chat.py:1930](../../../app/agent_chat.py)) currently calls `_iter_llm_stream` internally. Add an optional client param:

```python
async def _stream_text_reply(
    messages: list[dict[str, Any]],
    llm_client: Callable[..., AsyncIterator[dict[str, Any]]] | None = None,
) -> tuple[str, bool]:
    client = llm_client or _iter_llm_stream
    ...
    async for event in client(messages, None):
```

And at the round-cap call site ([agent_chat.py:2258](../../../app/agent_chat.py)) pass it: `final_text, ok = await _stream_text_reply(messages, llm_client)`.

- [ ] **Step 4: Route the tool worker through the seam**

In the tool worker ([agent_chat.py:2215](../../../app/agent_chat.py)), replace `result_holder["value"] = await _run_tool(user_id, name, args, emitter)` with:

```python
                    result_holder["value"] = await tool_runner(user_id, name, args, emitter)
```

- [ ] **Step 5: Verify the app still imports and unit tests pass**

Run: `python -c "from app.agent_chat import agent_chat_stream; print('ok')" && pytest -q`
Expected: `ok`, all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/agent_chat.py
git commit -m "refactor: add llm_client/tool_runner injection seams to agent_chat_stream"
```

---

### Task 7: Characterization tests for the agent loop

**Files:**
- Create: `tests/test_agent_loop_characterization.py`

> These lock current observable behavior of `agent_chat_stream` before any extraction. They use the seams (FakeLLM + a fake tool_runner) so they never touch the network or DB. `thread_id=None` so no persistence/compression runs.

- [ ] **Step 1: Write the characterization tests**

`tests/test_agent_loop_characterization.py`:

```python
import pytest

from app.agent_chat import agent_chat_stream
from tests.conftest import assistant_text, collect_events, event_types
from tests.fake_llm import FakeLLM, content_message, tool_call


async def _noop_tools(user_id, name, args, emit):
    return {"ok": True, "name": name, "echo_args": args}


@pytest.mark.asyncio
async def test_plain_text_reply_no_tools():
    fake = FakeLLM([content_message("这是直接回答。")])
    events = await collect_events(
        agent_chat_stream(1, "你好", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert "这是直接回答。" in assistant_text(events)
    assert event_types(events)[-1] == "done"
    assert not any(e["type"] == "tool_start" for e in events)


@pytest.mark.asyncio
async def test_single_tool_then_summary():
    async def tools(user_id, name, args, emit):
        return {"contacts": [{"id": 1, "email": "a@b.com"}], "total": 1}

    fake = FakeLLM([
        content_message("我来查一下", tool_calls=[tool_call("list_contacts", {"q": "isp"})]),
        content_message("找到 1 个联系人。"),
    ])
    events = await collect_events(
        agent_chat_stream(1, "找 isp 联系人", [], llm_client=fake, tool_runner=tools)
    )
    types = event_types(events)
    assert "tool_start" in types
    assert "tool_result" in types
    assert "找到 1 个联系人。" in assistant_text(events)
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_intro_only_then_recovers_with_tool():
    # First reply is intro-only ("让我查一下"); loop must nudge, second reply calls a tool.
    fake = FakeLLM([
        content_message("让我查一下"),
        content_message("好的", tool_calls=[tool_call("list_contacts", {"q": ""})]),
        content_message("已为你列出联系人。"),
    ])
    events = await collect_events(
        agent_chat_stream(1, "列出联系人", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert any(e["type"] == "tool_start" for e in events)
    assert event_types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_error_from_llm_surfaces_and_finishes():
    from tests.fake_llm import error_response

    fake = FakeLLM([error_response("LLM 请求失败 (500)")])
    events = await collect_events(
        agent_chat_stream(1, "x", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert any(e["type"] == "error" for e in events)
    assert event_types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_tool_json_not_leaked_into_assistant_bubble():
    # Model emits tool JSON as content with no tool_calls field; must not show raw JSON to user.
    fake = FakeLLM([
        content_message('{"name": "list_contacts", "arguments": {"q": "isp"}}'),
        content_message("完成。"),
    ])
    events = await collect_events(
        agent_chat_stream(1, "找联系人", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert '"arguments"' not in assistant_text(events)
```

- [ ] **Step 2: Run the characterization tests**

Run: `pytest tests/test_agent_loop_characterization.py -q`
Expected: all pass. If any fails, it documents current behavior — adjust the assertion to match what the loop actually emits today (the point is to lock current behavior, not to fix it yet). Record any surprising behavior in the test as a comment.

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_loop_characterization.py
git commit -m "test: characterize agent_chat_stream behavior before refactor"
```

---

## Phase C — Extract pure modules (under the characterization net)

### Task 8: Extract the SSE/stream parser

**Files:**
- Create: `app/pi_stream_parser.py`
- Modify: `app/llm.py`
- Create: `tests/test_stream_parser.py`

- [ ] **Step 1: Create `app/pi_stream_parser.py` by moving parser functions verbatim**

Move these four functions **unchanged** from `app/llm.py` into `app/pi_stream_parser.py` (keep their bodies exactly; add `from __future__ import annotations`, `import json`, `from typing import Any` at top): `_merge_tool_call_delta` ([llm.py:92-125](../../../app/llm.py)), `_apply_complete_message` ([llm.py:128-174](../../../app/llm.py)), `_parse_sse_or_json_lines` ([llm.py:177-199](../../../app/llm.py)), `_consume_stream_chunk` ([llm.py:202-242](../../../app/llm.py)). Rename to public names (drop leading underscore): `merge_tool_call_delta`, `apply_complete_message`, `parse_sse_or_json_lines`, `consume_stream_chunk`.

- [ ] **Step 2: Add a per-line SSE parser (new, for true streaming later)**

Append to `app/pi_stream_parser.py`:

```python
def parse_sse_line(line: str) -> dict[str, Any] | None:
    """Parse one SSE/JSONL line into a chunk dict, or None to skip."""
    line = (line or "").strip()
    if not line or line == "data: [DONE]":
        return None
    payload = line[5:].strip() if line.startswith("data:") else line
    if not payload or payload == "[DONE]":
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def assemble_message(
    content_parts: list[str],
    reasoning_parts: list[str],
    tool_calls: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the final assistant message from accumulated stream state."""
    import uuid

    message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts) or None}
    if reasoning_parts:
        message["reasoning_content"] = "".join(reasoning_parts)
    assembled: list[dict[str, Any]] = []
    for index in sorted(tool_calls):
        slot = tool_calls[index]
        fn = slot.get("function") or {}
        name = (fn.get("name") or "").strip()
        args = (fn.get("arguments") or "").strip()
        if not name and not args:
            continue
        if not slot.get("id"):
            slot["id"] = f"call_{uuid.uuid4().hex[:12]}"
        assembled.append(slot)
    if assembled:
        message["tool_calls"] = assembled
    return message
```

- [ ] **Step 3: Re-wire `app/llm.py` to import from the new module**

In `app/llm.py`, delete the four moved function definitions and add at the top:

```python
from app.pi_stream_parser import (
    apply_complete_message as _apply_complete_message,
    consume_stream_chunk as _consume_stream_chunk,
    merge_tool_call_delta as _merge_tool_call_delta,
    parse_sse_or_json_lines as _parse_sse_or_json_lines,
)
```

(Keeping the underscore aliases means the rest of `llm.py` is unchanged.)

- [ ] **Step 4: Write tests for the parser**

`tests/test_stream_parser.py`:

```python
from app.pi_stream_parser import (
    assemble_message,
    consume_stream_chunk,
    merge_tool_call_delta,
    parse_sse_line,
    parse_sse_or_json_lines,
)


def _consume(chunk):
    content, reasoning, tools, emitted = [], [], {}, [False]
    events = consume_stream_chunk(
        chunk,
        content_parts=content,
        reasoning_parts=reasoning,
        tool_calls=tools,
        emit_content_delta=True,
        tool_status_emitted=emitted,
    )
    return content, reasoning, tools, events


def test_content_delta_emitted():
    content, _, _, events = _consume({"choices": [{"delta": {"content": "hi"}}]})
    assert content == ["hi"]
    assert {"type": "content_delta", "text": "hi"} in events


def test_tool_call_delta_accumulates_arguments():
    tools = {}
    merge_tool_call_delta(tools, {"index": 0, "id": "c1", "function": {"name": "list_contacts"}})
    merge_tool_call_delta(tools, {"index": 0, "function": {"arguments": '{"q":'}})
    merge_tool_call_delta(tools, {"index": 0, "function": {"arguments": ' "isp"}'}})
    assert tools[0]["function"]["name"] == "list_contacts"
    assert tools[0]["function"]["arguments"] == '{"q": "isp"}'


def test_assemble_message_drops_empty_tool_slots():
    tools = {0: {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}}
    msg = assemble_message(["hello"], [], tools)
    assert msg["content"] == "hello"
    assert "tool_calls" not in msg


def test_assemble_message_assigns_missing_id():
    tools = {0: {"id": "", "type": "function", "function": {"name": "x", "arguments": "{}"}}}
    msg = assemble_message([], [], tools)
    assert msg["tool_calls"][0]["id"].startswith("call_")


def test_parse_sse_line():
    assert parse_sse_line("data: [DONE]") is None
    assert parse_sse_line("") is None
    assert parse_sse_line('data: {"a": 1}') == {"a": 1}
    assert parse_sse_line('{"b": 2}') == {"b": 2}


def test_parse_sse_or_json_lines_fallback_to_single_json():
    body = b'{"choices": [{"message": {"content": "hi"}}]}'
    chunks = parse_sse_or_json_lines(body)
    assert chunks and chunks[0]["choices"][0]["message"]["content"] == "hi"
```

- [ ] **Step 5: Run tests + app import**

Run: `python -c "import app.llm" && pytest tests/test_stream_parser.py tests/test_agent_loop_characterization.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/pi_stream_parser.py app/llm.py tests/test_stream_parser.py
git commit -m "refactor: extract SSE stream parser into pi_stream_parser with tests"
```

---

### Task 9: Extract tool-call parsing/recovery

**Files:**
- Create: `app/pi_tool_calls.py`
- Modify: `app/agent_chat.py`
- Create: `tests/test_tool_calls.py`

- [ ] **Step 1: Create `app/pi_tool_calls.py`**

Move these functions/constants **verbatim** from `app/agent_chat.py` into the new module: `KNOWN_TOOL_NAMES` ([agent_chat.py:66-94](../../../app/agent_chat.py)), `_TOOL_NAME_ALIASES` ([agent_chat.py:1067-1074](../../../app/agent_chat.py)), `_normalize_tool_name`, `_infer_tool_name`, `_coerce_list_contacts_args`, `_normalize_raw_tool_entry`, `_extract_tool_calls_from_content`, `_parse_tool_call`, `_ensure_tool_call_id`, `_prepare_tool_calls` ([agent_chat.py:1161-1374](../../../app/agent_chat.py)), and `_extract_json_args` ([agent_chat.py:911-928](../../../app/agent_chat.py)). Add module header `from __future__ import annotations`, `import json`, `import re`, `import uuid`, `from typing import Any`. Keep names as-is (with underscores) — they are internal helpers.

- [ ] **Step 2: Re-import them back into `agent_chat.py`**

In `app/agent_chat.py`, delete the moved definitions and add:

```python
from app.pi_tool_calls import (
    KNOWN_TOOL_NAMES,
    _coerce_list_contacts_args,
    _ensure_tool_call_id,
    _extract_json_args,
    _extract_tool_calls_from_content,
    _infer_tool_name,
    _normalize_raw_tool_entry,
    _normalize_tool_name,
    _parse_tool_call,
    _prepare_tool_calls,
)
```

Note: `_extract_json_args` is also used by `_parse_inline_tool_calls` (stays in agent_chat for now) and `KNOWN_TOOL_NAMES` is referenced by `pi_context`/`_run_tool` — the import keeps those working.

- [ ] **Step 3: Write tests**

`tests/test_tool_calls.py`:

```python
from app.pi_tool_calls import (
    _extract_tool_calls_from_content,
    _infer_tool_name,
    _parse_tool_call,
    _prepare_tool_calls,
)


def test_infer_tool_name_from_aliases():
    assert _infer_tool_name("search_contacts", {}) == "list_contacts"
    assert _infer_tool_name("functions.list_contacts", {}) == "list_contacts"


def test_infer_tool_name_from_args_shape():
    assert _infer_tool_name("", {"rows": []}) == "import_leads"
    assert _infer_tool_name("", {"text": "AS123"}) == "lookup_asns"
    assert _infer_tool_name("", {"contact_id": 5, "auto_import": True}) == "enrich_contact"


def test_parse_tool_call_valid():
    parsed = _parse_tool_call(
        {"function": {"name": "list_contacts", "arguments": '{"q": "isp"}'}}
    )
    assert parsed == ("list_contacts", {"q": "isp"})


def test_parse_tool_call_unknown_returns_none():
    assert _parse_tool_call({"function": {"name": "totally_made_up", "arguments": "{}"}}) is None


def test_parse_tool_call_nested_json_in_arguments():
    parsed = _parse_tool_call(
        {"function": {"name": "", "arguments": '{"name": "list_contacts", "arguments": {"q": "x"}}'}}
    )
    assert parsed == ("list_contacts", {"q": "x"})


def test_prepare_tool_calls_drops_invalid_keeps_valid():
    prepared = _prepare_tool_calls([
        {"function": {"name": "list_contacts", "arguments": '{"q": "a"}'}},
        {"function": {"name": "garbage", "arguments": "{}"}},
        "not-a-dict",
    ])
    names = [name for _, name, _ in prepared]
    assert names == ["list_contacts"]
    assert prepared[0][0]["id"]  # id ensured


def test_extract_tool_calls_from_content_json_array():
    text = 'sure: [{"name": "list_contacts", "arguments": {"q": "isp"}}]'
    calls = _extract_tool_calls_from_content(text)
    assert calls[0]["function"]["name"] == "list_contacts"
```

- [ ] **Step 4: Run tests + import + characterization**

Run: `python -c "import app.agent_chat" && pytest tests/test_tool_calls.py tests/test_agent_loop_characterization.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/pi_tool_calls.py app/agent_chat.py tests/test_tool_calls.py
git commit -m "refactor: extract tool-call parsing/recovery into pi_tool_calls with tests"
```

---

### Task 10: Extract reply heuristics

**Files:**
- Create: `app/pi_reply_heuristics.py`
- Modify: `app/agent_chat.py`
- Create: `tests/test_reply_heuristics.py`

- [ ] **Step 1: Create `app/pi_reply_heuristics.py`**

Move **verbatim** from `app/agent_chat.py`: `_TOOL_CONTENT_MARKERS` ([agent_chat.py:731-749](../../../app/agent_chat.py)), `_assistant_intro_before_tools`, `_content_looks_like_tool_call`, `_content_is_tool_json_fragment`, `_meaningful_assistant_content`, `_assistant_promises_tool_use`, `_user_requests_continuation`, `_infer_continuation_query`, `_make_discover_fallback_call` ([agent_chat.py:752-908](../../../app/agent_chat.py)). Also move `_parse_inline_tool_calls` ([agent_chat.py:1388-1411](../../../app/agent_chat.py)) and `_fallback_prepared_calls` ([agent_chat.py:1094-1158](../../../app/agent_chat.py)) and the three nudge constants + `_MAX_LLM_NUDGES` ([agent_chat.py:1076-1091](../../../app/agent_chat.py)). Add imports at top: `from __future__ import annotations`, `import json`, `import re`, `import uuid`, `from typing import Any`, and `from app.pi_tool_calls import _extract_json_args, _infer_tool_name, _prepare_tool_calls, _make_discover_fallback_call`.

Wait — `_make_discover_fallback_call` is defined among the heuristics; keep it in `pi_reply_heuristics.py`. `_fallback_prepared_calls` depends on `_prepare_tool_calls` (from pi_tool_calls) and `_user_requests_continuation`, `_infer_continuation_query`, `_make_discover_fallback_call` (local). `_parse_inline_tool_calls` depends on `_content_looks_like_tool_call`, `_assistant_intro_before_tools` (local), `_extract_json_args`, `_infer_tool_name` (from pi_tool_calls). Adjust the import line to: `from app.pi_tool_calls import _extract_json_args, _infer_tool_name, _prepare_tool_calls`.

- [ ] **Step 2: Re-import back into `agent_chat.py`**

Delete moved definitions; add:

```python
from app.pi_reply_heuristics import (
    _MAX_LLM_NUDGES,
    _CONTINUE_NUDGE,
    _EMPTY_RESPONSE_NUDGE,
    _INTRO_ONLY_NUDGE,
    _assistant_intro_before_tools,
    _assistant_promises_tool_use,
    _content_is_tool_json_fragment,
    _content_looks_like_tool_call,
    _fallback_prepared_calls,
    _infer_continuation_query,
    _make_discover_fallback_call,
    _meaningful_assistant_content,
    _parse_inline_tool_calls,
    _user_requests_continuation,
)
```

- [ ] **Step 3: Write tests**

`tests/test_reply_heuristics.py`:

```python
from app.pi_reply_heuristics import (
    _assistant_promises_tool_use,
    _content_is_tool_json_fragment,
    _meaningful_assistant_content,
    _parse_inline_tool_calls,
    _user_requests_continuation,
)


def test_meaningful_content_strips_tool_json_tail():
    assert _meaningful_assistant_content('我来查一下\n[{"name": "x"}]') == "我来查一下"


def test_meaningful_content_blank_for_pure_json_fragment():
    assert _meaningful_assistant_content('{"query": "isp"}') == ""


def test_tool_json_fragment_detection():
    assert _content_is_tool_json_fragment("[")
    assert _content_is_tool_json_fragment("[{")
    assert not _content_is_tool_json_fragment("这是正常的中文回复内容")


def test_promises_tool_use():
    assert _assistant_promises_tool_use("让我查一下")
    assert _assistant_promises_tool_use("好的，正在搜索：")
    assert not _assistant_promises_tool_use("已经为你找到了 3 个联系人。")


def test_user_requests_continuation():
    assert _user_requests_continuation("继续")
    assert _user_requests_continuation("还有吗")
    assert not _user_requests_continuation(
        "请帮我详细分析这家公司的网络架构和所有可能的对接人邮箱地址清单"
    )


def test_parse_inline_tool_calls_extracts_call():
    intro, calls = _parse_inline_tool_calls('好的[工具:list_contacts]{"q": "isp"}')
    assert calls and calls[0]["function"]["name"] == "list_contacts"
    assert "好的" in intro
```

- [ ] **Step 4: Run tests + import + characterization**

Run: `python -c "import app.agent_chat" && pytest tests/test_reply_heuristics.py tests/test_agent_loop_characterization.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/pi_reply_heuristics.py app/agent_chat.py tests/test_reply_heuristics.py
git commit -m "refactor: extract reply heuristics into pi_reply_heuristics with tests"
```

---

## Phase D — The decision state machine (the core fix)

### Task 11: Define `decide_turn` + `Decision` types

**Files:**
- Create: `app/pi_decisions.py`
- Create: `tests/test_decisions.py`

> This encodes — as a pure function — the branching currently inside the inner `while True` of `agent_chat_stream` ([agent_chat.py:2059-2179](../../../app/agent_chat.py)). It does NOT wire into the loop yet (Task 12 does that). Build it to match the characterized behavior.

- [ ] **Step 1: Write the failing tests**

`tests/test_decisions.py`:

```python
from app.pi_decisions import (
    EmitToolCalls,
    Fail,
    FallbackToolCalls,
    FinalReply,
    Retry,
    decide_turn,
)


def _assistant(content=None, tool_calls=None, reasoning=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if reasoning:
        msg["reasoning_content"] = reasoning
    return msg


def _valid_call(name="list_contacts", args='{"q": "isp"}'):
    return {"id": "c1", "type": "function", "function": {"name": name, "arguments": args}}


def test_valid_tool_calls_emit():
    d = decide_turn(
        _assistant("我来查", [_valid_call()]), "我来查",
        user_message="找联系人", history=[], nudge_count=0, max_nudges=2,
    )
    assert isinstance(d, EmitToolCalls)
    assert d.prepared_calls[0][1] == "list_contacts"


def test_plain_text_is_final_reply():
    d = decide_turn(
        _assistant("已为你找到 3 个联系人。"), "已为你找到 3 个联系人。",
        user_message="找联系人", history=[], nudge_count=0, max_nudges=2,
    )
    assert isinstance(d, FinalReply)
    assert "3 个联系人" in d.text


def test_empty_response_retries_then_fails():
    d = decide_turn(_assistant(None), "", user_message="x", history=[], nudge_count=0, max_nudges=2)
    assert isinstance(d, Retry)
    d2 = decide_turn(_assistant(None), "", user_message="x", history=[], nudge_count=2, max_nudges=2)
    assert isinstance(d2, Fail)


def test_intro_only_retries_then_falls_back():
    # "让我查一下" promises tool use but calls nothing.
    d = decide_turn(
        _assistant("让我查一下"), "让我查一下",
        user_message="列出运营商联系人", history=[], nudge_count=0, max_nudges=2,
    )
    assert isinstance(d, Retry)
    assert "工具" in d.nudge or "开场白" in d.nudge
    d2 = decide_turn(
        _assistant("让我查一下"), "让我查一下",
        user_message="列出运营商联系人", history=[], nudge_count=2, max_nudges=2,
    )
    assert isinstance(d2, FallbackToolCalls)


def test_inline_tool_call_in_content_is_emitted():
    d = decide_turn(
        _assistant('好的[工具:list_contacts]{"q": "isp"}'),
        '好的[工具:list_contacts]{"q": "isp"}',
        user_message="找联系人", history=[], nudge_count=0, max_nudges=2,
    )
    assert isinstance(d, EmitToolCalls)
    assert d.prepared_calls[0][1] == "list_contacts"


def test_continuation_request_falls_back_to_discover():
    history = [
        {"role": "user", "content": "找美国运营商 peering 联系人"},
        {"role": "tool", "name": "discover_leads", "summary": "30 条"},
    ]
    d = decide_turn(
        _assistant("好的，继续"), "好的，继续",
        user_message="继续", history=history, nudge_count=2, max_nudges=2,
    )
    assert isinstance(d, FallbackToolCalls)
    assert d.prepared_calls[0][1] == "discover_leads"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_decisions.py -q`
Expected: FAIL (`ModuleNotFoundError: app.pi_decisions`).

- [ ] **Step 3: Implement `app/pi_decisions.py`**

```python
"""Pure turn-decision logic for the Pi agent loop.

Given one LLM turn's result, decide what the driver should do next. No I/O.
Mirrors the branching previously inlined in agent_chat_stream.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.pi_reply_heuristics import (
    _assistant_promises_tool_use,
    _fallback_prepared_calls,
    _meaningful_assistant_content,
    _parse_inline_tool_calls,
    _user_requests_continuation,
)
from app.pi_tool_calls import _extract_tool_calls_from_content, _prepare_tool_calls

PreparedCall = tuple[dict[str, Any], str, dict[str, Any]]


@dataclass
class EmitToolCalls:
    prepared_calls: list[PreparedCall]
    intro_text: str = ""


@dataclass
class FinalReply:
    text: str


@dataclass
class Retry:
    nudge: str
    reason: str


@dataclass
class FallbackToolCalls:
    prepared_calls: list[PreparedCall]
    status_message: str


@dataclass
class Fail:
    error: str = "模型未返回有效回复，请换种说法或检查 LLM 配置"


Decision = EmitToolCalls | FinalReply | Retry | FallbackToolCalls | Fail

# Nudge strings live with the heuristics module to keep wording in one place.
from app.pi_reply_heuristics import (  # noqa: E402
    _CONTINUE_NUDGE,
    _EMPTY_RESPONSE_NUDGE,
    _INTRO_ONLY_NUDGE,
)


def _assistant_response_empty(assistant: dict[str, Any] | None, content_buffer: str) -> bool:
    if not assistant:
        return True
    content = (assistant.get("content") or content_buffer or "").strip()
    if content or (assistant.get("tool_calls") or []):
        return False
    return not str(assistant.get("reasoning_content") or "").strip()


def decide_turn(
    assistant: dict[str, Any] | None,
    content_buffer: str,
    *,
    user_message: str,
    history: list[dict[str, Any]],
    nudge_count: int,
    max_nudges: int,
) -> Decision:
    if _assistant_response_empty(assistant, content_buffer):
        if nudge_count < max_nudges:
            return Retry(_EMPTY_RESPONSE_NUDGE, "empty_response")
        return Fail()

    assistant = assistant or {}
    tool_calls = assistant.get("tool_calls") or []
    raw_content = (assistant.get("content") or content_buffer or "").strip()
    content = _meaningful_assistant_content(raw_content)

    # Recover tool calls embedded in content when the field is absent.
    if not tool_calls and raw_content:
        intro, inline_calls = _parse_inline_tool_calls(raw_content)
        if inline_calls:
            prepared = _prepare_tool_calls(inline_calls)
            if prepared:
                return EmitToolCalls(prepared, _meaningful_assistant_content(intro))

    if tool_calls:
        prepared = _prepare_tool_calls(tool_calls)
        if not prepared and raw_content:
            extracted = _extract_tool_calls_from_content(raw_content)
            if extracted:
                prepared = _prepare_tool_calls(extracted)
        if prepared:
            return EmitToolCalls(prepared, content)
        # tool_calls present but all invalid → retry, then fall back, then fail.
        if nudge_count < max_nudges:
            return Retry(_EMPTY_RESPONSE_NUDGE, "invalid_tool_calls")
        fallback = _fallback_prepared_calls(user_message, history)
        if fallback:
            return FallbackToolCalls(fallback, "工具调用无效，正在直接搜索 CRM…")
        return Fail()

    # No tool calls and some content.
    if content:
        wants_action = _assistant_promises_tool_use(content) or _user_requests_continuation(
            user_message
        )
        if wants_action:
            if nudge_count < max_nudges:
                if _user_requests_continuation(user_message):
                    return Retry(_CONTINUE_NUDGE, "continuation")
                return Retry(_INTRO_ONLY_NUDGE, "intro_only")
            fallback = _fallback_prepared_calls(user_message, history)
            if fallback:
                status = (
                    "正在直接继续上一任务…"
                    if _user_requests_continuation(user_message)
                    else "模型未调用工具，正在直接搜索 CRM…"
                )
                return FallbackToolCalls(fallback, status)
        return FinalReply(content)

    # No tool calls, no meaningful content (e.g. only tool-JSON fragment).
    if nudge_count < max_nudges:
        return Retry(_EMPTY_RESPONSE_NUDGE, "no_visible_content")
    fallback = _fallback_prepared_calls(user_message, history)
    if fallback:
        return FallbackToolCalls(fallback, "模型未调用工具，正在直接搜索 CRM…")
    return Fail()
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_decisions.py -q`
Expected: all pass. If a case mismatches, reconcile against the characterized behavior from Task 7 (the state machine must preserve observable outcomes).

- [ ] **Step 5: Commit**

```bash
git add app/pi_decisions.py tests/test_decisions.py
git commit -m "feat: add pure decide_turn state machine with exhaustive tests"
```

---

### Task 12: Wire `decide_turn` into the agent loop

**Files:**
- Modify: `app/agent_chat.py` (replace the inner `while True` branching with calls to `decide_turn`)
- Modify: `tests/test_agent_loop_characterization.py` (add scenarios now that behavior is centralized)

- [ ] **Step 1: Replace the inner decision block**

In `agent_chat_stream`, replace the body from the start of the inner `while True:` decision handling ([agent_chat.py:2059-2180](../../../app/agent_chat.py)) so that, after collecting `assistant` / `content_buffer` from the stream, it calls `decide_turn` and acts on the result. Replace lines 2059–2180 with:

```python
            decision = decide_turn(
                assistant,
                content_buffer,
                user_message=message,
                history=history or [],
                nudge_count=llm_nudge_count,
                max_nudges=_MAX_LLM_NUDGES,
            )

            if isinstance(decision, Retry):
                llm_nudge_count += 1
                messages.append({"role": "user", "content": decision.nudge})
                yield {"type": "status", "message": "模型未调用工具，正在重试…"}
                continue

            if isinstance(decision, Fail):
                yield {"type": "error", "message": decision.error}
                yield {"type": "done"}
                return

            if isinstance(decision, FinalReply):
                if not streamed_reply:
                    yield {"type": "assistant_start"}
                    yield {"type": "assistant_delta", "text": decision.text}
                yield {"type": "assistant_done", "text": decision.text}
                yield {"type": "done"}
                return

            if isinstance(decision, FallbackToolCalls):
                prepared_calls = decision.prepared_calls
                assistant = {**(assistant or {}), "role": "assistant", "content": content or None}
                yield {"type": "status", "message": decision.status_message}
                break

            # EmitToolCalls
            prepared_calls = decision.prepared_calls
            content = decision.intro_text
            assistant = {
                **(assistant or {}),
                "role": "assistant",
                "content": content or None,
                "tool_calls": [tc for tc, _, _ in prepared_calls],
            }
            break
```

Add `from app.pi_decisions import EmitToolCalls, Fail, FallbackToolCalls, FinalReply, Retry, decide_turn` to the imports. Remove now-dead local helpers that only the old block used, if any remain unreferenced (run `ruff check` to find them).

- [ ] **Step 2: Run characterization + decision tests**

Run: `pytest tests/test_agent_loop_characterization.py tests/test_decisions.py -q`
Expected: all pass (behavior preserved). Fix discrepancies by aligning the wiring, not by weakening characterization assertions.

- [ ] **Step 3: Add loop integration tests for retry/fallback/round-cap**

Append to `tests/test_agent_loop_characterization.py`:

```python
@pytest.mark.asyncio
async def test_empty_then_retry_then_fail_is_graceful():
    from tests.fake_llm import content_message

    fake = FakeLLM([content_message(""), content_message(""), content_message("")])
    events = await collect_events(
        agent_chat_stream(1, "x", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert any(e["type"] == "error" for e in events)
    assert event_types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_intro_only_exhausts_nudges_then_fallback_runs_tool():
    fake = FakeLLM([
        content_message("让我查一下"),
        content_message("让我查一下"),
        content_message("让我查一下"),
        content_message("已完成。"),
    ])
    seen = []

    async def tools(user_id, name, args, emit):
        seen.append(name)
        return {"contacts": [], "total": 0}

    events = await collect_events(
        agent_chat_stream(1, "列出运营商联系人", [], llm_client=fake, tool_runner=tools)
    )
    assert seen  # fallback forced a CRM search
    assert event_types(events)[-1] == "done"
```

- [ ] **Step 4: Run + import check**

Run: `python -c "import app.agent_chat" && pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/agent_chat.py tests/test_agent_loop_characterization.py
git commit -m "refactor: drive agent loop with decide_turn state machine"
```

---

## Phase E — True-streaming LLM client with retries

### Task 13: Build `pi_llm_client` (httpx true streaming + retries)

**Files:**
- Create: `app/pi_llm_client.py`
- Create: `tests/test_llm_client.py`

- [ ] **Step 1: Write the failing tests** (transport mocked via a fake httpx stream)

`tests/test_llm_client.py`:

```python
import httpx
import pytest

from app.pi_llm_client import RETRYABLE_STATUS, _next_backoff, stream_chat


def test_backoff_increases_and_is_bounded():
    delays = [_next_backoff(i) for i in range(5)]
    assert delays[0] < delays[1] < delays[2]
    assert all(d <= 20.0 for d in delays)


def test_retryable_status_set():
    assert 429 in RETRYABLE_STATUS and 503 in RETRYABLE_STATUS
    assert 400 not in RETRYABLE_STATUS


@pytest.mark.asyncio
async def test_stream_chat_yields_deltas_and_message(monkeypatch):
    from app import pi_llm_client as mod

    monkeypatch.setattr(mod, "_settings", lambda: ("key", "https://api.deepseek.com", "deepseek-chat"))

    sse_lines = [
        'data: {"choices": [{"delta": {"content": "你"}}]}',
        'data: {"choices": [{"delta": {"content": "好"}}]}',
        "data: [DONE]",
    ]

    class FakeResponse:
        status_code = 200
        headers: dict = {}

        async def aiter_lines(self):
            for line in sse_lines:
                yield line

        async def aread(self):
            return b""

        def raise_for_status(self):
            return None

    class FakeStreamCtx:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **k):
            return FakeStreamCtx()

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)

    events = [e async for e in stream_chat([{"role": "user", "content": "hi"}], None)]
    deltas = "".join(e["text"] for e in events if e["type"] == "content_delta")
    assert deltas == "你好"
    msg = [e for e in events if e["type"] == "message"][0]["message"]
    assert msg["content"] == "你好"


@pytest.mark.asyncio
async def test_stream_chat_retries_on_503_then_succeeds(monkeypatch):
    from app import pi_llm_client as mod

    monkeypatch.setattr(mod, "_settings", lambda: ("key", "https://api.deepseek.com", "deepseek-chat"))
    monkeypatch.setattr(mod.asyncio, "sleep", lambda *_a, **_k: _async_none())

    attempts = {"n": 0}

    class Resp503:
        status_code = 503
        headers: dict = {}

        async def aiter_lines(self):
            if False:
                yield ""

        async def aread(self):
            return b"overloaded"

    class Resp200:
        status_code = 200
        headers: dict = {}

        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "ok"}}]}'
            yield "data: [DONE]"

        async def aread(self):
            return b""

    class Ctx:
        def __init__(self, resp):
            self._resp = resp

        async def __aenter__(self):
            return self._resp

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **k):
            attempts["n"] += 1
            return Ctx(Resp503() if attempts["n"] == 1 else Resp200())

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)

    events = [e async for e in stream_chat([{"role": "user", "content": "hi"}], None)]
    assert attempts["n"] == 2  # retried once
    assert any(e["type"] == "content_delta" and e["text"] == "ok" for e in events)


async def _async_none():
    return None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_llm_client.py -q`
Expected: FAIL (`ModuleNotFoundError: app.pi_llm_client`).

- [ ] **Step 3: Implement `app/pi_llm_client.py`**

```python
"""Async, true-streaming LLM client with bounded retry/backoff.

Yields the same event contract agent_chat_stream consumes:
content_delta / status / message / error.
"""
from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm import (
    AGENT_REQUEST_TIMEOUT,
    REQUEST_TIMEOUT,
    _chat_completions_url,
    _settings,
    is_deepseek_provider,
    resolve_deepseek_thinking,
    sanitize_messages_for_api,
)
from app.pi_stream_parser import assemble_message, consume_stream_chunk, parse_sse_line

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
_BACKOFF_BASE = 0.5
_BACKOFF_CAP = 20.0


def _next_backoff(attempt: int) -> float:
    raw = _BACKOFF_BASE * (2**attempt)
    return min(_BACKOFF_CAP, raw) + random.uniform(0, _BACKOFF_BASE)


def _build_payload(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    temperature: float,
    tool_choice: Any,
    model: str,
    base_url: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": sanitize_messages_for_api(messages),
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice if tool_choice is not None else "auto"
    if is_deepseek_provider(model=model, base_url=base_url):
        thinking = resolve_deepseek_thinking(tools=tools)
        if thinking:
            payload["thinking"] = {"type": thinking}
            if thinking == "enabled" and tools:
                payload["reasoning_effort"] = "high"
    return payload


async def stream_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    temperature: float = 0.2,
    tool_choice: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    api_key, base_url, model = _settings()
    url = _chat_completions_url(base_url)
    payload = _build_payload(
        messages, tools, temperature=temperature, tool_choice=tool_choice,
        model=model, base_url=base_url,
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(AGENT_REQUEST_TIMEOUT if tools else REQUEST_TIMEOUT, connect=15.0)

    last_error = "LLM 请求失败"
    for attempt in range(MAX_RETRIES + 1):
        emitted_any = False
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        status_emitted = [False]
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code in RETRYABLE_STATUS:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        last_error = f"LLM 请求失败 ({resp.status_code}): {body[:200]}"
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(_retry_after(resp) or _next_backoff(attempt))
                            continue
                        yield {"type": "error", "message": last_error}
                        return
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        yield {
                            "type": "error",
                            "message": f"LLM 请求失败 ({resp.status_code}): {body[:300]}",
                        }
                        return
                    async for line in resp.aiter_lines():
                        chunk = parse_sse_line(line)
                        if chunk is None:
                            continue
                        for event in consume_stream_chunk(
                            chunk,
                            content_parts=content_parts,
                            reasoning_parts=reasoning_parts,
                            tool_calls=tool_calls,
                            emit_content_delta=True,
                            tool_status_emitted=status_emitted,
                        ):
                            emitted_any = True
                            yield event
            yield {"type": "message", "message": assemble_message(content_parts, reasoning_parts, tool_calls)}
            return
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_error = f"无法连接 LLM 服务: {exc}"
            if emitted_any:
                # Mid-stream failure after partial output — do not retry (would duplicate).
                yield {"type": "error", "message": last_error}
                return
            if attempt < MAX_RETRIES:
                await asyncio.sleep(_next_backoff(attempt))
                continue
            yield {"type": "error", "message": last_error}
            return

    yield {"type": "error", "message": last_error}


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_llm_client.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/pi_llm_client.py tests/test_llm_client.py
git commit -m "feat: add httpx true-streaming LLM client with retry/backoff"
```

---

### Task 14: Adapt the agent loop's default LLM client to `stream_chat`

**Files:**
- Modify: `app/agent_chat.py` (`_iter_llm_stream` delegates to `pi_llm_client.stream_chat`)

> `_iter_llm_stream` is the default `llm_client`. Make it an async passthrough to `stream_chat`, dropping the thread bridge. The injected-client tests already pass; this swaps the *default* transport to true streaming.

- [ ] **Step 1: Replace `_iter_llm_stream` body**

Replace `_iter_llm_stream` ([agent_chat.py:1898-1927](../../../app/agent_chat.py)) with:

```python
async def _iter_llm_stream(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    tool_choice: str | dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    try:
        async for event in stream_chat(messages, tools, tool_choice=tool_choice):
            yield event
    except LLMError as exc:
        yield {"type": "error", "message": str(exc)}
```

Add `from app.pi_llm_client import stream_chat` to imports. Keep `import threading` only if still used elsewhere (run `ruff check` — remove if now unused).

- [ ] **Step 2: Run full suite + import**

Run: `python -c "import app.agent_chat" && pytest tests/ -q`
Expected: all pass (characterization tests still green — they inject FakeLLM, so they don't exercise httpx; this confirms the default-path swap didn't break wiring).

- [ ] **Step 3: Commit**

```bash
git add app/agent_chat.py
git commit -m "refactor: default agent LLM transport to true-streaming stream_chat"
```

---

## Phase F — Budget guard, regression catalog, live smoke

### Task 15: Per-turn LLM call budget guard

**Files:**
- Modify: `app/agent_chat.py` (count LLM calls; stop gracefully past a cap)
- Create: `tests/test_budget_guard.py`

- [ ] **Step 1: Write the failing test**

`tests/test_budget_guard.py`:

```python
import pytest

from app.agent_chat import MAX_LLM_CALLS_PER_TURN, agent_chat_stream
from tests.conftest import collect_events, event_types
from tests.fake_llm import FakeLLM, content_message


async def _noop_tools(user_id, name, args, emit):
    return {"contacts": [], "total": 0}


@pytest.mark.asyncio
async def test_budget_guard_stops_runaway_loop():
    # Script far more nudge-inducing empty replies than the budget allows.
    fake = FakeLLM([content_message("") for _ in range(MAX_LLM_CALLS_PER_TURN + 10)])
    events = await collect_events(
        agent_chat_stream(1, "x", [], llm_client=fake, tool_runner=_noop_tools)
    )
    # Must terminate, not hang or exhaust the script.
    assert event_types(events)[-1] == "done"
    assert len(fake.calls) <= MAX_LLM_CALLS_PER_TURN
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_budget_guard.py -q`
Expected: FAIL (`ImportError: MAX_LLM_CALLS_PER_TURN`).

- [ ] **Step 3: Implement the guard**

In `app/agent_chat.py`, near the other constants ([agent_chat.py:62-65](../../../app/agent_chat.py)) add:

```python
MAX_LLM_CALLS_PER_TURN = 30
```

In `agent_chat_stream`, initialize `llm_call_count = 0` before the `for round_index` loop. Increment it immediately before each `llm_client(...)` invocation in the inner loop. At the top of the inner `while True:` (after the cancel check), add:

```python
            if llm_call_count >= MAX_LLM_CALLS_PER_TURN:
                yield {"type": "assistant_start"}
                yield {
                    "type": "assistant_delta",
                    "text": "本次对话已达调用上限，请简化问题后重试。",
                }
                yield {
                    "type": "assistant_done",
                    "text": "本次对话已达调用上限，请简化问题后重试。",
                }
                yield {"type": "done"}
                return
```

And wrap the call: `llm_call_count += 1` on the line before `async for event in llm_client(...)`.

- [ ] **Step 4: Run to verify pass + full suite**

Run: `pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/agent_chat.py tests/test_budget_guard.py
git commit -m "feat: cap LLM calls per turn to prevent runaway agent loops"
```

---

### Task 16: Regression catalog tests (one per historical bug)

**Files:**
- Create: `tests/test_regressions.py`

> Each test maps to a "Fix Pi…" commit from the spec's §10. Names reference the symptom so future failures are self-explaining.

- [ ] **Step 1: Write the regression tests**

`tests/test_regressions.py`:

```python
import pytest

from app.agent_chat import agent_chat_stream
from tests.conftest import assistant_text, collect_events, event_types
from tests.fake_llm import FakeLLM, content_message, tool_call


async def _noop_tools(user_id, name, args, emit):
    return {"contacts": [], "total": 0}


@pytest.mark.asyncio
async def test_regression_intro_only_does_not_stop_25733dc():
    # "让我查一下" alone must not end the turn without doing work.
    fake = FakeLLM([
        content_message("让我查一下"),
        content_message("好的", tool_calls=[tool_call("list_contacts", {"q": ""})]),
        content_message("已列出。"),
    ])
    events = await collect_events(
        agent_chat_stream(1, "列出联系人", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert any(e["type"] == "tool_start" for e in events)


@pytest.mark.asyncio
async def test_regression_empty_reply_no_blank_bubble_0a34da1():
    fake = FakeLLM([content_message(""), content_message(""), content_message("")])
    events = await collect_events(
        agent_chat_stream(1, "x", [], llm_client=fake, tool_runner=_noop_tools)
    )
    # No empty assistant_done bubbles; ends on a real error + done.
    assert all(str(e.get("text") or "").strip() for e in events if e["type"] == "assistant_done")
    assert any(e["type"] == "error" for e in events)


@pytest.mark.asyncio
async def test_regression_invalid_tool_call_no_infinite_loop_de9d52b():
    # All-invalid tool calls every time → must terminate, not loop forever.
    bad = [tool_call("totally_unknown_tool", {"foo": "bar"})]
    fake = FakeLLM([content_message("调用", tool_calls=bad) for _ in range(10)])
    events = await collect_events(
        agent_chat_stream(1, "做点什么", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert event_types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_regression_tool_json_not_in_bubble_de9d52b():
    fake = FakeLLM([
        content_message('{"name": "list_contacts", "arguments": {"q": "isp"}}'),
        content_message("完成。"),
    ])
    events = await collect_events(
        agent_chat_stream(1, "找联系人", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert '"arguments"' not in assistant_text(events)


@pytest.mark.asyncio
async def test_regression_continue_resumes_discover_25733dc():
    history = [
        {"role": "user", "content": "找美国运营商 peering 联系人"},
        {"role": "tool", "name": "discover_leads", "summary": "30 条"},
    ]
    seen = []

    async def tools(user_id, name, args, emit):
        seen.append(name)
        return {"lead_count": 0, "leads": []}

    fake = FakeLLM([
        content_message("好的，继续"),
        content_message("好的，继续"),
        content_message("好的，继续"),
        content_message("已扩展搜索。"),
    ])
    await collect_events(
        agent_chat_stream(1, "继续", history, llm_client=fake, tool_runner=tools)
    )
    assert "discover_leads" in seen


@pytest.mark.asyncio
async def test_regression_round_cap_produces_summary_a5d4291():
    # Model always calls a tool; loop must summarize at the round cap rather than error.
    fake = FakeLLM(
        [content_message("查", tool_calls=[tool_call("list_contacts", {"q": "x"})]) for _ in range(20)]
        + [content_message("这是最终总结。")]
    )
    events = await collect_events(
        agent_chat_stream(1, "不停地搜", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert event_types(events)[-1] == "done"
    assert assistant_text(events).strip()  # produced a final textual summary
```

- [ ] **Step 2: Run the regression tests**

Run: `pytest tests/test_regressions.py -q`
Expected: all pass. If `test_regression_round_cap_produces_summary` needs more scripted turns than `MAX_TOOL_ROUNDS`, adjust the script length to exceed `MAX_TOOL_ROUNDS` (12) so the cap path triggers.

- [ ] **Step 3: Commit**

```bash
git add tests/test_regressions.py
git commit -m "test: add regression catalog mapping historical Pi bugs to tests"
```

---

### Task 17: Opt-in live DeepSeek smoke test

**Files:**
- Create: `tests/test_live_llm_smoke.py`

- [ ] **Step 1: Write the env-gated smoke test**

`tests/test_live_llm_smoke.py`:

```python
import os

import pytest

from app.pi_llm_client import stream_chat

pytestmark = pytest.mark.skipif(
    os.getenv("PI_LIVE_LLM") != "1",
    reason="set PI_LIVE_LLM=1 (and configure LLM settings) to run live smoke",
)


@pytest.mark.asyncio
async def test_live_stream_returns_text():
    events = [
        e
        async for e in stream_chat(
            [{"role": "user", "content": "用一个字回答：你好吗"}], None
        )
    ]
    assert any(e["type"] == "content_delta" for e in events)
    assert [e for e in events if e["type"] == "message"]
```

- [ ] **Step 2: Verify it skips by default**

Run: `pytest tests/test_live_llm_smoke.py -q`
Expected: 1 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/test_live_llm_smoke.py
git commit -m "test: add opt-in live DeepSeek streaming smoke (PI_LIVE_LLM=1)"
```

---

## Phase G — Final verification

### Task 18: Full green sweep + dead-code cleanup

**Files:**
- Modify: `app/agent_chat.py` (remove any now-unreferenced locals flagged by ruff)

- [ ] **Step 1: Lint for dead code**

Run: `ruff check app/agent_chat.py`
Remove any unused imports/functions it flags that were superseded by the extractions (e.g. an orphaned `_assistant_response_empty` duplicate if both exist — keep the one in `pi_decisions`; in `agent_chat` import or delete as appropriate). Do NOT remove anything still referenced by the public facade or by `main.py`/`background_jobs.py`.

- [ ] **Step 2: Confirm facade exports intact**

Run: `python -c "from app.agent_chat import agent_chat_stream, history_entry_from_agent_event, release_pi_thread, try_acquire_pi_thread; print('facade ok')"`
Expected: `facade ok` (these are the symbols `main.py` imports — see [main.py:18-23](../../../app/main.py)).

- [ ] **Step 3: Confirm background_jobs imports intact**

Run: `python -c "import app.background_jobs; print('jobs ok')"`
Expected: `jobs ok`.

- [ ] **Step 4: Full local gate**

Run: `./scripts/test.sh`
Expected: ruff check clean, ruff format clean, all pytest pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead code superseded by Pi extraction; full green"
```

---

### Task 19: Push branch and open PR

- [ ] **Step 1: Push**

```bash
git push -u origin pi-reliability-test-foundation
```

- [ ] **Step 2: Open PR** (only if the user has asked to open one)

```bash
gh pr create --title "Pi reliability + test foundation (sub-project 1)" \
  --body "Implements docs/superpowers/specs/2026-06-06-pi-agent-reliability-test-foundation-design.md: extracts the agent decision logic into a pure decide_turn state machine, replaces fake streaming with an httpx true-streaming client (retry/backoff), and stands up pytest + ruff + GitHub Actions with a FakeLLM-driven regression net. Behavior preserved (characterization tests); callers unchanged."
```

- [ ] **Step 3: Confirm CI is green on the PR**

Run: `gh pr checks`
Expected: CI job passes.

---

## Self-Review

**Spec coverage** (each spec section → task):
- §4 module structure → Tasks 8–14 create `pi_stream_parser`, `pi_tool_calls`, `pi_reply_heuristics`, `pi_decisions`, `pi_llm_client`. (`pi_tools`/`pi_events` split deferred — see note below.)
- §5 decide_turn state machine → Tasks 11–12.
- §6 true streaming + retries → Tasks 13–14; sync-path retry wrapper → see note below.
- §7 injection seams → Task 6.
- §8 test foundation (FakeLLM, four layers) → Tasks 3–4 (FakeLLM), 7 (characterization/integration), 9–11 (unit), 16 (regression), 17 (live).
- §9 CI + tooling → Tasks 1, 2, 5.
- §10 regression catalog → Task 16.
- §11 error handling + budget guard → Tasks 13 (LLM errors), 15 (budget).
- §12 migration order → phases A–G follow it.

**Deviations from spec (intentional, scoped):**
1. **`pi_tools.py` / `pi_events.py` not split out.** The spec listed these, but the tool dispatch (`_run_tool`, `AGENT_TOOLS`) and event typing are large and not reliability hotspots; splitting them adds churn without reducing flakiness. They stay in `agent_chat.py` for this sub-project. *If the executor wants them, add an extraction task mirroring Task 9 — but it is not required for the DoD.* This keeps the plan focused on the two real hotspots (decisions + transport).
2. **Sync-path (`chat_completion`) retry wrapper deferred.** The reliability problem is the streaming agent path (now covered). Adding the shared backoff to the sync utility calls is a small follow-up; not on the critical path for agent reliability. Track as a follow-up task if desired.

These deviations narrow scope; they do not leave any DoD criterion unmet (DoD items 1–7 are all covered by Tasks above).

**Placeholder scan:** No TBD/TODO; every code step contains full code or an exact extraction instruction with line references. ✓

**Type consistency:** `Decision` variants (`EmitToolCalls.prepared_calls`/`.intro_text`, `Retry.nudge`/`.reason`, `FallbackToolCalls.prepared_calls`/`.status_message`, `FinalReply.text`, `Fail.error`) are defined in Task 11 and used identically in Task 12. `stream_chat(messages, tools, *, temperature, tool_choice)` defined in Task 13, called with that signature in Task 14. `llm_client(messages, tools, *, tool_choice)` seam (Task 6) matches both `FakeLLM.__call__` (Task 4) and `_iter_llm_stream` (Task 14). `tool_runner(user_id, name, args, emit)` seam matches `_run_tool` and test fakes. ✓

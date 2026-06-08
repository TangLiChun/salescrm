# Replace External Pi Agent with DeepSeek-Reasonix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the external Pi Coding Agent integration with DeepSeek-Reasonix, driven by a markdown skill + a zero-dependency Python helper CLI that wraps the existing `/api/agent/*` HTTP API.

**Architecture:** The Sales CRM backend is agent-agnostic — it exposes a Bearer-authenticated Agent API (`/api/agent/*`) plus an Agent Token. We swap only the client-side adapter: delete the pi-mono extension package and add `integrations/reasonix/` (a `salescrm` CLI Reasonix calls via its built-in `bash` tool, plus a skill). No MCP server, no Python backend changes. Deploy automation and the settings label are updated; the in-app "Pi 助手" web chat is untouched.

**Tech Stack:** Python 3 stdlib only (`argparse`/`json`/`urllib`) for the CLI; bash for deploy; vanilla TS/i18n for the settings label. Tests via pytest with monkeypatched HTTP (no real network/DB). Spec: `docs/superpowers/specs/2026-06-09-reasonix-external-agent-integration-design.md`.

**Conventions:** Run `ruff check . && ruff format --check . && pytest -q && npm run check:frontend` before each commit (CI also runs `git diff --exit-code` on built `app/static/js`/`i18n.js`, so rebuild the frontend before committing TS/i18n changes). The CLI file `integrations/reasonix/bin/salescrm` has no `.py` extension, so ruff does not lint it — keep it clean by hand. `scripts/deploy.sh` is shell; verify with `bash -n`.

---

## File Structure

**Create:**
- `integrations/reasonix/bin/salescrm` — zero-dep Python CLI wrapping the 4 Agent API endpoints (`health`/`contacts`/`import-leads`/`discover`). Executable, importable for tests.
- `integrations/reasonix/skills/salescrm/SKILL.md` — Reasonix skill describing when/how to use the CLI.
- `integrations/reasonix/reasonix.toml.example` — sample Reasonix config (skills path + notes).
- `integrations/reasonix/README.md` — setup/install guide.
- `tests/test_reasonix_cli.py` — unit tests for the CLI (stdlib, monkeypatched HTTP).

**Modify:**
- `scripts/deploy.sh` — port the pi automation block to Reasonix; `SKIP_PI` → `SKIP_REASONIX`.
- `frontend/src/i18n.ts` (+ rebuilt `app/static/i18n.js`) — neutralize the "Pi Agent API" settings strings.
- `app/static/index.html` — inline legend default text (line ~734).
- `FEATURE_PLAN.md` — line 41 integration reference.

**Delete:**
- `integrations/pi/` (entire directory: `README.md`, `package.json`, `extensions/salescrm.ts`, `skills/salescrm/SKILL.md`).

**Unchanged (explicitly):** `app/agent_routes.py`, `app/agent_auth.py`, all `app/pi_*.py`, the in-app "Pi 助手" nav/chat, and the Agent Token mechanism.

---

# Task 1: CLI request layer + `health`

**Files:**
- Create: `integrations/reasonix/bin/salescrm`
- Test: `tests/test_reasonix_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reasonix_cli.py
import importlib.util
import io
import json
import pathlib
import urllib.error
from importlib.machinery import SourceFileLoader

import pytest

CLI_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "integrations" / "reasonix" / "bin" / "salescrm"
)


def _load_cli():
    loader = SourceFileLoader("salescrm_cli", str(CLI_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


cli = _load_cli()


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b


def _capture(captured, payload=None):
    def _open(req):
        captured["req"] = req
        return FakeResp(payload if payload is not None else {"ok": True})

    return _open


def test_health_builds_authed_get(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    monkeypatch.setenv("SALESCRM_URL", "http://crm:9000")
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"ok": True}))

    assert cli.main(["health"]) == 0
    req = captured["req"]
    assert req.get_method() == "GET"
    assert req.full_url == "http://crm:9000/api/agent/health"
    assert req.get_header("Authorization") == "Bearer T"


def test_missing_token_errors(monkeypatch):
    monkeypatch.delenv("SALESCRM_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        cli.main(["health"])


def test_http_error_surfaces_status_and_detail(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    body = io.BytesIO(json.dumps({"detail": "未配置 LLM API Key"}).encode())
    err = urllib.error.HTTPError("http://x/api/agent/health", 503, "Unavailable", {}, body)

    def boom(req):
        raise err

    monkeypatch.setattr(cli, "_open", boom)
    with pytest.raises(SystemExit) as ei:
        cli.main(["health"])
    assert "503" in str(ei.value) and "LLM" in str(ei.value)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_reasonix_cli.py -q`
Expected: FAIL — `FileNotFoundError`/load error (the CLI file does not exist yet).

- [ ] **Step 3: Create `integrations/reasonix/bin/salescrm`**

```python
#!/usr/bin/env python3
"""Sales CRM helper CLI for DeepSeek-Reasonix.

Stdlib only. Wraps the Sales CRM Agent API (/api/agent/*) so a Reasonix agent can
drive lead import/discovery through its built-in `bash` tool.

Env:
  SALESCRM_URL    default http://127.0.0.1:8000
  SALESCRM_TOKEN  required — CRM 设置 → 自动化 → 外部 Agent API → Agent Token
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def base_url() -> str:
    return (os.environ.get("SALESCRM_URL") or "http://127.0.0.1:8000").rstrip("/")


def token() -> str:
    return (os.environ.get("SALESCRM_TOKEN") or "").strip()


def _open(req: urllib.request.Request):
    """HTTP seam — patched in tests."""
    return urllib.request.urlopen(req, timeout=30)


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode())
        if isinstance(payload, dict) and "detail" in payload:
            return str(payload["detail"])
    except Exception:  # noqa: BLE001 - fall back to reason on any parse failure
        pass
    return exc.reason or "request failed"


def request(method: str, path: str, *, params: dict | None = None, body=None) -> dict:
    tok = token()
    if not tok:
        raise SystemExit(
            "错误：SALESCRM_TOKEN 未设置。在 CRM 设置 → 自动化 → 外部 Agent API 生成 Token，"
            "并 export SALESCRM_TOKEN。"
        )
    url = base_url() + path
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {tok}")
    req.add_header("Content-Type", "application/json")
    try:
        resp = _open(req)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Sales CRM {exc.code}: {_error_detail(exc)}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"无法连接 Sales CRM ({base_url()}): {exc.reason}") from exc
    raw = resp.read().decode()
    return json.loads(raw) if raw else {}


def cmd_health(args) -> dict:
    return request("GET", "/api/agent/health")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="salescrm", description="Sales CRM agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", help="检查 CRM 与数据库连通性")
    p_health.set_defaults(func=cmd_health)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_reasonix_cli.py -q` → PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff format tests/test_reasonix_cli.py
.venv/bin/ruff check tests/test_reasonix_cli.py
git add integrations/reasonix/bin/salescrm tests/test_reasonix_cli.py
git commit -m "feat(reasonix): salescrm CLI request layer + health command"
```

---

# Task 2: CLI `contacts`, `import-leads`, `discover`

**Files:**
- Modify: `integrations/reasonix/bin/salescrm`
- Test: `tests/test_reasonix_cli.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_reasonix_cli.py`)

```python
def test_contacts_passes_query_params(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    monkeypatch.setenv("SALESCRM_URL", "http://crm:9000")
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"contacts": [], "total": 0}))

    cli.main(["contacts", "--status", "unsent", "--limit", "10", "--q", "isp"])
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(captured["req"].full_url)
    q = parse_qs(parsed.query)
    assert parsed.path == "/api/agent/contacts"
    assert q["status"] == ["unsent"] and q["limit"] == ["10"] and q["q"] == ["isp"]


def test_import_leads_array_from_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    p = tmp_path / "rows.json"
    p.write_text(json.dumps([{"email": "a@b.com"}]), encoding="utf-8")
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"imported": 1}))

    cli.main(["import-leads", str(p), "--source", "scrape"])
    req = captured["req"]
    assert req.get_method() == "POST"
    assert req.full_url.endswith("/api/agent/leads/import")
    body = json.loads(req.data.decode())
    assert body["rows"] == [{"email": "a@b.com"}]
    assert body["source"] == "scrape"


def test_import_leads_rows_wrapper_from_stdin_default_source(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(json.dumps({"rows": [{"email": "x@y.com"}]})))
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"imported": 1}))

    cli.main(["import-leads", "-"])
    body = json.loads(captured["req"].data.decode())
    assert body["rows"] == [{"email": "x@y.com"}]
    assert body["source"] == "reasonix-agent"


def test_discover_builds_post_body(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"imported": 0}))

    cli.main(["discover", "find US ISP peering", "--min-score", "70", "--auto-import"])
    req = captured["req"]
    assert req.full_url.endswith("/api/agent/leads/discover")
    body = json.loads(req.data.decode())
    assert body == {
        "query": "find US ISP peering",
        "min_score": 70,
        "delay": 0.5,
        "auto_import": True,
    }
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_reasonix_cli.py -q`
Expected: FAIL — argparse errors / `AttributeError` (subcommands not defined).

- [ ] **Step 3: Add the three commands + `load_rows` helper**

In `integrations/reasonix/bin/salescrm`, add a helper after `request(...)`:

```python
def load_rows(source: str) -> list:
    text = sys.stdin.read() if source == "-" else open(source, encoding="utf-8").read()
    data = json.loads(text)
    rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
    if not isinstance(rows, list):
        raise SystemExit('错误：import-leads 需要 JSON 数组或 {"rows":[...]}')
    return rows
```

Add command functions after `cmd_health`:

```python
def cmd_contacts(args) -> dict:
    return request(
        "GET",
        "/api/agent/contacts",
        params={
            "q": args.q,
            "status": args.status,
            "follow_up_status": args.follow_up,
            "limit": args.limit,
            "offset": args.offset,
        },
    )


def cmd_import_leads(args) -> dict:
    rows = load_rows(args.file)
    return request(
        "POST",
        "/api/agent/leads/import",
        body={"rows": rows, "source": args.source},
    )


def cmd_discover(args) -> dict:
    return request(
        "POST",
        "/api/agent/leads/discover",
        body={
            "query": args.query,
            "min_score": args.min_score,
            "delay": args.delay,
            "auto_import": args.auto_import,
        },
    )
```

Register them in `build_parser()` before `return parser`:

```python
    p_contacts = sub.add_parser("contacts", help="列出联系人")
    p_contacts.add_argument("--q", default=None, help="搜索关键词")
    p_contacts.add_argument(
        "--status", default="all", choices=["all", "sent", "unsent"], help="发信状态"
    )
    p_contacts.add_argument("--follow-up", dest="follow_up", default=None, help="跟进状态")
    p_contacts.add_argument("--limit", type=int, default=50, help="每页数量 (1-500)")
    p_contacts.add_argument("--offset", type=int, default=0, help="偏移")
    p_contacts.set_defaults(func=cmd_contacts)

    p_import = sub.add_parser("import-leads", help="导入线索 (JSON 数组或 {rows:[...]})")
    p_import.add_argument("file", help="JSON 文件路径，或 - 表示从 stdin 读取")
    p_import.add_argument("--source", default="reasonix-agent", help="来源标签")
    p_import.set_defaults(func=cmd_import_leads)

    p_discover = sub.add_parser("discover", help="AI 线索发现")
    p_discover.add_argument("query", help="自然语言查询 (至少 4 字)")
    p_discover.add_argument("--min-score", dest="min_score", type=int, default=60, help="最低分 0-100")
    p_discover.add_argument("--delay", type=float, default=0.5, help="每条请求间隔秒")
    p_discover.add_argument("--auto-import", dest="auto_import", action="store_true", help="自动导入")
    p_discover.set_defaults(func=cmd_discover)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_reasonix_cli.py -q` → PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff format tests/test_reasonix_cli.py
.venv/bin/ruff check tests/test_reasonix_cli.py
git add integrations/reasonix/bin/salescrm tests/test_reasonix_cli.py
git commit -m "feat(reasonix): salescrm CLI contacts/import-leads/discover commands"
```

---

# Task 3: Skill, sample config, README + make CLI executable

**Files:**
- Modify (permissions): `integrations/reasonix/bin/salescrm`
- Create: `integrations/reasonix/skills/salescrm/SKILL.md`
- Create: `integrations/reasonix/reasonix.toml.example`
- Create: `integrations/reasonix/README.md`

- [ ] **Step 1: Make the CLI executable and smoke-test it**

```bash
chmod +x integrations/reasonix/bin/salescrm
integrations/reasonix/bin/salescrm --help
```
Expected: argparse usage listing `health`, `contacts`, `import-leads`, `discover` (exit 0).

- [ ] **Step 2: Create `integrations/reasonix/skills/salescrm/SKILL.md`**

```markdown
---
name: salescrm
description: Use when importing network-operator leads into Sales CRM, or when the user mentions Sales CRM, ASN contacts, peering outreach, or lead discovery on this VPS.
---

# Sales CRM (via the `salescrm` CLI)

Sales CRM runs on the same VPS at `$SALESCRM_URL` (default `http://127.0.0.1:8000`).
Talk to it through the **`salescrm` CLI** using the `bash` tool — it wraps the CRM Agent
API and reads `SALESCRM_URL` / `SALESCRM_TOKEN` from the environment. Do NOT use browser
login.

## Setup

1. CRM Web UI → **设置 → 自动化 → 外部 Agent API** → **重新生成** → copy the Token.
2. Export env vars (deploy.sh writes `${APP_DIR}/.reasonix-env` and sources it from
   `~/.bashrc`; otherwise set them yourself):

   ```bash
   export SALESCRM_URL=http://127.0.0.1:8000
   export SALESCRM_TOKEN=<paste-token>
   ```

3. The `salescrm` CLI is on `PATH` (deploy.sh symlinks it to `/usr/local/bin/salescrm`).

## Commands

| Command | When to use |
|---------|-------------|
| `salescrm health` | Verify the CRM + DB are up before a long scrape/import job. |
| `salescrm contacts [--status all\|sent\|unsent] [--q TEXT] [--limit N]` | Inspect existing contacts (dedupe checks, follow-up). |
| `salescrm import-leads <file.json\|-> [--source TAG]` | Import scraped leads. Input is a JSON array of contact rows, or `{"rows": [...]}`. Use `-` to read from stdin. |
| `salescrm discover "<query>" [--min-score N] [--auto-import]` | Run AI lead discovery for a natural-language query. |

## Typical workflow

1. `salescrm health` — confirm connectivity.
2. Scrape / produce lead rows as JSON (each row: `email`, `org`, `name`, `asn`, `roles`...).
3. `echo "$ROWS_JSON" | salescrm import-leads -` (or pass a file path).
4. Report the returned counts (imported / skipped / total) to the user.

Errors print to stderr with the HTTP status + server detail and a non-zero exit code.
```

- [ ] **Step 3: Create `integrations/reasonix/reasonix.toml.example`**

```toml
# Sample Reasonix config for the Sales CRM integration.
# Copy relevant parts into your reasonix.toml (project root or ~/.config/reasonix/).
#
# 1) Register the Sales CRM skill directory:
[skills]
paths = ["/opt/salescrm/integrations/reasonix/skills"]

# 2) The `salescrm` CLI must be on PATH. deploy.sh symlinks it to /usr/local/bin/salescrm.
#    Manual alternative: add integrations/reasonix/bin to PATH.
#
# 3) Env (deploy.sh writes ${APP_DIR}/.reasonix-env and sources it from ~/.bashrc):
#       export SALESCRM_URL=http://127.0.0.1:8000
#       export SALESCRM_TOKEN=<token from 设置 → 自动化 → 外部 Agent API>
#
# 4) Your DeepSeek model + credentials are configured separately via `reasonix setup`
#    (out of scope for this integration).
```

- [ ] **Step 4: Create `integrations/reasonix/README.md`**

```markdown
# Sales CRM × DeepSeek-Reasonix

Let [DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix) import scraped
leads into Sales CRM from the same VPS, via the `salescrm` helper CLI.

The CRM side is unchanged: Reasonix calls the Agent API (`/api/agent/*`, Bearer token)
through the `salescrm` CLI using its built-in `bash` tool. No MCP server.

## Automated (deploy.sh)

`sudo ./scripts/deploy.sh` will (unless `SKIP_REASONIX=1`):

- read the Agent Token and write `${APP_DIR}/.reasonix-env` (sourced from `~/.bashrc`);
- install Reasonix (`npm i -g reasonix`);
- symlink the CLI to `/usr/local/bin/salescrm`;
- ensure `${APP_DIR}/reasonix.toml` registers the skills path;
- verify with the Agent API health check.

## Manual

1. CRM Web UI → **设置 → 自动化 → 外部 Agent API** → **重新生成** → copy Token.
2. ```bash
   export SALESCRM_URL=http://127.0.0.1:8000
   export SALESCRM_TOKEN=<token>
   ```
3. Install Reasonix: `npm i -g reasonix` (or a prebuilt binary from GitHub releases).
4. Put the CLI on PATH: `ln -sf "$PWD/integrations/reasonix/bin/salescrm" /usr/local/bin/salescrm`.
5. Register the skill: add `[skills] paths = [".../integrations/reasonix/skills"]` to your
   `reasonix.toml` (see `reasonix.toml.example`).
6. Configure your DeepSeek model/credentials: `reasonix setup`.

## Verify

```bash
source ${APP_DIR}/.reasonix-env
salescrm health
```
Expected: `{"ok": true, "db": true, "schema": true, ...}`.
```

- [ ] **Step 5: Commit**

```bash
git add integrations/reasonix
git update-index --chmod=+x integrations/reasonix/bin/salescrm
git commit -m "feat(reasonix): salescrm skill, sample config, README; mark CLI executable"
```

---

# Task 4: Port `scripts/deploy.sh` (pi → reasonix)

**Files:**
- Modify: `scripts/deploy.sh`

> No pytest coverage (shell). Verify with `bash -n` after editing.

- [ ] **Step 1: Rename gate, header comments, and state vars**

- Line ~21 comment: replace `跳过 Pi 重装` with `跳过 Reasonix 重装`.
- Line ~23 comment: replace `#   SKIP_PI=1       跳过 Pi Coding Agent 安装与配置` with `#   SKIP_REASONIX=1 跳过 Reasonix 安装与配置`.
- Line ~49: `SKIP_PI="${SKIP_PI:-0}"` → `SKIP_REASONIX="${SKIP_REASONIX:-0}"`.
- Lines ~58-59: `PI_ENV_FILE=""` → `REASONIX_ENV_FILE=""`; `PI_SETUP_OK=0` → `REASONIX_SETUP_OK=0`.
- Line ~461 warn: `Pi 需要 18+` → `Reasonix 需要 Node 18+`.

- [ ] **Step 2: Replace the env-file + autoload + install helpers**

Replace `write_pi_env_file`, `ensure_pi_env_autoload`, `install_pi_cli`, and
`install_pi_extension` (the block from `write_pi_env_file()` through the end of
`install_pi_extension()`) with:

```bash
write_reasonix_env_file() {
  local token="$1"
  REASONIX_ENV_FILE="${APP_DIR}/.reasonix-env"
  umask 077
  cat > "${REASONIX_ENV_FILE}" <<EOF
# Sales CRM Reasonix Agent — 由 deploy.sh 自动生成，请勿提交到 git
export SALESCRM_URL="http://127.0.0.1:${APP_PORT}"
export SALESCRM_TOKEN="${token}"
EOF
  chmod 600 "${REASONIX_ENV_FILE}"
  $SUDO chown "$(id -un)":"$(id -gn)" "${REASONIX_ENV_FILE}" 2>/dev/null || true
}

ensure_reasonix_env_autoload() {
  local marker="# salescrm-reasonix-env"
  local line="[[ -f \"${APP_DIR}/.reasonix-env\" ]] && source \"${APP_DIR}/.reasonix-env\""
  local rc="${HOME}/.bashrc"
  [[ -f "${rc}" ]] || return 0
  if grep -qF "${marker}" "${rc}" 2>/dev/null; then
    return 0
  fi
  {
    echo ""
    echo "${marker}"
    echo "${line}"
  } >> "${rc}"
}

install_reasonix_cli() {
  if command -v reasonix >/dev/null 2>&1; then
    log "Reasonix 已安装: $(reasonix --version 2>/dev/null | head -n 1 || echo reasonix)"
    return 0
  fi
  log "安装 DeepSeek-Reasonix..."
  npm install -g reasonix
  command -v reasonix >/dev/null 2>&1
}

link_salescrm_cli() {
  local src="${APP_DIR}/integrations/reasonix/bin/salescrm"
  [[ -f "${src}" ]] || return 1
  chmod +x "${src}" 2>/dev/null || true
  $SUDO ln -sf "${src}" /usr/local/bin/salescrm
}

register_reasonix_skill() {
  local cfg="${APP_DIR}/reasonix.toml"
  local skills_path="${APP_DIR}/integrations/reasonix/skills"
  if [[ -f "${cfg}" ]] && grep -qF "${skills_path}" "${cfg}" 2>/dev/null; then
    return 0
  fi
  cat >> "${cfg}" <<EOF

[skills]
paths = ["${skills_path}"]
EOF
}
```

- [ ] **Step 3: Replace `verify_pi_agent_api` and `setup_pi_agent`**

Replace `verify_pi_agent_api()` with the renamed version:

```bash
verify_agent_api() {
  local token="$1"
  curl -fsS --max-time 10 \
    -H "Authorization: Bearer ${token}" \
    "http://127.0.0.1:${APP_PORT}/api/agent/health" >/dev/null
}
```

Replace the entire `setup_pi_agent()` function with:

```bash
setup_reasonix_agent() {
  if [[ "${SKIP_REASONIX}" == "1" ]]; then
    log "跳过 Reasonix 安装 (SKIP_REASONIX=1)"
    return 0
  fi

  if [[ -f "${APP_DIR}/.reasonix-env" ]] && command -v reasonix >/dev/null 2>&1; then
    if [[ "${DEPLOY_STRATEGY}" == "restart" || "${DEPLOY_FAST}" == "1" ]]; then
      REASONIX_ENV_FILE="${APP_DIR}/.reasonix-env"
      REASONIX_SETUP_OK=1
      log "Reasonix 已安装，跳过重复配置（快速部署）"
      return 0
    fi
  fi

  if [[ ! -d "${APP_DIR}/integrations/reasonix" ]]; then
    warn "未找到 ${APP_DIR}/integrations/reasonix，跳过 Reasonix 安装"
    return 0
  fi

  log "配置 DeepSeek-Reasonix..."
  if ! install_node; then
    warn "Reasonix 未安装：Node.js 不可用"
    return 0
  fi

  local token
  token="$(fetch_agent_token)"
  if [[ -z "${token}" ]]; then
    warn "无法读取 Agent API Token，跳过 Reasonix 配置"
    return 0
  fi

  write_reasonix_env_file "${token}"
  # shellcheck disable=SC1090
  set +u
  source "${REASONIX_ENV_FILE}"
  set -u

  if ! link_salescrm_cli; then
    warn "salescrm CLI 链接失败：未找到 ${APP_DIR}/integrations/reasonix/bin/salescrm"
    return 0
  fi
  register_reasonix_skill

  if ! install_reasonix_cli; then
    warn "Reasonix 安装失败，已写入 ${REASONIX_ENV_FILE}，可稍后手动: npm i -g reasonix"
    return 0
  fi

  if verify_agent_api "${token}"; then
    REASONIX_SETUP_OK=1
    ensure_reasonix_env_autoload
    log "Reasonix 配置完成"
  else
    warn "Reasonix 已安装，但 Agent API 验证失败，请运行 ./scripts/check.sh"
  fi
}
```

- [ ] **Step 4: Update the call site and the summary**

- Line ~634: `setup_pi_agent` → `setup_reasonix_agent`.
- In `print_summary` (lines ~595-599), replace the Pi block with:

```bash
  if [[ "${REASONIX_SETUP_OK}" == "1" && -n "${REASONIX_ENV_FILE}" ]]; then
    echo " Reasonix: source ${REASONIX_ENV_FILE} && cd ${APP_DIR} && reasonix"
    echo " 验证:     source ${REASONIX_ENV_FILE} && salescrm health"
  elif [[ "${SKIP_REASONIX}" != "1" ]]; then
    echo " Reasonix: 安装未完成，见上方 WARNING 或 integrations/reasonix/README.md"
  fi
```

- [ ] **Step 5: Verify shell syntax**

```bash
bash -n scripts/deploy.sh && echo "syntax OK"
grep -n "SKIP_PI\|PI_ENV_FILE\|PI_SETUP_OK\|setup_pi_agent\|install_pi\|write_pi_env\|verify_pi_agent\|ensure_pi_env" scripts/deploy.sh || echo "no stale pi refs"
```
Expected: `syntax OK`, and `no stale pi refs` (every `*_pi_*` symbol renamed).

- [ ] **Step 6: Commit**

```bash
git add scripts/deploy.sh
git commit -m "feat(reasonix): port deploy.sh pi automation to Reasonix (SKIP_REASONIX)"
```

---

# Task 5: Neutralize the "Pi Agent API" settings label

**Files:**
- Modify: `frontend/src/i18n.ts` (zh + en), `app/static/index.html`
- Rebuild: `app/static/i18n.js`, `app/static/js/*` (via build)

> Keep i18n **key names** (`settings.piAgentApi`, etc.) — only change their **values** — so no `data-i18n`/TS references need updating. Do NOT touch `nav.piAgent`, `page.piAgent.*` (in-app "Pi 助手"), or `settings.agentToken*`.

- [ ] **Step 1: Update zh strings** in `frontend/src/i18n.ts`

Replace these zh values:
- `"settings.piAgentApi": "Pi Agent API",` → `"settings.piAgentApi": "外部 Agent API",`
- `"settings.piAgentDesc": '在同一台 VPS 上运行 <a href="https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent" target="_blank" rel="noopener">Pi Coding Agent</a> 时，用下方 Token 调用 CRM。Base URL：<code>http://127.0.0.1:8000</code>',`
  → `"settings.piAgentDesc": '让外部编码 agent（如 <a href="https://github.com/esengine/DeepSeek-Reasonix" target="_blank" rel="noopener">DeepSeek-Reasonix</a>）在同一台 VPS 上用下方 Token 调用 CRM。Base URL：<code>http://127.0.0.1:8000</code>',`
- `"settings.piInstallHint": "安装 Pi 扩展见仓库 <code>integrations/pi/README.md</code>",`
  → `"settings.piInstallHint": "集成步骤见仓库 <code>integrations/reasonix/README.md</code>",`
- `"msg.piAgentConfigured": "Pi Agent 已配置",` → `"msg.piAgentConfigured": "外部 Agent 已配置",`
- `"msg.confirmRegenerateToken": "重新生成后旧 Token 将立即失效，Pi Agent 需更新 SALESCRM_TOKEN。继续？",`
  → `"msg.confirmRegenerateToken": "重新生成后旧 Token 将立即失效，外部 Agent 需更新 SALESCRM_TOKEN。继续？",`

- [ ] **Step 2: Update en strings** in `frontend/src/i18n.ts`

- `"settings.piAgentApi": "Pi Agent API",` → `"settings.piAgentApi": "External Agent API",`
- `"settings.piAgentDesc": 'When running <a href="https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent" target="_blank" rel="noopener">Pi Coding Agent</a> on the same VPS, use the token below. Base URL: <code>http://127.0.0.1:8000</code>',`
  → `"settings.piAgentDesc": 'Let an external coding agent (e.g. <a href="https://github.com/esengine/DeepSeek-Reasonix" target="_blank" rel="noopener">DeepSeek-Reasonix</a>) on the same VPS call the CRM with the token below. Base URL: <code>http://127.0.0.1:8000</code>',`
- `"settings.piInstallHint": "See <code>integrations/pi/README.md</code> in the repo for Pi extension setup",`
  → `"settings.piInstallHint": "See <code>integrations/reasonix/README.md</code> in the repo for integration setup",`
- `"msg.piAgentConfigured": "Pi Agent configured",` → `"msg.piAgentConfigured": "External agent configured",`
- (en `msg.confirmRegenerateToken` does not mention Pi — leave as-is. Verify with `grep -n '"msg.confirmRegenerateToken"' frontend/src/i18n.ts` and only edit a line that contains "Pi".)

- [ ] **Step 3: Update inline legend text** in `app/static/index.html` (line ~734)

```html
                <legend data-i18n="settings.piAgentApi">外部 Agent API</legend>
```

- [ ] **Step 4: Rebuild and verify**

```bash
npm run check:frontend
git diff --exit-code -- app/static/i18n.js app/static/login.js app/static/js && echo "ARTIFACTS CLEAN"
grep -n "Pi Coding Agent\|pi-mono\|integrations/pi" frontend/src/i18n.ts && echo "STALE — fix" || echo "no stale pi refs in i18n"
```
Expected: build OK; after `git add` in Step 5 the artifacts are clean; no stale pi refs in i18n.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff format --check . && .venv/bin/pytest -q
git add frontend/src/i18n.ts app/static/index.html app/static/i18n.js app/static/js
git commit -m "feat(reasonix): neutralize 'Pi Agent API' settings label to External Agent API"
```

---

# Task 6: Delete `integrations/pi/` and fix references

**Files:**
- Delete: `integrations/pi/` (whole directory)
- Modify: `FEATURE_PLAN.md`

- [ ] **Step 1: Remove the pi integration package**

```bash
git rm -r integrations/pi
```

- [ ] **Step 2: Update `FEATURE_PLAN.md` line 41**

Replace:
```
| 20 | 外部 agent 集成 | done | Pi Agent API + integrations/pi 扩展包 |
```
with:
```
| 20 | 外部 agent 集成 | done | 外部 Agent API + integrations/reasonix（DeepSeek-Reasonix skill + salescrm CLI）|
```

- [ ] **Step 3: Verify no stale references remain**

```bash
grep -rn "integrations/pi\b\|pi-coding-agent\|@mariozechner/pi\|salescrm-pi" \
  --include="*.py" --include="*.ts" --include="*.sh" --include="*.md" --include="*.html" . \
  | grep -v "docs/superpowers/specs/2026-06-09" \
  || echo "no stale pi-integration references"
```
Expected: `no stale pi-integration references` (the spec doc may still mention the old path historically — that is fine).

- [ ] **Step 4: Full verification (mirror CI)**

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q && npm run check:frontend
git diff --exit-code -- app/static/i18n.js app/static/login.js app/static/js && echo "ARTIFACTS CLEAN"
bash -n scripts/deploy.sh && echo "deploy syntax OK"
```
All must pass / be clean.

- [ ] **Step 5: Commit + finalize**

```bash
git add -A
git commit -m "feat(reasonix): remove pi-coding-agent integration package"
```
Then offer the user merge/PR per `superpowers:finishing-a-development-branch`.

---

## Self-Review Notes

- **Spec coverage:** CLI request layer + 4 commands (T1,T2) · skill + sample config + README (T3) · executable bit (T3) · deploy.sh full port incl. `SKIP_REASONIX` (T4) · settings label rename zh+en + inline (T5) · delete `integrations/pi/` (T6) · FEATURE_PLAN reference (T6) · tests with monkeypatched HTTP (T1,T2) · no backend/`agent_routes`/`pi_*` changes (respected throughout). All spec sections map to a task.
- **No new runtime dependencies** (CLI is stdlib-only; no MCP).
- **CI guards:** frontend-touching task (T5) rebuilds artifacts + checks the built-artifact diff; the extensionless CLI is excluded from ruff by design and is covered by `tests/test_reasonix_cli.py`; deploy.sh checked via `bash -n`.
- **Out of scope (unchanged):** in-app "Pi 助手" (`nav.piAgent`/`page.piAgent.*`/`app/pi_*.py`), `/api/agent/*`, Agent Token generation.

# SMTP Throttled Email Sender Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add server-side SMTP sending with a rate-limited outbox (interval + daily cap + active hours), driven by Markdown email templates rendered to multipart text+html. Manual single sends stay `mailto:`.

**Architecture:** New `email_outbox` table + a dedicated throttled sender loop started in `lifespan` next to the scheduler. SMTP/cadence config lives in `settings_store`. Templates render server-side (Markdown → HTML + plain text). Reuses existing settings masking, scheduler loop pattern, contacts bulk bar, and `mark_contact_sent`.

**Tech Stack:** Python stdlib `smtplib`/`email`/`ssl` (no new deps), FastAPI, psycopg/Postgres, vanilla TS frontend. Markdown rendered by a small Python port of the frontend `renderMarkdown` (no new dep). Spec: `docs/superpowers/specs/2026-06-08-smtp-throttled-email-sender-design.md`.

**Conventions to follow:** Run `ruff check . && ruff format --check . && pytest -q && npm run check:frontend` before each commit (CI runs these + a `git diff --exit-code` on built `app/static/js`/`i18n.js`, so always rebuild the frontend before committing TS changes). i18n keys go in `frontend/src/i18n.ts` (source), never the compiled `app/static/i18n.js`. Tests use fake/monkeypatch, no real network/DB.

---

## File Structure

**Create:**
- `app/email_render.py` — variable substitution + Markdown→HTML; `render_email(template, contact) -> (subject, text, html)`.
- `app/email_sender.py` — throttle gate pure functions, `build_message`, `send_smtp`, the worker loop (`start_email_sender`/`stop_email_sender`).
- `tests/test_email_render.py`, `tests/test_email_sender.py`, `tests/test_email_outbox.py`.
- `frontend/src/js/modules/outbox.ts` — outbox view (list/pause/resume/retry/cancel) + enqueue modal handler.

**Modify:**
- `app/settings_store.py` — add SMTP/cadence keys to `DEFAULTS`, `smtp_password` to `SECRET_KEYS`.
- `app/database.py` — `email_outbox` DDL in `init_db()`; outbox CRUD functions.
- `app/main.py` — request models + routes (`/api/email/test`, `/api/email/queue`, `/api/email/outbox*`, `/api/email/sender/toggle`); start/stop sender in `lifespan`.
- `app/static/index.html` — SMTP form block in settings; "加入发送队列" button in contacts bulk bar; outbox view + nav entry.
- `frontend/src/js/modules/settings.ts` — SMTP fields in load/save payload + a "发送测试邮件" handler.
- `frontend/src/js/modules/contacts.ts` — "加入发送队列" handler opening the enqueue modal.
- `frontend/src/js/core/dom.ts` — element refs for new fields/buttons/view.
- `frontend/src/i18n.ts` — zh/en strings.
- `app/static/style.css` — outbox view + status badges + template preview.

---

# Phase 1 — SMTP config, test send, Markdown render

### Task 1: Markdown render module

**Files:**
- Create: `app/email_render.py`
- Test: `tests/test_email_render.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_email_render.py
from app.email_render import render_variables, markdown_to_html, render_email


def test_render_variables_single_brace():
    c = {"org": "ACME", "name": "Sam", "email": "s@a.com", "asn": 15169, "roles": "noc"}
    assert render_variables("Hi {name} at {org} (AS{asn})", c) == "Hi Sam at ACME (AS15169)"
    assert render_variables("{missing}", {}) == "{missing}"  # unknown left as-is


def test_markdown_basic():
    html = markdown_to_html("Hello **bold** and [link](https://x.com)")
    assert "<strong>bold</strong>" in html
    assert '<a href="https://x.com">link</a>' in html
    assert html.startswith("<p>")


def test_markdown_lists_and_escaping():
    html = markdown_to_html("- a\n- b")
    assert html.count("<li>") == 2 and "<ul>" in html
    assert "&lt;script&gt;" in markdown_to_html("<script>")  # html-escaped


def test_render_email_returns_triple():
    tmpl = {"subject": "Hi {name}", "body": "Dear {name},\n\n**Thanks**"}
    subject, text, html = render_email(tmpl, {"name": "Sam"})
    assert subject == "Hi Sam"
    assert text == "Dear Sam,\n\n**Thanks**"          # plain text = md source w/ vars
    assert "<strong>Thanks</strong>" in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_email_render.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `app/email_render.py`**

```python
from __future__ import annotations

import html as _html
import re


def render_variables(text: str, contact: dict) -> str:
    asn = str(contact.get("asn") or "")
    return (
        str(text or "")
        .replace("{org}", str(contact.get("org") or ""))
        .replace("{name}", str(contact.get("name") or ""))
        .replace("{email}", str(contact.get("email") or ""))
        .replace("{asn}", asn)
        .replace("{roles}", str(contact.get("roles") or ""))
    )


def _inline(text: str) -> str:
    out = _html.escape(text)
    out = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', out)
    return out


def markdown_to_html(text: str) -> str:
    out: list[str] = []
    list_tag: str | None = None

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append("</ul>" if list_tag == "ul" else "</ol>")
            list_tag = None

    for raw in str(text or "").split("\n"):
        line = raw.rstrip()
        m_ul = re.match(r"^[-*]\s+(.+)", line)
        m_ol = re.match(r"^\d+\.\s+(.+)", line)
        m_h = re.match(r"^(#{1,3})\s+(.+)", line)
        if m_ul:
            if list_tag != "ul":
                close_list()
                out.append("<ul>")
                list_tag = "ul"
            out.append(f"<li>{_inline(m_ul.group(1))}</li>")
        elif m_ol:
            if list_tag != "ol":
                close_list()
                out.append("<ol>")
                list_tag = "ol"
            out.append(f"<li>{_inline(m_ol.group(1))}</li>")
        elif m_h:
            close_list()
            level = len(m_h.group(1))
            out.append(f"<h{level}>{_inline(m_h.group(2))}</h{level}>")
        elif line.strip() == "":
            close_list()
        else:
            close_list()
            out.append(f"<p>{_inline(line)}</p>")
    close_list()
    return "".join(out)


def render_email(template: dict, contact: dict) -> tuple[str, str, str]:
    """Return (subject, plain_text, html). Plain text is the variable-substituted
    Markdown source (readable as-is); html is the rendered version."""
    subject = render_variables(template.get("subject", ""), contact)
    text = render_variables(template.get("body", ""), contact)
    return subject, text, markdown_to_html(text)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_email_render.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
ruff format app/email_render.py tests/test_email_render.py
git add app/email_render.py tests/test_email_render.py
git commit -m "feat(email): markdown render + variable substitution for templates"
```

---

### Task 2: SMTP send + throttle gates

**Files:**
- Create: `app/email_sender.py`
- Test: `tests/test_email_sender.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_email_sender.py
from datetime import datetime, timedelta, timezone

from app import email_sender


def test_active_hours_window():
    base = datetime(2026, 6, 8, 12, tzinfo=timezone.utc)
    assert email_sender.within_active_hours(base, 9, 18) is True
    assert email_sender.within_active_hours(base.replace(hour=20), 9, 18) is False
    assert email_sender.within_active_hours(base, 0, 0) is True  # 0==0 => 24h
    assert email_sender.within_active_hours(base.replace(hour=23), 22, 6) is True  # overnight


def test_interval_and_cap_gates():
    now = datetime(2026, 6, 8, 12, tzinfo=timezone.utc)
    assert email_sender.interval_elapsed(None, now, 5) is True
    assert email_sender.interval_elapsed(now - timedelta(minutes=6), now, 5) is True
    assert email_sender.interval_elapsed(now - timedelta(minutes=2), now, 5) is False
    assert email_sender.under_daily_cap(3, 50) is True
    assert email_sender.under_daily_cap(50, 50) is False
    assert email_sender.under_daily_cap(999, 0) is True  # 0 => unlimited


def test_build_message_multipart():
    settings = {"from_name": "Ops", "from_email": "ops@a.com"}
    row = {"to_email": "x@y.com", "subject": "Hi", "body_text": "plain", "body_html": "<p>rich</p>"}
    msg = email_sender.build_message(settings, row)
    assert msg["To"] == "x@y.com"
    assert msg["From"] == "Ops <ops@a.com>"
    assert msg["Subject"] == "Hi"
    assert msg.get_content_type() == "multipart/alternative"
    parts = [p.get_content_type() for p in msg.iter_parts()]
    assert "text/plain" in parts and "text/html" in parts


def test_send_smtp_starttls_path(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=20):
            calls.append(("ctor", host, port))

        def starttls(self, context=None):
            calls.append(("starttls",))

        def login(self, u, p):
            calls.append(("login", u))

        def send_message(self, msg):
            calls.append(("send", msg["To"]))

        def quit(self):
            calls.append(("quit",))

    monkeypatch.setattr(email_sender.smtplib, "SMTP", FakeSMTP)
    settings = {
        "smtp_host": "h", "smtp_port": "587", "smtp_security": "starttls",
        "smtp_username": "u", "smtp_password": "p",
    }
    msg = email_sender.build_message({"from_email": "o@a.com"}, {"to_email": "x@y.com", "subject": "s", "body_text": "t", "body_html": ""})
    email_sender.send_smtp(settings, msg)
    kinds = [c[0] for c in calls]
    assert kinds == ["ctor", "starttls", "login", "send", "quit"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_email_sender.py -q` → FAIL (module not found).

- [ ] **Step 3: Implement gates + send in `app/email_sender.py`** (worker loop added in Task 8; this step is the testable core)

```python
from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr

logger = logging.getLogger(__name__)


def within_active_hours(now: datetime, start_hour: int, end_hour: int) -> bool:
    if start_hour == end_hour:
        return True
    hour = now.hour
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour  # overnight window


def interval_elapsed(last_sent_at: datetime | None, now: datetime, interval_minutes: int) -> bool:
    if last_sent_at is None:
        return True
    return (now - last_sent_at).total_seconds() >= max(1, interval_minutes) * 60


def under_daily_cap(sent_today: int, cap: int) -> bool:
    return cap <= 0 or sent_today < cap


def build_message(settings: dict, row: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = row.get("subject") or ""
    msg["From"] = formataddr((settings.get("from_name") or "", settings.get("from_email") or ""))
    msg["To"] = row["to_email"]
    msg.set_content(row.get("body_text") or "")
    if (row.get("body_html") or "").strip():
        msg.add_alternative(row["body_html"], subtype="html")
    return msg


def send_smtp(settings: dict, msg: EmailMessage) -> None:
    host = settings["smtp_host"]
    port = int(settings.get("smtp_port") or 587)
    security = (settings.get("smtp_security") or "starttls").lower()
    username = settings.get("smtp_username") or ""
    password = settings.get("smtp_password") or ""
    context = ssl.create_default_context()
    if security == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=20)
    try:
        if security == "starttls":
            server.starttls(context=context)
        if username:
            server.login(username, password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 - already sending best-effort
            pass
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_email_sender.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
ruff format app/email_sender.py tests/test_email_sender.py
git add app/email_sender.py tests/test_email_sender.py
git commit -m "feat(email): smtp send + throttle gate functions"
```

---

### Task 3: SMTP settings keys

**Files:**
- Modify: `app/settings_store.py` (`DEFAULTS` ~line 21-56, `SECRET_KEYS` ~line 8-19)

- [ ] **Step 1: Add keys to `DEFAULTS`** (insert before the closing `}`)

```python
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_security": "starttls",
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from_name": "",
    "smtp_from_email": "",
    "email_sender_enabled": "0",
    "email_send_interval_minutes": "5",
    "email_daily_cap": "50",
    "email_active_start_hour": "9",
    "email_active_end_hour": "18",
```

- [ ] **Step 2: Add `smtp_password` to `SECRET_KEYS`** (add the line inside the set)

```python
    "smtp_password",
```

- [ ] **Step 3: Verify masking works**

Run: `python -c "from app.settings_store import SECRET_KEYS, DEFAULTS; assert 'smtp_password' in SECRET_KEYS; assert DEFAULTS['smtp_security']=='starttls'; print('ok')"`
Expected: `ok`. (No new test file; covered by existing settings behavior + Task 5 endpoint test.)

- [ ] **Step 4: Commit**

```bash
git add app/settings_store.py
git commit -m "feat(email): smtp + cadence settings keys (password masked)"
```

---

### Task 4: Test-send endpoint

**Files:**
- Modify: `app/main.py` (request models near other `BaseModel`s ~line 164+; routes near other settings routes ~line 471-482)
- Test: `tests/test_email_routes.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_email_routes.py
import app.main as main


async def test_email_test_uses_form_values_and_saved_password_fallback(monkeypatch):
    sent = {}

    def fake_send(settings, msg):
        sent["settings"] = settings
        sent["to"] = msg["To"]

    monkeypatch.setattr(main, "send_smtp", fake_send)
    monkeypatch.setattr(main, "build_message", lambda s, r: type("M", (), {"__getitem__": lambda self, k: r["to_email"]})())
    monkeypatch.setattr(main, "get_setting", lambda key, default="": "SAVEDPASS" if key == "smtp_password" else default)

    body = main.EmailTestRequest(to="x@y.com", host="h", port="587", security="starttls",
                                 username="u", password="", from_name="O", from_email="o@a.com")
    result = await main.send_test_email(body, {"id": 1})
    assert result["ok"] is True
    assert sent["settings"]["smtp_password"] == "SAVEDPASS"  # blank => saved fallback
    assert sent["to"] == "x@y.com"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_email_routes.py -q` → FAIL (`EmailTestRequest`/`send_test_email` missing).

- [ ] **Step 3: Implement model + route in `app/main.py`**

Add near the imports at top (with other `from app.X import`):
```python
from app.email_sender import build_message, send_smtp
```
Add request model (with the other `BaseModel`s):
```python
class EmailTestRequest(BaseModel):
    to: str
    host: str = ""
    port: str = "587"
    security: str = "starttls"
    username: str = ""
    password: str = ""
    from_name: str = ""
    from_email: str = ""
```
Add route (after the lead-preferences routes ~line 482):
```python
@app.post("/api/email/test")
async def send_test_email(body: EmailTestRequest, user: CurrentUser) -> dict:
    password = body.password.strip() or get_setting("smtp_password", "")
    settings = {
        "smtp_host": body.host.strip(),
        "smtp_port": body.port.strip() or "587",
        "smtp_security": body.security.strip() or "starttls",
        "smtp_username": body.username.strip(),
        "smtp_password": password,
        "from_name": body.from_name.strip(),
        "from_email": body.from_email.strip() or body.username.strip(),
    }
    if not settings["smtp_host"] or not settings["from_email"]:
        raise HTTPException(status_code=400, detail="请先填写 SMTP 服务器与发件邮箱")
    row = {
        "to_email": body.to.strip(),
        "subject": "Sales CRM SMTP 测试邮件",
        "body_text": "这是一封来自 Sales CRM 的 SMTP 测试邮件，收到说明配置可用。",
        "body_html": "<p>这是一封来自 Sales CRM 的 SMTP 测试邮件，收到说明配置可用。</p>",
    }
    try:
        msg = build_message(settings, row)
        await asyncio.to_thread(send_smtp, settings, msg)
    except Exception as exc:  # noqa: BLE001 - surface SMTP errors to the operator
        return {"ok": False, "error": str(exc)[:300]}
    return {"ok": True}
```
> `get_setting`, `asyncio`, `HTTPException` are already imported in `main.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_email_routes.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
ruff format app/main.py tests/test_email_routes.py
git add app/main.py tests/test_email_routes.py
git commit -m "feat(email): POST /api/email/test (form values, saved-password fallback)"
```

---

### Task 5: SMTP settings form + test button (frontend)

**Files:**
- Modify: `app/static/index.html` (settings AI section), `frontend/src/js/modules/settings.ts`, `frontend/src/js/core/dom.ts`, `frontend/src/i18n.ts`, `app/static/style.css`

- [ ] **Step 1: Add the SMTP form block** in `app/static/index.html` inside the settings view (after the AI/search block; mirror existing `.field` markup). Fields with ids: `smtp-host`, `smtp-port`, `smtp-security` (select none/ssl/starttls), `smtp-username`, `smtp-password` (type=password, `data-i18n-placeholder` for masked hint), `smtp-from-name`, `smtp-from-email`, plus cadence inputs `email-send-interval-minutes`, `email-daily-cap`, `email-active-start-hour`, `email-active-end-hour`, and `email-sender-enabled` (checkbox). Add a test row: `<input id="smtp-test-to">` + `<button id="smtp-test-btn" type="button" class="secondary-btn">` + `<span id="smtp-test-result" class="stats">`.

- [ ] **Step 2: Add dom refs** in `frontend/src/js/core/dom.ts` (mirror existing `getElementById` exports) for each id above.

- [ ] **Step 3: Wire load/save** in `frontend/src/js/modules/settings.ts`:
  - In `loadSettingsForm()` (after `const data = await api("/api/settings")`), set each SMTP field's value from `data` (`smtp-password` uses `data.smtp_password` masked + leave blank-to-keep behavior).
  - In `saveSettings()`'s payload, include all SMTP/cadence keys (skip `smtp_password` if unchanged/blank, matching the existing API-key pattern).

- [ ] **Step 4: Add the test handler** in `settings.ts`:

```typescript
export async function sendSmtpTest() {
  const to = (smtpTestTo?.value || "").trim();
  if (!to) { notifyInfo(t("email.testNeedTo")); return; }
  smtpTestResult.textContent = t("email.testSending");
  try {
    const data = await api("/api/email/test", {
      method: "POST",
      body: JSON.stringify({
        to,
        host: smtpHost.value, port: smtpPort.value, security: smtpSecurity.value,
        username: smtpUsername.value, password: smtpPassword.value,
        from_name: smtpFromName.value, from_email: smtpFromEmail.value,
      }),
    });
    smtpTestResult.textContent = data.ok ? t("email.testOk") : t("email.testFail", { error: data.error || "" });
  } catch (error) {
    smtpTestResult.textContent = t("email.testFail", { error: errorMessage(error, "") });
  }
}
```
Bind `smtpTestBtn?.addEventListener("click", () => sendSmtpTest().catch(() => {}))` in settings init.

- [ ] **Step 5: i18n** — add to `frontend/src/i18n.ts` (zh + en): `email.testNeedTo`, `email.testSending`, `email.testOk`, `email.testFail` ("发送失败：{error}"), plus labels `email.smtpTitle`, `email.host`, `email.port`, `email.security`, `email.username`, `email.password`, `email.fromName`, `email.fromEmail`, `email.testBtn`, and cadence labels. No em dashes in English copy.

- [ ] **Step 6: Build + verify + commit**

```bash
npm run check:frontend
ruff format --check . && pytest -q
git add app/static frontend/src
git commit -m "feat(email): smtp settings form + test-send button"
```

---

# Phase 2 — Outbox table, enqueue, sender worker

### Task 6: `email_outbox` table + DB functions

**Files:**
- Modify: `app/database.py` (DDL in `init_db()` ~after line 294 email_templates; functions near other contact functions)
- Test: `tests/test_email_outbox.py`

- [ ] **Step 1: Write the failing test** (functions accept a `conn` for fakeability, mirroring `dedupe_contacts`)

```python
# tests/test_email_outbox.py
from app import database


class _Cur:
    def __init__(self, rows=None, one=None):
        self._rows, self._one = rows or [], one
    def fetchall(self): return self._rows
    def fetchone(self): return self._one


class _Conn:
    def __init__(self):
        self.execs = []
        self.next_one = None
        self.next_all = []
    def execute(self, sql, params=None):
        self.execs.append((" ".join(sql.split()), params))
        verb = " ".join(sql.split()).upper()
        if "RETURNING" in verb or verb.startswith("SELECT"):
            return _Cur(rows=self.next_all, one=self.next_one)
        return _Cur()


def test_count_sent_today_uses_user_and_date(monkeypatch):
    conn = _Conn(); conn.next_one = {"n": 7}
    assert database.count_sent_emails_today(1, conn=conn) == 7
    assert any("status = 'sent'" in e[0] or "status='sent'" in e[0].replace(" ", "") for e in conn.execs)


def test_claim_next_queued_marks_sending(monkeypatch):
    conn = _Conn(); conn.next_one = {"id": 5, "to_email": "x@y.com", "subject": "s",
                                     "body_text": "t", "body_html": "", "contact_id": 9, "attempts": 0}
    row = database.claim_next_queued_email(conn=conn)
    assert row["id"] == 5
    joined = " ".join(e[0] for e in conn.execs)
    assert "SKIP LOCKED" in joined and "status = 'sending'" in joined.replace("='", "= '")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_email_outbox.py -q` → FAIL.

- [ ] **Step 3a: Add DDL** in `init_db()` (after the `email_templates` `CREATE TABLE` block):

```python
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_outbox (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
                template_id INTEGER,
                to_email TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                body_text TEXT NOT NULL DEFAULT '',
                body_html TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_outbox_claim "
            "ON email_outbox (status, scheduled_at)"
        )
```

- [ ] **Step 3b: Add functions** in `app/database.py` (each takes optional `conn`, mirroring `dedupe_contacts`/`get_conn` pattern):

```python
def enqueue_email(user_id, contact_id, template_id, to_email, subject, body_text, body_html, *, conn=None):
    def run(c):
        return c.execute(
            """
            INSERT INTO email_outbox
              (user_id, contact_id, template_id, to_email, subject, body_text, body_html)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """,
            (user_id, contact_id, template_id, to_email, subject, body_text, body_html),
        ).fetchone()["id"]
    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def email_queued_addresses(user_id, *, conn=None) -> set[str]:
    def run(c):
        rows = c.execute(
            "SELECT lower(to_email) AS e FROM email_outbox "
            "WHERE user_id=%s AND status IN ('queued','sending')",
            (user_id,),
        ).fetchall()
        return {r["e"] for r in rows}
    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def count_sent_emails_today(user_id, *, conn=None) -> int:
    def run(c):
        row = c.execute(
            "SELECT COUNT(*) AS n FROM email_outbox "
            "WHERE user_id=%s AND status = 'sent' AND sent_at::date = NOW()::date",
            (user_id,),
        ).fetchone()
        return int(row["n"]) if row else 0
    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def last_sent_email_at(user_id, *, conn=None):
    def run(c):
        row = c.execute(
            "SELECT MAX(sent_at) AS t FROM email_outbox WHERE user_id=%s AND status='sent'",
            (user_id,),
        ).fetchone()
        return row["t"] if row else None
    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def claim_next_queued_email(user_id=None, *, conn=None):
    where = "WHERE user_id=%s AND status='queued'" if user_id is not None else "WHERE status='queued'"
    params = (user_id,) if user_id is not None else ()
    sql = f"""
        UPDATE email_outbox SET status='sending', updated_at=NOW()
        WHERE id = (
            SELECT id FROM email_outbox {where}
            ORDER BY scheduled_at ASC FOR UPDATE SKIP LOCKED LIMIT 1
        )
        RETURNING id, user_id, contact_id, to_email, subject, body_text, body_html, attempts
    """
    def run(c):
        return c.execute(sql, params).fetchone()
    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def mark_email_sent(email_id, *, conn=None):
    def run(c):
        c.execute("UPDATE email_outbox SET status='sent', sent_at=NOW(), updated_at=NOW() WHERE id=%s", (email_id,))
    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def mark_email_failed(email_id, error, requeue, *, conn=None):
    status = "queued" if requeue else "failed"
    def run(c):
        c.execute(
            "UPDATE email_outbox SET status=%s, attempts=attempts+1, last_error=%s, updated_at=NOW() WHERE id=%s",
            (status, str(error)[:500], email_id),
        )
    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def list_outbox(user_id, status=None, limit=200):
    where = "WHERE user_id=%s" + (" AND status=%s" if status else "")
    params = (user_id, status) if status else (user_id,)
    with get_conn() as c:
        rows = c.execute(
            f"SELECT id, contact_id, to_email, subject, status, attempts, last_error, "
            f"scheduled_at, sent_at FROM email_outbox {where} ORDER BY scheduled_at DESC LIMIT {int(limit)}",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def update_outbox_status(user_id, email_id, status):
    with get_conn() as c:
        c.execute(
            "UPDATE email_outbox SET status=%s, updated_at=NOW() WHERE id=%s AND user_id=%s",
            (status, email_id, user_id),
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_email_outbox.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
ruff format app/database.py tests/test_email_outbox.py
git add app/database.py tests/test_email_outbox.py
git commit -m "feat(email): email_outbox table + queue/claim/status db functions"
```

---

### Task 7: Enqueue endpoint + contacts bulk action

**Files:**
- Modify: `app/main.py` (model + route), `frontend/src/js/modules/contacts.ts`, `app/static/index.html` (bulk bar button + enqueue modal), `frontend/src/js/core/dom.ts`, `frontend/src/i18n.ts`
- Test: extend `tests/test_email_routes.py`

- [ ] **Step 1: Write the failing test**

```python
async def test_queue_renders_and_skips(monkeypatch):
    import app.main as main
    contacts = {1: {"id": 1, "email": "a@x.com", "name": "A", "org": "X"},
                2: {"id": 2, "email": "", "name": "B"}}  # no email -> skipped
    enq = []
    monkeypatch.setattr(main, "get_contact", lambda uid, cid: contacts.get(cid))
    monkeypatch.setattr(main, "get_email_template", lambda uid, tid: {"subject": "Hi {name}", "body": "**Yo** {org}"})
    monkeypatch.setattr(main, "email_queued_addresses", lambda uid: set())
    monkeypatch.setattr(main, "enqueue_email", lambda *a, **k: enq.append(a) or len(enq))
    body = main.EmailQueueRequest(contact_ids=[1, 2], template_id=10, skip_sent=True)
    result = await main.queue_emails(body, {"id": 1})
    assert result["queued"] == 1
    assert result["skipped"]["no_email"] == 1
    # rendered subject/body present in the enqueue call
    assert any("Hi A" in str(a) for a in enq[0])
```

- [ ] **Step 2: Run to verify it fails** → `pytest tests/test_email_routes.py -q` FAIL.

- [ ] **Step 3: Implement** in `app/main.py`:

Add imports: `from app.email_render import render_email` and from `app.database` add `get_contact, enqueue_email, email_queued_addresses` (and `get_email_template` — confirm/import the existing single-template getter; if absent, add `get_email_template(user_id, template_id)` to `database.py` mirroring `list_email_templates`).
```python
class EmailQueueRequest(BaseModel):
    contact_ids: list[int]
    template_id: int
    skip_sent: bool = True


@app.post("/api/email/queue")
async def queue_emails(body: EmailQueueRequest, user: CurrentUser) -> dict:
    uid = user["id"]
    template = get_email_template(uid, body.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    already = email_queued_addresses(uid)
    queued = 0
    skipped = {"no_email": 0, "duplicate": 0, "already_sent": 0}
    for cid in body.contact_ids:
        contact = get_contact(uid, cid)
        if not contact or not (contact.get("email") or "").strip():
            skipped["no_email"] += 1
            continue
        email = contact["email"].strip()
        if email.lower() in already:
            skipped["duplicate"] += 1
            continue
        if body.skip_sent and contact.get("email_sent"):
            skipped["already_sent"] += 1
            continue
        subject, text, html = render_email(template, contact)
        enqueue_email(uid, cid, body.template_id, email, subject, text, html)
        already.add(email.lower())
        queued += 1
    return {"queued": queued, "skipped": skipped}
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Frontend** — add a "加入发送队列" button to the contacts bulk bar (`#contacts-bulk-bar` in `index.html`, after 标记已发). Add a small enqueue modal (template `<select>` + "跳过已发" checkbox + confirm). Handler in `contacts.ts`:

```typescript
export async function enqueueSelectedForSend(templateId, skipSent) {
  const contactIds = getSelectedContactIds();
  if (!contactIds.length) { notifyInfo(t("contacts.selectFirst")); return; }
  try {
    const data = await api("/api/email/queue", {
      method: "POST",
      body: JSON.stringify({ contact_ids: contactIds, template_id: Number(templateId), skip_sent: skipSent }),
    });
    showApiSuccess(t("email.queued", { n: data.queued }));
  } catch (error) { showApiError(error, t("email.queueFailed")); }
}
```
Add i18n keys `email.queued` ("已加入队列 {n} 封"), `email.queueFailed`, plus the bulk button label `contacts.addToQueue`.

- [ ] **Step 6: Build + verify + commit**

```bash
npm run check:frontend && ruff format --check . && pytest -q
git add app/main.py app/database.py app/static frontend/src tests/test_email_routes.py
git commit -m "feat(email): enqueue endpoint + contacts bulk add-to-queue"
```

---

### Task 8: Sender worker loop

**Files:**
- Modify: `app/email_sender.py` (add loop + start/stop), `app/main.py` (`lifespan` start/stop)
- Test: extend `tests/test_email_sender.py`

- [ ] **Step 1: Write the failing test** (the per-tick decision is a pure function so it's unit-testable without the loop)

```python
def test_sender_tick_respects_gates(monkeypatch):
    from app import email_sender as es
    # settings: enabled, interval 5, cap 50, hours 0-0 (24h)
    settings = {"email_sender_enabled": "1", "email_send_interval_minutes": "5",
                "email_daily_cap": "50", "email_active_start_hour": "0", "email_active_end_hour": "0",
                "smtp_host": "h", "smtp_from_email": "o@a.com"}
    claimed = {"row": {"id": 1, "user_id": 1, "to_email": "x@y.com", "subject": "s",
                       "body_text": "t", "body_html": "", "contact_id": 5, "attempts": 0}}
    actions = []
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    monkeypatch.setattr(es, "count_sent_emails_today", lambda uid=None: 0)
    monkeypatch.setattr(es, "last_sent_email_at", lambda uid=None: None)
    monkeypatch.setattr(es, "claim_next_queued_email", lambda: claimed["row"])
    monkeypatch.setattr(es, "send_smtp", lambda s, m: actions.append("sent"))
    monkeypatch.setattr(es, "mark_email_sent", lambda eid: actions.append(("done", eid)))
    monkeypatch.setattr(es, "mark_contact_sent", lambda uid, cid, sent=True: actions.append(("contact", cid)))

    import asyncio
    asyncio.get_event_loop().run_until_complete(es.sender_tick())
    assert "sent" in actions and ("done", 1) in actions and ("contact", 5) in actions
```

- [ ] **Step 2: Run to verify it fails** → FAIL (`sender_tick` missing).

- [ ] **Step 3: Implement loop in `app/email_sender.py`** (add imports + functions)

```python
import asyncio
from datetime import datetime, timezone

from app.database import (
    claim_next_queued_email,
    count_sent_emails_today,
    last_sent_email_at,
    mark_contact_sent,
    mark_email_failed,
    mark_email_sent,
    update_settings_disable_sender,  # see note below
)
from app.settings_store import get_settings, update_settings

_MAX_ATTEMPTS = 3
_sender_task: "asyncio.Task | None" = None


def _int(settings, key, default):
    try:
        return int(settings.get(key) or default)
    except (TypeError, ValueError):
        return default


async def sender_tick() -> None:
    settings = get_settings()
    if (settings.get("email_sender_enabled") or "0") == "0":
        return
    if not (settings.get("smtp_host") or "").strip():
        return
    now = datetime.now(timezone.utc)
    if not within_active_hours(now, _int(settings, "email_active_start_hour", 9),
                               _int(settings, "email_active_end_hour", 18)):
        return
    if not interval_elapsed(last_sent_email_at(), now, _int(settings, "email_send_interval_minutes", 5)):
        return
    if not under_daily_cap(count_sent_emails_today(), _int(settings, "email_daily_cap", 50)):
        return
    row = claim_next_queued_email()
    if not row:
        return
    smtp = {
        "smtp_host": settings["smtp_host"], "smtp_port": settings.get("smtp_port", "587"),
        "smtp_security": settings.get("smtp_security", "starttls"),
        "smtp_username": settings.get("smtp_username", ""), "smtp_password": settings.get("smtp_password", ""),
        "from_name": settings.get("smtp_from_name", ""),
        "from_email": settings.get("smtp_from_email") or settings.get("smtp_username", ""),
    }
    try:
        msg = build_message(smtp, row)
        await asyncio.to_thread(send_smtp, smtp, msg)
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPConnectError, ConnectionError, OSError) as exc:
        # config-level failure: requeue this item and pause the sender
        mark_email_failed(row["id"], str(exc), requeue=True)
        update_settings({"email_sender_enabled": "0"})
        logger.warning("Email sender paused after config error: %s", exc)
        return
    except Exception as exc:  # noqa: BLE001 - per-item failure, retry then fail
        requeue = int(row.get("attempts", 0)) + 1 < _MAX_ATTEMPTS
        mark_email_failed(row["id"], str(exc), requeue=requeue)
        return
    mark_email_sent(row["id"])
    if row.get("contact_id"):
        try:
            mark_contact_sent(row["user_id"], row["contact_id"], sent=True)
        except Exception:  # noqa: BLE001
            pass


async def _sender_loop() -> None:
    logger.info("Email sender started")
    while True:
        try:
            await sender_tick()
        except Exception:  # noqa: BLE001
            logger.exception("Email sender tick failed")
        await asyncio.sleep(60)


async def start_email_sender() -> None:
    global _sender_task
    if _sender_task is None or _sender_task.done():
        _sender_task = asyncio.create_task(_sender_loop())


async def stop_email_sender() -> None:
    global _sender_task
    if _sender_task is not None:
        _sender_task.cancel()
        try:
            await _sender_task
        except asyncio.CancelledError:
            pass
        _sender_task = None
```
> Remove the bogus `update_settings_disable_sender` import (use `update_settings({"email_sender_enabled": "0"})` as shown). `mark_contact_sent` already exists in `database.py`.

- [ ] **Step 4: Start/stop in `lifespan`** (`app/main.py`): import `start_email_sender, stop_email_sender`; in `lifespan`, after `await start_scheduler()` add `await start_email_sender()`, and add `await stop_email_sender()` to the shutdown side (after `yield`).

- [ ] **Step 5: Run to verify it passes** → `pytest tests/test_email_sender.py -q` PASS.

- [ ] **Step 6: Commit**

```bash
ruff format app/email_sender.py app/main.py tests/test_email_sender.py
git add app/email_sender.py app/main.py tests/test_email_sender.py
git commit -m "feat(email): throttled sender worker loop (interval/cap/active-hours, retry, pause)"
```

---

# Phase 3 — Outbox UI + polish

### Task 9: Outbox endpoints + view

**Files:**
- Modify: `app/main.py` (routes), create `frontend/src/js/modules/outbox.ts`, `app/static/index.html` (outbox view + nav), `frontend/src/js/core/dom.ts`, `frontend/src/i18n.ts`, `app/static/style.css`

- [ ] **Step 1: Add routes** in `app/main.py` (using Task 6 db functions):

```python
@app.get("/api/email/outbox")
def get_outbox(user: CurrentUser, status: str | None = None) -> dict:
    return {"items": list_outbox(user["id"], status=status)}


@app.post("/api/email/outbox/{email_id}/cancel")
def cancel_outbox(email_id: int, user: CurrentUser) -> dict:
    update_outbox_status(user["id"], email_id, "cancelled")
    return {"ok": True}


@app.post("/api/email/outbox/{email_id}/retry")
def retry_outbox(email_id: int, user: CurrentUser) -> dict:
    update_outbox_status(user["id"], email_id, "queued")
    return {"ok": True}


class SenderToggleRequest(BaseModel):
    enabled: bool


@app.post("/api/email/sender/toggle")
def toggle_sender(body: SenderToggleRequest, _: CurrentUser) -> dict:
    update_settings({"email_sender_enabled": "1" if body.enabled else "0"})
    return {"ok": True, "enabled": body.enabled}
```
Import `list_outbox, update_outbox_status` from `app.database`; `update_settings` from `app.settings_store`.

- [ ] **Step 2: Outbox view** — add a "发送队列" nav entry + `#outbox-view` panel in `index.html` (mirror an existing list view like schedules). Render in `frontend/src/js/modules/outbox.ts`:

```typescript
import { api } from "../core/utils.js";
import { t } from "../../i18n.js";

export async function loadOutbox(status = "") {
  const data = await api(`/api/email/outbox${status ? `?status=${status}` : ""}`);
  renderOutbox(data.items || []);
}

export function renderOutbox(items) {
  // counts by status + a table: to_email · subject · status badge · attempts · actions(cancel/retry)
  // status badge classes: queued/sending=caution, sent=positive, failed/cancelled=danger (reuse status-badge styles)
}
```
Wire pause/resume to `/api/email/sender/toggle`, cancel/retry to the per-id endpoints, then `loadOutbox()` to refresh. Poll every ~15s while the view is active (mirror jobs polling).

- [ ] **Step 3: i18n + styles** — `email.outboxTitle`, status labels, `email.pause`/`email.resume`/`email.retry`/`email.cancel`, counts. Reuse existing `.status-badge` styles; add minimal CSS only if needed.

- [ ] **Step 4: Build + verify + commit**

```bash
npm run check:frontend && ruff format --check . && pytest -q
git add app/main.py app/static frontend/src
git commit -m "feat(email): outbox view (counts, pause/resume, retry/cancel)"
```

---

### Task 10: Template Markdown preview + finalize

**Files:**
- Modify: `frontend/src/js/modules/settings.ts` (or wherever the template editor lives — `contacts.ts` `renderEmailTemplatesList`), `app/static/index.html`, `app/static/style.css`, `frontend/src/i18n.ts`

- [ ] **Step 1: Add a live Markdown preview** next to the template body textarea: on `input`, render `renderMarkdown(renderTemplateText(body, sampleContact))` (reuse the existing `renderMarkdown` from `pi.ts` — export it or copy a shared helper) into a `.template-preview` panel. Add a one-line hint that the body supports Markdown + `{org}/{name}/{email}/{asn}/{roles}` variables, and a deliverability note (SPF/DKIM/DMARC) under the SMTP form.

- [ ] **Step 2: Full verification** (mirror CI exactly)

```bash
ruff check . && ruff format --check . && pytest -q && npm run check:frontend
git diff --exit-code -- app/static/i18n.js app/static/login.js app/static/js   # built artifacts current
```
All must pass / be clean.

- [ ] **Step 3: Commit + finalize**

```bash
git add app/static frontend/src
git commit -m "feat(email): markdown template preview + deliverability hint"
```
Then offer the user merge/PR per `superpowers:finishing-a-development-branch`.

---

## Self-Review Notes

- **Spec coverage:** SMTP settings (T3,T5) · test send before save (T4,T5) · markdown multipart (T1,T8) · outbox table (T6) · enqueue + skip rules (T7) · throttle interval/cap/active-hours (T2,T8) · claim-lock/no-double-send (T6) · retry + config-error pause (T8) · outbox UI pause/resume/retry/cancel (T9) · security masking (T3) · deliverability hint (T10) · tests throughout. All spec sections map to a task.
- **No new dependencies** (stdlib smtplib/email/ssl; markdown ported).
- **CI guards:** every commit step pairs with `ruff format` + (for frontend) `npm run check:frontend` so the built-artifact diff + format checks stay green.
- **Known follow-ups (out of scope, in spec §2 non-goals):** open/click tracking, unsubscribe, WYSIWYG, at-rest password encryption.

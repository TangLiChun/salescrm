from datetime import UTC, datetime, timedelta

from app import email_sender


def test_active_hours_window():
    base = datetime(2026, 6, 8, 12, tzinfo=UTC)
    assert email_sender.within_active_hours(base, 9, 18) is True
    assert email_sender.within_active_hours(base.replace(hour=20), 9, 18) is False
    assert email_sender.within_active_hours(base, 0, 0) is True  # 0==0 => 24h
    assert email_sender.within_active_hours(base.replace(hour=23), 22, 6) is True  # overnight


def test_interval_and_cap_gates():
    now = datetime(2026, 6, 8, 12, tzinfo=UTC)
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
        "smtp_host": "h",
        "smtp_port": "587",
        "smtp_security": "starttls",
        "smtp_username": "u",
        "smtp_password": "p",
    }
    msg = email_sender.build_message(
        {"from_email": "o@a.com"},
        {"to_email": "x@y.com", "subject": "s", "body_text": "t", "body_html": ""},
    )
    email_sender.send_smtp(settings, msg)
    kinds = [c[0] for c in calls]
    assert kinds == ["ctor", "starttls", "login", "send", "quit"]


def test_sender_tick_respects_gates(monkeypatch):
    from app import email_sender as es

    # settings: enabled, interval 5, cap 50, hours 0-0 (24h)
    settings = {
        "email_sender_enabled": "1",
        "email_send_interval_minutes": "5",
        "email_daily_cap": "50",
        "email_active_start_hour": "0",
        "email_active_end_hour": "0",
        "smtp_host": "h",
        "smtp_from_email": "o@a.com",
    }
    claimed = {
        "row": {
            "id": 1,
            "user_id": 1,
            "to_email": "x@y.com",
            "subject": "s",
            "body_text": "t",
            "body_html": "",
            "contact_id": 5,
            "attempts": 0,
        }
    }
    actions = []
    monkeypatch.setattr(es, "get_settings", lambda: settings)
    monkeypatch.setattr(es, "count_sent_emails_today", lambda uid=None: 0)
    monkeypatch.setattr(es, "last_sent_email_at", lambda uid=None: None)
    monkeypatch.setattr(es, "claim_next_queued_email", lambda: claimed["row"])
    monkeypatch.setattr(es, "send_smtp", lambda s, m: actions.append("sent"))
    monkeypatch.setattr(es, "mark_email_sent", lambda eid: actions.append(("done", eid)))
    monkeypatch.setattr(
        es, "mark_contact_sent", lambda uid, cid, sent=True: actions.append(("contact", cid))
    )

    import asyncio

    asyncio.run(es.sender_tick())
    assert "sent" in actions and ("done", 1) in actions and ("contact", 5) in actions

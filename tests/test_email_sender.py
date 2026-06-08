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

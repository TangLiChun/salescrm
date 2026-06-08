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

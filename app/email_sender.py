from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr

from app.database import (
    claim_next_queued_email,
    count_sent_emails_today,
    last_sent_email_at,
    mark_contact_sent,
    mark_email_failed,
    mark_email_sent,
)
from app.settings_store import get_settings, update_settings

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_sender_task: asyncio.Task | None = None


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


def _int(settings: dict, key: str, default: int) -> int:
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
    now = datetime.now(UTC)
    if not within_active_hours(
        now,
        _int(settings, "email_active_start_hour", 9),
        _int(settings, "email_active_end_hour", 18),
    ):
        return
    if not interval_elapsed(
        last_sent_email_at(), now, _int(settings, "email_send_interval_minutes", 5)
    ):
        return
    if not under_daily_cap(count_sent_emails_today(), _int(settings, "email_daily_cap", 50)):
        return
    row = claim_next_queued_email()
    if not row:
        return
    smtp = {
        "smtp_host": settings["smtp_host"],
        "smtp_port": settings.get("smtp_port", "587"),
        "smtp_security": settings.get("smtp_security", "starttls"),
        "smtp_username": settings.get("smtp_username", ""),
        "smtp_password": settings.get("smtp_password", ""),
        "from_name": settings.get("smtp_from_name", ""),
        "from_email": settings.get("smtp_from_email") or settings.get("smtp_username", ""),
    }
    try:
        msg = build_message(smtp, row)
        await asyncio.to_thread(send_smtp, smtp, msg)
    except (
        smtplib.SMTPAuthenticationError,
        smtplib.SMTPConnectError,
        ConnectionError,
        OSError,
    ) as exc:
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
        except Exception:  # noqa: BLE001 - contact may be deleted; send already succeeded
            pass


async def _sender_loop() -> None:
    logger.info("Email sender started")
    while True:
        try:
            await sender_tick()
        except Exception:  # noqa: BLE001 - keep the loop alive across tick failures
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

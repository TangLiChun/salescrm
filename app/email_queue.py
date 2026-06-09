"""Shared email queueing logic, used by both the HTTP route and the Pi tool."""

from __future__ import annotations

from app.database import (
    email_queued_addresses,
    enqueue_email,
    get_contact,
    get_email_template,
)
from app.email_render import render_email


def queue_emails_for_contacts(
    user_id: int,
    contact_ids: list[int],
    template_id: int,
    *,
    skip_sent: bool = True,
) -> dict:
    """Queue one rendered email per contact, deduping against the outbox.

    Returns {"queued": n, "skipped": {...}} or {"error": ...} when the
    template does not exist.
    """
    template = get_email_template(user_id, template_id)
    if not template:
        return {"error": "模板不存在"}

    already = email_queued_addresses(user_id)
    queued = 0
    skipped = {"no_email": 0, "duplicate": 0, "already_sent": 0, "not_found": 0}
    for cid in contact_ids:
        contact = get_contact(user_id, cid)
        if not contact:
            skipped["not_found"] += 1
            continue
        if not (contact.get("email") or "").strip():
            skipped["no_email"] += 1
            continue
        email = contact["email"].strip()
        if email.lower() in already:
            skipped["duplicate"] += 1
            continue
        if skip_sent and contact.get("email_sent"):
            skipped["already_sent"] += 1
            continue
        subject, text, html = render_email(template, contact)
        enqueue_email(user_id, cid, template_id, email, subject, text, html)
        already.add(email.lower())
        queued += 1
    return {"queued": queued, "skipped": skipped, "template": template.get("name") or ""}

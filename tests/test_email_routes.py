import app.auth as auth
import app.database as database
import app.settings_store as settings_store

database.init_db = lambda: None
settings_store.get_setting = lambda key, default="": default
auth.session_secret = lambda: "test-secret"

import app.main as main  # noqa: E402


async def test_email_test_uses_form_values_and_saved_password_fallback(monkeypatch):
    sent = {}

    def fake_send(settings, msg):
        sent["settings"] = settings
        sent["to"] = msg["To"]

    monkeypatch.setattr(main, "send_smtp", fake_send)
    monkeypatch.setattr(
        main,
        "build_message",
        lambda s, r: type("M", (), {"__getitem__": lambda self, k: r["to_email"]})(),
    )
    monkeypatch.setattr(
        main,
        "get_setting",
        lambda key, default="": "SAVEDPASS" if key == "smtp_password" else default,
    )

    body = main.EmailTestRequest(
        to="x@y.com",
        host="h",
        port="587",
        security="starttls",
        username="u",
        password="",
        from_name="O",
        from_email="o@a.com",
    )
    result = await main.send_test_email(body, {"id": 1})
    assert result["ok"] is True
    assert sent["settings"]["smtp_password"] == "SAVEDPASS"  # blank => saved fallback
    assert sent["to"] == "x@y.com"


async def test_queue_renders_and_skips(monkeypatch):
    # 排队逻辑已抽到 app.email_queue（Pi 工具与路由共用），在那里打桩。
    import app.email_queue as email_queue

    contacts = {
        1: {"id": 1, "email": "a@x.com", "name": "A", "org": "X"},
        2: {"id": 2, "email": "", "name": "B"},  # no email -> skipped
    }
    enq = []
    monkeypatch.setattr(email_queue, "get_contact", lambda uid, cid: contacts.get(cid))
    monkeypatch.setattr(
        email_queue,
        "get_email_template",
        lambda uid, tid: {"subject": "Hi {name}", "body": "**Yo** {org}"},
    )
    monkeypatch.setattr(email_queue, "email_queued_addresses", lambda uid: set())
    monkeypatch.setattr(email_queue, "enqueue_email", lambda *a, **k: enq.append(a) or len(enq))
    body = main.EmailQueueRequest(contact_ids=[1, 2], template_id=10, skip_sent=True)
    result = await main.queue_emails(body, {"id": 1})
    assert result["queued"] == 1
    assert result["skipped"]["no_email"] == 1
    # rendered subject/body present in the enqueue call
    assert any("Hi A" in str(a) for a in enq[0])


def test_outbox_routes_delegate(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "list_outbox", lambda uid, status=None: [{"id": 1, "status": status}])
    monkeypatch.setattr(
        main, "update_outbox_status", lambda uid, eid, s: calls.append(("status", uid, eid, s))
    )
    monkeypatch.setattr(
        main, "update_settings", lambda updates: calls.append(("settings", updates))
    )

    assert main.get_outbox({"id": 1})["items"][0]["id"] == 1
    main.cancel_outbox(7, {"id": 1})
    main.retry_outbox(8, {"id": 1})
    main.toggle_sender(main.SenderToggleRequest(enabled=True), {"id": 1})

    assert ("status", 1, 7, "cancelled") in calls
    assert ("status", 1, 8, "queued") in calls
    assert ("settings", {"email_sender_enabled": "1"}) in calls

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from app.agent_chat import agent_chat_stream
from app.agent_routes import router as agent_router
from app.auth import (
    SESSION_USER_KEY,
    CurrentUser,
    authenticate_user,
    session_secret,
)
from app.database import (
    bulk_delete_contacts,
    bulk_update_contacts,
    check_db,
    check_schema,
    contacts_to_csv,
    count_contacts,
    create_contact_note,
    create_scheduled_job,
    create_email_template,
    dedupe_contacts,
    delete_contact,
    delete_contact_note,
    delete_email_template,
    delete_scheduled_job,
    FOLLOW_UP_STATUSES,
    get_contact,
    get_contact_stats,
    get_scheduled_job,
    get_user_auth_by_id,
    import_contacts,
    init_db,
    list_contact_notes,
    list_contacts,
    list_email_templates,
    list_job_runs,
    list_scheduled_jobs,
    mark_contact_sent,
    update_contact,
    update_contact_follow_up_status,
    update_email_template,
    update_scheduled_job,
    update_user_password,
)
from app.background_jobs import (
    get_job_for_user,
    list_jobs_for_user,
    recover_background_jobs_on_startup,
    spawn_background_job,
)
from app.lead_discovery import discover_leads_stream
from app.llm import llm_configured
from app.scheduler import run_scheduled_job, start_scheduler, stop_scheduler
from app.security import verify_password
from app.pi_chat_store import (
    create_pi_thread,
    delete_pi_thread,
    get_pi_thread,
    list_pi_threads,
    sync_pi_threads_from_client,
    upsert_pi_thread,
)
from app.settings_store import (
    get_public_settings,
    get_settings_for_edit,
    get_setting,
    regenerate_agent_api_token,
    update_settings,
)
from app.sources import list_channels
from arin_lookup import lookup_asns_batch, parse_asns_from_text, rows_to_csv

APP_DIR = Path(__file__).resolve().parent
MAX_ASNS = 200


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    recover_background_jobs_on_startup()
    await start_scheduler()
    yield
    await stop_scheduler()


app = FastAPI(title="Sales CRM — ASN RDAP Lookup", lifespan=lifespan)

# Session middleware reads app_settings — tables must exist before import-time setup.
init_db()

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    https_only=get_setting("session_https_only", "0") == "1",
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
app.include_router(agent_router)


class LookupRequest(BaseModel):
    text: str = Field(min_length=1)
    delay: float = Field(default=1.0, ge=0, le=5)
    timeout: float = Field(default=20.0, ge=5, le=60)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ImportContactsRequest(BaseModel):
    rows: list[dict] = Field(min_length=1)


class LeadDiscoverRequest(BaseModel):
    query: str = Field(min_length=4, max_length=2000)
    min_score: int = Field(default=60, ge=0, le=100)
    delay: float = Field(default=0.5, ge=0, le=5)
    auto_import: bool = False


class EnrichContactJobRequest(BaseModel):
    contact_id: int = Field(gt=0)
    min_score: int = Field(default=50, ge=0, le=100)
    auto_import: bool = True


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=4, max_length=2000)
    interval_hours: int = Field(default=24, ge=1, le=168)
    min_score: int = Field(default=60, ge=0, le=100)
    auto_import: bool = True
    enabled: bool = True


class ScheduleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    query: str | None = Field(default=None, max_length=2000)
    interval_hours: int | None = Field(default=None, ge=1, le=168)
    min_score: int | None = Field(default=None, ge=0, le=100)
    auto_import: bool | None = None
    enabled: bool | None = None


class MarkSentRequest(BaseModel):
    sent: bool = True


class ContactFollowUpStatusRequest(BaseModel):
    follow_up_status: str = Field(min_length=1, max_length=32)


class ContactNoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ContactUpdateRequest(BaseModel):
    org: str | None = Field(default=None, max_length=500)
    name: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    roles: str | None = Field(default=None, max_length=500)


class ContactBulkRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=32)
    follow_up_status: str | None = Field(default=None, max_length=32)


class SettingsUpdateRequest(BaseModel):
    default_admin_user: str | None = None
    default_admin_password: str | None = None
    session_secret: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    tavily_api_key: str | None = None
    serpapi_key: str | None = None
    brave_search_key: str | None = None
    brightdata_api_key: str | None = None
    brightdata_serp_zone: str | None = None
    brightdata_serp_data_format: str | None = None
    scheduler_enabled: str | None = None
    scheduler_poll_seconds: str | None = None
    session_https_only: str | None = None
    import_blocklist: str | None = None
    import_allowlist: str | None = None
    zhipu_api_key: str | None = None
    zhipu_search_engine: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class EmailTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=10000)


class EmailTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    subject: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=10000)


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list)
    thread_id: str | None = Field(default=None, max_length=64)


class PiThreadCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)


class PiThreadUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    history: list[dict] | None = None


class PiThreadSyncRequest(BaseModel):
    threads: list[dict] = Field(default_factory=list)
    active_thread_id: str | None = Field(default=None, max_length=64)


def render_page(filename: str) -> HTMLResponse:
    html = (APP_DIR / "static" / filename).read_text(encoding="utf-8")
    return HTMLResponse(html)


def require_login(request: Request) -> dict | None:
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        return None
    from app.database import get_user_by_id

    user = get_user_by_id(user_id)
    if not user:
        request.session.clear()
        return None
    return {"id": user["id"], "username": user["username"]}


@app.get("/health")
def health() -> dict:
    db_ok = check_db()
    schema_ok = check_schema() if db_ok else False
    return {"ok": db_ok and schema_ok, "db": db_ok, "schema": schema_ok}


@app.get("/login", response_class=HTMLResponse, response_model=None)
def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    if require_login(request):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return render_page("login.html")


@app.get("/", response_class=HTMLResponse, response_model=None)
def index(request: Request) -> HTMLResponse | RedirectResponse:
    if not require_login(request):
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return render_page("index.html")


@app.get("/api/config")
def public_config() -> dict:
    config = get_public_settings()
    config["search_channels"] = list_channels()
    return config


@app.get("/api/settings")
def get_settings(_: CurrentUser) -> dict:
    return get_settings_for_edit()


@app.put("/api/settings")
def save_settings(body: SettingsUpdateRequest, _: CurrentUser) -> dict:
    updates = body.model_dump(exclude_none=True)
    return update_settings(updates)


@app.post("/api/settings/agent-token/regenerate")
def regenerate_agent_token(_: CurrentUser) -> dict:
    token = regenerate_agent_api_token()
    return {"agent_api_token": token, "agent_api_url": "http://127.0.0.1:8000"}


@app.get("/api/me")
def me(request: Request) -> dict:
    user = require_login(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return user


@app.get("/api/stats")
def stats(user: CurrentUser) -> dict:
    return get_contact_stats(user["id"])


@app.get("/api/backup")
def download_backup(user: CurrentUser) -> Response:
    contacts = list_contacts(user["id"], limit=100000)
    payload = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "database": "postgresql",
        "contacts": contacts,
        "stats": get_contact_stats(user["id"]),
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"salescrm_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/me/password")
def change_password(body: ChangePasswordRequest, user: CurrentUser) -> dict:
    auth = get_user_auth_by_id(user["id"])
    if not auth or not verify_password(body.current_password, auth["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同")
    if not update_user_password(user["id"], body.new_password):
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True}


@app.post("/api/login")
def login(body: LoginRequest, request: Request) -> dict:
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    request.session[SESSION_USER_KEY] = user["id"]
    return user


@app.post("/api/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@app.get("/api/contacts")
def get_contacts(
    user: CurrentUser,
    status: str = "all",
    follow_up_status: str = "all",
    q: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    if status not in {"all", "sent", "unsent"}:
        raise HTTPException(status_code=400, detail="status 必须是 all/sent/unsent")
    if follow_up_status != "all" and follow_up_status not in FOLLOW_UP_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"follow_up_status 必须是 all 或 {'/'.join(FOLLOW_UP_STATUSES)}",
        )
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    total = count_contacts(
        user["id"],
        status=status,
        follow_up_status=follow_up_status,
        q=q,
    )
    contacts = list_contacts(
        user["id"],
        status=status,
        follow_up_status=follow_up_status,
        q=q,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    sent_count = sum(1 for item in contacts if item.get("email_sent"))
    pages = max(1, (total + page_size - 1) // page_size)
    return {
        "contacts": contacts,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "sent_count": sent_count,
        "unsent_count": len(contacts) - sent_count,
    }


@app.get("/api/contacts/export")
def export_contacts(
    user: CurrentUser,
    status: str = "all",
    follow_up_status: str = "all",
    q: str = "",
) -> Response:
    if status not in {"all", "sent", "unsent"}:
        raise HTTPException(status_code=400, detail="status 必须是 all/sent/unsent")
    contacts = list_contacts(
        user["id"],
        status=status,
        follow_up_status=follow_up_status,
        q=q,
    )
    csv_data = contacts_to_csv(contacts)
    filename = f"contacts_{time.strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/contacts/import")
def import_contact_rows(body: ImportContactsRequest, user: CurrentUser) -> dict:
    result = import_contacts(user["id"], body.rows)
    result["total"] = count_contacts(user["id"])
    return result


@app.delete("/api/contacts/{contact_id}")
def remove_contact(contact_id: int, user: CurrentUser) -> dict:
    if not delete_contact(user["id"], contact_id):
        raise HTTPException(status_code=404, detail="联系人不存在")
    return {"ok": True}


@app.patch("/api/contacts/{contact_id}")
def patch_contact(
    contact_id: int, body: ContactUpdateRequest, user: CurrentUser
) -> dict:
    contact = update_contact(
        user["id"],
        contact_id,
        org=body.org,
        name=body.name,
        notes=body.notes,
        roles=body.roles,
    )
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")
    return contact


@app.post("/api/contacts/bulk")
def bulk_contacts(body: ContactBulkRequest, user: CurrentUser) -> dict:
    action = body.action.strip().lower()
    if action == "status":
        if not body.follow_up_status or body.follow_up_status not in FOLLOW_UP_STATUSES:
            raise HTTPException(status_code=400, detail="无效的 follow_up_status")
        return bulk_update_contacts(
            user["id"], body.ids, follow_up_status=body.follow_up_status
        )
    if action == "mark_sent":
        return bulk_update_contacts(user["id"], body.ids, email_sent=True)
    if action == "unmark_sent":
        return bulk_update_contacts(user["id"], body.ids, email_sent=False)
    if action == "delete":
        return bulk_delete_contacts(user["id"], body.ids)
    raise HTTPException(status_code=400, detail="action 无效")


@app.post("/api/contacts/{contact_id}/mark-sent")
def mark_sent(contact_id: int, body: MarkSentRequest, user: CurrentUser) -> dict:
    if not mark_contact_sent(user["id"], contact_id, sent=body.sent):
        raise HTTPException(status_code=404, detail="联系人不存在")
    return {"ok": True, "sent": body.sent}


@app.get("/api/contacts/{contact_id}/notes")
def get_contact_notes(contact_id: int, user: CurrentUser) -> dict:
    notes = list_contact_notes(user["id"], contact_id)
    if notes is None:
        raise HTTPException(status_code=404, detail="联系人不存在")
    return {"notes": notes, "total": len(notes)}


@app.post("/api/contacts/{contact_id}/notes")
def add_contact_note(
    contact_id: int, body: ContactNoteRequest, user: CurrentUser
) -> dict:
    note = create_contact_note(user["id"], contact_id, body.body)
    if note is None:
        raise HTTPException(status_code=404, detail="联系人不存在或备注为空")
    return note


@app.delete("/api/contacts/{contact_id}/notes/{note_id}")
def remove_contact_note(contact_id: int, note_id: int, user: CurrentUser) -> dict:
    if not delete_contact_note(user["id"], contact_id, note_id):
        raise HTTPException(status_code=404, detail="备注不存在")
    return {"ok": True}


@app.patch("/api/contacts/{contact_id}/status")
def patch_contact_status(
    contact_id: int, body: ContactFollowUpStatusRequest, user: CurrentUser
) -> dict:
    status_value = body.follow_up_status.strip().lower()
    if status_value not in FOLLOW_UP_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"follow_up_status 必须是 {'/'.join(FOLLOW_UP_STATUSES)}",
        )
    if not update_contact_follow_up_status(user["id"], contact_id, status_value):
        raise HTTPException(status_code=404, detail="联系人不存在")
    return {"ok": True, "follow_up_status": status_value}


@app.post("/api/contacts/dedupe")
def dedupe(user: CurrentUser) -> dict:
    result = dedupe_contacts(user_id=user["id"])
    result["total"] = count_contacts(user["id"])
    return result


@app.get("/api/email-templates")
def get_email_templates(user: CurrentUser) -> dict:
    templates = list_email_templates(user["id"])
    return {"templates": templates, "total": len(templates)}


@app.post("/api/email-templates")
def add_email_template(body: EmailTemplateRequest, user: CurrentUser) -> dict:
    return create_email_template(
        user["id"], name=body.name, subject=body.subject, body=body.body
    )


@app.put("/api/email-templates/{template_id}")
def save_email_template(
    template_id: int, body: EmailTemplateUpdateRequest, user: CurrentUser
) -> dict:
    template = update_email_template(
        user["id"],
        template_id,
        name=body.name,
        subject=body.subject,
        body=body.body,
    )
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return template


@app.delete("/api/email-templates/{template_id}")
def remove_email_template(template_id: int, user: CurrentUser) -> dict:
    if not delete_email_template(user["id"], template_id):
        raise HTTPException(status_code=404, detail="模板不存在")
    return {"ok": True}


@app.get("/api/schedules")
def get_schedules(user: CurrentUser) -> dict:
    jobs = list_scheduled_jobs(user["id"])
    return {"schedules": jobs, "total": len(jobs)}


@app.post("/api/schedules")
def create_schedule(body: ScheduleRequest, user: CurrentUser) -> dict:
    if not llm_configured():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key，无法创建定时任务")
    job = create_scheduled_job(
        user["id"],
        name=body.name,
        query=body.query,
        interval_hours=body.interval_hours,
        min_score=body.min_score,
        auto_import=body.auto_import,
        enabled=body.enabled,
    )
    return job


@app.patch("/api/schedules/{job_id}")
def patch_schedule(job_id: int, body: ScheduleUpdateRequest, user: CurrentUser) -> dict:
    job = update_scheduled_job(
        user["id"],
        job_id,
        name=body.name,
        query=body.query,
        interval_hours=body.interval_hours,
        min_score=body.min_score,
        auto_import=body.auto_import,
        enabled=body.enabled,
    )
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return job


@app.delete("/api/schedules/{job_id}")
def remove_schedule(job_id: int, user: CurrentUser) -> dict:
    if not delete_scheduled_job(user["id"], job_id):
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return {"ok": True}


@app.get("/api/schedules/{job_id}/runs")
def get_schedule_runs(job_id: int, user: CurrentUser, limit: int = 20) -> dict:
    runs = list_job_runs(user["id"], job_id, limit=min(max(limit, 1), 100))
    if runs is None:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return {"runs": runs, "total": len(runs)}


@app.post("/api/schedules/{job_id}/run")
async def run_schedule_now(job_id: int, user: CurrentUser) -> dict:
    if not llm_configured():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")
    job = get_scheduled_job(user["id"], job_id)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return await run_scheduled_job(job)


@app.post("/api/agent/chat/stream")
async def agent_chat_stream_route(body: AgentChatRequest, user: CurrentUser) -> StreamingResponse:
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置 LLM API Key，请在系统设置中填写",
        )

    async def event_generator():
        async for event in agent_chat_stream(
            user["id"],
            body.message,
            body.history,
            thread_id=body.thread_id,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/pi/threads")
def get_pi_threads(user: CurrentUser) -> dict:
    return {"threads": list_pi_threads(user["id"])}


@app.get("/api/pi/threads/{thread_id}")
def get_pi_thread_route(thread_id: str, user: CurrentUser) -> dict:
    thread = get_pi_thread(user["id"], thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="对话不存在")
    return thread


@app.post("/api/pi/threads")
def create_pi_thread_route(body: PiThreadCreateRequest, user: CurrentUser) -> dict:
    return create_pi_thread(user["id"], title=body.title)


@app.put("/api/pi/threads/{thread_id}")
def update_pi_thread_route(
    thread_id: str, body: PiThreadUpdateRequest, user: CurrentUser
) -> dict:
    thread = upsert_pi_thread(
        user["id"],
        thread_id,
        title=body.title,
        history=body.history,
    )
    if not thread:
        raise HTTPException(status_code=404, detail="对话不存在")
    return thread


@app.delete("/api/pi/threads/{thread_id}")
def delete_pi_thread_route(thread_id: str, user: CurrentUser) -> dict:
    if not delete_pi_thread(user["id"], thread_id):
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}


@app.post("/api/pi/threads/sync")
def sync_pi_threads_route(body: PiThreadSyncRequest, user: CurrentUser) -> dict:
    result = sync_pi_threads_from_client(user["id"], body.threads)
    if body.active_thread_id:
        result["active_thread_id"] = body.active_thread_id
    return result


@app.post("/api/lookup/parse")
def lookup_parse(body: LookupRequest, _: CurrentUser) -> dict:
    asns = parse_asns_from_text(body.text)
    return {
        "asns": asns,
        "total": len(asns),
        "max": MAX_ASNS,
        "over_limit": len(asns) > MAX_ASNS,
    }


@app.post("/api/lookup")
async def lookup_batch(body: LookupRequest, _: CurrentUser) -> dict:
    asns = parse_asns_from_text(body.text)
    if not asns:
        raise HTTPException(status_code=400, detail="No valid ASNs found.")
    if len(asns) > MAX_ASNS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_ASNS} ASNs per request.")

    all_rows = await lookup_asns_batch(
        asns,
        body.timeout,
        delay=body.delay,
    )

    rows = [row.to_dict() for row in all_rows]
    emails = sum(1 for row in all_rows if row.email)
    errors = sum(1 for row in all_rows if row.error)
    return {
        "asns": len(asns),
        "rows": rows,
        "emails": emails,
        "errors": errors,
        "csv": rows_to_csv(all_rows),
    }


@app.post("/api/lookup/stream")
async def lookup_stream(body: LookupRequest, _: CurrentUser) -> StreamingResponse:
    asns = parse_asns_from_text(body.text)
    if not asns:
        raise HTTPException(status_code=400, detail="No valid ASNs found.")
    if len(asns) > MAX_ASNS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_ASNS} ASNs per request.")

    async def event_generator():
        total = len(asns)
        yield f"data: {json.dumps({'type': 'parsed', 'asns': asns, 'total': total}, ensure_ascii=False)}\n\n"

        progress_queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def on_progress(index: int, total: int, asn: int, rows) -> None:
            await progress_queue.put(
                {
                    "type": "progress",
                    "index": index,
                    "total": total,
                    "asn": asn,
                    "rows": [row.to_dict() for row in rows],
                }
            )

        async def run_batch() -> None:
            await lookup_asns_batch(
                asns,
                body.timeout,
                delay=body.delay,
                on_progress=on_progress,
            )
            await progress_queue.put(None)

        batch_task = asyncio.create_task(run_batch())
        while True:
            payload = await progress_queue.get()
            if payload is None:
                break
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        await batch_task

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/jobs/lookup")
async def create_lookup_job(body: LookupRequest, user: CurrentUser) -> dict:
    asns = parse_asns_from_text(body.text)
    if not asns:
        raise HTTPException(status_code=400, detail="No valid ASNs found.")
    if len(asns) > MAX_ASNS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_ASNS} ASNs per request.")
    job = spawn_background_job(
        user["id"],
        "lookup",
        {"text": body.text, "delay": body.delay, "timeout": body.timeout},
    )
    return {"job": job}


@app.post("/api/jobs/leads/discover")
async def create_lead_discover_job(body: LeadDiscoverRequest, user: CurrentUser) -> dict:
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置 LLM API Key，请在系统设置中填写",
        )
    job = spawn_background_job(
        user["id"],
        "lead_discover",
        {
            "query": body.query,
            "min_score": body.min_score,
            "delay": body.delay,
            "auto_import": body.auto_import,
        },
    )
    return {"job": job}


@app.post("/api/jobs/enrich")
async def create_enrich_contact_job(body: EnrichContactJobRequest, user: CurrentUser) -> dict:
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置 LLM API Key，请在系统设置中填写",
        )
    contact = get_contact(user["id"], body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="联系人不存在")
    if not (contact.get("email") or "").strip():
        raise HTTPException(status_code=400, detail="该联系人没有邮箱，无法作为扩展锚点")
    job = spawn_background_job(
        user["id"],
        "enrich_contact",
        {
            "contact_id": body.contact_id,
            "min_score": body.min_score,
            "auto_import": body.auto_import,
        },
    )
    return {"job": job}


@app.get("/api/jobs")
def list_background_jobs_route(user: CurrentUser, active: bool = False) -> dict:
    jobs = list_jobs_for_user(user["id"], active_only=active)
    return {"jobs": jobs}


@app.get("/api/jobs/{job_id}")
def get_background_job_route(job_id: int, user: CurrentUser) -> dict:
    job = get_job_for_user(user["id"], job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"job": job}


@app.post("/api/leads/discover/stream")
async def discover_leads(body: LeadDiscoverRequest, user: CurrentUser) -> StreamingResponse:
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置 LLM API Key，请在系统设置中填写",
        )

    async def event_generator():
        async for event in discover_leads_stream(
            body.query,
            min_score=body.min_score,
            delay=body.delay,
            auto_import=body.auto_import,
            user_id=user["id"],
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from app.agent_chat import (
    agent_chat_stream,
    history_entry_from_agent_event,
    release_pi_thread,
    try_acquire_pi_thread,
)
from app.agent_routes import router as agent_router
from app.auth import (
    SESSION_USER_KEY,
    CurrentUser,
    authenticate_user,
    session_secret,
)
from app.background_jobs import (
    PiAgentThreadBusyError,
    get_job_for_user,
    iter_job_events,
    list_jobs_for_user,
    recover_background_jobs_on_startup,
    request_cancel_background_job,
    spawn_background_job,
)
from app.database import (
    FOLLOW_UP_STATUSES,
    LEAD_REVIEW_STATUSES,
    bulk_delete_contacts,
    bulk_update_contacts,
    check_db,
    check_schema,
    contacts_to_csv,
    count_contacts,
    create_contact_note,
    create_email_template,
    create_scheduled_job,
    dedupe_contacts,
    delete_contact,
    delete_contact_note,
    delete_email_template,
    delete_scheduled_job,
    get_contact,
    get_contact_stats,
    get_scheduled_job,
    get_user_auth_by_id,
    get_workbench_summary,
    has_active_pi_agent_job,
    import_contacts,
    import_lead_reviews,
    init_db,
    list_contact_notes,
    list_contact_organizations,
    list_contacts,
    list_email_templates,
    list_job_runs,
    list_lead_reviews,
    list_outbox,
    list_scheduled_jobs,
    mark_contact_sent,
    update_contact,
    update_contact_follow_up_status,
    update_email_template,
    update_lead_review_status,
    update_outbox_status,
    update_scheduled_job,
    update_user_password,
)
from app.email_queue import queue_emails_for_contacts
from app.email_sender import build_message, send_smtp, start_email_sender, stop_email_sender
from app.lead_discovery import discover_leads_stream
from app.llm import llm_configured
from app.pi_agent_proxy import (
    pi_agent_service_url,
    sanitize_agent_history,
    stream_pi_agent_events,
)
from app.pi_chat_store import (
    append_pi_thread_history_entries,
    compress_thread_context_until_current,
    create_pi_thread,
    delete_pi_thread,
    fork_pi_thread,
    get_pi_thread,
    list_pi_threads,
    sync_pi_threads_from_client,
    upsert_pi_thread,
)
from app.pi_internal_routes import router as pi_internal_router
from app.rate_limit import login_limiter
from app.scheduler import (
    get_scheduler_status,
    restart_scheduler,
    run_scheduled_job,
    start_scheduler,
    stop_scheduler,
)
from app.security import verify_password
from app.security_headers import SecurityHeadersMiddleware
from app.settings_store import (
    get_public_settings,
    get_setting,
    get_settings_for_edit,
    regenerate_agent_api_token,
    update_settings,
)
from app.sources import list_channels
from app.sources.channel_registry import get_channel_config
from arin_lookup import lookup_asns_batch, parse_asns_from_text, rows_to_csv

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
MAX_ASNS = 200
logger = logging.getLogger(__name__)


class VersionedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if isinstance(response, Response) and path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


def asset_version() -> str:
    env = os.environ.get("ASSET_VERSION")
    if env:
        return env
    main_js = STATIC_DIR / "js" / "main.js"
    try:
        return str(int(main_js.stat().st_mtime))
    except OSError:
        return str(int(time.time()))


def _warn_insecure_defaults() -> None:
    from app.settings_store import DEFAULTS

    if get_setting("default_admin_password", "") == DEFAULTS["default_admin_password"]:
        logger.warning(
            "管理员账号仍在使用默认密码（%s）。商用/公网部署前请登录后立即修改密码。",
            DEFAULTS["default_admin_user"],
        )
    if get_setting("session_https_only", "0") != "1":
        logger.info(
            "session_https_only=0：会话 Cookie 未启用 Secure 标记。"
            "通过 HTTPS 反向代理对外服务时，请在系统设置中开启。"
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    _warn_insecure_defaults()
    await recover_background_jobs_on_startup()
    await start_scheduler()
    await start_email_sender()
    yield
    await stop_email_sender()
    await stop_scheduler()


app = FastAPI(title="Sales CRM — ASN RDAP Lookup", lifespan=lifespan)

# Session middleware reads app_settings — tables must exist before import-time setup.
init_db()

_https_only = get_setting("session_https_only", "0") == "1"
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    https_only=_https_only,
)
# 外层包安全头：对包括 4xx/5xx 在内的所有 HTTP 响应生效。
app.add_middleware(SecurityHeadersMiddleware, hsts=_https_only)
app.mount("/static", VersionedStaticFiles(directory=STATIC_DIR), name="static")
app.include_router(agent_router)
app.include_router(pi_internal_router)


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


class PiAgentJobRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, max_length=64)


class ScheduleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=4, max_length=2000)
    interval_hours: int | None = Field(default=None, ge=1, le=168)
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)
    run_mode: str = Field(default="interval")
    cooldown_minutes: int = Field(default=15, ge=5, le=1440)
    min_score: int = Field(default=60, ge=0, le=100)
    auto_import: bool = True
    enabled: bool = True


class ScheduleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    query: str | None = Field(default=None, max_length=2000)
    interval_hours: int | None = Field(default=None, ge=1, le=168)
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)
    run_mode: str | None = None
    cooldown_minutes: int | None = Field(default=None, ge=5, le=1440)
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
    linkedin: str | None = Field(default=None, max_length=500)
    x: str | None = Field(default=None, max_length=500)
    facebook: str | None = Field(default=None, max_length=500)


class ContactBulkRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=32)
    follow_up_status: str | None = Field(default=None, max_length=32)


class LeadReviewStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)


class LeadReviewImportRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class SettingsUpdateRequest(BaseModel):
    default_admin_user: str | None = None
    default_admin_password: str | None = None
    session_secret: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_thinking_mode: str | None = None
    tavily_api_key: str | None = None
    serpapi_key: str | None = None
    brave_search_key: str | None = None
    brightdata_api_key: str | None = None
    brightdata_serp_zone: str | None = None
    brightdata_serp_data_format: str | None = None
    brightdata_linkedin_dataset_id: str | None = None
    brightdata_linkedin_enabled: str | None = None
    brightdata_x_dataset_id: str | None = None
    brightdata_x_enabled: str | None = None
    brightdata_facebook_dataset_id: str | None = None
    brightdata_facebook_enabled: str | None = None
    brightdata_web_unlocker_zone: str | None = None
    brightdata_web_unlocker_enabled: str | None = None
    brightdata_web_unlocker_max_urls: str | None = None
    lowendtalk_enabled: str | None = None
    webhostingtalk_enabled: str | None = None
    scheduler_enabled: str | None = None
    scheduler_poll_seconds: str | None = None
    session_https_only: str | None = None
    import_blocklist: str | None = None
    import_allowlist: str | None = None
    zhipu_api_key: str | None = None
    zhipu_search_engine: str | None = None
    shodan_api_key: str | None = None
    shodan_enabled: str | None = None


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
    history: list[dict[str, Any]] = Field(default_factory=list)
    thread_id: str | None = Field(default=None, max_length=64)


class PiThreadCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)


class PiThreadUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    history: list[dict] | None = None


class PiThreadSyncRequest(BaseModel):
    threads: list[dict] = Field(default_factory=list)
    active_thread_id: str | None = Field(default=None, max_length=64)


class PiThreadForkRequest(BaseModel):
    through_index: int = Field(ge=0, le=10000)


def render_page(filename: str) -> HTMLResponse:
    html = (STATIC_DIR / filename).read_text(encoding="utf-8")
    if filename.endswith(".html"):
        version = asset_version()
        html = html.replace(
            'src="/static/js/main.js"',
            f'src="/static/js/main.js?v={version}"',
        )
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, must-revalidate"})


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
    config["data_channel_config"] = get_channel_config()
    return config


@app.get("/api/settings")
def get_settings(_: CurrentUser) -> dict:
    return get_settings_for_edit()


@app.get("/api/lead-preferences")
def get_lead_preferences(user: CurrentUser) -> dict:
    from app.lead_preferences import get_prefs

    return {"preferences": get_prefs(user["id"])}


@app.post("/api/lead-preferences/reset")
def reset_lead_preferences(user: CurrentUser) -> dict:
    from app.lead_preferences import reset_prefs

    return {"preferences": reset_prefs(user["id"]), "ok": True}


class EmailTestRequest(BaseModel):
    to: str
    host: str = ""
    port: str = "587"
    security: str = "starttls"
    username: str = ""
    password: str = ""
    from_name: str = ""
    from_email: str = ""


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


class EmailQueueRequest(BaseModel):
    contact_ids: list[int]
    template_id: int
    skip_sent: bool = True


@app.post("/api/email/queue")
async def queue_emails(body: EmailQueueRequest, user: CurrentUser) -> dict:
    result = queue_emails_for_contacts(
        user["id"], body.contact_ids, body.template_id, skip_sent=body.skip_sent
    )
    if result.get("error"):
        raise HTTPException(status_code=404, detail=str(result["error"]))
    return result


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


class PiRestorePrefsRequest(BaseModel):
    preferences: dict = Field(default_factory=dict)


@app.post("/api/pi/restore-prefs")
def restore_pi_prefs(body: PiRestorePrefsRequest, user: CurrentUser) -> dict:
    """Undo a Pi-triggered reset_lead_preferences by writing the captured blob back."""
    from app.lead_preferences import save_prefs

    return {"ok": True, "preferences": save_prefs(user["id"], body.preferences or {})}


class PiConfirmToolRequest(BaseModel):
    thread_id: str | None = None
    name: str
    args: dict = Field(default_factory=dict)


@app.post("/api/pi/confirm-tool")
async def confirm_pi_tool(body: PiConfirmToolRequest, user: CurrentUser) -> dict:
    """Execute a destructive Pi tool after the user confirms it on screen.

    This is the only path that passes allow_destructive=True, so the model can
    never trigger a deletion on its own from the agent loop.
    """
    from app.agent_chat import (
        PI_DESTRUCTIVE_TOOLS,
        ToolEmitter,
        _run_tool,
        tool_result_summary,
    )

    if body.name not in PI_DESTRUCTIVE_TOOLS:
        raise HTTPException(status_code=400, detail="该操作无需确认")

    emitter = ToolEmitter(asyncio.Queue())
    result = await _run_tool(
        user["id"], body.name, body.args or {}, emitter, allow_destructive=True
    )
    if body.thread_id and isinstance(result, dict) and not result.get("error"):
        summary = tool_result_summary(body.name, result)
        await asyncio.to_thread(
            append_pi_thread_history_entries,
            user["id"],
            body.thread_id,
            [{"role": "tool", "name": body.name, "summary": summary}],
        )
    return {"result": result}


@app.put("/api/settings")
async def save_settings(body: SettingsUpdateRequest, _: CurrentUser) -> dict:
    from app.settings_store import get_settings

    before = get_settings()
    updates = body.model_dump(exclude_none=True)
    result = update_settings(updates)
    scheduler_changed = (
        "scheduler_enabled" in updates
        and updates.get("scheduler_enabled") != before.get("scheduler_enabled")
    ) or "scheduler_poll_seconds" in updates
    if scheduler_changed:
        await restart_scheduler()
    return result


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


@app.get("/api/workbench")
def workbench(user: CurrentUser) -> dict:
    return get_workbench_summary(user["id"])


@app.get("/api/contact-orgs")
def contact_orgs(user: CurrentUser, limit: int = 80) -> dict:
    orgs = list_contact_organizations(user["id"], limit=limit)
    return {"organizations": orgs, "total": len(orgs)}


@app.get("/api/lead-reviews")
def get_lead_reviews(user: CurrentUser, status: str = "pending", limit: int = 100) -> dict:
    if status != "all" and status not in LEAD_REVIEW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status 必须是 all 或 {'/'.join(LEAD_REVIEW_STATUSES)}",
        )
    reviews = list_lead_reviews(user["id"], status=status, limit=limit)
    return {"reviews": reviews, "total": len(reviews)}


@app.patch("/api/lead-reviews/{review_id}")
def patch_lead_review(review_id: int, body: LeadReviewStatusRequest, user: CurrentUser) -> dict:
    status_value = body.status.strip().lower()
    if status_value not in LEAD_REVIEW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status 必须是 {'/'.join(LEAD_REVIEW_STATUSES)}",
        )
    review = update_lead_review_status(user["id"], review_id, status_value)
    if not review:
        raise HTTPException(status_code=404, detail="审核线索不存在")
    return review


@app.post("/api/lead-reviews/import")
def import_reviewed_leads(body: LeadReviewImportRequest, user: CurrentUser) -> dict:
    result = import_lead_reviews(user["id"], body.ids)
    result["total"] = count_contacts(user["id"])
    return result


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同"
        )
    if not update_user_password(user["id"], body.new_password):
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True}


@app.post("/api/login")
def login(body: LoginRequest, request: Request) -> dict:
    client_ip = request.client.host if request.client else "unknown"
    limiter_key = f"{client_ip}:{body.username.strip().lower()}"
    retry_after = login_limiter.retry_after(limiter_key)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试过于频繁，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )

    user = authenticate_user(body.username, body.password)
    if not user:
        login_limiter.record_failure(limiter_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    login_limiter.reset(limiter_key)
    # Drop any pre-login session state so an attacker-supplied cookie cannot
    # carry over into the authenticated session.
    request.session.clear()
    request.session[SESSION_USER_KEY] = user["id"]

    result = dict(user)
    if body.password == get_setting("default_admin_password", ""):
        result["must_change_password"] = True
    return result


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
def patch_contact(contact_id: int, body: ContactUpdateRequest, user: CurrentUser) -> dict:
    contact = update_contact(
        user["id"],
        contact_id,
        org=body.org,
        name=body.name,
        notes=body.notes,
        roles=body.roles,
        linkedin=body.linkedin,
        x=body.x,
        facebook=body.facebook,
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
        return bulk_update_contacts(user["id"], body.ids, follow_up_status=body.follow_up_status)
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
def add_contact_note(contact_id: int, body: ContactNoteRequest, user: CurrentUser) -> dict:
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
    return create_email_template(user["id"], name=body.name, subject=body.subject, body=body.body)


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


@app.get("/api/schedules/status")
def schedules_status(_: CurrentUser) -> dict:
    return get_scheduler_status()


@app.get("/api/schedules")
def get_schedules(user: CurrentUser) -> dict:
    jobs = list_scheduled_jobs(user["id"])
    return {"schedules": jobs, "total": len(jobs), "scheduler": get_scheduler_status()}


@app.post("/api/schedules")
def create_schedule(body: ScheduleRequest, user: CurrentUser) -> dict:
    if not llm_configured():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key，无法创建定时任务")
    job = create_scheduled_job(
        user["id"],
        name=body.name,
        query=body.query,
        interval_hours=body.interval_hours,
        interval_minutes=body.interval_minutes,
        run_mode=body.run_mode,
        cooldown_minutes=body.cooldown_minutes,
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
        interval_minutes=body.interval_minutes,
        run_mode=body.run_mode,
        cooldown_minutes=body.cooldown_minutes,
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
async def agent_chat_stream_route(
    body: AgentChatRequest,
    user: CurrentUser,
    request: Request,
) -> StreamingResponse:
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置 LLM API Key，请在系统设置中填写",
        )

    user_id = user["id"]
    thread_id = body.thread_id
    if thread_id:
        if has_active_pi_agent_job(user_id, thread_id):
            raise HTTPException(
                status_code=409,
                detail="该对话已有后台 Pi 任务运行中，请等待完成后再发送",
            )
        if not try_acquire_pi_thread(user_id, thread_id):
            raise HTTPException(
                status_code=409,
                detail="该对话已有 Pi 任务运行中，请等待完成后再发送",
            )

    async def persist_stream_entries(
        entries: list[dict[str, Any]],
        *,
        compress: bool,
    ) -> None:
        if not thread_id or not entries:
            return
        await asyncio.to_thread(
            append_pi_thread_history_entries,
            user_id,
            thread_id,
            entries,
        )
        if compress:
            await asyncio.to_thread(
                compress_thread_context_until_current,
                user_id,
                thread_id,
            )

    async def event_generator():
        disconnected = {"value": False}

        async def watch_disconnect() -> None:
            try:
                while True:
                    if await request.is_disconnected():
                        disconnected["value"] = True
                        return
                    await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                return

        watch_task = asyncio.create_task(watch_disconnect())
        new_entries: list[dict[str, Any]] = []
        cancelled = False
        errored = False

        try:
            stream_source = (
                stream_pi_agent_events(
                    user_id,
                    body.message,
                    thread_id=body.thread_id,
                    history=body.history,
                    cancel_check=lambda: disconnected["value"],
                )
                if pi_agent_service_url()
                else agent_chat_stream(
                    user_id,
                    body.message,
                    sanitize_agent_history(body.history),
                    thread_id=thread_id,
                    cancel_check=lambda: disconnected["value"],
                )
            )
            async for event in stream_source:
                entry = history_entry_from_agent_event(event)
                if entry:
                    new_entries.append(entry)
                event_type = event.get("type")
                if event_type == "error":
                    if event.get("message") == "任务已停止":
                        cancelled = True
                    else:
                        errored = True
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event_type == "done":
                    break
        except Exception as exc:  # noqa: BLE001 - keep the browser SSE stream explainable
            errored = True
            logger.exception("Pi agent stream failed")
            message = str(exc).strip() or "Pi 助手执行失败，请稍后重试"
            event = {"type": "error", "message": f"Pi 助手执行失败：{message[:500]}"}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        finally:
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task
            try:
                await persist_stream_entries(
                    new_entries,
                    compress=bool(new_entries) and not cancelled and not errored,
                )
            except Exception:  # noqa: BLE001 - never leave the Pi thread locked
                logger.exception("Failed to persist Pi stream entries")
            finally:
                release_pi_thread(user_id, thread_id)

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


@app.post("/api/pi/threads/{thread_id}/fork")
def fork_pi_thread_route(thread_id: str, body: PiThreadForkRequest, user: CurrentUser) -> dict:
    thread = fork_pi_thread(user["id"], thread_id, body.through_index)
    if not thread:
        raise HTTPException(status_code=404, detail="对话不存在")
    return thread


@app.put("/api/pi/threads/{thread_id}")
def update_pi_thread_route(thread_id: str, body: PiThreadUpdateRequest, user: CurrentUser) -> dict:
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


@app.post("/api/jobs/pi-agent")
async def create_pi_agent_job(body: PiAgentJobRequest, user: CurrentUser) -> dict:
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置 LLM API Key，请在系统设置中填写",
        )
    if body.thread_id:
        thread = get_pi_thread(user["id"], body.thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="对话不存在")
    try:
        job = spawn_background_job(
            user["id"],
            "pi_agent",
            {
                "message": body.message.strip(),
                "thread_id": body.thread_id,
            },
        )
    except PiAgentThreadBusyError:
        raise HTTPException(
            status_code=409, detail="该对话已有 Pi 任务运行中，请等待完成后再发送"
        ) from None
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


@app.get("/api/jobs/events")
async def jobs_events_stream(user: CurrentUser) -> StreamingResponse:
    return StreamingResponse(
        iter_job_events(user["id"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


@app.post("/api/jobs/{job_id}/cancel")
def cancel_background_job_route(job_id: int, user: CurrentUser) -> dict:
    job = request_cancel_background_job(user["id"], job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或无法停止")
    return {"ok": True, "job": job}


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

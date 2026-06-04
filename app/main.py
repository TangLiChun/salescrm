from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    SESSION_USER_KEY,
    CurrentUser,
    authenticate_user,
    session_secret,
)
from app.database import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USER,
    create_scheduled_job,
    dedupe_contacts,
    delete_contact,
    delete_scheduled_job,
    import_contacts,
    init_db,
    list_contacts,
    list_scheduled_jobs,
    mark_contact_sent,
    update_scheduled_job,
)
from app.lead_discovery import discover_leads_stream
from app.llm import llm_configured
from app.scheduler import start_scheduler, stop_scheduler
from app.sources import list_channels
from arin_lookup import lookup_asn, parse_asns_from_text, rows_to_csv

APP_DIR = Path(__file__).resolve().parent
MAX_ASNS = 200


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    await start_scheduler()
    yield
    await stop_scheduler()


app = FastAPI(title="Sales CRM — ARIN ASN Lookup", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=session_secret(), https_only=os.getenv("SESSION_HTTPS_ONLY") == "1")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


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


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    if require_login(request):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return render_page("login.html")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse | RedirectResponse:
    if not require_login(request):
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return render_page("index.html")


@app.get("/api/config")
def public_config() -> dict:
    return {
        "default_username": DEFAULT_ADMIN_USER,
        "default_password_hint": DEFAULT_ADMIN_PASSWORD,
        "llm_configured": llm_configured(),
        "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        "search_channels": list_channels(),
        "scheduler_enabled": os.getenv("SCHEDULER_ENABLED", "1") != "0",
    }


@app.get("/api/me")
def me(request: Request) -> dict:
    user = require_login(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return user


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
def get_contacts(user: CurrentUser, status: str = "all") -> dict:
    if status not in {"all", "sent", "unsent"}:
        raise HTTPException(status_code=400, detail="status 必须是 all/sent/unsent")
    contacts = list_contacts(user["id"], status=status)
    sent_count = sum(1 for item in contacts if item.get("email_sent"))
    return {
        "contacts": contacts,
        "total": len(contacts),
        "sent_count": sent_count,
        "unsent_count": len(contacts) - sent_count,
    }


@app.post("/api/contacts/import")
def import_contact_rows(body: ImportContactsRequest, user: CurrentUser) -> dict:
    result = import_contacts(user["id"], body.rows)
    result["total"] = len(list_contacts(user["id"]))
    return result


@app.delete("/api/contacts/{contact_id}")
def remove_contact(contact_id: int, user: CurrentUser) -> dict:
    if not delete_contact(user["id"], contact_id):
        raise HTTPException(status_code=404, detail="联系人不存在")
    return {"ok": True}


@app.post("/api/contacts/{contact_id}/mark-sent")
def mark_sent(contact_id: int, body: MarkSentRequest, user: CurrentUser) -> dict:
    if not mark_contact_sent(user["id"], contact_id, sent=body.sent):
        raise HTTPException(status_code=404, detail="联系人不存在")
    return {"ok": True, "sent": body.sent}


@app.post("/api/contacts/dedupe")
def dedupe(user: CurrentUser) -> dict:
    result = dedupe_contacts(user_id=user["id"])
    result["total"] = len(list_contacts(user["id"]))
    return result


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


@app.post("/api/lookup")
def lookup_batch(body: LookupRequest, _: CurrentUser) -> dict:
    asns = parse_asns_from_text(body.text)
    if not asns:
        raise HTTPException(status_code=400, detail="No valid ASNs found.")
    if len(asns) > MAX_ASNS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_ASNS} ASNs per request.")

    all_rows = []
    for index, asn in enumerate(asns):
        all_rows.extend(lookup_asn(asn, body.timeout))
        if index + 1 < len(asns) and body.delay:
            time.sleep(body.delay)

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
        for index, asn in enumerate(asns):
            rows = await asyncio.to_thread(lookup_asn, asn, body.timeout)
            payload = {
                "type": "progress",
                "index": index + 1,
                "total": total,
                "asn": asn,
                "rows": [row.to_dict() for row in rows],
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if index + 1 < total and body.delay:
                await asyncio.sleep(body.delay)

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/leads/discover/stream")
async def discover_leads(body: LeadDiscoverRequest, user: CurrentUser) -> StreamingResponse:
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="未配置 LLM API Key，请在环境变量中设置 LLM_API_KEY",
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

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
    delete_contact,
    import_contacts,
    init_db,
    list_contacts,
)
from app.lead_discovery import discover_leads_stream
from app.llm import llm_configured
from arin_lookup import lookup_asn, parse_asns_from_text, rows_to_csv

APP_DIR = Path(__file__).resolve().parent
MAX_ASNS = 200


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


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
def get_contacts(user: CurrentUser) -> dict:
    contacts = list_contacts(user["id"])
    return {"contacts": contacts, "total": len(contacts)}


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

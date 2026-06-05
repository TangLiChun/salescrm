from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent_auth import AgentUser
from app.database import check_db, check_schema, count_contacts, import_contacts, list_contacts
from app.lead_discovery import run_lead_discovery_batch
from app.llm import llm_configured

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentImportRequest(BaseModel):
    rows: list[dict] = Field(min_length=1)
    source: str = Field(default="pi-agent", max_length=64)


class AgentDiscoverRequest(BaseModel):
    query: str = Field(min_length=4, max_length=2000)
    min_score: int = Field(default=60, ge=0, le=100)
    delay: float = Field(default=0.5, ge=0, le=5)
    auto_import: bool = False


@router.get("/health")
def agent_health(user: AgentUser) -> dict:
    db_ok = check_db()
    schema_ok = check_schema() if db_ok else False
    return {
        "ok": db_ok and schema_ok,
        "db": db_ok,
        "schema": schema_ok,
        "user": user["username"],
    }


@router.post("/leads/import")
def agent_import_leads(body: AgentImportRequest, user: AgentUser) -> dict:
    payload: list[dict] = []
    for row in body.rows:
        item = dict(row)
        item.setdefault("source", body.source)
        payload.append(item)
    result = import_contacts(user["id"], payload)
    result["total"] = count_contacts(user["id"])
    return result


@router.get("/contacts")
def agent_list_contacts(
    user: AgentUser,
    q: str | None = None,
    status: str = Query(default="all", pattern="^(all|sent|unsent)$"),
    follow_up_status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    contacts = list_contacts(
        user["id"],
        status=status,
        follow_up_status=follow_up_status,
        q=q,
        limit=limit,
        offset=offset,
    )
    total = count_contacts(
        user["id"],
        status=status,
        follow_up_status=follow_up_status,
        q=q,
    )
    return {"contacts": contacts, "total": total, "limit": limit, "offset": offset}


@router.post("/leads/discover")
async def agent_discover_leads(body: AgentDiscoverRequest, user: AgentUser) -> dict:
    if not llm_configured():
        raise HTTPException(status_code=503, detail="未配置 LLM API Key")

    result = await run_lead_discovery_batch(
        body.query,
        min_score=body.min_score,
        delay=body.delay,
        auto_import=body.auto_import,
        user_id=user["id"],
    )
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return result

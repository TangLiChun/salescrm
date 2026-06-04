from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from arin_lookup import lookup_asn, parse_asns_from_text, rows_to_csv

APP_DIR = Path(__file__).resolve().parent
MAX_ASNS = 200

app = FastAPI(title="Sales CRM — ARIN ASN Lookup")
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


class LookupRequest(BaseModel):
    text: str = Field(min_length=1)
    delay: float = Field(default=1.0, ge=0, le=5)
    timeout: float = Field(default=20.0, ge=5, le=60)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (APP_DIR / "static" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.post("/api/lookup")
def lookup_batch(body: LookupRequest) -> dict:
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
async def lookup_stream(body: LookupRequest) -> StreamingResponse:
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

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.database import (
    create_background_job,
    get_background_job,
    list_background_jobs,
    mark_interrupted_background_jobs,
    update_background_job,
)
from app.lead_discovery import discover_leads_stream
from arin_lookup import RoleContact, lookup_asn, parse_asns_from_text, rows_to_csv

logger = logging.getLogger(__name__)

_running: set[int] = set()
MAX_ASNS = 200


def _public_job(job: dict | None) -> dict | None:
    if not job:
        return None
    out = dict(job)
    for key in ("params_json", "progress_json", "result_json"):
        raw = out.get(key)
        if isinstance(raw, str) and raw:
            try:
                out[key.replace("_json", "")] = json.loads(raw)
            except json.JSONDecodeError:
                out[key.replace("_json", "")] = {}
        else:
            out[key.replace("_json", "")] = {}
        out.pop(key, None)
    return out


async def _run_lookup_job(job_id: int) -> None:
    job = get_background_job(job_id)
    if not job:
        return
    params = json.loads(job.get("params_json") or "{}")
    text = str(params.get("text") or "")
    delay = float(params.get("delay") or 0)
    timeout = float(params.get("timeout") or 30)

    asns = parse_asns_from_text(text)
    if not asns:
        update_background_job(
            job_id,
            status="error",
            message="No valid ASNs found.",
            finished_at=True,
        )
        return
    if len(asns) > MAX_ASNS:
        update_background_job(
            job_id,
            status="error",
            message=f"Maximum {MAX_ASNS} ASNs per request.",
            finished_at=True,
        )
        return

    update_background_job(job_id, status="running", message="lookup running")
    all_rows: list[dict[str, Any]] = []
    total = len(asns)

    try:
        update_background_job(
            job_id,
            progress={"type": "parsed", "asns": asns, "total": total},
        )
        for index, asn in enumerate(asns):
            rows = await asyncio.to_thread(lookup_asn, asn, timeout)
            row_dicts = [row.to_dict() for row in rows]
            all_rows.extend(row_dicts)
            update_background_job(
                job_id,
                progress={
                    "type": "progress",
                    "index": index + 1,
                    "total": total,
                    "asn": asn,
                    "rows": row_dicts,
                },
            )
            if index + 1 < total and delay:
                await asyncio.sleep(delay)

        emails = sum(1 for row in all_rows if row.get("email"))
        errors = sum(1 for row in all_rows if row.get("error"))
        update_background_job(
            job_id,
            status="done",
            message="lookup complete",
            progress={"type": "done"},
            result={
                "asns": total,
                "rows": all_rows,
                "emails": emails,
                "errors": errors,
                "csv": _rows_to_csv(all_rows),
            },
            finished_at=True,
        )
    except Exception as exc:  # noqa: BLE001 — persist job failure for UI polling
        logger.exception("lookup job %s failed", job_id)
        update_background_job(
            job_id,
            status="error",
            message=str(exc),
            finished_at=True,
        )


def _rows_to_csv(rows: list[dict[str, Any]]) -> str:
    objects = [
        RoleContact(
            asn=int(row.get("asn") or 0),
            org=row.get("org") or None,
            roles=row.get("roles") if isinstance(row.get("roles"), list) else [],
            name=row.get("name") or None,
            email=row.get("email") or None,
            handle=row.get("handle") or None,
            rir=row.get("rir") or None,
            error=row.get("error") or None,
        )
        for row in rows
    ]
    return rows_to_csv(objects)


async def _run_lead_discover_job(job_id: int) -> None:
    job = get_background_job(job_id)
    if not job:
        return
    params = json.loads(job.get("params_json") or "{}")
    query = str(params.get("query") or "")
    min_score = int(params.get("min_score") or 60)
    delay = float(params.get("delay") or 0.5)
    auto_import = bool(params.get("auto_import"))
    user_id = int(job["user_id"])

    update_background_job(job_id, status="running", message="lead discovery running")
    leads: list[dict[str, Any]] = []
    last_import: dict[str, Any] | None = None

    try:
        async for event in discover_leads_stream(
            query,
            min_score=min_score,
            delay=delay,
            auto_import=auto_import,
            user_id=user_id,
        ):
            event_type = event.get("type")
            if event_type == "error":
                update_background_job(
                    job_id,
                    status="error",
                    message=str(event.get("message") or "lead discovery failed"),
                    progress=event,
                    finished_at=True,
                )
                return
            if event_type == "lead":
                lead = event.get("lead")
                if lead:
                    leads.append(lead)
            if event_type == "done":
                last_import = event.get("import")
                if event.get("leads"):
                    leads = list(event.get("leads") or [])
            update_background_job(job_id, progress=event)

        update_background_job(
            job_id,
            status="done",
            message=f"found {len(leads)} leads",
            progress={"type": "done"},
            result={"leads": leads, "import": last_import},
            finished_at=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("lead discover job %s failed", job_id)
        update_background_job(
            job_id,
            status="error",
            message=str(exc),
            finished_at=True,
        )


async def _execute_job(job_id: int) -> None:
    if job_id in _running:
        return
    _running.add(job_id)
    try:
        job = get_background_job(job_id)
        if not job or job.get("status") not in ("pending", "running"):
            return
        job_type = job.get("job_type")
        if job_type == "lookup":
            await _run_lookup_job(job_id)
        elif job_type == "lead_discover":
            await _run_lead_discover_job(job_id)
        else:
            update_background_job(
                job_id,
                status="error",
                message=f"unknown job type: {job_type}",
                finished_at=True,
            )
    finally:
        _running.discard(job_id)


def spawn_background_job(user_id: int, job_type: str, params: dict[str, Any]) -> dict:
    job = create_background_job(user_id, job_type, params)
    asyncio.create_task(_execute_job(job["id"]))
    return _public_job(job) or {}


def recover_background_jobs_on_startup() -> None:
    mark_interrupted_background_jobs()


def get_job_for_user(user_id: int, job_id: int) -> dict | None:
    return _public_job(get_background_job(job_id, user_id=user_id))


def list_jobs_for_user(user_id: int, *, active_only: bool = False) -> list[dict]:
    jobs = list_background_jobs(user_id, active_only=active_only)
    return [_public_job(job) or {} for job in jobs]

from __future__ import annotations

import asyncio
import logging

from app.database import insert_job_run, list_due_scheduled_jobs, mark_job_run
from app.lead_discovery import run_lead_discovery_batch
from app.llm import llm_configured
from app.settings_store import get_setting

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None


def scheduler_enabled() -> bool:
    return get_setting("scheduler_enabled", "1") != "0"


def scheduler_interval_seconds() -> int:
    try:
        return max(30, int(get_setting("scheduler_poll_seconds", "60") or 60))
    except ValueError:
        return 60


async def _run_job(job: dict) -> None:
    job_id = job["id"]
    user_id = job["user_id"]
    try:
        result = await run_lead_discovery_batch(
            job["query"],
            min_score=job["min_score"],
            delay=0.5,
            auto_import=job["auto_import"],
            user_id=user_id,
        )
        if result.get("error"):
            msg = result["error"]
            mark_job_run(
                job_id,
                status="error",
                message=msg,
                interval_hours=job["interval_hours"],
            )
            insert_job_run(job_id, status="error", message=msg)
            return
        leads = result.get("leads") or []
        imported = (result.get("import") or {}).get("imported", 0)
        msg = f"找到 {len(leads)} 条线索，导入 {imported} 条"
        mark_job_run(
            job_id,
            status="ok",
            message=msg,
            interval_hours=job["interval_hours"],
        )
        insert_job_run(
            job_id,
            status="ok",
            message=msg,
            leads_found=len(leads),
            imported=imported,
        )
    except Exception as exc:
        logger.exception("Scheduled job %s failed", job_id)
        msg = str(exc)
        mark_job_run(
            job_id,
            status="error",
            message=msg,
            interval_hours=job["interval_hours"],
        )
        insert_job_run(job_id, status="error", message=msg)


async def _scheduler_loop() -> None:
    while True:
        try:
            if llm_configured():
                jobs = list_due_scheduled_jobs()
                for job in jobs:
                    await _run_job(job)
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(scheduler_interval_seconds())


async def start_scheduler() -> None:
    global _scheduler_task
    if not scheduler_enabled():
        return
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())


async def stop_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None

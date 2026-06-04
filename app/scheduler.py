from __future__ import annotations

import asyncio
import logging
import os

from app.database import list_due_scheduled_jobs, mark_job_run
from app.lead_discovery import run_lead_discovery_batch
from app.llm import llm_configured

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None


def scheduler_enabled() -> bool:
    return os.getenv("SCHEDULER_ENABLED", "1") != "0"


def scheduler_interval_seconds() -> int:
    try:
        return max(30, int(os.getenv("SCHEDULER_POLL_SECONDS", "60")))
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
            mark_job_run(
                job_id,
                status="error",
                message=result["error"],
                interval_hours=job["interval_hours"],
            )
            return
        leads = result.get("leads") or []
        imported = (result.get("import") or {}).get("imported", 0)
        mark_job_run(
            job_id,
            status="ok",
            message=f"找到 {len(leads)} 条线索，导入 {imported} 条",
            interval_hours=job["interval_hours"],
        )
    except Exception as exc:
        logger.exception("Scheduled job %s failed", job_id)
        mark_job_run(
            job_id,
            status="error",
            message=str(exc),
            interval_hours=job["interval_hours"],
        )


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

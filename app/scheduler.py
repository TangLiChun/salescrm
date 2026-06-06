from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.database import (
    claim_scheduled_job,
    count_active_scheduled_jobs,
    insert_job_run,
    list_due_scheduled_jobs,
    mark_job_run,
)
from app.lead_discovery import run_lead_discovery_batch
from app.llm import llm_configured
from app.settings_store import get_setting

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None
_running_jobs: set[int] = set()
_run_lock = asyncio.Lock()


def scheduler_enabled() -> bool:
    return get_setting("scheduler_enabled", "1") != "0"


def scheduler_interval_seconds() -> int:
    try:
        return max(30, int(get_setting("scheduler_poll_seconds", "60") or 60))
    except ValueError:
        return 60


def get_scheduler_status() -> dict[str, Any]:
    counts = count_active_scheduled_jobs()
    return {
        "enabled": scheduler_enabled(),
        "running": _scheduler_task is not None and not _scheduler_task.done(),
        "poll_seconds": scheduler_interval_seconds(),
        "llm_configured": llm_configured(),
        "active_jobs": counts["running"],
        "enabled_jobs": counts["enabled"],
        "total_jobs": counts["total"],
    }


async def run_scheduled_job(job: dict) -> dict:
    from app.lead_preferences import effective_min_score, get_prefs

    job_id = int(job["id"])
    user_id = int(job["user_id"])
    if not claim_scheduled_job(job_id):
        return {"ok": False, "status": "skipped", "message": "任务已在运行中"}

    prefs = get_prefs(user_id)
    min_score = effective_min_score(prefs, int(job["min_score"]))

    try:
        result = await run_lead_discovery_batch(
            job["query"],
            min_score=min_score,
            delay=0.5,
            auto_import=bool(job["auto_import"]),
            user_id=user_id,
        )
        schedule_kwargs = {
            "interval_minutes": int(
                job.get("interval_minutes") or job.get("interval_hours", 24) * 60
            ),
            "run_mode": job.get("run_mode") or "interval",
            "cooldown_minutes": int(job.get("cooldown_minutes") or 15),
        }
        if result.get("error"):
            msg = result["error"]
            mark_job_run(job_id, status="error", message=msg, **schedule_kwargs)
            insert_job_run(job_id, status="error", message=msg)
            return {"ok": False, "status": "error", "message": msg}
        leads = result.get("leads") or []
        imported = (result.get("import") or {}).get("imported", 0)
        msg = f"找到 {len(leads)} 条线索，导入 {imported} 条"
        mark_job_run(job_id, status="ok", message=msg, **schedule_kwargs)
        insert_job_run(
            job_id,
            status="ok",
            message=msg,
            leads_found=len(leads),
            imported=imported,
        )
        return {
            "ok": True,
            "status": "ok",
            "message": msg,
            "leads_found": len(leads),
            "imported": imported,
        }
    except Exception as exc:
        logger.exception("Scheduled job %s failed", job_id)
        msg = str(exc)
        mark_job_run(
            job_id,
            status="error",
            message=msg,
            interval_minutes=int(job.get("interval_minutes") or job.get("interval_hours", 24) * 60),
            run_mode=job.get("run_mode") or "interval",
            cooldown_minutes=int(job.get("cooldown_minutes") or 15),
        )
        insert_job_run(job_id, status="error", message=msg)
        return {"ok": False, "status": "error", "message": msg}
    finally:
        _running_jobs.discard(job_id)


async def _run_job(job: dict) -> None:
    job_id = int(job["id"])
    async with _run_lock:
        if job_id in _running_jobs:
            return
        _running_jobs.add(job_id)
    try:
        await run_scheduled_job(job)
    finally:
        _running_jobs.discard(job_id)


async def _scheduler_loop() -> None:
    logger.info("Lead discovery scheduler started (poll=%ss)", scheduler_interval_seconds())
    while True:
        try:
            if scheduler_enabled() and llm_configured():
                jobs = list_due_scheduled_jobs()
                if jobs:
                    logger.info("Running %s due scheduled job(s)", len(jobs))
                for job in jobs:
                    if not scheduler_enabled():
                        break
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


async def restart_scheduler() -> None:
    await stop_scheduler()
    await start_scheduler()

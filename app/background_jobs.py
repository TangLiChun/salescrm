from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from app.agent_chat import (
    agent_chat_stream,
    history_entry_from_agent_event,
    is_pi_thread_streaming,
    tool_result_summary,
)
from app.contact_enrichment import enrich_contact_stream
from app.database import (
    create_background_job,
    get_background_job,
    has_active_pi_agent_job,
    list_background_jobs,
    list_resumable_background_jobs,
    update_background_job,
    utc_now,
)
from app.lead_checkpoint import (
    checkpoint_resume_message,
    parse_checkpoint,
    progress_from_checkpoint,
)
from app.lead_discovery import discover_leads_stream
from app.pi_agent_proxy import pi_agent_service_url, stream_pi_agent_events
from app.pi_chat_store import (
    append_pi_thread_history_entries,
    compress_thread_context_until_current,
    get_pi_thread,
    upsert_pi_thread,
)
from arin_lookup import RoleContact, lookup_asns_batch, parse_asns_from_text, rows_to_csv

logger = logging.getLogger(__name__)

_running: set[int] = set()
_cancel_requested: set[int] = set()
_job_tasks: dict[int, asyncio.Task] = {}
MAX_ASNS = 200
MAX_PROGRESS_EVENTS = 40
_job_event_subscribers: dict[int, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)


def _is_cancelled(job_id: int) -> bool:
    return job_id in _cancel_requested


def request_cancel_background_job(user_id: int, job_id: int) -> dict | None:
    job = get_background_job(job_id, user_id=user_id)
    if not job or job.get("status") not in ("pending", "running"):
        return None
    _cancel_requested.add(job_id)
    _update_job(job_id, message="正在停止…")
    task = _job_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
    return get_job_for_user(user_id, job_id)


def _update_job(job_id: int, **kwargs: Any) -> None:
    update_background_job(job_id, **kwargs)
    _publish_job_event(job_id)


def _publish_job_event(job_id: int) -> None:
    job = get_background_job(job_id)
    if not job:
        return
    public = _public_job(job)
    if not public:
        return
    user_id = int(job["user_id"])
    payload = {"type": "job", "job": public}
    dead: list[asyncio.Queue[dict[str, Any]]] = []
    for queue in list(_job_event_subscribers.get(user_id, ())):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(queue)
    for queue in dead:
        unsubscribe_job_events(user_id, queue)


def subscribe_job_events(user_id: int) -> asyncio.Queue[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
    _job_event_subscribers[user_id].add(queue)
    return queue


def unsubscribe_job_events(user_id: int, queue: asyncio.Queue[dict[str, Any]]) -> None:
    subs = _job_event_subscribers.get(user_id)
    if not subs:
        return
    subs.discard(queue)
    if not subs:
        _job_event_subscribers.pop(user_id, None)


def _public_job(job: dict | None) -> dict | None:
    if not job:
        return None
    out = dict(job)
    checkpoint = parse_checkpoint(out.get("checkpoint_json"))
    if checkpoint:
        out["checkpoint_phase"] = checkpoint.get("phase")
    out.pop("checkpoint_json", None)
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


def _progress_event_label(event: dict[str, Any]) -> str:
    event_type = event.get("type") or "status"
    if event_type == "tool_start":
        name = str(event.get("name") or "tool")
        return f"调用 {name}"
    if event_type == "tool_progress":
        name = str(event.get("name") or "tool")
        message = str(event.get("message") or "").strip()
        return f"{name} · {message}" if message else name
    if event_type == "tool_result":
        name = str(event.get("name") or "tool")
        summary = str(event.get("summary") or event.get("message") or "").strip()
        return f"{name} 完成 · {summary[:120]}" if summary else f"{name} 完成"
    if event_type == "assistant_done":
        text = str(event.get("text") or "").strip()
        return text[:160] if text else "助手回复"
    message = str(event.get("message") or "").strip()
    if message:
        return message
    if event_type == "progress" and event.get("asn"):
        return f"AS{event.get('asn')}"
    return event_type


def _merge_progress_events(
    job_id: int, slim: dict[str, Any], event: dict[str, Any]
) -> dict[str, Any]:
    job = get_background_job(job_id)
    current: dict[str, Any] = {}
    if job and job.get("progress_json"):
        try:
            current = json.loads(job["progress_json"])
        except json.JSONDecodeError:
            current = {}
    events = list(current.get("events") or [])
    events.append(
        {
            "type": slim.get("type") or event.get("type") or "status",
            "message": _progress_event_label(event),
            "name": slim.get("name") or event.get("name"),
            "at": utc_now().isoformat(),
        }
    )
    slim["events"] = events[-MAX_PROGRESS_EVENTS:]
    return slim


def _update_job_progress(job_id: int, event: dict[str, Any], **kwargs: Any) -> None:
    slim = _merge_progress_events(job_id, _slim_progress(event), event)
    _update_job(job_id, progress=slim, **kwargs)


def _slim_progress(event: dict[str, Any]) -> dict[str, Any]:
    """Store lightweight progress snapshots; full payloads belong in result_json."""
    event_type = event.get("type") or "status"
    if event_type == "progress":
        asn = event.get("asn")
        message = event.get("message") or (f"AS{asn}" if asn else "")
        return {
            "type": "progress",
            "index": event.get("index"),
            "total": event.get("total"),
            "asn": asn,
            "message": message,
        }
    slim: dict[str, Any] = {"type": event_type}
    message = event.get("message")
    if message:
        slim["message"] = str(message)
    if event_type == "source_result":
        slim["source"] = event.get("source")
        slim["count"] = event.get("count")
    if event.get("phase"):
        slim["phase"] = event.get("phase")
    if event_type in ("tool_start", "tool_progress", "tool_result"):
        slim["name"] = event.get("name")
    if event_type == "parsed":
        slim["total"] = event.get("total")
    return slim


async def _run_lookup_job(job_id: int) -> None:
    if _is_cancelled(job_id):
        _update_job(job_id, status="cancelled", message="已停止", finished_at=True)
        return
    job = get_background_job(job_id)
    if not job:
        return
    params = json.loads(job.get("params_json") or "{}")
    text = str(params.get("text") or "")
    delay = float(params.get("delay") or 0)
    timeout = float(params.get("timeout") or 30)

    asns = parse_asns_from_text(text)
    if not asns:
        _update_job(
            job_id,
            status="error",
            message="No valid ASNs found.",
            finished_at=True,
        )
        return
    if len(asns) > MAX_ASNS:
        _update_job(
            job_id,
            status="error",
            message=f"Maximum {MAX_ASNS} ASNs per request.",
            finished_at=True,
        )
        return

    _update_job(job_id, status="running", message="lookup running")
    total = len(asns)

    try:
        _update_job_progress(
            job_id,
            {"type": "parsed", "total": total, "message": f"parsed {total} ASNs"},
        )

        async def on_progress(index: int, total: int, asn: int, rows) -> None:
            if _is_cancelled(job_id):
                raise asyncio.CancelledError("job cancelled")
            _update_job_progress(
                job_id,
                {
                    "type": "progress",
                    "index": index,
                    "total": total,
                    "asn": asn,
                    "message": f"AS{asn}",
                },
            )

        batch_rows = await lookup_asns_batch(
            asns,
            timeout,
            delay=delay,
            on_progress=on_progress,
        )
        if _is_cancelled(job_id):
            _update_job(job_id, status="cancelled", message="已停止", finished_at=True)
            return
        all_rows = [row.to_dict() for row in batch_rows]

        emails = sum(1 for row in all_rows if row.get("email"))
        errors = sum(1 for row in all_rows if row.get("error"))
        _update_job(
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
    except asyncio.CancelledError:
        _update_job(job_id, status="cancelled", message="已停止", finished_at=True)
    except Exception as exc:  # noqa: BLE001 — persist job failure for UI polling
        logger.exception("lookup job %s failed", job_id)
        _update_job(
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

    checkpoint = parse_checkpoint(job.get("checkpoint_json"))
    if checkpoint and checkpoint.get("query") != query:
        checkpoint = None

    start_message = checkpoint_resume_message(checkpoint) or "lead discovery running"
    _update_job(job_id, status="running", message=start_message)
    leads: list[dict[str, Any]] = []
    last_import: dict[str, Any] | None = None

    def save_checkpoint(data: dict[str, Any]) -> None:
        _update_job(
            job_id,
            checkpoint=data,
            progress=progress_from_checkpoint(data),
        )

    try:
        async for event in discover_leads_stream(
            query,
            min_score=min_score,
            delay=delay,
            auto_import=auto_import,
            user_id=user_id,
            checkpoint=checkpoint,
            on_checkpoint=save_checkpoint,
        ):
            if _is_cancelled(job_id):
                _update_job(job_id, status="cancelled", message="已停止", finished_at=True)
                return
            event_type = event.get("type")
            if event_type == "error":
                _update_job(
                    job_id,
                    status="error",
                    message=str(event.get("message") or "lead discovery failed"),
                    progress=_slim_progress(event),
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
            _update_job_progress(job_id, event)

        _update_job(
            job_id,
            status="done",
            message=f"found {len(leads)} leads",
            progress={"type": "done"},
            result={"leads": leads, "import": last_import},
            clear_checkpoint=True,
            finished_at=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("lead discover job %s failed", job_id)
        _update_job(
            job_id,
            status="error",
            message=str(exc),
            finished_at=True,
        )


async def _run_enrich_contact_job(job_id: int) -> None:
    job = get_background_job(job_id)
    if not job:
        return
    params = json.loads(job.get("params_json") or "{}")
    contact_id = int(params.get("contact_id") or 0)
    min_score = int(params.get("min_score") or 50)
    auto_import = bool(params.get("auto_import", True))
    user_id = int(job["user_id"])

    if contact_id <= 0:
        _update_job(
            job_id,
            status="error",
            message="contact_id invalid",
            finished_at=True,
        )
        return

    _update_job(job_id, status="running", message="contact enrich running")
    leads: list[dict[str, Any]] = []
    last_import: dict[str, Any] | None = None
    done_message = ""

    try:
        async for event in enrich_contact_stream(
            user_id,
            contact_id,
            min_score=min_score,
            auto_import=auto_import,
        ):
            if _is_cancelled(job_id):
                _update_job(job_id, status="cancelled", message="已停止", finished_at=True)
                return
            event_type = event.get("type")
            if event_type == "error":
                _update_job(
                    job_id,
                    status="error",
                    message=str(event.get("message") or "contact enrich failed"),
                    progress=_slim_progress(event),
                    finished_at=True,
                )
                return
            if event_type == "lead":
                lead = event.get("lead")
                if lead:
                    leads.append(lead)
            if event_type == "done":
                last_import = event.get("import")
                done_message = str(event.get("message") or "")
                if event.get("leads"):
                    leads = list(event.get("leads") or [])
            _update_job_progress(job_id, event)

        _update_job(
            job_id,
            status="done",
            message=done_message or f"enriched contact #{contact_id}: {len(leads)} leads",
            progress={"type": "done"},
            result={
                "leads": leads,
                "import": last_import,
                "contact_id": contact_id,
                "message": done_message,
            },
            finished_at=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("enrich contact job %s failed", job_id)
        _update_job(
            job_id,
            status="error",
            message=str(exc),
            finished_at=True,
        )


def _ensure_user_message_on_thread(user_id: int, thread_id: str | None, message: str) -> None:
    if not thread_id or not message:
        return
    thread = get_pi_thread(user_id, thread_id)
    history = list((thread or {}).get("history") or [])
    if history and history[-1].get("role") == "user" and history[-1].get("content") == message:
        return
    upsert_pi_thread(user_id, thread_id, history=history + [{"role": "user", "content": message}])


async def _run_pi_agent_job(job_id: int) -> None:
    job = get_background_job(job_id)
    if not job:
        return
    params = json.loads(job.get("params_json") or "{}")
    message = str(params.get("message") or "").strip()
    thread_id = str(params.get("thread_id") or "").strip() or None
    user_id = int(job["user_id"])

    if not message:
        _update_job(
            job_id,
            status="error",
            message="empty message",
            finished_at=True,
        )
        return

    _update_job(job_id, status="running", message="Pi 任务运行中")
    _ensure_user_message_on_thread(user_id, thread_id, message)

    new_entries: list[dict[str, Any]] = []
    last_assistant = ""
    error_msg: str | None = None

    try:
        stream_source = (
            stream_pi_agent_events(
                user_id,
                message,
                thread_id=thread_id,
                history=None,
                cancel_check=lambda: _is_cancelled(job_id),
            )
            if pi_agent_service_url()
            else agent_chat_stream(
                user_id,
                message,
                None,
                thread_id=thread_id,
                cancel_check=lambda: _is_cancelled(job_id),
            )
        )
        async for event in stream_source:
            event_type = event.get("type")
            if event_type == "error":
                error_msg = str(event.get("message") or "Pi 任务失败")
                if error_msg == "任务已停止":
                    error_msg = None
                break
            if event_type == "tool_start":
                _update_job_progress(job_id, event)
            elif event_type in ("status", "tool_progress"):
                _update_job_progress(job_id, event)
            elif event_type == "tool_result":
                name = str(event.get("name") or "tool")
                result = event.get("result") or {}
                summary = tool_result_summary(name, result)
                _update_job_progress(
                    job_id,
                    {**event, "summary": summary},
                )
                entry = history_entry_from_agent_event(event)
                if entry:
                    new_entries.append(entry)
            elif event_type == "assistant_done":
                text = str(event.get("text") or "").strip()
                _update_job_progress(job_id, event)
                entry = history_entry_from_agent_event(event)
                if entry:
                    new_entries.append(entry)
                    last_assistant = text
            elif event_type == "done":
                break

        if _is_cancelled(job_id):
            if thread_id and new_entries:
                append_pi_thread_history_entries(user_id, thread_id, new_entries)
            _update_job(
                job_id,
                status="cancelled",
                message="已停止",
                progress={"type": "cancelled", "message": "已停止"},
                result={
                    "thread_id": thread_id,
                    "assistant": last_assistant,
                    "entries": len(new_entries),
                    "partial": True,
                },
                finished_at=True,
            )
            return

        if error_msg:
            if thread_id and new_entries:
                append_pi_thread_history_entries(user_id, thread_id, new_entries)
            _update_job(
                job_id,
                status="error",
                message=error_msg,
                progress={"type": "error", "message": error_msg},
                finished_at=True,
            )
            return

        if thread_id and new_entries:
            append_pi_thread_history_entries(user_id, thread_id, new_entries)
            await asyncio.to_thread(compress_thread_context_until_current, user_id, thread_id)

        _update_job(
            job_id,
            status="done",
            message=(last_assistant[:200] if last_assistant else "Pi 任务完成"),
            progress={"type": "done"},
            result={
                "thread_id": thread_id,
                "assistant": last_assistant,
                "entries": len(new_entries),
            },
            finished_at=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("pi agent job %s failed", job_id)
        _update_job(
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
        if _is_cancelled(job_id):
            _update_job(job_id, status="cancelled", message="已停止", finished_at=True)
            return
        job = get_background_job(job_id)
        if not job or job.get("status") not in ("pending", "running"):
            return
        job_type = job.get("job_type")
        if job_type == "lookup":
            await _run_lookup_job(job_id)
        elif job_type == "lead_discover":
            await _run_lead_discover_job(job_id)
        elif job_type == "enrich_contact":
            await _run_enrich_contact_job(job_id)
        elif job_type == "pi_agent":
            await _run_pi_agent_job(job_id)
        else:
            _update_job(
                job_id,
                status="error",
                message=f"unknown job type: {job_type}",
                finished_at=True,
            )
    except asyncio.CancelledError:
        _update_job(job_id, status="cancelled", message="已停止", finished_at=True)
    finally:
        _running.discard(job_id)
        _cancel_requested.discard(job_id)
        _job_tasks.pop(job_id, None)


def spawn_background_job(user_id: int, job_type: str, params: dict[str, Any]) -> dict:
    if job_type == "pi_agent":
        thread_id = str(params.get("thread_id") or "").strip()
        if thread_id:
            if has_active_pi_agent_job(user_id, thread_id):
                raise PiAgentThreadBusyError(thread_id)
            if is_pi_thread_streaming(user_id, thread_id):
                raise PiAgentThreadBusyError(thread_id)
    job = create_background_job(user_id, job_type, params)
    job_id = int(job["id"])
    task = asyncio.create_task(_execute_job(job_id))
    _job_tasks[job_id] = task
    _publish_job_event(job_id)
    return _public_job(job) or {}


class PiAgentThreadBusyError(Exception):
    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        super().__init__(f"pi_agent already running for thread {thread_id}")


async def recover_background_jobs_on_startup() -> None:
    jobs = list_resumable_background_jobs()
    if not jobs:
        return
    for job in jobs:
        job_id = int(job["id"])
        if job.get("status") == "running":
            resume_msg = ""
            if job.get("job_type") == "lead_discover":
                resume_msg = checkpoint_resume_message(parse_checkpoint(job.get("checkpoint_json")))
            message = resume_msg or "服务重启，已重新排队"
            _update_job(
                job_id,
                status="pending",
                message=message,
            )
        asyncio.create_task(_execute_job(job_id))
    logger.info("Re-queued %s background job(s) after startup", len(jobs))


def get_job_for_user(user_id: int, job_id: int) -> dict | None:
    return _public_job(get_background_job(job_id, user_id=user_id))


def list_jobs_for_user(user_id: int, *, active_only: bool = False) -> list[dict]:
    jobs = list_background_jobs(user_id, active_only=active_only)
    return [_public_job(job) or {} for job in jobs]


async def iter_job_events(user_id: int):
    """SSE stream of background job updates for a user."""
    queue = subscribe_job_events(user_id)
    try:
        for job in list_jobs_for_user(user_id, active_only=True):
            payload = {"type": "job", "job": job}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            except TimeoutError:
                yield ": keepalive\n\n"
    finally:
        unsubscribe_job_events(user_id, queue)

from __future__ import annotations

import json
from typing import Any

PHASE_PLANNED = "planned"
PHASE_SOURCES_DONE = "sources_done"
PHASE_WEB_EXTRACTED = "web_extracted"
PHASE_RDAP_PROGRESS = "rdap_progress"
PHASE_SCORED = "scored"

PHASE_ORDER = (
    PHASE_PLANNED,
    PHASE_SOURCES_DONE,
    PHASE_WEB_EXTRACTED,
    PHASE_RDAP_PROGRESS,
    PHASE_SCORED,
)

PHASE_LABELS = {
    PHASE_PLANNED: "已规划搜索策略",
    PHASE_SOURCES_DONE: "搜索引擎/PeeringDB 采集完成",
    PHASE_WEB_EXTRACTED: "网页/论坛线索提取完成",
    PHASE_RDAP_PROGRESS: "RDAP 查询进行中",
    PHASE_SCORED: "AI 评分完成",
}


def phase_index(phase: str | None) -> int:
    if not phase:
        return -1
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return -1


def phase_at_least(current: str | None, target: str) -> bool:
    return phase_index(current) >= phase_index(target)


def parse_checkpoint(raw: Any) -> dict[str, Any] | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
    return None


def checkpoint_resume_message(checkpoint: dict[str, Any] | None) -> str:
    if not checkpoint:
        return ""
    phase = str(checkpoint.get("phase") or "")
    label = PHASE_LABELS.get(phase, phase)
    if phase == PHASE_RDAP_PROGRESS:
        done = len(checkpoint.get("rdap_done_asns") or [])
        total = len(checkpoint.get("asn_targets") or [])
        if total:
            return f"从断点续跑：{label}（{done}/{total}）"
    return f"从断点续跑：{label}"


def progress_from_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    phase = str(checkpoint.get("phase") or "")
    progress: dict[str, Any] = {"type": "checkpoint", "phase": phase}
    message = PHASE_LABELS.get(phase, phase)
    if phase == PHASE_RDAP_PROGRESS:
        done = len(checkpoint.get("rdap_done_asns") or [])
        total = len(checkpoint.get("asn_targets") or [])
        progress.update(
            {
                "index": done,
                "total": total,
                "message": f"RDAP {done}/{total}",
            }
        )
    else:
        progress["message"] = message
    return progress

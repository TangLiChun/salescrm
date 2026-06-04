from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
REQUEST_TIMEOUT = 60.0


class LLMError(RuntimeError):
    pass


def llm_configured() -> bool:
    return bool(os.getenv("LLM_API_KEY", "").strip())


def _settings() -> tuple[str, str, str]:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        raise LLMError("未配置 LLM API Key，请设置环境变量 LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("LLM_MODEL", DEFAULT_MODEL)
    return api_key, base_url, model


def chat_completion(messages: list[dict[str, str]], *, temperature: float = 0.2) -> str:
    api_key, base_url, model = _settings()
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMError(f"LLM 请求失败 ({exc.code}): {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"无法连接 LLM 服务: {exc.reason}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM 返回格式异常") from exc


def parse_json_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("LLM 未返回有效 JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMError("LLM JSON 格式不正确")
    return parsed


def plan_lead_search(user_query: str) -> dict[str, Any]:
    system = (
        "你是 B2B 网络基础设施销售线索研究助手。"
        "根据用户的自然语言需求，输出 JSON 对象，字段："
        "keywords(字符串数组，用于 PeeringDB 网络搜索，3-8 个英文关键词，如 isp,cable,datacenter,cloud), "
        "preferred_roles(字符串数组，从 abuse,administrative,technical,routing,noc 中选择，销售场景优先 technical/administrative/routing), "
        "max_asns(整数，5-30), "
        "summary(中文，简要说明搜索策略，80字以内), "
        "target_profile(中文，描述理想客户画像，60字以内)。"
        "只返回 JSON。"
    )
    raw = chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_query},
        ]
    )
    plan = parse_json_response(raw)
    keywords = [str(item).strip() for item in plan.get("keywords") or [] if str(item).strip()]
    roles = [str(item).strip() for item in plan.get("preferred_roles") or [] if str(item).strip()]
    max_asns = plan.get("max_asns", 15)
    try:
        max_asns = max(5, min(30, int(max_asns)))
    except (TypeError, ValueError):
        max_asns = 15
    if not keywords:
        keywords = _fallback_keywords(user_query)
    if not roles:
        roles = ["technical", "administrative", "routing"]
    plan["keywords"] = keywords[:8]
    plan["preferred_roles"] = roles[:5]
    plan["max_asns"] = max_asns
    plan["summary"] = str(plan.get("summary") or "将根据关键词搜索 PeeringDB 网络并查询 ARIN role 邮箱。")
    plan["target_profile"] = str(plan.get("target_profile") or user_query)
    return plan


def score_leads(user_query: str, plan: dict[str, Any], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []

    compact = []
    for index, row in enumerate(candidates):
        compact.append(
            {
                "index": index,
                "asn": row.get("asn"),
                "org": row.get("org"),
                "name": row.get("name"),
                "email": row.get("email"),
                "roles": row.get("roles"),
            }
        )

    system = (
        "你是 B2B 销售线索评分助手。根据用户需求与候选联系人，输出 JSON："
        '{"results":[{"index":0,"score":0-100,"relevant":true/false,"reason":"中文，30字以内"}]}。'
        "评分标准：与用户需求匹配度、角色是否适合销售触达（technical/administrative/routing 更高，abuse 较低）。"
        "只返回 JSON。"
    )
    user = json.dumps(
        {
            "user_query": user_query,
            "target_profile": plan.get("target_profile"),
            "candidates": compact,
        },
        ensure_ascii=False,
    )
    raw = chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
    )
    parsed = parse_json_response(raw)
    results = parsed.get("results") or []
    scored: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(candidates):
            continue
        row = dict(candidates[index])
        row["lead_score"] = max(0, min(100, int(item.get("score", 0))))
        row["lead_reason"] = str(item.get("reason") or "")
        row["lead_relevant"] = bool(item.get("relevant", row["lead_score"] >= 60))
        scored.append(row)
    return scored


def _fallback_keywords(user_query: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z]{3,}", user_query.lower())
    if tokens:
        return tokens[:5]
    return ["network", "isp", "datacenter"]

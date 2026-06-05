from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.settings_store import get_setting
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
REQUEST_TIMEOUT = 60.0
AGENT_REQUEST_TIMEOUT = 180.0


class LLMError(RuntimeError):
    pass


def llm_configured() -> bool:
    return bool(get_setting("llm_api_key", "").strip())


def _settings() -> tuple[str, str, str]:
    api_key = get_setting("llm_api_key", "").strip()
    if not api_key:
        raise LLMError("未配置 LLM API Key，请在系统设置中填写")
    base_url = get_setting("llm_base_url", DEFAULT_BASE_URL).rstrip("/")
    model = get_setting("llm_model", DEFAULT_MODEL)
    return api_key, base_url, model


def chat_completion(messages: list[dict[str, str]], *, temperature: float = 0.2) -> str:
    message = chat_completion_with_tools(messages, tools=None, temperature=temperature, json_mode=True)
    content = message.get("content")
    if not content:
        raise LLMError("LLM 返回空内容")
    return content


def chat_completion_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> dict[str, Any]:
    message = None
    for event in chat_completion_with_tools_stream(
        messages,
        tools,
        temperature=temperature,
        json_mode=json_mode,
    ):
        if event.get("type") == "message":
            message = event["message"]
        elif event.get("type") == "error":
            raise LLMError(event.get("message") or "LLM 请求失败")
    if not message:
        raise LLMError("LLM 返回空内容")
    return message


def chat_completion_with_tools_stream(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    temperature: float = 0.2,
    json_mode: bool = False,
):
    """Yield content deltas while streaming, then the assembled assistant message."""
    api_key, base_url, model = _settings()
    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    elif json_mode:
        payload["response_format"] = {"type": "json_object"}

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = AGENT_REQUEST_TIMEOUT if tools else REQUEST_TIMEOUT

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: dict[int, dict[str, Any]] = {}

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece:
                    content_parts.append(piece)
                    if not tools:
                        yield {"type": "content_delta", "text": piece}

                reasoning_piece = delta.get("reasoning_content")
                if reasoning_piece:
                    reasoning_parts.append(reasoning_piece)

                for tool_delta in delta.get("tool_calls") or []:
                    index = int(tool_delta.get("index") or 0)
                    slot = tool_calls.setdefault(
                        index,
                        {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        },
                    )
                    if tool_delta.get("id"):
                        slot["id"] = tool_delta["id"]
                    fn = tool_delta.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        yield {"type": "error", "message": f"LLM 请求失败 ({exc.code}): {detail[:300]}"}
        return
    except urllib.error.URLError as exc:
        yield {"type": "error", "message": f"无法连接 LLM 服务: {exc.reason}"}
        return

    message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts) or None}
    if reasoning_parts:
        message["reasoning_content"] = "".join(reasoning_parts)
    if tool_calls:
        message["tool_calls"] = [tool_calls[index] for index in sorted(tool_calls)]
    yield {"type": "message", "message": message}


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


def plan_lead_search(user_query: str, *, preference_hints: str | None = None) -> dict[str, Any]:
    system = (
        "你是 B2B 销售线索研究助手，会通过多种渠道找线索：搜索引擎、PeeringDB、ARIN RDAP。"
        "根据用户需求输出 JSON："
        "keywords(3-8个英文词，用于 PeeringDB/网络库搜索), "
        "web_queries(3-6个搜索引擎查询语句，英文为主，覆盖公司类型/行业/联系人/peering/ASN等角度), "
        "preferred_roles(从 abuse,administrative,technical,routing,noc 选，销售优先 technical/administrative/routing), "
        "max_asns(5-25), max_web_results(10-30), "
        "summary(中文，80字内，说明多渠道搜索策略), "
        "target_profile(中文，理想客户画像)。"
        "只返回 JSON。"
    )
    user_content = user_query
    if preference_hints:
        user_content = f"{user_query}\n\n【用户历史偏好与反馈】\n{preference_hints}"
    raw = chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
    )
    plan = parse_json_response(raw)
    keywords = [str(item).strip() for item in plan.get("keywords") or [] if str(item).strip()]
    web_queries = [str(item).strip() for item in plan.get("web_queries") or [] if str(item).strip()]
    roles = [str(item).strip() for item in plan.get("preferred_roles") or [] if str(item).strip()]
    max_asns = plan.get("max_asns", 15)
    max_web_results = plan.get("max_web_results", 20)
    try:
        max_asns = max(5, min(25, int(max_asns)))
    except (TypeError, ValueError):
        max_asns = 15
    try:
        max_web_results = max(10, min(30, int(max_web_results)))
    except (TypeError, ValueError):
        max_web_results = 20
    if not keywords:
        keywords = _fallback_keywords(user_query)
    if not web_queries:
        web_queries = [f"{kw} ASN peering contact email" for kw in keywords[:4]]
    if not roles:
        roles = ["technical", "administrative", "routing"]
    plan["keywords"] = keywords[:8]
    plan["web_queries"] = web_queries[:6]
    plan["preferred_roles"] = roles[:5]
    plan["max_asns"] = max_asns
    plan["max_web_results"] = max_web_results
    plan["summary"] = str(
        plan.get("summary") or "将通过搜索引擎、PeeringDB 和 ARIN RDAP 多渠道搜索并汇总线索。"
    )
    plan["target_profile"] = str(plan.get("target_profile") or user_query)
    return plan


def extract_leads_from_web(
    user_query: str,
    plan: dict[str, Any],
    web_results: list[dict[str, Any]],
    regex_emails: list[str],
    regex_asns: list[int],
) -> list[dict[str, Any]]:
    if not web_results and not regex_emails:
        return []

    compact_results = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "snippet": item.get("snippet"),
            "backend": item.get("backend"),
        }
        for item in web_results[:25]
    ]
    system = (
        "你是销售线索提取助手。从搜索引擎结果中提取潜在客户线索，输出 JSON："
        '{"leads":[{"org":"公司/组织名","name":"联系人或部门名","email":"邮箱或空","asn":12345或null,"source_detail":"来源说明","confidence":0-100}]}。'
        "规则：只提取与用户需求相关的网络/ISP/数据中心/云/CDN/基础设施公司；"
        "优先有邮箱的；没有邮箱但有明确 ASN 也可输出；不要编造邮箱；confidence 表示匹配度。"
        "最多 20 条。只返回 JSON。"
    )
    user = json.dumps(
        {
            "user_query": user_query,
            "target_profile": plan.get("target_profile"),
            "search_results": compact_results,
            "regex_emails": regex_emails[:20],
            "regex_asns": regex_asns[:20],
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
    leads: list[dict[str, Any]] = []
    for item in parsed.get("leads") or []:
        if not isinstance(item, dict):
            continue
        email = str(item.get("email") or "").strip().lower()
        org = str(item.get("org") or "").strip()
        asn = item.get("asn")
        if not email and not org and not asn:
            continue
        row: dict[str, Any] = {
            "org": org,
            "name": str(item.get("name") or "").strip(),
            "email": email,
            "roles": [],
            "source": "web-search",
            "source_detail": str(item.get("source_detail") or "搜索引擎"),
            "lead_confidence": max(0, min(100, int(item.get("confidence", 50)))),
        }
        if asn:
            try:
                row["asn"] = int(asn)
            except (TypeError, ValueError):
                pass
        leads.append(row)

    for email in regex_emails:
        if any(lead.get("email") == email for lead in leads):
            continue
        leads.append(
            {
                "org": "",
                "name": "",
                "email": email,
                "roles": [],
                "source": "web-search",
                "source_detail": "搜索引擎正则提取",
                "lead_confidence": 40,
            }
        )
    return leads[:20]


def score_leads(
    user_query: str,
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    preference_hints: str | None = None,
) -> list[dict[str, Any]]:
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
                "source": row.get("source"),
                "source_detail": row.get("source_detail"),
            }
        )

    system = (
        "你是 B2B 销售线索评分助手。根据用户需求与候选联系人，输出 JSON："
        '{"results":[{"index":0,"score":0-100,"relevant":true/false,"reason":"中文，30字以内"}]}。'
        "评分标准：与用户需求匹配度、角色是否适合销售触达（technical/administrative/routing 更高，abuse 较低）。"
    )
    if preference_hints:
        system += f" 用户历史反馈：{preference_hints}"
    system += " 只返回 JSON。"
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

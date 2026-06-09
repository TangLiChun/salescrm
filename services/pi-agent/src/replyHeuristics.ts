import { randomUUID } from "node:crypto";
import {
  extractJsonArgs,
  inferToolName,
  prepareToolCalls,
  type ToolRegistry,
} from "./toolCalls.js";

// Markers that unambiguously begin a machine tool-call payload leaking into the
// assistant's text content. Kept deliberately narrow: only patterns that start a
// JSON tool-call object/array or a known special-token block. Bare keys like
// '"name":' and the old '\n[' / startsWith('[') heuristics were removed because
// they silently truncate ordinary prose (markdown links, "[1]" references,
// bracketed labels, JSON examples) — the "reply a few words then stop" bug.
const TOOL_CONTENT_MARKERS = [
  "[{",
  "[工具",
  "[tool",
  "tool_calls",
  "tool_call",
  "dsml",
  "<|",
  "<｜",
  "```json",
  '{"query',
  '{"queries',
  '{"name"',
  '{"function"',
];

export const EMPTY_RESPONSE_NUDGE =
  "（系统）请用中文回复用户，并调用合适的 CRM 工具完成任务，" +
  "例如 list_contacts（搜索联系人）、delete_contacts（删除联系人）。";

export const INTRO_ONLY_NUDGE =
  "（系统）不要只回复开场白就停止。请立即调用 list_contacts、discover_leads、web_search、" +
  "lookup_asns 等工具完成用户请求，然后再总结结果。";

export const CONTINUE_NUDGE =
  "（系统）用户要求继续上一任务。不要只回复「好的、继续」就结束。" +
  "请立即调用 discover_leads、list_contacts、lookup_asns 等工具继续执行，然后再总结。";

export function assistantIntroBeforeTools(content: string): string {
  const text = (content || "").trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  let cutAt = text.length;
  for (const marker of TOOL_CONTENT_MARKERS) {
    const idx = lower.indexOf(marker.toLowerCase());
    if (idx >= 0) cutAt = Math.min(cutAt, idx);
  }
  let result = text.slice(0, cutAt).trim();
  if (result.endsWith("[")) result = result.slice(0, -1).trimEnd();
  return result;
}

function contentLooksLikeToolCall(content: string): boolean {
  const lower = (content || "").toLowerCase();
  if (TOOL_CONTENT_MARKERS.some((marker) => lower.includes(marker.toLowerCase()))) return true;
  return /^\s*[\[{]/.test(content || "");
}

function contentIsToolJsonFragment(content: string): boolean {
  const text = (content || "").trim();
  if (!text) return false;
  if (["[", "{", "(", "[{", "({"].includes(text)) return true;
  if (/^[\[\{\(,]+$/.test(text)) return true;
  // Short JSON-looking fragment (e.g. '[{' or '{"q') — but NOT bracketed prose
  // like "[已完成] 已导入 3 条线索。". Require a JSON opener after the bracket.
  if (/^[\[\{]\s*["\[\{]/.test(text) && text.length < 24) return true;
  return false;
}

export function meaningfulAssistantContent(content: string): string {
  const visible = assistantIntroBeforeTools(content);
  if (!visible || contentIsToolJsonFragment(visible)) return "";
  return visible;
}

export function assistantPromisesToolUse(content: string): boolean {
  const text = (content || "").trim();
  if (!text) return false;
  if (text.endsWith("：") || text.endsWith(":") || text.endsWith("…") || text.endsWith("...")) {
    return true;
  }
  const lower = text.toLowerCase();
  const markers = [
    "我先",
    "让我",
    "我来",
    "正在",
    "接下来",
    "马上",
    "这就",
    "帮你查",
    "帮你搜",
    "拉一下",
    "补查",
    "再扫",
    "再查",
    "再搜",
    "再找",
    "继续",
    "接着",
    "开始搜",
    "开始查",
    "去搜",
    "去查",
    "搜索 crm",
    "查一下",
    "筛出",
    "搜索更多",
    "继续搜索",
    "继续查找",
    "再看看",
    "找找",
  ];
  if (markers.some((marker) => lower.includes(marker))) return true;
  if (
    text.length <= 120 &&
    ["搜索", "查找", "查询", "筛选", "挖掘", "扩展"].some((verb) => text.includes(verb))
  ) {
    if (["好的", "行", "嗯", "OK", "ok", "继续", "马上", "正在"].some((prefix) => text.includes(prefix))) {
      return true;
    }
  }
  return false;
}

export function userRequestsContinuation(message: string): boolean {
  const text = (message || "").trim();
  if (!text || text.length > 48) return false;
  const lower = text.toLowerCase();
  const markers = [
    "继续",
    "再看看",
    "再看",
    "还有吗",
    "再来",
    "接着",
    "再搜",
    "再查",
    "再找",
    "更多",
    "continue",
    "more",
  ];
  return markers.some((marker) => lower.includes(marker));
}

function inferContinuationQuery(history: Record<string, unknown>[], userMessage: string): string {
  const substantive: string[] = [];
  let sawDiscover = false;
  for (const item of history) {
    const role = item.role;
    if (role === "user") {
      const content = String(item.content || "").trim();
      if (content && !userRequestsContinuation(content)) substantive.push(content);
    } else if (role === "tool" && item.name === "discover_leads") {
      sawDiscover = true;
    }
  }
  if (!substantive.length && !sawDiscover) return "";

  const base =
    substantive[substantive.length - 1] || "扩展线索搜索，找更多符合条件的组织和联系人";
  if (!userRequestsContinuation(userMessage)) return base;

  const leadTokens = ["线索", "公司", "isp", "运营商", "peering", "asn", "大企业", "大公司", "知名"];
  const lowerBase = base.toLowerCase();
  if (sawDiscover || leadTokens.some((token) => lowerBase.includes(token))) {
    return `${base}（用户要求继续，请扩展搜索范围并找更多结果）`;
  }
  return `${base}（继续）`;
}

function makeDiscoverFallbackCall(query: string): Record<string, unknown> {
  return {
    id: `fallback-${randomUUID().slice(0, 8)}`,
    type: "function",
    function: {
      name: "discover_leads",
      arguments: JSON.stringify({ query, min_score: 60, auto_import: true }),
    },
  };
}

export function parseInlineToolCalls(
  content: string,
  registry?: ToolRegistry,
): [string, Record<string, unknown>[]] {
  const text = (content || "").trim();
  if (!text || !contentLooksLikeToolCall(text)) return [text, []];

  const intro = assistantIntroBeforeTools(text);
  let name = "unknown";
  const nameMatch = text.match(/\[(?:工具|tool)[:\s]*([a-zA-Z0-9_]+)\]/i);
  if (nameMatch) name = nameMatch[1]!;
  const args = extractJsonArgs(text);
  name = inferToolName(name, args, registry);
  if (name === "unknown" && !Object.keys(args).length) return [text, []];

  return [
    intro,
    [
      {
        id: `inline-${randomUUID().slice(0, 8)}`,
        type: "function",
        function: { name, arguments: JSON.stringify(args) },
      },
    ],
  ];
}

export function fallbackPreparedCalls(
  userMessage: string,
  history: Record<string, unknown>[] | null = null,
  registry?: ToolRegistry,
): Array<[Record<string, unknown>, string, Record<string, unknown>]> {
  const text = (userMessage || "").trim();
  const lower = text.toLowerCase();
  if (!text) return [];

  if (userRequestsContinuation(text)) {
    const query = inferContinuationQuery(history || [], text);
    if (query) return prepareToolCalls([makeDiscoverFallbackCall(query)], registry);
    return prepareToolCalls(
      [
        {
          id: `fallback-${randomUUID().slice(0, 8)}`,
          type: "function",
          function: {
            name: "list_contacts",
            arguments: JSON.stringify({ q: "", limit: 100 }),
          },
        },
      ],
      registry,
    );
  }

  let queries: string[] = [];
  if (
    ["运营商", "operator", " isp", "isp ", "电信", "联通", "移动"].some((token) => text.includes(token)) ||
    (text.includes("还有") && text.includes("其他"))
  ) {
    queries = [
      "运营商",
      "ISP",
      "Telecom",
      "Network",
      "Transit",
      "Cogent",
      "Verizon",
      "AT&T",
      "TDS",
      "RCN",
      "GTT",
    ];
  } else if (lower.includes("abuse")) {
    queries = ["abuse@"];
  } else if (["联系人", "crm", "搜索", "找出", "列出", "还有"].some((token) => text.includes(token))) {
    queries = ["", "Network", "ISP"];
  }

  if (!queries.length) return [];

  return prepareToolCalls(
    queries.slice(0, 8).map((query) => ({
      id: `fallback-${randomUUID().slice(0, 8)}`,
      type: "function",
      function: {
        name: "list_contacts",
        arguments: JSON.stringify({ q: query, limit: 100 }),
      },
    })),
    registry,
  );
}

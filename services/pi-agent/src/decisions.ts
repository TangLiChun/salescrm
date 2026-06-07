import type { AssistantMessage, Decision } from "./types.js";
import {
  CONTINUE_NUDGE,
  EMPTY_RESPONSE_NUDGE,
  INTRO_ONLY_NUDGE,
  assistantPromisesToolUse,
  fallbackPreparedCalls,
  meaningfulAssistantContent,
  parseInlineToolCalls,
  userRequestsContinuation,
} from "./replyHeuristics.js";
import { extractToolCallsFromContent, prepareToolCalls } from "./toolCalls.js";

const INTERRUPTED_RESPONSE_REASONS = new Set(["length", "insufficient_system_resource"]);
const INTERRUPTED_RESPONSE_NUDGE =
  "（系统）上一轮模型输出被截断或上游推理资源中断。" +
  "请重新完成用户请求；需要工具时立即调用工具，不要只回复开场白。";

function assistantResponseEmpty(
  assistant: AssistantMessage | null | undefined,
  contentBuffer: string,
): boolean {
  if (!assistant) return true;
  const content = String(assistant.content ?? contentBuffer ?? "").trim();
  const toolCalls = assistant.tool_calls || [];
  if (content || toolCalls.length) return false;
  const reasoning = String(assistant.reasoning_content || "").trim();
  return !reasoning;
}

export function decideTurn(
  assistant: AssistantMessage | null | undefined,
  contentBuffer: string,
  opts: {
    userMessage: string;
    history: Record<string, unknown>[];
    nudgeCount: number;
    maxNudges: number;
  },
): Decision {
  const { userMessage, history, nudgeCount, maxNudges } = opts;

  if (assistantResponseEmpty(assistant, contentBuffer)) {
    if (nudgeCount < maxNudges) {
      return { kind: "retry", nudge: EMPTY_RESPONSE_NUDGE, reason: "empty_response" };
    }
    return { kind: "fail" };
  }

  const msg = assistant || {};
  const finishReason = String(msg.finish_reason || "").trim();
  if (finishReason === "content_filter") {
    return { kind: "fail", error: "模型输出被内容安全策略过滤，请换种说法或缩小请求范围。" };
  }
  if (INTERRUPTED_RESPONSE_REASONS.has(finishReason)) {
    if (nudgeCount < maxNudges) {
      return { kind: "retry", nudge: INTERRUPTED_RESPONSE_NUDGE, reason: finishReason };
    }
    return { kind: "fail", error: "模型输出被截断或上游推理资源中断，请稍后重试。" };
  }

  let rawToolCalls = [...(msg.tool_calls || [])];
  const rawContent = String(msg.content ?? contentBuffer ?? "").trim();
  let content = meaningfulAssistantContent(rawContent);

  if (finishReason === "tool_calls" && !rawToolCalls.length) {
    if (nudgeCount < maxNudges) {
      return { kind: "retry", nudge: EMPTY_RESPONSE_NUDGE, reason: "missing_tool_calls" };
    }
    const fallbackCalls = fallbackPreparedCalls(userMessage, history);
    if (fallbackCalls.length) {
      return {
        kind: "fallback_tool_calls",
        preparedCalls: fallbackCalls,
        statusMessage: "工具调用缺失，正在直接搜索 CRM…",
      };
    }
    return { kind: "fail" };
  }

  if (!rawToolCalls.length && rawContent) {
    const [intro, inlineCalls] = parseInlineToolCalls(rawContent);
    if (inlineCalls.length) {
      rawToolCalls = inlineCalls;
      content = meaningfulAssistantContent(intro);
    }
  }

  if (content && !rawToolCalls.length) {
    const continueRequest = userRequestsContinuation(userMessage);
    const promises = assistantPromisesToolUse(content);
    const shouldAct = promises || continueRequest;

    if (shouldAct && nudgeCount < maxNudges) {
      return {
        kind: "retry",
        nudge: continueRequest ? CONTINUE_NUDGE : INTRO_ONLY_NUDGE,
        reason: continueRequest ? "continuation" : "intro_only",
      };
    }

    const fallbackCalls = fallbackPreparedCalls(userMessage, history);
    if (fallbackCalls.length && shouldAct) {
      return {
        kind: "fallback_tool_calls",
        preparedCalls: fallbackCalls,
        statusMessage: continueRequest
          ? "正在直接继续上一任务…"
          : "模型未调用工具，正在直接搜索 CRM…",
      };
    }

    if (continueRequest) {
      return { kind: "fail", error: "无法继续上一任务，请补充更具体的搜索描述" };
    }
    return { kind: "final_reply", text: content };
  }

  if (!rawToolCalls.length) {
    if (nudgeCount < maxNudges) {
      return { kind: "retry", nudge: EMPTY_RESPONSE_NUDGE, reason: "no_visible_content" };
    }
    return { kind: "fail" };
  }

  let prepared = prepareToolCalls(rawToolCalls);
  if (!prepared.length && rawContent) {
    const extracted = extractToolCallsFromContent(rawContent);
    if (extracted.length) prepared = prepareToolCalls(extracted);
    if (!prepared.length) {
      const [intro2, inline2] = parseInlineToolCalls(rawContent);
      if (inline2.length) {
        prepared = prepareToolCalls(inline2);
        content = meaningfulAssistantContent(intro2);
      }
    }
  }

  if (prepared.length) {
    return { kind: "emit_tool_calls", preparedCalls: prepared, introText: content };
  }

  if (nudgeCount < maxNudges) {
    return { kind: "retry", nudge: EMPTY_RESPONSE_NUDGE, reason: "invalid_tool_calls" };
  }

  const fallbackCalls = fallbackPreparedCalls(userMessage, history);
  if (fallbackCalls.length) {
    return {
      kind: "fallback_tool_calls",
      preparedCalls: fallbackCalls,
      statusMessage: "工具调用无效，正在直接搜索 CRM…",
    };
  }

  return { kind: "fail" };
}

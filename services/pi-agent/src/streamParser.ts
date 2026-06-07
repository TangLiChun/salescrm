import { randomUUID } from "node:crypto";

export type ToolCallSlot = {
  id: string;
  type: string;
  function: { name: string; arguments: string };
};

export function mergeToolCallDelta(
  toolCalls: Map<number, ToolCallSlot>,
  toolDelta: Record<string, unknown>,
): void {
  const index = Number(toolDelta.index ?? 0);
  let slot = toolCalls.get(index);
  if (!slot) {
    slot = { id: "", type: "function", function: { name: "", arguments: "" } };
    toolCalls.set(index, slot);
  }
  if (toolDelta.id) slot.id = String(toolDelta.id);

  let fn = toolDelta.function;
  if (typeof fn === "string") {
    try {
      fn = JSON.parse(fn);
    } catch {
      fn = {};
    }
  }
  if (!fn || typeof fn !== "object") fn = {};
  const fnObj = fn as Record<string, unknown>;
  if (fnObj.name) slot.function.name += String(fnObj.name);
  else if (toolDelta.name) slot.function.name += String(toolDelta.name);
  if (fnObj.arguments) slot.function.arguments += String(fnObj.arguments);
  else if (toolDelta.arguments !== undefined) {
    const piece = toolDelta.arguments;
    slot.function.arguments +=
      typeof piece === "string" ? piece : JSON.stringify(piece);
  }
}

function applyCompleteMessage(
  contentParts: string[],
  reasoningParts: string[],
  toolCalls: Map<number, ToolCallSlot>,
  message: Record<string, unknown>,
): void {
  const content = message.content;
  if (content) {
    const full = String(content);
    const joined = contentParts.join("");
    if (!joined) contentParts.push(full);
    else if (full.length > joined.length) contentParts.splice(0, contentParts.length, full);
  }

  const reasoning = message.reasoning_content ?? message.reasoning;
  if (reasoning) {
    const fullReasoning = String(reasoning);
    const joinedReasoning = reasoningParts.join("");
    if (!joinedReasoning) reasoningParts.push(fullReasoning);
    else if (fullReasoning.length > joinedReasoning.length) {
      reasoningParts.splice(0, reasoningParts.length, fullReasoning);
    }
  }

  const rawCalls = message.tool_calls;
  if (!Array.isArray(rawCalls)) return;
  rawCalls.forEach((raw, index) => {
    if (!raw || typeof raw !== "object") return;
    let slot = toolCalls.get(index);
    if (!slot) {
      slot = { id: "", type: "function", function: { name: "", arguments: "" } };
      toolCalls.set(index, slot);
    }
    if (raw.id) slot.id = String(raw.id);
    const fn = raw.function;
    if (fn && typeof fn === "object") {
      if (fn.name) slot.function.name = String(fn.name);
      if (fn.arguments !== undefined) {
        slot.function.arguments =
          typeof fn.arguments === "string" ? fn.arguments : JSON.stringify(fn.arguments);
      }
    }
  });
}

export function consumeStreamChunk(
  chunk: Record<string, unknown>,
  state: {
    contentParts: string[];
    reasoningParts: string[];
    toolCalls: Map<number, ToolCallSlot>;
    toolStatusEmitted: boolean;
    finishReasons: string[];
    emitContentDelta: boolean;
  },
): Array<Record<string, unknown>> {
  const events: Array<Record<string, unknown>> = [];
  const choices = (chunk.choices as Record<string, unknown>[]) || [{}];
  for (const choice of choices) {
    const finishReason = choice.finish_reason;
    if (finishReason != null) state.finishReasons.push(String(finishReason));

    const delta = (choice.delta as Record<string, unknown>) || {};
    const piece = delta.content;
    if (piece) {
      state.contentParts.push(String(piece));
      if (state.emitContentDelta) events.push({ type: "content_delta", text: String(piece) });
    }

    const reasoningPiece = delta.reasoning_content ?? delta.reasoning;
    if (reasoningPiece) {
      state.reasoningParts.push(String(reasoningPiece));
      if (!state.toolStatusEmitted && !state.contentParts.length) {
        state.toolStatusEmitted = true;
        events.push({ type: "status", message: "模型推理中…" });
      }
    }

    for (const toolDelta of (delta.tool_calls as Record<string, unknown>[]) || []) {
      if (!toolDelta || typeof toolDelta !== "object") continue;
      if (!state.toolStatusEmitted) {
        state.toolStatusEmitted = true;
        events.push({ type: "status", message: "正在准备工具调用…" });
      }
      mergeToolCallDelta(state.toolCalls, toolDelta);
    }

    const message = choice.message;
    if (message && typeof message === "object") {
      applyCompleteMessage(
        state.contentParts,
        state.reasoningParts,
        state.toolCalls,
        message as Record<string, unknown>,
      );
    }
  }
  return events;
}

export function parseSseLine(line: string): Record<string, unknown> | null {
  const trimmed = (line || "").trim();
  if (!trimmed || trimmed === "data: [DONE]") return null;
  const payload = trimmed.startsWith("data:") ? trimmed.slice(5).trim() : trimmed;
  if (!payload || payload === "[DONE]") return null;
  try {
    const parsed = JSON.parse(payload);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

export function assembleMessage(
  contentParts: string[],
  reasoningParts: string[],
  toolCalls: Map<number, ToolCallSlot>,
  finishReasons: string[],
): Record<string, unknown> {
  const message: Record<string, unknown> = {
    role: "assistant",
    content: contentParts.join("") || null,
  };
  if (finishReasons.length) message.finish_reason = finishReasons[finishReasons.length - 1];
  if (reasoningParts.length) message.reasoning_content = reasoningParts.join("");

  const assembled: ToolCallSlot[] = [];
  for (const index of [...toolCalls.keys()].sort((a, b) => a - b)) {
    const slot = toolCalls.get(index)!;
    const name = (slot.function.name || "").trim();
    const args = (slot.function.arguments || "").trim();
    if (!name && !args) continue;
    if (!slot.id) slot.id = `call_${randomUUID().replace(/-/g, "").slice(0, 12)}`;
    assembled.push(slot);
  }
  if (assembled.length) message.tool_calls = assembled;
  return message;
}

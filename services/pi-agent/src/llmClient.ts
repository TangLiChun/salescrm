import type { LlmStreamEvent, LlmConfig } from "./types.js";
import { assembleMessage, consumeStreamChunk, parseSseLine } from "./streamParser.js";

const RETRYABLE_STATUS = new Set([429, 500, 502, 503, 504]);
const MAX_RETRIES = 3;
const BACKOFF_BASE = 0.5;
const BACKOFF_CAP = 20;
const AGENT_REQUEST_TIMEOUT_MS = 180_000;

function chatCompletionsUrl(baseUrl: string): string {
  const base = (baseUrl || "https://api.openai.com/v1").replace(/\/$/, "");
  return base.endsWith("/chat/completions") ? base : `${base}/chat/completions`;
}

function isDeepSeekProvider(model: string, baseUrl: string): boolean {
  const hay = `${model} ${baseUrl}`.toLowerCase();
  return hay.includes("deepseek");
}

function sanitizeMessagesForApi(messages: Record<string, unknown>[]): Record<string, unknown>[] {
  return messages
    .filter((raw) => raw && typeof raw === "object")
    .map((raw) => {
      const msg = { ...raw };
      if (msg.role === "assistant" && !(msg.tool_calls as unknown[] | undefined)?.length) {
        delete msg.reasoning_content;
        delete msg.reasoning;
      }
      return msg;
    });
}

function buildPayload(
  messages: Record<string, unknown>[],
  tools: Record<string, unknown>[] | null,
  config: LlmConfig,
  toolChoice: unknown,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    model: config.model,
    temperature: 0.2,
    messages: sanitizeMessagesForApi(messages),
    stream: true,
  };
  if (tools?.length) {
    payload.tools = tools;
    payload.tool_choice = toolChoice ?? "auto";
  }
  if (isDeepSeekProvider(config.model, config.base_url)) {
    const thinking = config.thinking;
    if (thinking) {
      payload.thinking = { type: thinking };
      if (thinking === "enabled" && tools?.length) payload.reasoning_effort = "high";
    }
  }
  return payload;
}

function nextBackoff(attempt: number): number {
  return Math.min(BACKOFF_CAP, BACKOFF_BASE * 2 ** attempt) + Math.random() * BACKOFF_BASE;
}

function retryAfter(resp: Response): number | null {
  const value = resp.headers.get("Retry-After");
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export async function* streamChat(
  messages: Record<string, unknown>[],
  tools: Record<string, unknown>[] | null,
  config: LlmConfig,
  toolChoice: unknown = null,
): AsyncGenerator<LlmStreamEvent> {
  const url = chatCompletionsUrl(config.base_url);
  const payload = buildPayload(messages, tools, config, toolChoice);
  const headers = {
    Authorization: `Bearer ${config.api_key}`,
    "Content-Type": "application/json",
  };

  let lastError = "LLM 请求失败";
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt += 1) {
    let emittedAny = false;
    const contentParts: string[] = [];
    const reasoningParts: string[] = [];
    const toolCalls = new Map<number, import("./streamParser.js").ToolCallSlot>();
    const finishReasons: string[] = [];
    const streamState = {
      contentParts,
      reasoningParts,
      toolCalls,
      toolStatusEmitted: false,
      finishReasons,
      emitContentDelta: true,
    };

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), AGENT_REQUEST_TIMEOUT_MS);

    try {
      const resp = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (RETRYABLE_STATUS.has(resp.status)) {
        const body = await resp.text();
        lastError = `LLM 请求失败 (${resp.status}): ${body.slice(0, 200)}`;
        if (attempt < MAX_RETRIES) {
          const delay = Math.min(retryAfter(resp) ?? nextBackoff(attempt), BACKOFF_CAP);
          await new Promise((resolve) => setTimeout(resolve, delay * 1000));
          continue;
        }
        yield { type: "error", message: lastError };
        return;
      }

      if (!resp.ok) {
        const body = await resp.text();
        yield { type: "error", message: `LLM 请求失败 (${resp.status}): ${body.slice(0, 300)}` };
        return;
      }

      const reader = resp.body?.getReader();
      if (!reader) {
        yield { type: "error", message: "LLM 响应体为空" };
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const chunk = parseSseLine(line);
          if (!chunk) continue;
          const events = consumeStreamChunk(chunk, streamState);
          for (const event of events) {
            emittedAny = true;
            if (event.type === "content_delta") {
              yield { type: "content_delta", text: String(event.text || "") };
            } else if (event.type === "reasoning_start") {
              yield { type: "reasoning_start" };
            } else if (event.type === "reasoning_delta") {
              yield { type: "reasoning_delta", text: String(event.text || "") };
            } else if (event.type === "status") {
              yield { type: "status", message: String(event.message || "Pi 助手处理中…") };
            }
          }
        }
      }

      yield {
        type: "message",
        message: assembleMessage(contentParts, reasoningParts, toolCalls, finishReasons),
      };
      return;
    } catch (err) {
      lastError = `无法连接 LLM 服务: ${err instanceof Error ? err.message : String(err)}`;
      if (emittedAny) {
        yield { type: "error", message: lastError };
        return;
      }
      if (attempt < MAX_RETRIES) {
        await new Promise((resolve) => setTimeout(resolve, nextBackoff(attempt) * 1000));
        continue;
      }
      yield { type: "error", message: lastError };
      return;
    } finally {
      clearTimeout(timeout);
    }
  }

  yield { type: "error", message: lastError };
}

export function formatAssistantMessageForApi(
  assistant: Record<string, unknown> | null | undefined,
  content: string | null,
  toolCalls: Record<string, unknown>[] | null,
): Record<string, unknown> {
  const msg: Record<string, unknown> = { role: "assistant", content: content || null };
  const calls = toolCalls || [];
  if (calls.length) {
    msg.tool_calls = calls;
    const reasoning = String(
      assistant?.reasoning_content || assistant?.reasoning || "",
    ).trim();
    if (reasoning) msg.reasoning_content = reasoning;
  }
  return msg;
}

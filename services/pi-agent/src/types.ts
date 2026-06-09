export const MAX_TOOL_ROUNDS = 12;
export const MAX_LLM_CALLS_PER_TURN = 30;
export const MAX_EXECUTED_TOOL_CALLS_PER_TURN = 8;
export const MAX_LLM_NUDGES = 2;
export const TOOL_HEARTBEAT_MS = 12_000;

export type LlmConfig = {
  api_key: string;
  base_url: string;
  model: string;
  thinking?: string | null;
};

export type AgentEvent =
  | { type: "status"; message: string }
  | { type: "context"; stats: Record<string, unknown> }
  | { type: "reasoning_start" }
  | { type: "reasoning_delta"; text: string }
  | { type: "reasoning_done" }
  | { type: "assistant_start" }
  | { type: "assistant_delta"; text: string }
  | { type: "assistant_done"; text: string }
  | { type: "tool_start"; name: string; args: Record<string, unknown> }
  | { type: "tool_progress"; name?: string; message: string }
  | { type: "tool_event"; name?: string; event: unknown }
  | { type: "tool_result"; name: string; result: Record<string, unknown> }
  | {
      type: "tool_blocked";
      name: string;
      args: Record<string, unknown>;
      reason?: string;
    }
  | { type: "error"; message: string }
  | { type: "done" };

export type PreparedCall = [Record<string, unknown>, string, Record<string, unknown>];

export type AssistantMessage = {
  role?: string;
  content?: string | null;
  tool_calls?: Record<string, unknown>[];
  reasoning_content?: string;
  reasoning?: string;
  finish_reason?: string;
};

export type LlmStreamEvent =
  | { type: "content_delta"; text: string }
  | { type: "status"; message: string }
  | { type: "reasoning_start" }
  | { type: "reasoning_delta"; text: string }
  | { type: "reasoning_done" }
  | { type: "message"; message: AssistantMessage }
  | { type: "error"; message: string };

export type Decision =
  | { kind: "emit_tool_calls"; preparedCalls: PreparedCall[]; introText: string }
  | { kind: "final_reply"; text: string }
  | { kind: "retry"; nudge: string; reason: string }
  | { kind: "fallback_tool_calls"; preparedCalls: PreparedCall[]; statusMessage: string }
  | { kind: "fail"; error?: string };

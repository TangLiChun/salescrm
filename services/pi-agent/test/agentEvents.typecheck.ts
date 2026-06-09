import type { AgentEvent } from "../src/types.js";

const validEvents = [
  { type: "status", message: "working" },
  { type: "context", stats: { usage_percent: 12 } },
  { type: "reasoning_start" },
  { type: "reasoning_delta", text: "thinking" },
  { type: "reasoning_done" },
  { type: "assistant_start" },
  { type: "assistant_delta", text: "hello" },
  { type: "assistant_done", text: "done" },
  { type: "tool_start", name: "list_contacts", args: { q: "isp" } },
  { type: "tool_progress", name: "list_contacts", message: "searching" },
  { type: "tool_event", name: "list_contacts", event: { kind: "row" } },
  { type: "tool_result", name: "list_contacts", result: { total: 2 } },
  { type: "tool_blocked", name: "web_search", args: {}, reason: "blocked" },
  { type: "error", message: "failed" },
  { type: "done" },
] satisfies AgentEvent[];

void validEvents;

// @ts-expect-error assistant_delta must carry text.
const missingAssistantDeltaText: AgentEvent = { type: "assistant_delta" };
void missingAssistantDeltaText;

// @ts-expect-error tool_start must carry args.
const missingToolArgs: AgentEvent = { type: "tool_start", name: "list_contacts" };
void missingToolArgs;

// @ts-expect-error unknown event types are not part of the public stream contract.
const unknownEvent: AgentEvent = { type: "assistant_chunk", text: "hello" };
void unknownEvent;

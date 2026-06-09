// Shared test harness for the pi-agent sidecar: a scriptable fake of the
// Python internal API and a scripted LLM stream, so agentLoop scenarios run
// fully offline and deterministically.

export const LLM_CONFIG = {
  api_key: "test-key",
  base_url: "http://llm.test/v1",
  model: "test-model",
};

export const DEFAULT_TOOLS = [
  "list_contacts",
  "get_contact",
  "get_stats",
  "lookup_asns",
  "discover_leads",
  "web_search",
  "import_leads",
  "delete_contacts",
].map((name) => ({ type: "function", function: { name, parameters: { type: "object" } } }));

export class FakePython {
  constructor(opts = {}) {
    this.opts = opts;
    this.calls = {
      prepare: [],
      runTool: [],
      toolBlock: [],
      forceSummary: [],
      recoverOverflow: [],
    };
  }

  async prepare(input) {
    this.calls.prepare.push(input);
    if (this.opts.prepare) return this.opts.prepare(input);
    return {
      messages: [
        { role: "system", content: "你是 Pi 助手。" },
        { role: "user", content: input.message },
      ],
      context_event: { type: "context", stats: { usage_percent: 5 } },
      tools: this.opts.tools ?? DEFAULT_TOOLS,
      tool_aliases: this.opts.toolAliases ?? {},
      history: this.opts.history ?? [],
      status_messages: this.opts.statusMessages ?? [],
    };
  }

  async checkToolBlock(input) {
    this.calls.toolBlock.push(input);
    if (this.opts.checkToolBlock) return this.opts.checkToolBlock(input);
    return { blocked: false };
  }

  async recoverOverflow(input) {
    this.calls.recoverOverflow.push(input);
    if (this.opts.recoverOverflow) return this.opts.recoverOverflow(input);
    return {
      messages: [
        { role: "system", content: "你是 Pi 助手。" },
        { role: "user", content: input.message },
      ],
      context_event: { type: "context", stats: { usage_percent: 1, compressed: true } },
      history: [],
      status_messages: ["已压缩线索上下文"],
    };
  }

  async shouldForceSummary(input) {
    this.calls.forceSummary.push(input);
    if (this.opts.shouldForceSummary) return this.opts.shouldForceSummary(input);
    return false;
  }

  async *runTool(input) {
    this.calls.runTool.push(input);
    if (this.opts.runTool) return yield* this.opts.runTool(input);
    return { result: { ok: true, tool: input.name }, llmContent: "" };
  }
}

function turnToEvents(turn) {
  if (Array.isArray(turn)) return turn;
  if (turn.error) return [{ type: "error", message: turn.error }];

  const events = [];
  const message = { role: "assistant", content: turn.content ?? null };
  if (turn.reasoning) {
    events.push({ type: "reasoning_start" });
    events.push({ type: "reasoning_delta", text: turn.reasoning });
    message.reasoning_content = turn.reasoning;
  }
  if (turn.content) {
    const text = turn.content;
    const mid = Math.ceil(text.length / 2);
    for (const piece of [text.slice(0, mid), text.slice(mid)]) {
      if (piece) events.push({ type: "content_delta", text: piece });
    }
  }
  if (turn.toolCalls?.length) {
    events.push({ type: "status", message: "正在准备工具调用…" });
    message.tool_calls = turn.toolCalls.map((tc, index) => ({
      id: tc.id ?? `call_${index}`,
      type: "function",
      function: { name: tc.name, arguments: JSON.stringify(tc.args ?? {}) },
    }));
    message.finish_reason = "tool_calls";
  }
  if (turn.finishReason) message.finish_reason = turn.finishReason;
  events.push({ type: "message", message });
  return events;
}

/**
 * Build a streamChat replacement that replays scripted turns. Each turn is
 * either a raw LlmStreamEvent array or a convenience object:
 *   { content?, reasoning?, toolCalls?: [{name, args, id?}], finishReason?, error? }
 * Calls are recorded on `.calls` (messages snapshot, tools, toolChoice).
 */
export function scriptedLlm(turns) {
  const calls = [];
  let cursor = 0;
  async function* streamChatImpl(messages, tools, _config, toolChoice) {
    calls.push({
      messages: messages.map((msg) => ({ ...msg })),
      tools,
      toolChoice,
    });
    const turn = turns[Math.min(cursor, turns.length - 1)];
    cursor += 1;
    for (const event of turnToEvents(turn)) yield event;
  }
  streamChatImpl.calls = calls;
  return streamChatImpl;
}

export async function collect(gen) {
  const events = [];
  for await (const event of gen) events.push(event);
  return events;
}

export const eventTypes = (events) => events.map((event) => event.type);

export const ofType = (events, type) => events.filter((event) => event.type === type);

export const lastAssistantText = (events) => {
  const dones = ofType(events, "assistant_done");
  return dones.length ? dones[dones.length - 1].text : "";
};

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

import type { AgentEvent, LlmConfig } from "./types.js";

export class PythonClient {
  constructor(
    private baseUrl: string,
    private secret: string,
  ) {}

  private headers(): Record<string, string> {
    return {
      "Content-Type": "application/json",
      "X-Internal-Secret": this.secret,
    };
  }

  async getLlmConfig(): Promise<LlmConfig> {
    const resp = await fetch(`${this.baseUrl}/api/internal/pi/llm-config`, {
      headers: this.headers(),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`LLM config failed (${resp.status}): ${text.slice(0, 200)}`);
    }
    return (await resp.json()) as LlmConfig;
  }

  async prepare(input: {
    user_id: number;
    message: string;
    thread_id?: string | null;
    history?: Record<string, unknown>[] | null;
  }): Promise<{
    messages: Record<string, unknown>[];
    context_event: AgentEvent;
    tools: Record<string, unknown>[];
    tool_aliases: Record<string, string>;
    history: Record<string, unknown>[];
    status_messages: string[];
  }> {
    const resp = await fetch(`${this.baseUrl}/api/internal/pi/prepare`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(input),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Prepare failed (${resp.status}): ${text.slice(0, 200)}`);
    }
    return (await resp.json()) as {
      messages: Record<string, unknown>[];
      context_event: AgentEvent;
      tools: Record<string, unknown>[];
      tool_aliases: Record<string, string>;
      history: Record<string, unknown>[];
      status_messages: string[];
    };
  }

  async checkToolBlock(input: {
    name: string;
    user_message: string;
    current_batch_names: string[];
    executed_names: string[];
    executed_count: number;
  }): Promise<{
    blocked: boolean;
    reason?: string;
    result?: Record<string, unknown>;
    llm_content?: string;
  }> {
    const resp = await fetch(`${this.baseUrl}/api/internal/pi/tool-block`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(input),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Tool block check failed (${resp.status}): ${text.slice(0, 200)}`);
    }
    return (await resp.json()) as {
      blocked: boolean;
      reason?: string;
      result?: Record<string, unknown>;
      llm_content?: string;
    };
  }

  async recoverOverflow(input: {
    user_id: number;
    message: string;
    thread_id: string;
  }): Promise<{
    messages: Record<string, unknown>[];
    context_event: AgentEvent;
    history: Record<string, unknown>[];
    status_messages: string[];
  }> {
    const resp = await fetch(`${this.baseUrl}/api/internal/pi/recover-overflow`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(input),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Recover overflow failed (${resp.status}): ${text.slice(0, 200)}`);
    }
    return (await resp.json()) as {
      messages: Record<string, unknown>[];
      context_event: AgentEvent;
      history: Record<string, unknown>[];
      status_messages: string[];
    };
  }

  async shouldForceSummary(input: {
    name: string;
    user_message: string;
    executed_count: number;
  }): Promise<boolean> {
    const resp = await fetch(`${this.baseUrl}/api/internal/pi/force-summary`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(input),
    });
    if (!resp.ok) return false;
    const data = (await resp.json()) as { force?: boolean };
    return Boolean(data.force);
  }

  async *runTool(input: {
    user_id: number;
    name: string;
    args: Record<string, unknown>;
  }): AsyncGenerator<AgentEvent, { result: Record<string, unknown>; llmContent: string }> {
    const resp = await fetch(`${this.baseUrl}/api/internal/pi/tools/run`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(input),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Tool run failed (${resp.status}): ${text.slice(0, 200)}`);
    }

    const reader = resp.body?.getReader();
    if (!reader) throw new Error("Tool run response body empty");

    const decoder = new TextDecoder();
    let buffer = "";
    let finalResult: Record<string, unknown> = { error: "工具执行失败" };
    let llmContent = "";

    const parseEventLine = (line: string): Record<string, unknown> | null => {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) return null;
      const payload = trimmed.slice(5).trim();
      if (!payload) return null;
      try {
        const event = JSON.parse(payload) as unknown;
        return event && typeof event === "object" ? (event as Record<string, unknown>) : null;
      } catch {
        return null;
      }
    };

    const pendingLines: string[] = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        const tail = buffer + decoder.decode();
        if (tail.trim()) pendingLines.push(tail);
        buffer = "";
      } else {
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        pendingLines.push(...lines);
      }
      for (const line of pendingLines) {
        const event = parseEventLine(line);
        if (!event) continue;
        if (event.type === "tool_progress") {
          yield { type: "tool_progress", message: String(event.message || "") };
        } else if (event.type === "tool_event") {
          yield { type: "tool_event", event: event.event };
        } else if (event.type === "done") {
          finalResult = (event.result as Record<string, unknown>) || finalResult;
          llmContent = String(event.llm_content || "");
        }
      }
      pendingLines.length = 0;
      if (done) break;
    }

    return { result: finalResult, llmContent };
  }
}

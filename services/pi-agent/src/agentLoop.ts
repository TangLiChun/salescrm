import { decideTurn } from "./decisions.js";
import { formatAssistantMessageForApi, streamChat } from "./llmClient.js";
import { PythonClient } from "./pythonClient.js";
import {
  assistantIntroBeforeTools,
  meaningfulAssistantContent,
} from "./replyHeuristics.js";
import { isContextOverflowError } from "./llmErrors.js";
import { canParallelizeToolBatch } from "./parallelTools.js";
import { createToolRegistry } from "./toolCalls.js";
import {
  MAX_LLM_CALLS_PER_TURN,
  MAX_LLM_NUDGES,
  MAX_TOOL_ROUNDS,
  TOOL_HEARTBEAT_MS,
} from "./types.js";
import type { AgentEvent, AssistantMessage, LlmConfig, PreparedCall } from "./types.js";

export type StreamChatFn = typeof streamChat;

async function streamTextReply(
  messages: Record<string, unknown>[],
  tools: Record<string, unknown>[] | null,
  config: LlmConfig,
  llmStream: StreamChatFn,
): Promise<[string, boolean]> {
  let assistant: AssistantMessage | null = null;
  let contentBuffer = "";
  for await (const event of llmStream(messages, tools, config, null)) {
    if (event.type === "error") return ["", false];
    if (event.type === "content_delta") contentBuffer += event.text;
    if (event.type === "message") assistant = event.message;
  }
  const content = String(assistant?.content ?? contentBuffer ?? "").trim();
  return [content, Boolean(content)];
}

async function* finalizeWithSummary(
  messages: Record<string, unknown>[],
  config: LlmConfig,
  instruction: string,
  llmStream: StreamChatFn,
  emptyFallback: string,
): AsyncGenerator<AgentEvent> {
  messages.push({ role: "user", content: instruction });
  let [finalText, ok] = await streamTextReply(messages, null, config, llmStream);
  if (!ok) finalText = emptyFallback;
  yield { type: "assistant_start" };
  yield { type: "assistant_delta", text: finalText };
  yield { type: "assistant_done", text: finalText };
  yield { type: "done" };
}

export async function* agentChatStream(input: {
  userId: number;
  message: string;
  threadId?: string | null;
  history?: Record<string, unknown>[] | null;
  cancelCheck?: () => boolean;
  python: PythonClient;
  llmConfig: LlmConfig;
  /** Test seam: defaults to the real LLM stream. */
  streamChatImpl?: StreamChatFn;
  /** Test seam: heartbeat interval while a tool runs. */
  toolHeartbeatMs?: number;
}): AsyncGenerator<AgentEvent> {
  const { userId, message, threadId, python, llmConfig } = input;
  const cancelCheck = input.cancelCheck ?? (() => false);
  const llmStream = input.streamChatImpl ?? streamChat;
  const toolHeartbeatMs = input.toolHeartbeatMs ?? TOOL_HEARTBEAT_MS;

  if (cancelCheck()) {
    yield { type: "error", message: "任务已停止" };
    yield { type: "done" };
    return;
  }

  yield { type: "status", message: "Pi 助手思考中…" };

  const prepared = await python.prepare({
    user_id: userId,
    message,
    thread_id: threadId,
    history: input.history,
  });

  for (const statusMessage of prepared.status_messages || []) {
    yield { type: "status", message: statusMessage };
  }
  yield prepared.context_event;

  const messages = prepared.messages;
  const history = prepared.history || [];
  const tools = prepared.tools;
  const toolRegistry = createToolRegistry(tools, prepared.tool_aliases || {});

  let llmCallCount = 0;
  const executedToolNames: string[] = [];
  let executedToolCount = 0;

  for (let roundIndex = 0; roundIndex < MAX_TOOL_ROUNDS; roundIndex += 1) {
    if (cancelCheck()) {
      yield { type: "error", message: "任务已停止" };
      yield { type: "done" };
      return;
    }
    if (roundIndex > 0) {
      yield { type: "status", message: "正在整理工具结果…" };
    }

    let assistant: AssistantMessage | null = null;
    let contentBuffer = "";
    let streamedReply = false;
    let llmNudgeCount = 0;
    let content = "";
    let preparedCalls: PreparedCall[] = [];

    while (true) {
      if (cancelCheck()) {
        yield { type: "error", message: "任务已停止" };
        yield { type: "done" };
        return;
      }
      if (llmCallCount >= MAX_LLM_CALLS_PER_TURN) {
        const msg = "本次对话已达调用上限，请简化问题后重试。";
        yield { type: "assistant_start" };
        yield { type: "assistant_delta", text: msg };
        yield { type: "assistant_done", text: msg };
        yield { type: "done" };
        return;
      }

      assistant = null;
      contentBuffer = "";
      streamedReply = false;
      let lastStreamedVisible = "";
      let reasoningOpen = false;

      const toolChoice = llmNudgeCount > 0 && tools.length ? "required" : null;
      llmCallCount += 1;

      let overflowRetried = false;
      let llmStreamDone = false;
      while (!llmStreamDone) {
        let recoverOverflow = false;
        for await (const event of llmStream(messages, tools, llmConfig, toolChoice)) {
          if (event.type === "error") {
            const errMsg = event.message || "LLM 请求失败";
            if (
              !overflowRetried &&
              threadId &&
              isContextOverflowError(errMsg)
            ) {
              overflowRetried = true;
              recoverOverflow = true;
              yield { type: "status", message: "上下文过长，正在压缩后重试…" };
              const recovered = await python.recoverOverflow({
                user_id: userId,
                message,
                thread_id: threadId,
              });
              messages.length = 0;
              messages.push(...recovered.messages);
              for (const statusMessage of recovered.status_messages || []) {
                yield { type: "status", message: statusMessage };
              }
              yield recovered.context_event;
              break;
            }
            yield { type: "error", message: errMsg };
            yield { type: "done" };
            return;
          }
          if (event.type === "reasoning_start") {
            reasoningOpen = true;
            yield { type: "reasoning_start" };
          } else if (event.type === "reasoning_delta") {
            yield { type: "reasoning_delta", text: event.text };
          } else if (event.type === "content_delta") {
            if (reasoningOpen) {
              reasoningOpen = false;
              yield { type: "reasoning_done" };
            }
            contentBuffer += event.text;
            const visible = meaningfulAssistantContent(contentBuffer);
            if (visible && visible.length > lastStreamedVisible.length) {
              const delta = visible.slice(lastStreamedVisible.length);
              lastStreamedVisible = visible;
              if (delta) {
                if (!streamedReply) {
                  streamedReply = true;
                  yield { type: "assistant_start" };
                }
                yield { type: "assistant_delta", text: delta };
              }
            }
          } else if (event.type === "status") {
            yield { type: "status", message: event.message || "Pi 助手处理中…" };
          } else if (event.type === "message") {
            assistant = event.message;
          }
        }
        if (recoverOverflow) continue;
        llmStreamDone = true;
      }
      if (reasoningOpen) {
        yield { type: "reasoning_done" };
      }

      const decision = decideTurn(assistant, contentBuffer, {
        userMessage: message,
        history,
        nudgeCount: llmNudgeCount,
        maxNudges: MAX_LLM_NUDGES,
        toolRegistry,
      });

      if (decision.kind === "retry") {
        llmNudgeCount += 1;
        messages.push({ role: "user", content: decision.nudge });
        yield { type: "status", message: "模型未调用工具，正在重试…" };
        continue;
      }

      if (decision.kind === "fail") {
        yield {
          type: "error",
          message: decision.error || "模型未返回有效回复，请换种说法或检查 LLM 配置",
        };
        yield { type: "done" };
        return;
      }

      if (decision.kind === "final_reply") {
        if (!streamedReply) {
          yield { type: "assistant_start" };
          yield { type: "assistant_delta", text: decision.text };
        }
        yield { type: "assistant_done", text: decision.text };
        yield { type: "done" };
        return;
      }

      if (decision.kind === "fallback_tool_calls") {
        preparedCalls = decision.preparedCalls;
        content = meaningfulAssistantContent(
          String(assistant?.content ?? contentBuffer ?? ""),
        );
        assistant = { ...(assistant || {}), role: "assistant", content: content || null };
        yield { type: "status", message: decision.statusMessage };
        break;
      }

      preparedCalls = decision.preparedCalls;
      content = decision.introText;
      assistant = {
        ...(assistant || {}),
        role: "assistant",
        content: content || null,
        tool_calls: preparedCalls.map(([tc]) => tc),
      };
      break;
    }

    if (!assistant) {
      yield { type: "error", message: "模型未返回有效回复，请换种说法或检查 LLM 配置" };
      yield { type: "done" };
      return;
    }

    const intro = meaningfulAssistantContent(
      content || assistantIntroBeforeTools(contentBuffer),
    );
    if (intro) {
      if (!streamedReply) yield { type: "assistant_start" };
      yield { type: "assistant_done", text: intro };
    } else if (streamedReply) {
      const visible = meaningfulAssistantContent(contentBuffer.trim());
      if (visible) yield { type: "assistant_done", text: visible };
    }

    const executedCalls = preparedCalls.map(([toolCall]) => toolCall);
    messages.push(
      formatAssistantMessageForApi(assistant as Record<string, unknown>, intro || null, executedCalls),
    );

    const currentBatchNames = new Set(preparedCalls.map(([, name]) => name));
    let shouldForceSummary = false;

    const runOneTool = async (
      toolCall: PreparedCall[0],
      name: string,
      args: Record<string, unknown>,
      onProgress: (event: AgentEvent) => void,
    ): Promise<{ toolResult: Record<string, unknown>; llmContent: string }> => {
      let toolResult: Record<string, unknown> = { error: "工具执行失败" };
      let llmContent = "";
      try {
        const toolGen = python.runTool({ user_id: userId, name, args });
        let lastHeartbeat = Date.now();
        // Keep at most one in-flight next() across heartbeat timeouts; calling
        // next() again while the previous promise is pending would queue a
        // second pull whose resolved event is silently dropped.
        let nextPromise: ReturnType<typeof toolGen.next> | null = null;
        while (true) {
          if (!nextPromise) nextPromise = toolGen.next();
          const raceMs = Math.max(100, toolHeartbeatMs - (Date.now() - lastHeartbeat));
          let heartbeatTimer: NodeJS.Timeout | undefined;
          const timeoutPromise = new Promise<{ timedOut: true }>((resolve) => {
            heartbeatTimer = setTimeout(() => resolve({ timedOut: true }), raceMs);
          });
          const winner = await Promise.race([
            nextPromise.then((value) => ({ timedOut: false as const, value })),
            timeoutPromise,
          ]);
          clearTimeout(heartbeatTimer);
          if ("timedOut" in winner && winner.timedOut) {
            onProgress({ type: "status", message: `仍在执行 ${name}…` });
            lastHeartbeat = Date.now();
            continue;
          }
          nextPromise = null;
          const step = (winner as { timedOut: false; value: Awaited<ReturnType<typeof toolGen.next>> }).value;
          if (step.done) {
            toolResult = step.value.result;
            llmContent = step.value.llmContent;
            break;
          }
          const event = step.value;
          if (event.type === "tool_progress") {
            onProgress({ type: "tool_progress", name, message: event.message });
          } else if (event.type === "tool_event") {
            onProgress({ type: "tool_event", name, event: event.event });
          }
          lastHeartbeat = Date.now();
        }
      } catch (err) {
        const detail = err instanceof Error ? err.message : String(err);
        toolResult = { error: `工具 ${name} 执行失败：${detail.slice(0, 300)}` };
        llmContent = "";
      }
      return { toolResult, llmContent };
    };

    const allowedCalls: PreparedCall[] = [];
    for (const call of preparedCalls) {
      const [, name, args] = call;
      const block = await python.checkToolBlock({
        name,
        user_message: message,
        current_batch_names: [...currentBatchNames],
        executed_names: executedToolNames,
        executed_count: executedToolCount,
      });
      if (block.blocked) {
        const blockedResult = block.result || { error: block.reason || "blocked" };
        yield {
          type: "tool_blocked",
          name,
          args,
          reason: block.reason,
        };
        messages.push({
          role: "tool",
          tool_call_id: call[0].id,
          content: block.llm_content || JSON.stringify(blockedResult),
        });
        const allowAsnLookupCorrection =
          String(block.reason || "").startsWith("明确 ASN") &&
          !executedToolNames.includes("lookup_asns") &&
          !currentBatchNames.has("lookup_asns");
        if (!allowAsnLookupCorrection) shouldForceSummary = true;
        continue;
      }
      allowedCalls.push(call);
    }

    const parallelBatch =
      allowedCalls.length > 1 &&
      canParallelizeToolBatch(allowedCalls.map(([, name]) => name));

    if (parallelBatch) {
      for (const [, name, args] of allowedCalls) {
        yield { type: "tool_start", name, args };
      }
      const progressQueues = allowedCalls.map(() => [] as AgentEvent[]);
      const outcomeSlots: Array<
        | null
        | {
            toolCall: PreparedCall[0];
            name: string;
            toolResult: Record<string, unknown>;
            llmContent: string;
          }
      > = allowedCalls.map(() => null);
      // Event-driven drain: progress and completions wake the loop instead of
      // polling. Polling with Promise.race over already-settled promises spins
      // the microtask queue once the first tool finishes (allocating timers
      // until OOM), so every push/completion resolves the current wake signal.
      let wake: () => void = () => {};
      const notify = () => wake();
      // runOneTool never rejects (failures become error results), so these
      // fire-and-forget promises are safe; completion is tracked via slots.
      for (const [index, [toolCall, name, args]] of allowedCalls.entries()) {
        void runOneTool(toolCall, name, args, (event) => {
          progressQueues[index].push(event);
          notify();
        }).then((outcome) => {
          outcomeSlots[index] = { toolCall, name, ...outcome };
          notify();
        });
      }
      const drainQueues = function* (): Generator<AgentEvent> {
        for (const queue of progressQueues) {
          while (queue.length) {
            const event = queue.shift()!;
            if (event.type === "tool_progress") {
              yield { type: "tool_progress", name: event.name, message: event.message };
            } else if (event.type === "tool_event") {
              yield { type: "tool_event", name: event.name, event: event.event };
            } else if (event.type === "status") {
              yield { type: "status", message: event.message };
            }
          }
        }
      };
      while (outcomeSlots.some((slot) => slot === null)) {
        // Re-arm before draining so notifications fired while we yield are
        // not lost between the drain and the await.
        const wakeSignal = new Promise<void>((resolve) => {
          wake = resolve;
        });
        yield* drainQueues();
        if (outcomeSlots.some((slot) => slot === null)) await wakeSignal;
      }
      // Flush progress emitted between the last drain and the final completion.
      yield* drainQueues();
      for (let i = 0; i < outcomeSlots.length; i += 1) {
        const slot = outcomeSlots[i]!;
        const { toolCall, name, toolResult, llmContent } = slot;
        executedToolCount += 1;
        executedToolNames.push(name);
        yield { type: "tool_result", name, result: toolResult };
        messages.push({
          role: "tool",
          tool_call_id: toolCall.id,
          content: llmContent || JSON.stringify(toolResult),
        });
        if (
          await python.shouldForceSummary({
            name,
            user_message: message,
            executed_count: executedToolCount,
          })
        ) {
          shouldForceSummary = true;
        }
      }
    } else {
      for (const [toolCall, name, args] of allowedCalls) {
        if (cancelCheck()) {
          yield { type: "error", message: "任务已停止" };
          yield { type: "done" };
          return;
        }
        yield { type: "tool_start", name, args };
        executedToolCount += 1;
        executedToolNames.push(name);
        const pending: AgentEvent[] = [];
        let wake: () => void = () => {};
        let outcome: { toolResult: Record<string, unknown>; llmContent: string } | null = null;
        // runOneTool never rejects (it converts failures into error results),
        // so a plain .then is safe here.
        void runOneTool(toolCall, name, args, (event) => {
          pending.push(event);
          wake();
        }).then((value) => {
          outcome = value;
          wake();
        });
        const drainPending = function* (): Generator<AgentEvent> {
          while (pending.length) {
            const event = pending.shift()!;
            if (event.type === "tool_progress") {
              yield { type: "tool_progress", name: event.name, message: event.message };
            } else if (event.type === "tool_event") {
              yield { type: "tool_event", name: event.name, event: event.event };
            } else if (event.type === "status") {
              yield { type: "status", message: event.message };
            }
          }
        };
        while (outcome === null) {
          const wakeSignal = new Promise<void>((resolve) => {
            wake = resolve;
          });
          yield* drainPending();
          if (outcome === null) await wakeSignal;
        }
        // Flush progress emitted between the last drain and completion.
        yield* drainPending();
        const { toolResult, llmContent } = outcome;
        yield { type: "tool_result", name, result: toolResult };
        messages.push({
          role: "tool",
          tool_call_id: toolCall.id,
          content: llmContent || JSON.stringify(toolResult),
        });
        if (
          await python.shouldForceSummary({
            name,
            user_message: message,
            executed_count: executedToolCount,
          })
        ) {
          shouldForceSummary = true;
        }
      }
    }

    if (shouldForceSummary) {
      yield* finalizeWithSummary(
        messages,
        llmConfig,
        "（系统）关键工具已完成，或本轮工具预算/商用护栏已触发。" +
          "请立即根据已有工具结果给出简洁总结和下一步建议，不要再调用任何工具。",
        llmStream,
        "工具结果已整理完毕，请查看上方结果并按需继续缩小范围。",
      );
      return;
    }

    if (roundIndex === MAX_TOOL_ROUNDS - 1) {
      yield* finalizeWithSummary(
        messages,
        llmConfig,
        "（系统）本轮工具调用已达上限。请根据已有工具结果直接给出总结与下一步建议，" +
          "不要再调用任何工具。",
        llmStream,
        "已达到最大工具调用轮次，请简化问题后重试。",
      );
      return;
    }
  }

  yield { type: "error", message: "对话未完成，请重试" };
  yield { type: "done" };
}

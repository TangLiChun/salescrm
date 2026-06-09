import { decideTurn } from "./decisions.js";
import { formatAssistantMessageForApi, streamChat } from "./llmClient.js";
import { PythonClient } from "./pythonClient.js";
import {
  assistantIntroBeforeTools,
  meaningfulAssistantContent,
} from "./replyHeuristics.js";
import {
  MAX_LLM_CALLS_PER_TURN,
  MAX_LLM_NUDGES,
  MAX_TOOL_ROUNDS,
  TOOL_HEARTBEAT_MS,
} from "./types.js";
import type { AgentEvent, AssistantMessage, LlmConfig, PreparedCall } from "./types.js";

async function* streamTextReply(
  messages: Record<string, unknown>[],
  tools: Record<string, unknown>[] | null,
  config: LlmConfig,
): AsyncGenerator<never, [string, boolean]> {
  let assistant: AssistantMessage | null = null;
  let contentBuffer = "";
  for await (const event of streamChat(messages, tools, config, null)) {
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
): AsyncGenerator<AgentEvent> {
  messages.push({ role: "user", content: instruction });
  const replyGen = streamTextReply(messages, null, config);
  let finalText = "";
  let ok = false;
  while (true) {
    const step = await replyGen.next();
    if (step.done) {
      [finalText, ok] = step.value;
      break;
    }
  }
  if (!ok) finalText = "工具结果已整理完毕，请查看上方结果并按需继续缩小范围。";
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
}): AsyncGenerator<AgentEvent> {
  const { userId, message, threadId, python, llmConfig } = input;
  const cancelCheck = input.cancelCheck ?? (() => false);

  if (cancelCheck()) {
    yield { type: "error", message: "任务已停止" };
    yield { type: "done" };
    return;
  }

  yield { type: "status", message: "Reasonix 思考中…" };

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

      const toolChoice = llmNudgeCount > 0 && tools.length ? "required" : null;
      llmCallCount += 1;

      for await (const event of streamChat(messages, tools, llmConfig, toolChoice)) {
        if (event.type === "error") {
          yield { type: "error", message: event.message || "LLM 请求失败" };
          yield { type: "done" };
          return;
        }
        if (event.type === "content_delta") {
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
          yield { type: "status", message: event.message || "Reasonix 处理中…" };
        } else if (event.type === "message") {
          assistant = event.message;
        }
      }

      const decision = decideTurn(assistant, contentBuffer, {
        userMessage: message,
        history,
        nudgeCount: llmNudgeCount,
        maxNudges: MAX_LLM_NUDGES,
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

    for (const [toolCall, name, args] of preparedCalls) {
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
          tool_call_id: toolCall.id,
          content: block.llm_content || JSON.stringify(blockedResult),
        });
        const allowAsnLookupCorrection =
          String(block.reason || "").startsWith("明确 ASN") &&
          !executedToolNames.includes("lookup_asns") &&
          !currentBatchNames.has("lookup_asns");
        if (!allowAsnLookupCorrection) shouldForceSummary = true;
        continue;
      }

      yield { type: "tool_start", name, args };
      executedToolCount += 1;
      executedToolNames.push(name);

      const toolGen = python.runTool({ user_id: userId, name, args });
      let toolResult: Record<string, unknown> = { error: "工具执行失败" };
      let llmContent = "";
      let lastHeartbeat = Date.now();
      while (true) {
        const raceMs = Math.max(100, TOOL_HEARTBEAT_MS - (Date.now() - lastHeartbeat));
        const nextPromise = toolGen.next();
        const timeoutPromise = new Promise<{ timedOut: true }>((resolve) =>
          setTimeout(() => resolve({ timedOut: true }), raceMs),
        );
        const winner = await Promise.race([
          nextPromise.then((value) => ({ timedOut: false as const, value })),
          timeoutPromise,
        ]);
        if ("timedOut" in winner && winner.timedOut) {
          yield { type: "status", message: `仍在执行 ${name}…` };
          lastHeartbeat = Date.now();
          continue;
        }
        const step = (winner as { timedOut: false; value: IteratorResult<AgentEvent> }).value;
        if (step.done) {
          toolResult = step.value.result;
          llmContent = step.value.llmContent;
          break;
        }
        const event = step.value;
        if (event.type === "tool_progress") {
          yield { type: "tool_progress", name, message: event.message };
        } else if (event.type === "tool_event") {
          yield { type: "tool_event", name, event: event.event };
        }
        lastHeartbeat = Date.now();
      }

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

    if (shouldForceSummary) {
      const reason =
        "（系统）关键工具已完成，或本轮工具预算/商用护栏已触发。" +
        "请立即根据已有工具结果给出简洁总结和下一步建议，不要再调用任何工具。";
      yield* finalizeWithSummary(messages, llmConfig, reason);
      return;
    }

    if (roundIndex === MAX_TOOL_ROUNDS - 1) {
      messages.push({
        role: "user",
        content:
          "（系统）本轮工具调用已达上限。请根据已有工具结果直接给出总结与下一步建议，" +
          "不要再调用任何工具。",
      });
      const replyGen = streamTextReply(messages, null, llmConfig);
      let finalText = "";
      let ok = false;
      while (true) {
        const step = await replyGen.next();
        if (step.done) {
          [finalText, ok] = step.value;
          break;
        }
      }
      if (!ok) finalText = "已达到最大工具调用轮次，请简化问题后重试。";
      yield { type: "assistant_start" };
      yield { type: "assistant_delta", text: finalText };
      yield { type: "assistant_done", text: finalText };
      yield { type: "done" };
      return;
    }
  }

  yield { type: "error", message: "对话未完成，请重试" };
  yield { type: "done" };
}

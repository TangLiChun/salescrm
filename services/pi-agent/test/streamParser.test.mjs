import test from "node:test";
import assert from "node:assert/strict";

import {
  assembleMessage,
  consumeStreamChunk,
  mergeToolCallDelta,
  parseSseLine,
} from "../dist/streamParser.js";

function freshState() {
  return {
    contentParts: [],
    reasoningParts: [],
    toolCalls: new Map(),
    toolStatusEmitted: false,
    finishReasons: [],
    emitContentDelta: true,
  };
}

test("parseSseLine：data 前缀、DONE 哨兵、坏 JSON、裸 JSON", () => {
  assert.deepEqual(parseSseLine('data: {"a":1}'), { a: 1 });
  assert.equal(parseSseLine("data: [DONE]"), null);
  assert.equal(parseSseLine("[DONE]"), null);
  assert.equal(parseSseLine(""), null);
  assert.equal(parseSseLine("data: {broken"), null);
  assert.deepEqual(parseSseLine('{"b":2}'), { b: 2 });
});

test("mergeToolCallDelta：跨 chunk 拼接 name 与 arguments", () => {
  const slots = new Map();
  mergeToolCallDelta(slots, { index: 0, id: "call_a", function: { name: "list_", arguments: '{"q"' } });
  mergeToolCallDelta(slots, { index: 0, function: { name: "contacts", arguments: ':"isp"}' } });
  const slot = slots.get(0);
  assert.equal(slot.id, "call_a");
  assert.equal(slot.function.name, "list_contacts");
  assert.deepEqual(JSON.parse(slot.function.arguments), { q: "isp" });
});

test("mergeToolCallDelta：不同 index 写入不同槽位；function 可为 JSON 字符串", () => {
  const slots = new Map();
  mergeToolCallDelta(slots, { index: 0, function: { name: "a" } });
  mergeToolCallDelta(slots, { index: 1, function: '{"name":"b","arguments":"{}"}' });
  assert.equal(slots.get(0).function.name, "a");
  assert.equal(slots.get(1).function.name, "b");
});

test("consumeStreamChunk：content 增量累积并发出事件", () => {
  const state = freshState();
  const events = consumeStreamChunk(
    { choices: [{ delta: { content: "你好" } }] },
    state,
  );
  assert.deepEqual(events, [{ type: "content_delta", text: "你好" }]);
  assert.deepEqual(state.contentParts, ["你好"]);
});

test("consumeStreamChunk：首个推理增量触发 reasoning_start，工具增量只发一次 status", () => {
  const state = freshState();
  const first = consumeStreamChunk({ choices: [{ delta: { reasoning_content: "想" } }] }, state);
  assert.deepEqual(first.map((event) => event.type), ["reasoning_start", "reasoning_delta"]);
  const second = consumeStreamChunk({ choices: [{ delta: { reasoning_content: "想想" } }] }, state);
  assert.deepEqual(second.map((event) => event.type), ["reasoning_delta"]);

  const toolState = freshState();
  const toolEvents = consumeStreamChunk(
    { choices: [{ delta: { tool_calls: [{ index: 0, function: { name: "x" } }] } }] },
    toolState,
  );
  assert.deepEqual(toolEvents.map((event) => event.type), ["status"]);
  const again = consumeStreamChunk(
    { choices: [{ delta: { tool_calls: [{ index: 0, function: { arguments: "{}" } }] } }] },
    toolState,
  );
  assert.equal(again.length, 0);
});

test("consumeStreamChunk：非流式完整 message 覆盖较短的增量内容", () => {
  const state = freshState();
  consumeStreamChunk({ choices: [{ delta: { content: "部分" } }] }, state);
  consumeStreamChunk(
    {
      choices: [
        {
          finish_reason: "stop",
          message: {
            content: "部分内容的完整版本",
            tool_calls: [{ id: "c1", function: { name: "list_contacts", arguments: { q: "x" } } }],
          },
        },
      ],
    },
    state,
  );
  assert.equal(state.contentParts.join(""), "部分内容的完整版本");
  assert.equal(state.toolCalls.get(0).function.name, "list_contacts");
  assert.equal(state.toolCalls.get(0).function.arguments, '{"q":"x"}');
  assert.deepEqual(state.finishReasons, ["stop"]);
});

test("assembleMessage：按 index 排序、跳过空槽、补 id、取最后的 finish_reason", () => {
  const slots = new Map();
  slots.set(1, { id: "", type: "function", function: { name: "b_tool", arguments: "{}" } });
  slots.set(0, { id: "call_a", type: "function", function: { name: "a_tool", arguments: "{}" } });
  slots.set(2, { id: "", type: "function", function: { name: "", arguments: "" } });

  const message = assembleMessage(["你好"], ["想了想"], slots, ["tool_calls", "stop"]);
  assert.equal(message.role, "assistant");
  assert.equal(message.content, "你好");
  assert.equal(message.reasoning_content, "想了想");
  assert.equal(message.finish_reason, "stop");
  assert.equal(message.tool_calls.length, 2);
  assert.deepEqual(
    message.tool_calls.map((tc) => tc.function.name),
    ["a_tool", "b_tool"],
  );
  assert.ok(message.tool_calls[1].id.startsWith("call_"), "缺失的 id 应自动生成");
});

test("assembleMessage：无内容时 content 为 null 且不带 tool_calls", () => {
  const message = assembleMessage([], [], new Map(), []);
  assert.equal(message.content, null);
  assert.ok(!("tool_calls" in message));
  assert.ok(!("finish_reason" in message));
});

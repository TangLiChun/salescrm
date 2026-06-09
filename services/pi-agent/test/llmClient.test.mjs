import test from "node:test";
import assert from "node:assert/strict";

import { formatAssistantMessageForApi, streamChat } from "../dist/llmClient.js";
import { LLM_CONFIG, collect } from "./helpers.mjs";

function sseBody(chunks) {
  return chunks.map((chunk) => `data: ${JSON.stringify(chunk)}\n`).join("") + "data: [DONE]\n";
}

function withMockFetch(impl, fn) {
  const original = globalThis.fetch;
  globalThis.fetch = impl;
  return fn().finally(() => {
    globalThis.fetch = original;
  });
}

const MESSAGES = [{ role: "user", content: "你好" }];

test("streamChat：SSE 流转换为 content_delta + 汇总 message", async () => {
  const requests = [];
  await withMockFetch(
    async (url, init) => {
      requests.push({ url, payload: JSON.parse(init.body) });
      return new Response(
        sseBody([
          { choices: [{ delta: { content: "你" } }] },
          { choices: [{ delta: { content: "好" } }] },
          { choices: [{ finish_reason: "stop", delta: {} }] },
        ]),
        { status: 200 },
      );
    },
    async () => {
      const events = await collect(streamChat(MESSAGES, null, LLM_CONFIG));
      const deltas = events.filter((event) => event.type === "content_delta");
      assert.equal(deltas.map((event) => event.text).join(""), "你好");
      const message = events.find((event) => event.type === "message").message;
      assert.equal(message.content, "你好");
      assert.equal(message.finish_reason, "stop");
    },
  );
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "http://llm.test/v1/chat/completions");
  assert.equal(requests[0].payload.model, "test-model");
  assert.equal(requests[0].payload.stream, true);
  assert.ok(!("tools" in requests[0].payload), "无工具时不应传 tools 字段");
});

test("streamChat：流末尾无换行的 data 行也会被解析（回归：尾部 buffer 丢弃）", async () => {
  await withMockFetch(
    async () =>
      new Response(
        // 注意：最后一行刻意不带换行符。
        `data: ${JSON.stringify({ choices: [{ delta: { content: "完整回复" } }] })}`,
        { status: 200 },
      ),
    async () => {
      const events = await collect(streamChat(MESSAGES, null, LLM_CONFIG));
      const message = events.find((event) => event.type === "message").message;
      assert.equal(message.content, "完整回复");
    },
  );
});

test("streamChat：429 按 Retry-After 重试后成功", async () => {
  let calls = 0;
  await withMockFetch(
    async () => {
      calls += 1;
      if (calls === 1) {
        return new Response("rate limited", { status: 429, headers: { "Retry-After": "0" } });
      }
      return new Response(sseBody([{ choices: [{ delta: { content: "ok" } }] }]), { status: 200 });
    },
    async () => {
      const events = await collect(streamChat(MESSAGES, null, LLM_CONFIG));
      assert.ok(events.some((event) => event.type === "message"));
      assert.ok(!events.some((event) => event.type === "error"));
    },
  );
  assert.equal(calls, 2);
});

test("streamChat：400 类错误不重试，直接报错", async () => {
  let calls = 0;
  await withMockFetch(
    async () => {
      calls += 1;
      return new Response('{"error":"bad request"}', { status: 400 });
    },
    async () => {
      const events = await collect(streamChat(MESSAGES, null, LLM_CONFIG));
      assert.equal(events.length, 1);
      assert.equal(events[0].type, "error");
      assert.ok(events[0].message.includes("400"));
    },
  );
  assert.equal(calls, 1);
});

test("streamChat：带工具时传 tools 与 tool_choice", async () => {
  const tools = [{ type: "function", function: { name: "list_contacts", parameters: {} } }];
  let payload = null;
  await withMockFetch(
    async (_url, init) => {
      payload = JSON.parse(init.body);
      return new Response(sseBody([{ choices: [{ delta: { content: "ok" } }] }]), { status: 200 });
    },
    async () => {
      await collect(streamChat(MESSAGES, tools, LLM_CONFIG, "required"));
    },
  );
  assert.deepEqual(payload.tools, tools);
  assert.equal(payload.tool_choice, "required");
});

test("streamChat：发送前剥离无工具调用的 assistant 推理字段", async () => {
  const messages = [
    { role: "user", content: "你好" },
    { role: "assistant", content: "回复", reasoning_content: "内部推理" },
    { role: "assistant", content: null, tool_calls: [{ id: "c1" }], reasoning_content: "保留" },
  ];
  let payload = null;
  await withMockFetch(
    async (_url, init) => {
      payload = JSON.parse(init.body);
      return new Response(sseBody([{ choices: [{ delta: { content: "ok" } }] }]), { status: 200 });
    },
    async () => {
      await collect(streamChat(messages, null, LLM_CONFIG));
    },
  );
  assert.ok(!("reasoning_content" in payload.messages[1]), "纯文本 assistant 的推理应剥离");
  assert.equal(payload.messages[2].reasoning_content, "保留");
});

test("formatAssistantMessageForApi：仅带工具调用时保留推理", () => {
  const withTools = formatAssistantMessageForApi(
    { reasoning_content: "推理" },
    "开场白",
    [{ id: "c1" }],
  );
  assert.equal(withTools.reasoning_content, "推理");
  assert.equal(withTools.content, "开场白");

  const noTools = formatAssistantMessageForApi({ reasoning_content: "推理" }, "回复", []);
  assert.ok(!("reasoning_content" in noTools));
  assert.equal(noTools.content, "回复");

  const empty = formatAssistantMessageForApi(null, "", null);
  assert.equal(empty.content, null);
});

import test from "node:test";
import assert from "node:assert/strict";

import { PythonClient } from "../dist/pythonClient.js";

function withMockFetch(impl, fn) {
  const original = globalThis.fetch;
  globalThis.fetch = impl;
  return fn().finally(() => {
    globalThis.fetch = original;
  });
}

async function drainRunTool(client) {
  const gen = client.runTool({ user_id: 1, name: "list_contacts", args: { q: "x" } });
  const events = [];
  while (true) {
    const step = await gen.next();
    if (step.done) return { events, outcome: step.value };
    events.push(step.value);
  }
}

test("runTool：解析 progress/event/done 事件流", async () => {
  const body =
    'data: {"type":"tool_progress","message":"搜索中"}\n' +
    'data: {"type":"tool_event","event":{"kind":"row","id":1}}\n' +
    'data: {"type":"done","result":{"total":2},"llm_content":"共 2 条"}\n';
  await withMockFetch(
    async (url, init) => {
      assert.ok(String(url).endsWith("/api/internal/pi/tools/run"));
      assert.equal(init.headers["X-Internal-Secret"], "s3cret");
      return new Response(body, { status: 200 });
    },
    async () => {
      const client = new PythonClient("http://crm.test", "s3cret");
      const { events, outcome } = await drainRunTool(client);
      assert.deepEqual(events.map((event) => event.type), ["tool_progress", "tool_event"]);
      assert.deepEqual(outcome.result, { total: 2 });
      assert.equal(outcome.llmContent, "共 2 条");
    },
  );
});

test("runTool：坏 JSON 行与非 data 行被跳过而不是抛异常（回归）", async () => {
  const body =
    ": comment line\n" +
    "data: {broken json\n" +
    'data: {"type":"tool_progress","message":"ok"}\n' +
    'data: {"type":"done","result":{"total":1},"llm_content":""}\n';
  await withMockFetch(
    async () => new Response(body, { status: 200 }),
    async () => {
      const client = new PythonClient("http://crm.test", "s");
      const { events, outcome } = await drainRunTool(client);
      assert.equal(events.length, 1);
      assert.deepEqual(outcome.result, { total: 1 });
    },
  );
});

test("runTool：末尾无换行的 done 行也被处理（回归：尾部 buffer 丢弃）", async () => {
  const body = 'data: {"type":"done","result":{"total":9},"llm_content":"九条"}';
  await withMockFetch(
    async () => new Response(body, { status: 200 }),
    async () => {
      const client = new PythonClient("http://crm.test", "s");
      const { outcome } = await drainRunTool(client);
      assert.deepEqual(outcome.result, { total: 9 });
      assert.equal(outcome.llmContent, "九条");
    },
  );
});

test("runTool：HTTP 失败抛出带状态码的错误", async () => {
  await withMockFetch(
    async () => new Response("internal error", { status: 500 }),
    async () => {
      const client = new PythonClient("http://crm.test", "s");
      await assert.rejects(
        () => drainRunTool(client),
        (err) => err.message.includes("500"),
      );
    },
  );
});

test("shouldForceSummary：HTTP 失败时回退为 false 而不是抛异常", async () => {
  await withMockFetch(
    async () => new Response("oops", { status: 500 }),
    async () => {
      const client = new PythonClient("http://crm.test", "s");
      const force = await client.shouldForceSummary({
        name: "list_contacts",
        user_message: "x",
        executed_count: 1,
      });
      assert.equal(force, false);
    },
  );
});

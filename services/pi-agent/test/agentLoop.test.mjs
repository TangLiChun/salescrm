import test from "node:test";
import assert from "node:assert/strict";

import { agentChatStream } from "../dist/agentLoop.js";
import { MAX_TOOL_ROUNDS } from "../dist/types.js";
import {
  FakePython,
  LLM_CONFIG,
  collect,
  eventTypes,
  lastAssistantText,
  ofType,
  scriptedLlm,
  sleep,
} from "./helpers.mjs";

function runLoop({ python, llm, message = "搜索 ISP 联系人", threadId = "t-1", ...rest }) {
  return agentChatStream({
    userId: 7,
    message,
    threadId,
    python,
    llmConfig: LLM_CONFIG,
    streamChatImpl: llm,
    ...rest,
  });
}

test("纯文本回复：完整事件序列且无工具调用", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([{ content: "你好，我是 Pi，可以帮你管理 CRM 线索。" }]);
  const events = await collect(runLoop({ python, llm, message: "你好" }));

  const types = eventTypes(events);
  assert.equal(types[0], "status");
  assert.ok(types.includes("context"));
  assert.ok(types.includes("assistant_start"));
  assert.equal(types[types.length - 2], "assistant_done");
  assert.equal(types[types.length - 1], "done");
  assert.equal(lastAssistantText(events), "你好，我是 Pi，可以帮你管理 CRM 线索。");
  assert.equal(python.calls.runTool.length, 0);
  assert.equal(ofType(events, "error").length, 0);
});

test("流式增量拼起来等于最终回复", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([{ content: "线索已经整理完毕，共 12 条。" }]);
  const events = await collect(runLoop({ python, llm }));

  const streamed = ofType(events, "assistant_delta").map((event) => event.text).join("");
  assert.equal(streamed, lastAssistantText(events));
});

test("推理事件按 reasoning_start/delta/done 顺序转发", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([{ reasoning: "用户想要打招呼", content: "你好！" }]);
  const events = await collect(runLoop({ python, llm, message: "你好" }));

  const types = eventTypes(events);
  const rStart = types.indexOf("reasoning_start");
  const rDone = types.indexOf("reasoning_done");
  const aStart = types.indexOf("assistant_start");
  assert.ok(rStart >= 0 && rDone > rStart, "reasoning 应成对出现");
  assert.ok(aStart > rDone, "正文应在推理结束后开始");
  assert.equal(ofType(events, "reasoning_delta").map((event) => event.text).join(""), "用户想要打招呼");
});

test("一轮工具调用后给出总结，并把工具结果回灌给模型", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([
    { toolCalls: [{ name: "list_contacts", args: { q: "isp" } }] },
    { content: "共找到 2 条 ISP 联系人。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  const types = eventTypes(events);
  assert.ok(types.indexOf("tool_start") < types.indexOf("tool_result"));
  assert.equal(lastAssistantText(events), "共找到 2 条 ISP 联系人。");
  assert.deepEqual(python.calls.runTool[0], { user_id: 7, name: "list_contacts", args: { q: "isp" } });

  // 第二次 LLM 调用应包含 assistant(tool_calls) + tool 消息。
  const secondCall = llm.calls[1];
  const roles = secondCall.messages.map((msg) => msg.role);
  assert.ok(roles.includes("tool"));
  const assistantMsg = secondCall.messages.find((msg) => msg.tool_calls?.length);
  assert.ok(assistantMsg, "应把带 tool_calls 的 assistant 消息回灌");
});

test("工具调用前的开场白先以 assistant_done 落地", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([
    { content: "我先搜索一下 CRM：", toolCalls: [{ name: "list_contacts", args: { q: "noc" } }] },
    { content: "搜索完成。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  const dones = ofType(events, "assistant_done");
  assert.equal(dones[0].text, "我先搜索一下 CRM：");
  const types = eventTypes(events);
  assert.ok(types.indexOf("assistant_done") < types.indexOf("tool_start"));
  assert.equal(dones[dones.length - 1].text, "搜索完成。");
});

test("正文里内联的 JSON 工具调用会被解析执行", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([
    { content: '[{"name":"list_contacts","arguments":{"q":"noc"}}]' },
    { content: "已为你查到结果。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  assert.equal(python.calls.runTool.length, 1);
  assert.deepEqual(python.calls.runTool[0].args, { q: "noc" });
  assert.equal(lastAssistantText(events), "已为你查到结果。");
});

test("只回开场白会被 nudge 重试，并把系统提示写入对话", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([
    { content: "好的，我来搜索 CRM" },
    { toolCalls: [{ name: "list_contacts", args: { q: "isp" } }] },
    { content: "搜索完成，共 3 条。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  assert.equal(llm.calls.length, 3);
  const nudge = llm.calls[1].messages[llm.calls[1].messages.length - 1];
  assert.equal(nudge.role, "user");
  assert.ok(String(nudge.content).startsWith("（系统）"));
  assert.ok(ofType(events, "status").some((event) => event.message.includes("重试")));
  assert.equal(lastAssistantText(events), "搜索完成，共 3 条。");
});

test("模型持续空响应时报错收尾而不是死循环", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([{ content: "" }]);
  const events = await collect(runLoop({ python, llm }));

  assert.equal(ofType(events, "error").length, 1);
  assert.equal(eventTypes(events)[eventTypes(events).length - 1], "done");
  assert.ok(llm.calls.length >= 2, "应先 nudge 重试再失败");
});

test("LLM 错误直接上报并结束", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([{ error: "LLM 请求失败 (401): bad key" }]);
  const events = await collect(runLoop({ python, llm }));

  assert.ok(ofType(events, "error")[0].message.includes("401"));
  assert.equal(eventTypes(events)[eventTypes(events).length - 1], "done");
});

test("上下文溢出：压缩恢复后重试同一轮", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([
    { error: "This model's maximum context length is 65536 tokens" },
    { content: "压缩后已完成回答。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  assert.equal(python.calls.recoverOverflow.length, 1);
  assert.ok(ofType(events, "status").some((event) => event.message.includes("压缩")));
  assert.equal(ofType(events, "context").length, 2, "恢复后应再发一次 context 事件");
  assert.equal(lastAssistantText(events), "压缩后已完成回答。");
  assert.equal(ofType(events, "error").length, 0);
});

test("无 threadId 时溢出错误直接上报，不尝试恢复", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([{ error: "maximum context length exceeded" }]);
  const events = await collect(runLoop({ python, llm, threadId: null }));

  assert.equal(python.calls.recoverOverflow.length, 0);
  assert.equal(ofType(events, "error").length, 1);
});

test("溢出恢复只重试一次，二次溢出直接报错", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([
    { error: "maximum context length exceeded" },
    { error: "maximum context length exceeded" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  assert.equal(python.calls.recoverOverflow.length, 1);
  assert.equal(ofType(events, "error").length, 1);
});

test("取消检查：开始前取消立即结束", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([{ content: "不应该到这里" }]);
  const events = await collect(runLoop({ python, llm, cancelCheck: () => true }));

  assert.deepEqual(eventTypes(events), ["error", "done"]);
  assert.equal(python.calls.prepare.length, 0);
});

test("工具被护栏拦截：发 tool_blocked 并强制总结", async () => {
  const python = new FakePython({
    checkToolBlock: (input) =>
      input.name === "web_search"
        ? { blocked: true, reason: "外部搜索预算已用尽", llm_content: '{"error":"budget"}' }
        : { blocked: false },
  });
  const llm = scriptedLlm([
    { toolCalls: [{ name: "web_search", args: { query: "isp peering" } }] },
    { content: "已根据现有结果总结。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  const blocked = ofType(events, "tool_blocked");
  assert.equal(blocked.length, 1);
  assert.equal(blocked[0].name, "web_search");
  assert.equal(python.calls.runTool.length, 0);
  assert.equal(lastAssistantText(events), "已根据现有结果总结。");
  // 强制总结调用不应再带工具。
  assert.equal(llm.calls[1].tools, null);
});

test("shouldForceSummary 命中后立即收口总结", async () => {
  const python = new FakePython({
    shouldForceSummary: (input) => input.name === "discover_leads",
  });
  const llm = scriptedLlm([
    { toolCalls: [{ name: "discover_leads", args: { query: "isp" } }] },
    { content: "挖掘完成，共导入 5 条线索。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  assert.equal(lastAssistantText(events), "挖掘完成，共导入 5 条线索。");
  assert.equal(llm.calls.length, 2);
  assert.equal(llm.calls[1].tools, null);
});

test("并行批次：可并行工具一起启动且进度事件不丢", async () => {
  const python = new FakePython({
    async *runTool(input) {
      yield { type: "tool_progress", message: `进度-${input.name}` };
      await sleep(20);
      yield { type: "tool_progress", message: `收尾-${input.name}` };
      return { result: { ok: input.name }, llmContent: "" };
    },
  });
  const llm = scriptedLlm([
    {
      toolCalls: [
        { name: "list_contacts", args: { q: "isp" } },
        { name: "get_stats", args: {} },
      ],
    },
    { content: "统计与搜索都完成了。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  const types = eventTypes(events);
  const starts = types.reduce((acc, t, i) => (t === "tool_start" ? [...acc, i] : acc), []);
  const firstResult = types.indexOf("tool_result");
  assert.equal(starts.length, 2);
  assert.ok(starts[1] < firstResult, "两个 tool_start 都应早于第一个 tool_result");
  assert.equal(ofType(events, "tool_result").length, 2);

  const progress = ofType(events, "tool_progress").map((event) => event.message).sort();
  assert.deepEqual(progress, ["收尾-get_stats", "收尾-list_contacts", "进度-get_stats", "进度-list_contacts"]);
  assert.equal(lastAssistantText(events), "统计与搜索都完成了。");
});

test("并行批次完成时间错开不忙等（回归：先完成的槽位导致 Promise.race 空转 OOM）", async () => {
  const python = new FakePython({
    async *runTool(input) {
      // 一快一慢，制造一个"已完成 + 仍在等待"的窗口。
      await sleep(input.name === "list_contacts" ? 5 : 150);
      yield { type: "tool_progress", message: `done-${input.name}` };
      return { result: { ok: input.name }, llmContent: "" };
    },
  });
  const llm = scriptedLlm([
    {
      toolCalls: [
        { name: "list_contacts", args: { q: "isp" } },
        { name: "get_stats", args: {} },
      ],
    },
    { content: "完成。" },
  ]);
  const started = Date.now();
  const events = await collect(runLoop({ python, llm }));
  assert.ok(Date.now() - started < 2_000, "等待循环不应忙等");
  assert.equal(ofType(events, "tool_result").length, 2);
  assert.equal(
    ofType(events, "tool_progress").length,
    2,
    "两个工具的收尾进度都应送达",
  );
  assert.equal(lastAssistantText(events), "完成。");
});

test("含非并行安全工具的批次按顺序执行", async () => {
  const order = [];
  const python = new FakePython({
    async *runTool(input) {
      order.push(`start-${input.name}`);
      await sleep(10);
      order.push(`end-${input.name}`);
      return { result: { ok: true }, llmContent: "" };
    },
  });
  const llm = scriptedLlm([
    {
      toolCalls: [
        { name: "list_contacts", args: { q: "isp" } },
        { name: "delete_contacts", args: { ids: [1] } },
      ],
    },
    { content: "完成。" },
  ]);
  await collect(runLoop({ python, llm }));

  assert.deepEqual(order, [
    "start-list_contacts",
    "end-list_contacts",
    "start-delete_contacts",
    "end-delete_contacts",
  ]);
});

test("单个工具抛异常不会终结整轮：错误结果回灌给模型", async () => {
  const python = new FakePython({
    // eslint-disable-next-line require-yield
    async *runTool(input) {
      if (input.name === "list_contacts") throw new Error("Tool run failed (500): boom");
      return { result: { ok: true }, llmContent: "" };
    },
  });
  const llm = scriptedLlm([
    { toolCalls: [{ name: "list_contacts", args: { q: "isp" } }] },
    { content: "工具暂时不可用，建议稍后再试。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  const result = ofType(events, "tool_result")[0];
  assert.ok(String(result.result.error).includes("boom"));
  assert.equal(lastAssistantText(events), "工具暂时不可用，建议稍后再试。");
  assert.equal(ofType(events, "error").length, 0);

  const toolMsg = llm.calls[1].messages.find((msg) => msg.role === "tool");
  assert.ok(String(toolMsg.content).includes("boom"), "错误详情应回灌给模型");
});

test("心跳期间到达的工具事件不丢失（回归：重复 next() 丢事件）", async () => {
  const python = new FakePython({
    async *runTool() {
      yield { type: "tool_progress", message: "step1" };
      await sleep(350);
      yield { type: "tool_progress", message: "step2" };
      return { result: { ok: true }, llmContent: "" };
    },
  });
  const llm = scriptedLlm([
    { toolCalls: [{ name: "list_contacts", args: { q: "isp" } }] },
    { content: "完成。" },
  ]);
  const events = await collect(runLoop({ python, llm, toolHeartbeatMs: 120 }));

  const progress = ofType(events, "tool_progress").map((event) => event.message);
  assert.deepEqual(progress, ["step1", "step2"]);
  assert.ok(
    ofType(events, "status").some((event) => event.message.includes("仍在执行")),
    "慢工具应触发心跳状态",
  );
  assert.deepEqual(ofType(events, "tool_result")[0].result, { ok: true });
});

test("达到最大工具轮次后强制总结收口", async () => {
  const python = new FakePython();
  const turns = Array.from({ length: MAX_TOOL_ROUNDS }, (_, i) => ({
    toolCalls: [{ name: "list_contacts", args: { q: `批次${i}` } }],
  }));
  turns.push({ content: "已达轮次上限，以下是汇总。" });
  const llm = scriptedLlm(turns);
  const events = await collect(runLoop({ python, llm }));

  assert.equal(python.calls.runTool.length, MAX_TOOL_ROUNDS);
  assert.equal(lastAssistantText(events), "已达轮次上限，以下是汇总。");
  const finalCall = llm.calls[llm.calls.length - 1];
  assert.equal(finalCall.tools, null, "强制总结不应再提供工具");
  const sysNudge = finalCall.messages[finalCall.messages.length - 1];
  assert.ok(String(sysNudge.content).includes("上限"));
});

test("strict registry：未知工具名不会被执行，nudge 后恢复", async () => {
  const python = new FakePython();
  const llm = scriptedLlm([
    // 参数形状也无法推断出已知工具，确保走"非法调用"分支。
    { toolCalls: [{ name: "totally_fake_tool", args: { mystery: 1 } }] },
    { toolCalls: [{ name: "list_contacts", args: { q: "x" } }] },
    { content: "完成。" },
  ]);
  const events = await collect(runLoop({ python, llm }));

  assert.equal(python.calls.runTool.length, 1);
  assert.equal(python.calls.runTool[0].name, "list_contacts");
  assert.equal(lastAssistantText(events), "完成。");
});

test("工具名别名（prepare 下发）会被归一化执行", async () => {
  const python = new FakePython({ toolAliases: { search_contacts: "list_contacts" } });
  const llm = scriptedLlm([
    { toolCalls: [{ name: "functions.search_contacts", args: { keyword: "isp" } }] },
    { content: "完成。" },
  ]);
  await collect(runLoop({ python, llm }));

  assert.equal(python.calls.runTool.length, 1);
  assert.equal(python.calls.runTool[0].name, "list_contacts");
  assert.equal(python.calls.runTool[0].args.q, "isp");
});

test("prepare 下发的 status_messages 原样转发", async () => {
  const python = new FakePython({ statusMessages: ["已加载 3 条历史"] });
  const llm = scriptedLlm([{ content: "好的。" }]);
  const events = await collect(runLoop({ python, llm }));

  assert.ok(ofType(events, "status").some((event) => event.message === "已加载 3 条历史"));
});

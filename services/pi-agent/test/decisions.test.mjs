import test from "node:test";
import assert from "node:assert/strict";

import { decideTurn } from "../dist/decisions.js";
import { createToolRegistry } from "../dist/toolCalls.js";
import { DEFAULT_TOOLS } from "./helpers.mjs";

const registry = createToolRegistry(DEFAULT_TOOLS, { search_contacts: "list_contacts" });

function decide(assistant, contentBuffer = "", opts = {}) {
  return decideTurn(assistant, contentBuffer, {
    userMessage: opts.userMessage ?? "搜索 ISP 联系人",
    history: opts.history ?? [],
    nudgeCount: opts.nudgeCount ?? 0,
    maxNudges: opts.maxNudges ?? 2,
    toolRegistry: opts.toolRegistry ?? registry,
  });
}

function toolCall(name, args = {}) {
  return {
    id: "call_1",
    type: "function",
    function: { name, arguments: JSON.stringify(args) },
  };
}

test("空响应：先 retry，nudge 用尽后 fail", () => {
  assert.equal(decide(null).kind, "retry");
  assert.equal(decide({ role: "assistant", content: "" }).kind, "retry");
  assert.equal(decide(null, "", { nudgeCount: 2 }).kind, "fail");
});

test("仅有推理内容不算空响应，但会因无可见内容而 retry", () => {
  const decision = decide({ role: "assistant", content: null, reasoning_content: "思考中" });
  assert.equal(decision.kind, "retry");
  assert.equal(decision.reason, "no_visible_content");
});

test("content_filter 直接失败并带提示", () => {
  const decision = decide({ role: "assistant", content: "x", finish_reason: "content_filter" });
  assert.equal(decision.kind, "fail");
  assert.ok(decision.error.includes("内容安全"));
});

test("上游资源中断：先 retry 再 fail", () => {
  const msg = { role: "assistant", content: "部分输出", finish_reason: "insufficient_system_resource" };
  assert.equal(decide(msg).kind, "retry");
  const final = decide(msg, "", { nudgeCount: 2 });
  assert.equal(final.kind, "fail");
  assert.ok(final.error.includes("截断"));
});

test("length 截断不丢弃内容：当普通最终回复处理", () => {
  const decision = decide({ role: "assistant", content: "已找到 3 条联系人", finish_reason: "length" });
  assert.equal(decision.kind, "final_reply");
  assert.equal(decision.text, "已找到 3 条联系人");
});

test("finish_reason=tool_calls 但缺 tool_calls：retry 后回落到 fallback 搜索", () => {
  // 带一点内容避免命中更早的空响应检查。
  const msg = { role: "assistant", content: "好的", finish_reason: "tool_calls" };
  assert.equal(decide(msg).kind, "retry");
  const fallback = decide(msg, "", { nudgeCount: 2, userMessage: "搜索运营商联系人" });
  assert.equal(fallback.kind, "fallback_tool_calls");
  assert.ok(fallback.preparedCalls.length > 0);
  assert.ok(fallback.preparedCalls.every(([, name]) => name === "list_contacts"));
});

test("普通文本回答 → final_reply", () => {
  const decision = decide({ role: "assistant", content: "目前 CRM 共有 120 条联系人。" });
  assert.equal(decision.kind, "final_reply");
});

test("承诺要调工具的开场白 → retry intro_only", () => {
  const decision = decide({ role: "assistant", content: "好的，我先搜索一下 CRM：" });
  assert.equal(decision.kind, "retry");
  assert.equal(decision.reason, "intro_only");
});

test("用户说「继续」但模型只回了客套话 → retry continuation", () => {
  const decision = decide(
    { role: "assistant", content: "好的，马上继续。" },
    "",
    { userMessage: "继续" },
  );
  assert.equal(decision.kind, "retry");
  assert.equal(decision.reason, "continuation");
});

test("「继续」且 nudge 用尽 → 直接 fallback 执行上一任务", () => {
  const decision = decide(
    { role: "assistant", content: "好的，马上继续。" },
    "",
    {
      userMessage: "继续",
      nudgeCount: 2,
      history: [{ role: "user", content: "帮我挖掘 ISP 线索" }],
    },
  );
  assert.equal(decision.kind, "fallback_tool_calls");
  assert.equal(decision.preparedCalls[0][1], "discover_leads");
  assert.ok(JSON.stringify(decision.preparedCalls[0][2]).includes("ISP 线索"));
});

test("合法 tool_calls → emit，开场白作为 introText", () => {
  const decision = decide({
    role: "assistant",
    content: "我先查一下：",
    tool_calls: [toolCall("list_contacts", { q: "isp" })],
  });
  assert.equal(decision.kind, "emit_tool_calls");
  assert.equal(decision.preparedCalls[0][1], "list_contacts");
  assert.equal(decision.introText, "我先查一下：");
});

test("别名工具名在 emit 前被归一化", () => {
  const decision = decide({
    role: "assistant",
    content: null,
    tool_calls: [toolCall("functions.search_contacts", { keyword: "noc" })],
  });
  assert.equal(decision.kind, "emit_tool_calls");
  assert.equal(decision.preparedCalls[0][1], "list_contacts");
  assert.equal(decision.preparedCalls[0][2].q, "noc");
});

test("全部 tool_calls 名字非法且无内容可恢复 → retry invalid_tool_calls", () => {
  const decision = decide({
    role: "assistant",
    content: null,
    tool_calls: [toolCall("not_real", {})],
  });
  assert.equal(decision.kind, "retry");
  assert.equal(decision.reason, "invalid_tool_calls");
});

test("非法 tool_calls 但正文里有内联 JSON → 从内容恢复 emit", () => {
  const decision = decide({
    role: "assistant",
    content: '[{"name":"list_contacts","arguments":{"q":"noc"}}]',
    tool_calls: [toolCall("not_real", {})],
  });
  assert.equal(decision.kind, "emit_tool_calls");
  assert.equal(decision.preparedCalls[0][1], "list_contacts");
  assert.deepEqual(decision.preparedCalls[0][2], { q: "noc" });
});

test("无 registry 时保持宽松：未知工具名也 emit（兼容旧路径）", () => {
  const decision = decideTurn(
    { role: "assistant", content: null, tool_calls: [toolCall("custom_tool", { a: 1 })] },
    "",
    { userMessage: "x", history: [], nudgeCount: 0, maxNudges: 2 },
  );
  assert.equal(decision.kind, "emit_tool_calls");
  assert.equal(decision.preparedCalls[0][1], "custom_tool");
});

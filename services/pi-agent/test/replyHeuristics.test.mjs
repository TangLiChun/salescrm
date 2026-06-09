import test from "node:test";
import assert from "node:assert/strict";

import {
  assistantIntroBeforeTools,
  assistantPromisesToolUse,
  fallbackPreparedCalls,
  meaningfulAssistantContent,
  parseInlineToolCalls,
  userRequestsContinuation,
} from "../dist/replyHeuristics.js";
import { createToolRegistry } from "../dist/toolCalls.js";
import { DEFAULT_TOOLS } from "./helpers.mjs";

const registry = createToolRegistry(DEFAULT_TOOLS, {});

test("普通散文不被截断（回归：括号引用被误判为工具 JSON）", () => {
  const prose = "已完成 [1] 项任务，详见 [报告链接](https://example.com)。[已完成] 共 3 条。";
  assert.equal(meaningfulAssistantContent(prose), prose);
});

test("工具 JSON 泄漏进正文时在标记处截断", () => {
  assert.equal(
    assistantIntroBeforeTools('我先搜索：[{"name":"list_contacts"}]'),
    "我先搜索：",
  );
  assert.equal(assistantIntroBeforeTools('好的```json\n{"q":"isp"}\n```'), "好的");
  assert.equal(meaningfulAssistantContent('{"query":"isp peering"}'), "");
});

test("纯 JSON 碎片视为无内容", () => {
  for (const fragment of ["[{", "{", "[", '[{"q', "[{(,"]) {
    assert.equal(meaningfulAssistantContent(fragment), "", `碎片 ${fragment} 应为空`);
  }
});

test("assistantPromisesToolUse 识别开场白承诺", () => {
  assert.ok(assistantPromisesToolUse("好的，我先搜索一下 CRM："));
  assert.ok(assistantPromisesToolUse("马上帮你查一下相关线索"));
  assert.ok(assistantPromisesToolUse("正在整理…"));
  assert.ok(!assistantPromisesToolUse("目前 CRM 共有 120 条联系人。"));
  assert.ok(!assistantPromisesToolUse(""));
});

test("userRequestsContinuation 只匹配短的继续类消息", () => {
  assert.ok(userRequestsContinuation("继续"));
  assert.ok(userRequestsContinuation("还有吗"));
  assert.ok(userRequestsContinuation("more"));
  assert.ok(!userRequestsContinuation("帮我搜索运营商联系人"));
  // 超过 48 字的长消息即使包含「继续」也不算继续类指令。
  assert.ok(
    !userRequestsContinuation(
      "继续之前我想先确认一下这批线索的质量到底怎么样，麻烦把每一条线索的评分细则、数据来源和最近一次联系记录都完整列出来",
    ),
  );
});

test("parseInlineToolCalls 解析 [工具:xxx] 标记与 JSON 参数", () => {
  const [intro, calls] = parseInlineToolCalls('先搜索一下 [工具:list_contacts] {"q":"noc"}', registry);
  assert.equal(intro, "先搜索一下");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].function.name, "list_contacts");
  assert.deepEqual(JSON.parse(calls[0].function.arguments), { q: "noc" });
});

test("parseInlineToolCalls 对普通散文不产生调用", () => {
  const prose = "这批联系人质量不错，建议优先跟进。";
  const [intro, calls] = parseInlineToolCalls(prose, registry);
  assert.equal(intro, prose);
  assert.equal(calls.length, 0);
});

test("fallback：运营商类请求生成多路 list_contacts 查询", () => {
  const calls = fallbackPreparedCalls("还有其他运营商联系人吗", null, registry);
  assert.ok(calls.length >= 2);
  assert.ok(calls.every(([, name]) => name === "list_contacts"));
  const queries = calls.map(([, , args]) => args.q);
  assert.ok(queries.includes("ISP"));
});

test("fallback：abuse 请求只搜 abuse@", () => {
  const calls = fallbackPreparedCalls("找一下 abuse 邮箱", null, registry);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][2].q, "abuse@");
});

test("fallback：继续 + discover 历史 → 扩展挖掘", () => {
  const history = [
    { role: "user", content: "挖掘美国 ISP 线索" },
    { role: "tool", name: "discover_leads", content: "{}" },
  ];
  const calls = fallbackPreparedCalls("继续", history, registry);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1], "discover_leads");
  const args = calls[0][2];
  assert.ok(String(args.query).includes("挖掘美国 ISP 线索"));
  assert.ok(String(args.query).includes("扩展"));
});

test("fallback：继续但无历史 → 空（讲不清要继续什么）", () => {
  const calls = fallbackPreparedCalls("继续", [], registry);
  // 没有可推断的任务时退化为 list_contacts 全量扫描
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1], "list_contacts");
});

test("fallback 尊重 strict registry：registry 不含 discover_leads 时不强造调用", () => {
  const narrowRegistry = createToolRegistry(
    [{ type: "function", function: { name: "list_contacts", parameters: {} } }],
    {},
  );
  const history = [
    { role: "user", content: "挖掘美国 ISP 线索" },
    { role: "tool", name: "discover_leads", content: "{}" },
  ];
  const calls = fallbackPreparedCalls("继续", history, narrowRegistry);
  assert.ok(calls.every(([, name]) => name !== "discover_leads"));
});

test("无关请求不触发 fallback", () => {
  assert.equal(fallbackPreparedCalls("今天天气怎么样", null, registry).length, 0);
  assert.equal(fallbackPreparedCalls("", null, registry).length, 0);
});

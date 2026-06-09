import test from "node:test";
import assert from "node:assert/strict";

import {
  createToolRegistry,
  extractJsonArgs,
  extractToolCallsFromContent,
  inferToolName,
  normalizeToolName,
  prepareToolCalls,
} from "../dist/toolCalls.js";

const tools = [
  { type: "function", function: { name: "list_contacts", parameters: {} } },
  { type: "function", function: { name: "lookup_asns", parameters: {} } },
  { type: "function", function: { name: "import_leads", parameters: {} } },
  { type: "function", function: { name: "web_search", parameters: {} } },
];

const registry = createToolRegistry(tools, {
  search_contacts: "list_contacts",
  list_contact: "list_contacts",
});

test("别名映射 + keyword 参数纠偏为 q", () => {
  const prepared = prepareToolCalls(
    [{ function: { name: "functions.search_contacts", arguments: '{"keyword":"isp"}' } }],
    registry,
  );
  assert.equal(prepared.length, 1);
  assert.equal(prepared[0][1], "list_contacts");
  assert.deepEqual(prepared[0][2], { keyword: "isp", q: "isp" });
});

test("strict registry 拒绝未知工具名", () => {
  const prepared = prepareToolCalls(
    [{ function: { name: "not_a_real_tool", arguments: "{}" } }],
    registry,
  );
  assert.equal(prepared.length, 0);
});

test("按参数形状推断工具名时尊重 registry", () => {
  assert.equal(inferToolName("", { text: "AS15169" }, registry), "lookup_asns");
  assert.equal(inferToolName("", { rows: [] }, registry), "import_leads");
  assert.equal(inferToolName("", { queries: ["a"] }, registry), "web_search");
  // get_contact 不在 registry 内，形状推断也不放行。
  assert.equal(inferToolName("", { contact_id: 1 }, registry), "unknown");
});

test("normalizeToolName 剥离 provider 前缀与点路径", () => {
  assert.equal(normalizeToolName("functions.list_contacts", registry), "list_contacts");
  assert.equal(normalizeToolName("Tools.List_Contacts", registry), "list_contacts");
  assert.equal(normalizeToolName("ns.api.search_contacts", registry), "search_contacts");
  assert.equal(normalizeToolName("  WEB_SEARCH ", registry), "web_search");
});

test("正文内联 JSON 数组提取为工具调用", () => {
  const calls = extractToolCallsFromContent(
    '先查一下 [{"name":"list_contacts","arguments":{"q":"noc"}}]',
    registry,
  );
  const prepared = prepareToolCalls(calls, registry);
  assert.equal(prepared.length, 1);
  assert.equal(prepared[0][1], "list_contacts");
  assert.deepEqual(prepared[0][2], { q: "noc" });
});

test("正文内联多个调用全部提取", () => {
  const calls = extractToolCallsFromContent(
    '[{"name":"list_contacts","arguments":{"q":"a"}},{"name":"lookup_asns","arguments":{"text":"AS1"}}]',
    registry,
  );
  const prepared = prepareToolCalls(calls, registry);
  assert.deepEqual(
    prepared.map(([, name]) => name),
    ["list_contacts", "lookup_asns"],
  );
});

test("仅有 JSON 参数时按形状推断（registry 内才放行）", () => {
  const calls = extractToolCallsFromContent('{"text":"AS15169 AS3356"}', registry);
  const prepared = prepareToolCalls(calls, registry);
  assert.equal(prepared.length, 1);
  assert.equal(prepared[0][1], "lookup_asns");
});

test("extractJsonArgs：剥离特殊 token 噪声并取最长合法 JSON", () => {
  assert.deepEqual(extractJsonArgs('<|tool_call|>{"q":"isp"}<|end|>'), { q: "isp" });
  assert.deepEqual(extractJsonArgs('前缀 {"a":{"b":1}} 尾巴'), { a: { b: 1 } });
  assert.deepEqual(extractJsonArgs("没有 JSON"), {});
  assert.deepEqual(extractJsonArgs("{broken"), {});
});

test("嵌套 arguments 字符串（name 藏在 arguments 里）可恢复", () => {
  const prepared = prepareToolCalls(
    [
      {
        function: {
          name: "",
          arguments: '{"name":"list_contacts","arguments":{"q":"isp"}}',
        },
      },
    ],
    registry,
  );
  assert.equal(prepared.length, 1);
  assert.equal(prepared[0][1], "list_contacts");
  assert.deepEqual(prepared[0][2], { q: "isp" });
});

test("缺失 id 的调用自动生成 call_ 前缀 id，并补 type", () => {
  const prepared = prepareToolCalls(
    [{ function: { name: "list_contacts", arguments: '{"q":"x"}' } }],
    registry,
  );
  const [toolCall] = prepared[0];
  assert.ok(String(toolCall.id).startsWith("call_"));
  assert.equal(toolCall.type, "function");
  assert.equal(JSON.parse(toolCall.function.arguments).q, "x");
});

test("arguments 为对象（非字符串）时同样可用", () => {
  const prepared = prepareToolCalls(
    [{ function: { name: "list_contacts", arguments: { q: "直接对象" } } }],
    registry,
  );
  assert.deepEqual(prepared[0][2], { q: "直接对象" });
});

test("坏 JSON arguments 容错为空参数而不是崩溃", () => {
  const prepared = prepareToolCalls(
    [{ function: { name: "list_contacts", arguments: '{"q": broken' } }],
    registry,
  );
  assert.equal(prepared.length, 1);
  assert.deepEqual(prepared[0][2], {});
});

test("keywords 数组合并为 q 字符串", () => {
  const prepared = prepareToolCalls(
    [{ function: { name: "list_contacts", arguments: '{"keywords":["isp","noc"]}' } }],
    registry,
  );
  assert.equal(prepared[0][2].q, "isp noc");
});

test("非对象条目被跳过", () => {
  const prepared = prepareToolCalls([null, "x", 42, { function: { name: "list_contacts", arguments: "{}" } }], registry);
  assert.equal(prepared.length, 1);
});

test("无 registry 的旧路径保持宽松", () => {
  const prepared = prepareToolCalls([
    { function: { name: "not_a_real_tool", arguments: "{}" } },
  ]);
  assert.equal(prepared.length, 1);
  assert.equal(prepared[0][1], "not_a_real_tool");
});

test("createToolRegistry 清洗大小写与空白，丢弃空别名", () => {
  const reg = createToolRegistry(
    [{ type: "function", function: { name: "  List_Contacts " } }],
    { " Find_Contacts ": "LIST_CONTACTS", bad: "  " },
  );
  assert.ok(reg.knownToolNames.has("list_contacts"));
  assert.equal(reg.aliases["find_contacts"], "list_contacts");
  assert.ok(!("bad" in reg.aliases));
  assert.equal(reg.allowUnknownToolNames, false);
});

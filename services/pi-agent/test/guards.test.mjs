import test from "node:test";
import assert from "node:assert/strict";

import { isContextOverflowError } from "../dist/llmErrors.js";
import { PARALLEL_SAFE_TOOLS, canParallelizeToolBatch } from "../dist/parallelTools.js";

test("isContextOverflowError 识别中英文溢出报错", () => {
  const positives = [
    "This model's maximum context length is 65536 tokens",
    "LLM 请求失败 (400): context_length_exceeded",
    "Prompt is too long, please reduce the length",
    "请求被拒绝：上下文过长",
    "token 超限，请压缩后重试",
  ];
  for (const message of positives) {
    assert.ok(isContextOverflowError(message), `应识别: ${message}`);
  }
});

test("isContextOverflowError 不误判普通错误", () => {
  const negatives = ["", null, undefined, "LLM 请求失败 (401): invalid api key", "网络超时"];
  for (const message of negatives) {
    assert.ok(!isContextOverflowError(message), `不应识别: ${message}`);
  }
});

test("canParallelizeToolBatch：全只读工具且 ≥2 个才并行", () => {
  assert.ok(canParallelizeToolBatch(["list_contacts", "get_stats"]));
  assert.ok(!canParallelizeToolBatch(["list_contacts"]), "单个工具无需并行");
  assert.ok(!canParallelizeToolBatch(["list_contacts", "delete_contacts"]), "写操作禁止并行");
  assert.ok(!canParallelizeToolBatch([]));
});

test("PARALLEL_SAFE_TOOLS 不包含任何写操作工具", () => {
  const writeTools = [
    "delete_contacts",
    "import_leads",
    "add_contact_note",
    "mark_contact_sent",
    "enrich_contact",
    "discover_leads",
    "web_search",
    "queue_emails",
    "import_lead_reviews",
  ];
  for (const name of writeTools) {
    assert.ok(!PARALLEL_SAFE_TOOLS.has(name), `${name} 不应标记为并行安全`);
  }
});

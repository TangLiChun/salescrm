/**
 * Sales CRM — Pi Coding Agent extension
 *
 * Env:
 *   SALESCRM_URL   default http://127.0.0.1:8000
 *   SALESCRM_TOKEN required — from CRM 系统设置 → 自动化 → Pi Agent API
 */

import { Type } from "@mariozechner/pi-ai";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

type JsonValue = Record<string, unknown> | unknown[] | string | number | boolean | null;

function baseUrl(): string {
  return (process.env.SALESCRM_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function token(): string {
  return (process.env.SALESCRM_TOKEN || "").trim();
}

async function salescrmRequest(
  path: string,
  options: { method?: string; body?: JsonValue } = {},
): Promise<{ status: number; data: unknown; text: string }> {
  const auth = token();
  if (!auth) {
    throw new Error("SALESCRM_TOKEN 未设置。在 CRM 系统设置 → 自动化 → Pi Agent API 生成 Token。");
  }

  const res = await fetch(`${baseUrl()}${path}`, {
    method: options.method || "GET",
    headers: {
      Authorization: `Bearer ${auth}`,
      "Content-Type": "application/json",
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const text = await res.text();
  let data: unknown = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    const detail =
      typeof data === "object" && data && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : text.slice(0, 400);
    throw new Error(`Sales CRM ${res.status}: ${detail}`);
  }

  return { status: res.status, data, text };
}

function textResult(payload: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (_event, ctx) => {
    if (!token()) {
      ctx.ui.notify(
        "Sales CRM: 请设置 SALESCRM_TOKEN（CRM → 系统设置 → 自动化 → Pi Agent API）",
        "warn",
      );
      return;
    }
    try {
      const { data } = await salescrmRequest("/api/agent/health");
      const user = typeof data === "object" && data && "user" in data ? (data as { user: string }).user : "";
      ctx.ui.notify(`Sales CRM 已连接${user ? ` (${user})` : ""}`, "info");
    } catch (error) {
      ctx.ui.notify(`Sales CRM 连接失败: ${error instanceof Error ? error.message : String(error)}`, "error");
    }
  });

  pi.registerTool({
    name: "salescrm_health",
    label: "Sales CRM Health",
    description: "Check Sales CRM agent API connectivity and database schema",
    parameters: Type.Object({}),
    async execute() {
      const { data } = await salescrmRequest("/api/agent/health");
      return textResult(data);
    },
  });

  pi.registerTool({
    name: "salescrm_list_contacts",
    label: "Sales CRM List Contacts",
    description: "Search contacts in Sales CRM to avoid duplicates before import",
    parameters: Type.Object({
      q: Type.Optional(Type.String({ description: "Search org/name/email/notes" })),
      limit: Type.Optional(Type.Number({ minimum: 1, maximum: 500, description: "Max rows (default 50)" })),
    }),
    async execute(_id, params) {
      const { q, limit } = params as { q?: string; limit?: number };
      const query = new URLSearchParams();
      if (q) query.set("q", q);
      if (limit) query.set("limit", String(limit));
      const suffix = query.toString() ? `?${query.toString()}` : "";
      const { data } = await salescrmRequest(`/api/agent/contacts${suffix}`);
      return textResult(data);
    },
  });

  pi.registerTool({
    name: "salescrm_import_leads",
    label: "Sales CRM Import Leads",
    description: "Import lead rows into Sales CRM (email required). Use source pi-agent by default.",
    parameters: Type.Object({
      rows: Type.Array(
        Type.Object({
          email: Type.String({ description: "Contact email (required)" }),
          org: Type.Optional(Type.String()),
          name: Type.Optional(Type.String()),
          asn: Type.Optional(Type.Number()),
          roles: Type.Optional(Type.Union([Type.String(), Type.Array(Type.String())])),
          notes: Type.Optional(Type.String()),
          handle: Type.Optional(Type.String()),
          rir: Type.Optional(Type.String()),
          source: Type.Optional(Type.String()),
        }),
        { minItems: 1 },
      ),
      source: Type.Optional(Type.String({ description: "Default source tag (pi-agent)" })),
    }),
    async execute(_id, params) {
      const { rows, source } = params as { rows: JsonValue[]; source?: string };
      const { data } = await salescrmRequest("/api/agent/leads/import", {
        method: "POST",
        body: { rows, source: source || "pi-agent" },
      });
      return textResult(data);
    },
  });

  pi.registerTool({
    name: "salescrm_discover_leads",
    label: "Sales CRM AI Discover",
    description: "Run built-in Sales CRM AI lead discovery (requires LLM configured in CRM settings)",
    parameters: Type.Object({
      query: Type.String({ description: "Natural language lead search request" }),
      min_score: Type.Optional(Type.Number({ minimum: 0, maximum: 100 })),
      auto_import: Type.Optional(Type.Boolean({ description: "Import high-score leads automatically" })),
    }),
    async execute(_id, params) {
      const { query, min_score, auto_import } = params as {
        query: string;
        min_score?: number;
        auto_import?: boolean;
      };
      const { data } = await salescrmRequest("/api/agent/leads/discover", {
        method: "POST",
        body: { query, min_score: min_score ?? 60, auto_import: Boolean(auto_import) },
      });
      return textResult(data);
    },
  });
}

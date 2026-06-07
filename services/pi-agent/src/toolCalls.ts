import { randomUUID } from "node:crypto";

export const KNOWN_TOOL_NAMES = new Set([
  "list_contacts",
  "import_leads",
  "get_contact",
  "get_stats",
  "update_contact",
  "mark_contact_sent",
  "delete_contacts",
  "add_contact_note",
  "list_contact_notes",
  "get_lead_preferences",
  "reset_lead_preferences",
  "dedupe_contacts",
  "get_import_filters",
  "update_import_filters",
  "list_schedules",
  "create_schedule",
  "update_schedule",
  "get_search_config",
  "shodan_search",
  "web_search",
  "fetch_web_pages",
  "search_hosting_forums",
  "lookup_asns",
  "discover_leads",
  "enrich_contact",
  "collect_linkedin_profiles",
  "collect_x_profiles",
  "collect_facebook_profiles",
]);

const TOOL_NAME_ALIASES: Record<string, string> = {
  search_contacts: "list_contacts",
  list_contact: "list_contacts",
  find_contacts: "list_contacts",
  delete_contact: "delete_contacts",
  remove_contacts: "delete_contacts",
  bulk_delete_contacts: "delete_contacts",
};

export function normalizeToolName(name: string): string {
  let cleaned = (name || "").trim().toLowerCase();
  for (const prefix of ["functions.", "function.", "tool.", "tools."]) {
    if (cleaned.startsWith(prefix)) cleaned = cleaned.slice(prefix.length);
  }
  if (cleaned.includes(".") && !KNOWN_TOOL_NAMES.has(cleaned)) {
    const tail = cleaned.split(".").pop() || cleaned;
    if (KNOWN_TOOL_NAMES.has(tail) || tail in TOOL_NAME_ALIASES) cleaned = tail;
  }
  return cleaned;
}

export function inferToolName(name: string, args: Record<string, unknown>): string {
  const cleaned = normalizeToolName(name);
  if (KNOWN_TOOL_NAMES.has(cleaned)) return cleaned;
  if (cleaned in TOOL_NAME_ALIASES) return TOOL_NAME_ALIASES[cleaned]!;
  if ("contact_ids" in args || "ids" in args) return "delete_contacts";
  if ("queries" in args || ("query" in args && !("q" in args) && "max_results" in args)) {
    return "web_search";
  }
  if ("text" in args || "asns" in args) return "lookup_asns";
  if ("contact_id" in args && ("auto_import" in args || "min_score" in args)) {
    return "enrich_contact";
  }
  if ("contact_id" in args && "note" in args) return "add_contact_note";
  if ("contact_id" in args && "sent" in args) return "mark_contact_sent";
  if ("contact_id" in args && !args.q) return "get_contact";
  if ("rows" in args) return "import_leads";
  if ("keywords" in args || "keyword" in args) return "list_contacts";
  if ("q" in args || ("limit" in args && !("query" in args) && !("queries" in args))) {
    return "list_contacts";
  }
  return cleaned || "unknown";
}

function coerceListContactsArgs(args: Record<string, unknown>): Record<string, unknown> {
  if ("q" in args) return args;
  for (const key of ["keywords", "keyword", "search", "query", "term", "filter"]) {
    if (!(key in args)) continue;
    const val = args[key];
    args.q = Array.isArray(val) ? val.filter(Boolean).join(" ") : String(val);
    break;
  }
  return args;
}

function normalizeRawToolEntry(item: Record<string, unknown>): Record<string, unknown> {
  let fn = item.function;
  if (typeof fn === "string") {
    try {
      fn = JSON.parse(fn) as Record<string, unknown>;
    } catch {
      fn = {};
    }
  }
  if (fn && typeof fn === "object" && (fn as Record<string, unknown>).name) {
    const fnObj = fn as Record<string, unknown>;
    const args = fnObj.arguments;
    const argsStr =
      typeof args === "object" && args !== null
        ? JSON.stringify(args)
        : String(args ?? "{}");
    return {
      id: String(item.id || `inline-${randomUUID().slice(0, 8)}`),
      type: "function",
      function: { name: String(fnObj.name), arguments: argsStr },
    };
  }
  const name = String(item.name || "").trim();
  const rawArgs = item.arguments;
  let argsStr = "{}";
  if (typeof rawArgs === "object" && rawArgs !== null) {
    argsStr = JSON.stringify(rawArgs);
  } else if (rawArgs != null) {
    argsStr = String(rawArgs);
  }
  return {
    id: String(item.id || `inline-${randomUUID().slice(0, 8)}`),
    type: "function",
    function: { name, arguments: argsStr },
  };
}

export function extractJsonArgs(text: string): Record<string, unknown> {
  const start = text.indexOf("{");
  if (start < 0) return {};
  let blob = text.slice(start);
  blob = blob.replace(/<\|[^|>]*\|>/gi, "");
  blob = blob.replace(/<\s*\/?\s*\|\s*\|[^>]*>/gi, "");
  blob = blob.trim();
  for (let end = blob.length; end > 0; end -= 1) {
    if (blob[end - 1] !== "}") continue;
    try {
      const parsed = JSON.parse(blob.slice(0, end));
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
    } catch {
      /* continue */
    }
  }
  return {};
}

export function extractToolCallsFromContent(text: string): Record<string, unknown>[] {
  const trimmed = (text || "").trim();
  if (!trimmed) return [];

  const start = trimmed.indexOf("[");
  if (start >= 0) {
    const blob = trimmed.slice(start);
    for (let end = blob.length; end > 0; end -= 1) {
      if (blob[end - 1] !== "}" && blob[end - 1] !== "]") continue;
      try {
        const parsed = JSON.parse(blob.slice(0, end));
        if (Array.isArray(parsed)) {
          const calls = parsed.filter((item) => item && typeof item === "object");
          if (calls.length) return calls.map((item) => normalizeRawToolEntry(item));
        }
      } catch {
        /* continue */
      }
    }
  }

  const args = extractJsonArgs(trimmed);
  if (Object.keys(args).length) {
    const name = inferToolName("", args);
    if (name !== "unknown") return [normalizeRawToolEntry({ name, arguments: args })];
  }

  const nameMatch = trimmed.match(/"name"\s*:\s*"([a-zA-Z0-9_]+)"/);
  if (nameMatch) {
    return [normalizeRawToolEntry({ name: nameMatch[1], arguments: extractJsonArgs(trimmed) })];
  }
  return [];
}

function parseToolCall(toolCall: Record<string, unknown>): [string, Record<string, unknown>] | null {
  let fn = toolCall.function;
  if (typeof fn === "string") {
    try {
      fn = JSON.parse(fn);
    } catch {
      fn = {};
    }
  }
  if (!fn || typeof fn !== "object") fn = {};
  const fnObj = fn as Record<string, unknown>;

  let name = String(fnObj.name || toolCall.name || "").trim();
  let rawArgs = fnObj.arguments ?? toolCall.arguments ?? "{}";
  let args: Record<string, unknown>;
  if (typeof rawArgs === "object" && rawArgs !== null) {
    args = rawArgs as Record<string, unknown>;
  } else {
    try {
      args = rawArgs ? JSON.parse(String(rawArgs)) : {};
    } catch {
      args = {};
    }
  }
  if (!args || typeof args !== "object") args = {};

  if ((!name || name === "unknown") && typeof rawArgs === "string" && rawArgs.trim()) {
    const nameMatch = rawArgs.match(/"name"\s*:\s*"([a-zA-Z0-9_]+)"/);
    if (nameMatch) name = nameMatch[1]!;
    try {
      const nested = JSON.parse(rawArgs);
      if (nested && typeof nested === "object") {
        if (nested.name) name = String(nested.name);
        if (typeof nested.arguments === "object" && nested.arguments) {
          args = nested.arguments;
        } else if (typeof nested.arguments === "string") {
          try {
            const parsedArgs = JSON.parse(nested.arguments);
            if (parsedArgs && typeof parsedArgs === "object") args = parsedArgs;
          } catch {
            /* ignore */
          }
        } else if (!("name" in nested)) {
          args = nested;
        }
      }
    } catch {
      /* ignore */
    }
  }

  name = inferToolName(name, args);
  if (name === "list_contacts") coerceListContactsArgs(args);
  if (name === "unknown") return null;
  return [name, args];
}

function ensureToolCallId(toolCall: Record<string, unknown>): string {
  let toolId = String(toolCall.id || "").trim();
  if (!toolId) {
    toolId = `call_${randomUUID().replace(/-/g, "").slice(0, 12)}`;
    toolCall.id = toolId;
  }
  return toolId;
}

export function prepareToolCalls(
  toolCalls: unknown[],
): Array<[Record<string, unknown>, string, Record<string, unknown>]> {
  const prepared: Array<[Record<string, unknown>, string, Record<string, unknown>]> = [];
  for (const raw of toolCalls) {
    if (!raw || typeof raw !== "object") continue;
    const parsed = parseToolCall(raw as Record<string, unknown>);
    if (!parsed) continue;
    const [name, args] = parsed;
    const toolCall = { ...(raw as Record<string, unknown>) };
    ensureToolCallId(toolCall);
    toolCall.function = { name, arguments: JSON.stringify(args) };
    toolCall.type = toolCall.type || "function";
    prepared.push([toolCall, name, args]);
  }
  return prepared;
}

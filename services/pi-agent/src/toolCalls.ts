import { randomUUID } from "node:crypto";

export type ToolRegistry = {
  knownToolNames: ReadonlySet<string>;
  aliases: Readonly<Record<string, string>>;
  allowUnknownToolNames: boolean;
};

const EMPTY_TOOL_REGISTRY: ToolRegistry = {
  knownToolNames: new Set<string>(),
  aliases: {},
  allowUnknownToolNames: true,
};

export function createToolRegistry(
  tools: Record<string, unknown>[] | null | undefined,
  aliases: Record<string, string> | null | undefined = {},
): ToolRegistry {
  const names = new Set<string>();
  for (const tool of tools || []) {
    const fn = tool.function;
    if (!fn || typeof fn !== "object") continue;
    const name = String((fn as Record<string, unknown>).name || "").trim().toLowerCase();
    if (name) names.add(name);
  }
  const cleanedAliases: Record<string, string> = {};
  for (const [from, to] of Object.entries(aliases || {})) {
    const source = from.trim().toLowerCase();
    const target = to.trim().toLowerCase();
    if (!source || !target) continue;
    cleanedAliases[source] = target;
  }
  return {
    knownToolNames: names,
    aliases: cleanedAliases,
    allowUnknownToolNames: false,
  };
}

function registryOrDefault(registry?: ToolRegistry): ToolRegistry {
  return registry || EMPTY_TOOL_REGISTRY;
}

function isKnownToolName(name: string, registry?: ToolRegistry): boolean {
  const active = registryOrDefault(registry);
  return active.allowUnknownToolNames || active.knownToolNames.has(name);
}

function aliasTarget(name: string, registry?: ToolRegistry): string | null {
  const aliases = registryOrDefault(registry).aliases;
  const target = aliases[name];
  if (!target) return null;
  return isKnownToolName(target, registry) ? target : null;
}

export function normalizeToolName(name: string, registry?: ToolRegistry): string {
  let cleaned = (name || "").trim().toLowerCase();
  for (const prefix of ["functions.", "function.", "tool.", "tools."]) {
    if (cleaned.startsWith(prefix)) cleaned = cleaned.slice(prefix.length);
  }
  if (cleaned.includes(".") && !isKnownToolName(cleaned, registry)) {
    const tail = cleaned.split(".").pop() || cleaned;
    if (isKnownToolName(tail, registry) || aliasTarget(tail, registry)) cleaned = tail;
  }
  return cleaned;
}

function inferKnownToolName(candidate: string, registry?: ToolRegistry): string {
  return isKnownToolName(candidate, registry) ? candidate : "unknown";
}

export function inferToolName(
  name: string,
  args: Record<string, unknown>,
  registry?: ToolRegistry,
): string {
  const cleaned = normalizeToolName(name, registry);
  const alias = aliasTarget(cleaned, registry);
  if (alias) return alias;
  if (isKnownToolName(cleaned, registry) && cleaned) return cleaned;
  if ("contact_ids" in args || "ids" in args) return inferKnownToolName("delete_contacts", registry);
  if ("queries" in args || ("query" in args && !("q" in args) && "max_results" in args)) {
    return inferKnownToolName("web_search", registry);
  }
  if ("text" in args || "asns" in args) return inferKnownToolName("lookup_asns", registry);
  if ("contact_id" in args && ("auto_import" in args || "min_score" in args)) {
    return inferKnownToolName("enrich_contact", registry);
  }
  if ("contact_id" in args && "note" in args) return inferKnownToolName("add_contact_note", registry);
  if ("contact_id" in args && "sent" in args) return inferKnownToolName("mark_contact_sent", registry);
  if ("contact_id" in args && !args.q) return inferKnownToolName("get_contact", registry);
  if ("rows" in args) return inferKnownToolName("import_leads", registry);
  if ("keywords" in args || "keyword" in args) return inferKnownToolName("list_contacts", registry);
  if ("q" in args || ("limit" in args && !("query" in args) && !("queries" in args))) {
    return inferKnownToolName("list_contacts", registry);
  }
  if (!cleaned) return "unknown";
  return inferKnownToolName(cleaned, registry);
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

export function extractToolCallsFromContent(
  text: string,
  registry?: ToolRegistry,
): Record<string, unknown>[] {
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
    const name = inferToolName("", args, registry);
    if (name !== "unknown") return [normalizeRawToolEntry({ name, arguments: args })];
  }

  const nameMatch = trimmed.match(/"name"\s*:\s*"([a-zA-Z0-9_]+)"/);
  if (nameMatch) {
    return [normalizeRawToolEntry({ name: nameMatch[1], arguments: extractJsonArgs(trimmed) })];
  }
  return [];
}

function parseToolCall(
  toolCall: Record<string, unknown>,
  registry?: ToolRegistry,
): [string, Record<string, unknown>] | null {
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

  name = inferToolName(name, args, registry);
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
  registry?: ToolRegistry,
): Array<[Record<string, unknown>, string, Record<string, unknown>]> {
  const prepared: Array<[Record<string, unknown>, string, Record<string, unknown>]> = [];
  for (const raw of toolCalls) {
    if (!raw || typeof raw !== "object") continue;
    const parsed = parseToolCall(raw as Record<string, unknown>, registry);
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

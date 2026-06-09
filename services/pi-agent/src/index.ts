import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { agentChatStream } from "./agentLoop.js";
import { PythonClient } from "./pythonClient.js";

const app = new Hono();

// Mirrors app/internal_secret.py: placeholder or short secrets are treated as
// "not configured" so the service refuses all requests instead of accepting a
// guessable header value.
const WEAK_INTERNAL_SECRETS = new Set([
  "change-me-in-production",
  "change-me",
  "changeme",
  "dev-secret",
  "secret",
  "password",
  "internal-secret",
  "pi-internal-secret",
  "salescrm",
  "123456",
  "test",
]);
const MIN_INTERNAL_SECRET_LENGTH = 16;

function internalSecret(): string {
  const value = (process.env.PI_INTERNAL_SECRET || "").trim();
  if (!value) return "";
  if (WEAK_INTERNAL_SECRETS.has(value.toLowerCase())) return "";
  if (value.length < MIN_INTERNAL_SECRET_LENGTH) return "";
  return value;
}

function crmBaseUrl(): string {
  return (process.env.CRM_INTERNAL_URL || "http://salescrm:8000").replace(/\/$/, "");
}

function verifySecret(header: string | undefined): boolean {
  const secret = internalSecret();
  return Boolean(secret && header === secret);
}

app.get("/health", (c) => c.json({ ok: true, service: "pi-agent" }));

app.post("/stream", async (c) => {
  if (!verifySecret(c.req.header("X-Internal-Secret"))) {
    return c.json({ detail: "Forbidden" }, 403);
  }

  let body: {
    user_id: number;
    message: string;
    thread_id?: string | null;
    history?: Record<string, unknown>[] | null;
    cancel_token?: string;
  };
  try {
    body = await c.req.json();
  } catch {
    return c.json({ detail: "Invalid JSON body" }, 400);
  }
  if (!Number.isFinite(Number(body.user_id)) || typeof body.message !== "string" || !body.message.trim()) {
    return c.json({ detail: "user_id and message are required" }, 400);
  }

  // When the Python proxy drops the connection (user pressed stop or the
  // browser went away), stop calling the LLM and tools instead of finishing
  // the turn into the void.
  let clientGone = false;
  c.req.raw.signal?.addEventListener("abort", () => {
    clientGone = true;
  });

  const python = new PythonClient(crmBaseUrl(), internalSecret());
  let llmConfig;
  try {
    llmConfig = await python.getLlmConfig();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return c.json({ detail: message }, 503);
  }

  return streamSSE(c, async (stream) => {
    try {
      for await (const event of agentChatStream({
        userId: body.user_id,
        message: body.message,
        threadId: body.thread_id,
        history: body.history,
        python,
        llmConfig,
        cancelCheck: () => clientGone,
      })) {
        await stream.writeSSE({ data: JSON.stringify(event) });
        if (event.type === "done") break;
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await stream.writeSSE({
        data: JSON.stringify({ type: "error", message: `Pi 助手执行失败：${message.slice(0, 500)}` }),
      });
      await stream.writeSSE({ data: JSON.stringify({ type: "done" }) });
    }
  });
});

const port = Number(process.env.PORT || 8001);
serve({ fetch: app.fetch, port }, () => {
  console.log(`pi-agent listening on :${port}`);
});

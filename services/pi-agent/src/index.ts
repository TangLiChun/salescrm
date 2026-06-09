import { serve } from "@hono/node-server";
import { Hono } from "hono";
import { streamSSE } from "hono/streaming";
import { agentChatStream } from "./agentLoop.js";
import { PythonClient } from "./pythonClient.js";

const app = new Hono();

function internalSecret(): string {
  return (process.env.PI_INTERNAL_SECRET || "").trim();
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

  const body = await c.req.json<{
    user_id: number;
    message: string;
    thread_id?: string | null;
    history?: Record<string, unknown>[] | null;
    cancel_token?: string;
  }>();

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
        cancelCheck: () => false,
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

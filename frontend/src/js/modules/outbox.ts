import { t } from "../../i18n.js";
import { showApiSuccess } from "../core/api-feedback.js";
import { state } from "../core/state.js";
import { api, escapeHtml } from "../core/utils.js";

const STATUS_TONE: Record<string, string> = {
  queued: "caution",
  sending: "caution",
  sent: "positive",
  failed: "danger",
  cancelled: "danger",
};

let senderEnabled = true;

function capitalize(value: string) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

export async function loadOutbox() {
  const filter = document.getElementById("outbox-status-filter");
  const status = (filter?.value || "").trim();
  const data = await api(`/api/email/outbox${status ? `?status=${encodeURIComponent(status)}` : ""}`);
  renderOutbox(data.items || []);
}

export function renderOutbox(items) {
  const body = document.getElementById("outbox-body");
  const counts = document.getElementById("outbox-counts");
  if (!body) return;

  const tally: Record<string, number> = {};
  for (const item of items) tally[item.status] = (tally[item.status] || 0) + 1;
  if (counts) {
    counts.textContent = t("email.outboxCounts", {
      queued: tally.queued || 0,
      sent: tally.sent || 0,
      failed: tally.failed || 0,
    });
  }

  if (!items.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="5">${escapeHtml(t("email.outboxEmpty"))}</td></tr>`;
    return;
  }

  body.innerHTML = items
    .map((item) => {
      const tone = STATUS_TONE[item.status] || "neutral";
      const canCancel = item.status === "queued" || item.status === "sending";
      const canRetry = item.status === "failed" || item.status === "cancelled";
      const actions = [
        canCancel
          ? `<button type="button" class="link-btn" data-outbox-action="cancel" data-id="${item.id}">${escapeHtml(t("email.cancel"))}</button>`
          : "",
        canRetry
          ? `<button type="button" class="link-btn" data-outbox-action="retry" data-id="${item.id}">${escapeHtml(t("email.retry"))}</button>`
          : "",
      ]
        .filter(Boolean)
        .join(" ");
      const title = item.last_error ? ` title="${escapeHtml(item.last_error)}"` : "";
      return `<tr>
        <td>${escapeHtml(item.to_email || "")}</td>
        <td>${escapeHtml(item.subject || "")}</td>
        <td><span class="outbox-status outbox-status-${tone}"${title}>${escapeHtml(t(`email.status${capitalize(item.status)}`))}</span></td>
        <td>${item.attempts || 0}</td>
        <td>${actions || "—"}</td>
      </tr>`;
    })
    .join("");
}

function updateSenderToggleLabel() {
  const btn = document.getElementById("outbox-sender-toggle");
  if (btn) btn.textContent = t(senderEnabled ? "email.pause" : "email.resume");
}

export async function refreshSenderState() {
  try {
    const data = await api("/api/settings");
    senderEnabled = (data.email_sender_enabled || "0") === "1";
  } catch {
    // best-effort: leave the previous label
  }
  updateSenderToggleLabel();
}

export async function toggleSender() {
  const data = await api("/api/email/sender/toggle", {
    method: "POST",
    body: JSON.stringify({ enabled: !senderEnabled }),
  });
  senderEnabled = Boolean(data.enabled);
  updateSenderToggleLabel();
  showApiSuccess(t(senderEnabled ? "email.resumed" : "email.paused"));
}

export async function outboxAction(action, emailId) {
  await api(`/api/email/outbox/${emailId}/${action}`, { method: "POST" });
  await loadOutbox();
}

export function startOutboxAutoRefresh() {
  stopOutboxAutoRefresh();
  state.outboxRefreshTimer = window.setInterval(() => {
    loadOutbox().catch(() => {});
  }, 15000);
}

export function stopOutboxAutoRefresh() {
  if (state.outboxRefreshTimer) {
    window.clearInterval(state.outboxRefreshTimer);
    state.outboxRefreshTimer = null;
  }
}

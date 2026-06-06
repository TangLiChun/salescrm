import { t, followUpLabel } from "../../i18n.js";
import * as dom from "../core/dom.js";
import { api, escapeHtml } from "../core/utils.js";

const {
  dashboardStatsEl,
  statsSummaryEl,
  chartFollowUpEl,
  chartSentEl,
  chartSourceEl,
  chartRecentEl,
} = dom;

export function renderBarChart(container: HTMLElement, items: AnyRecord[], { getLabel = (k: any) => k, colors }: AnyRecord = {}) {
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = `<p class="stats">${t("msg.noData")}</p>`;
    return;
  }
  const max = Math.max(...items.map((item) => item.count), 1);
  items.forEach((item, index) => {
    const pct = Math.round((item.count / max) * 100);
    const fillColor = colors?.[index] ? `background:${colors[index]};` : "";
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `
      <label title="${escapeHtml(getLabel(item.key))}">${escapeHtml(getLabel(item.key))}</label>
      <div class="bar-track"><div class="bar-fill" style="${fillColor}width:${pct}%"></div></div>
      <em>${item.count}</em>
    `;
    container.appendChild(row);
  });
}

export function renderDashboard(data: AnyRecord) {
  dashboardStatsEl.textContent = t("msg.dashboardStats", {
    total: data.total,
    sent: data.sent,
    unsent: data.unsent,
  });
  statsSummaryEl.innerHTML = `
    <div class="stat-card"><strong>${data.total}</strong><span>${t("stats.totalContacts")}</span></div>
    <div class="stat-card"><strong>${data.sent}</strong><span>${t("stats.sentEmails")}</span></div>
    <div class="stat-card"><strong>${data.unsent}</strong><span>${t("stats.unsentEmails")}</span></div>
    <div class="stat-card"><strong>${data.by_follow_up_status.interested || 0}</strong><span>${t("followUp.interested")}</span></div>
  `;
  renderBarChart(
    chartFollowUpEl,
    Object.entries(data.by_follow_up_status || {}).map(([key, count]) => ({ key, count })),
    { getLabel: (key) => followUpLabel(key) },
  );
  renderBarChart(
    chartSentEl,
    [
      { key: "sent", count: data.sent },
      { key: "unsent", count: data.unsent },
    ],
    { getLabel: (key) => (key === "sent" ? t("stats.sentShort") : t("stats.unsentShort")), colors: ["var(--chart-pos)", "var(--chart-neutral)"] },
  );
  renderBarChart(
    chartSourceEl,
    Object.entries(data.by_source || {})
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => Number(b.count) - Number(a.count)),
  );
  renderBarChart(
    chartRecentEl,
    (data.recent_imports || []).map((row) => ({ key: row.date, count: row.count })),
  );
}

export async function loadStats() {
  dashboardStatsEl.textContent = t("common.loading");
  renderDashboard(await api("/api/stats"));
}

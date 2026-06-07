import { t, followUpLabel } from "../../i18n.js";
import * as dom from "../core/dom.js";
import { api, escapeHtml } from "../core/utils.js";
const { dashboardStatsEl, statsSummaryEl, chartFollowUpEl, chartSentEl, chartSourceEl, chartRecentEl, } = dom;
function statCard(value, label, action = {}) {
    const attrs = ['data-goto-view="contacts"'];
    if (action.contactStatus)
        attrs.push(`data-contact-status="${escapeHtml(action.contactStatus)}"`);
    if (action.contactFollowUp)
        attrs.push(`data-contact-follow-up="${escapeHtml(action.contactFollowUp)}"`);
    return `
    <button type="button" class="stat-card stat-card-action" ${attrs.join(" ")}>
      <strong>${escapeHtml(String(value ?? 0))}</strong>
      <span>${escapeHtml(label)}</span>
    </button>`;
}
export function renderBarChart(container, items, { getLabel = (k) => k, colors } = {}) {
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
export function renderDashboard(data) {
    dashboardStatsEl.textContent = t("msg.dashboardStats", {
        total: data.total,
        sent: data.sent,
        unsent: data.unsent,
    });
    statsSummaryEl.innerHTML = [
        statCard(data.total, t("stats.totalContacts")),
        statCard(data.sent, t("stats.sentEmails"), { contactStatus: "sent" }),
        statCard(data.unsent, t("stats.unsentEmails"), { contactStatus: "unsent" }),
        statCard(data.by_follow_up_status?.interested || 0, t("followUp.interested"), { contactFollowUp: "interested" }),
    ].join("");
    renderBarChart(chartFollowUpEl, Object.entries(data.by_follow_up_status || {}).map(([key, count]) => ({ key, count })), { getLabel: (key) => followUpLabel(key) });
    renderBarChart(chartSentEl, [
        { key: "sent", count: data.sent },
        { key: "unsent", count: data.unsent },
    ], { getLabel: (key) => (key === "sent" ? t("stats.sentShort") : t("stats.unsentShort")), colors: ["var(--chart-pos)", "var(--chart-neutral)"] });
    renderBarChart(chartSourceEl, Object.entries(data.by_source || {})
        .map(([key, count]) => ({ key, count }))
        .sort((a, b) => Number(b.count) - Number(a.count)));
    renderBarChart(chartRecentEl, (data.recent_imports || []).map((row) => ({ key: row.date, count: row.count })));
}
export async function loadStats() {
    dashboardStatsEl.textContent = t("common.loading");
    renderDashboard(await api("/api/stats"));
}

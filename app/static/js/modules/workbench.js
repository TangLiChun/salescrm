import { t, followUpLabel } from "../../i18n.js";
import * as dom from "../core/dom.js";
import { state } from "../core/state.js";
import { api, escapeHtml, formatImportResult } from "../core/utils.js";
import { showApiError, showApiSuccess } from "../core/api-feedback.js";
import { deps } from "../core/deps.js";
import { scoreBadgeClass, formatSource } from "./leads.js";
const { workbenchStatsEl, workbenchMetricsEl, leadReviewStatsEl, leadReviewBody, importReviewedLeadsBtn, workbenchFollowupsEl, workbenchNewContactsEl, } = dom;
function metricCard(value, label, tone = "") {
    return `
    <div class="stat-card ${tone ? `stat-card-${tone}` : ""}">
      <strong>${escapeHtml(String(value ?? 0))}</strong>
      <span>${escapeHtml(label)}</span>
    </div>`;
}
function emptyStateHtml(message, actions = []) {
    const ctas = actions.length
        ? `<div class="empty-state-ctas">${actions
            .map((action) => {
            const attrs = [`data-goto-view="${escapeHtml(action.view)}"`];
            if (action.contactStatus)
                attrs.push(`data-contact-status="${escapeHtml(action.contactStatus)}"`);
            if (action.contactFollowUp)
                attrs.push(`data-contact-follow-up="${escapeHtml(action.contactFollowUp)}"`);
            return `<button type="button" class="secondary-btn empty-state-cta" ${attrs.join(" ")}>${escapeHtml(t(action.labelKey))}</button>`;
        })
            .join("")}</div>`
        : "";
    return `<div class="empty-state-block"><p class="stats">${escapeHtml(message)}</p>${ctas}</div>`;
}
function contactActionItem(contact) {
    const roles = String(contact.roles || "")
        .split(",")
        .filter(Boolean)
        .slice(0, 3)
        .map((role) => `<span class="role-tag">${escapeHtml(role)}</span>`)
        .join("");
    return `
    <div class="action-list-item">
      <div>
        <strong>${escapeHtml(contact.org || contact.name || contact.email || "—")}</strong>
        <p class="stats">${escapeHtml(contact.email || "—")} · ${contact.asn ? `AS${escapeHtml(String(contact.asn))}` : "ASN —"} · ${escapeHtml(followUpLabel(contact.follow_up_status))}</p>
        <div>${roles || ""}</div>
      </div>
      <a class="link-btn" href="mailto:${encodeURIComponent(contact.email || "")}">${escapeHtml(t("contacts.actionMail"))}</a>
    </div>`;
}
function renderActionList(container, items, emptyText, emptyActions = []) {
    if (!container)
        return;
    if (!items?.length) {
        container.innerHTML = emptyStateHtml(emptyText, emptyActions);
        return;
    }
    container.innerHTML = items.map(contactActionItem).join("");
}
function leadRolesHtml(lead) {
    return (lead.roles || [])
        .slice(0, 4)
        .map((role) => `<span class="role-tag">${escapeHtml(role)}</span>`)
        .join("");
}
function reviewRow(review) {
    const lead = review.lead || {};
    const checked = state.selectedLeadReviewIds.has(review.id) ? "checked" : "";
    return `
    <tr class="motion-row-in">
      <td class="col-select"><input type="checkbox" class="lead-review-select" data-id="${review.id}" ${checked}></td>
      <td><span class="${scoreBadgeClass(review.score || lead.lead_score)}">${escapeHtml(String(review.score || lead.lead_score || 0))}</span></td>
      <td>${escapeHtml(review.org || lead.org || lead.network_name || "—")}</td>
      <td><a class="email-link" href="mailto:${escapeHtml(review.email || lead.email || "")}">${escapeHtml(review.email || lead.email || "—")}</a></td>
      <td>${leadRolesHtml(lead) || "—"}</td>
      <td class="mono">${review.asn || lead.asn ? `AS${escapeHtml(String(review.asn || lead.asn))}` : "—"}</td>
      <td>${escapeHtml(formatSource({ source: review.source || lead.source }))}</td>
      <td class="review-actions">
        <button type="button" class="link-btn lead-review-import" data-id="${review.id}">${escapeHtml(t("workbench.importOne"))}</button>
        <button type="button" class="link-btn lead-review-skip" data-id="${review.id}">${escapeHtml(t("workbench.skip"))}</button>
      </td>
    </tr>`;
}
const REVIEW_EMPTY_ACTIONS = [
    { view: "pi-agent", labelKey: "workbench.ctaPiLeads" },
    { view: "ai-leads", labelKey: "workbench.ctaAiLeads" },
    { view: "lookup", labelKey: "workbench.ctaAsnLookup" },
];
export function updateLeadReviewSelection() {
    const currentIds = new Set(state.leadReviews.map((item) => item.id));
    for (const id of [...state.selectedLeadReviewIds]) {
        if (!currentIds.has(id))
            state.selectedLeadReviewIds.delete(id);
    }
    if (leadReviewStatsEl) {
        leadReviewStatsEl.textContent = t("workbench.reviewStats", {
            total: state.leadReviews.length,
            selected: state.selectedLeadReviewIds.size,
        });
    }
    if (importReviewedLeadsBtn) {
        importReviewedLeadsBtn.disabled = state.selectedLeadReviewIds.size === 0;
    }
}
export function renderLeadReviews() {
    if (!leadReviewBody)
        return;
    if (!state.leadReviews.length) {
        leadReviewBody.innerHTML = `<tr class="empty-row"><td colspan="8" class="empty-state">${emptyStateHtml(t("workbench.noReviewLeads"), REVIEW_EMPTY_ACTIONS)}</td></tr>`;
        updateLeadReviewSelection();
        return;
    }
    leadReviewBody.innerHTML = state.leadReviews.map(reviewRow).join("");
    updateLeadReviewSelection();
}
export function renderWorkbench(data) {
    if (workbenchStatsEl) {
        workbenchStatsEl.textContent = t("workbench.stats", { date: data.today || "" });
    }
    if (workbenchMetricsEl) {
        workbenchMetricsEl.innerHTML = [
            metricCard(data.pending_reviews, t("workbench.metricPending"), "accent"),
            metricCard(data.due_followups, t("workbench.metricDue"), "caution"),
            metricCard(data.unsent_new, t("workbench.metricUnsent"), ""),
            metricCard(data.warm_contacts, t("workbench.metricWarm"), "positive"),
            metricCard(data.imported_today, t("workbench.metricToday"), ""),
        ].join("");
    }
    state.leadReviews = data.review_items || [];
    renderLeadReviews();
    renderActionList(workbenchFollowupsEl, data.followup_items || [], t("workbench.noFollowups"), [
        { view: "contacts", labelKey: "workbench.ctaContacts" },
    ]);
    renderActionList(workbenchNewContactsEl, data.new_items || [], t("workbench.noNewContacts"), [
        { view: "contacts", labelKey: "workbench.ctaUnsentContacts", contactStatus: "unsent" },
    ]);
}
export async function loadWorkbench() {
    if (workbenchStatsEl)
        workbenchStatsEl.textContent = t("common.loading");
    const data = await api("/api/workbench");
    renderWorkbench(data);
}
export async function importSelectedLeadReviews(ids = [...state.selectedLeadReviewIds]) {
    if (!ids.length)
        return;
    const result = await api("/api/lead-reviews/import", {
        method: "POST",
        body: JSON.stringify({ ids }),
    });
    state.selectedLeadReviewIds.clear();
    showApiSuccess(formatImportResult(result));
    await Promise.all([
        loadWorkbench(),
        deps.loadContacts?.(),
    ]);
}
export async function skipLeadReview(id) {
    await api(`/api/lead-reviews/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "skipped" }),
    });
    state.selectedLeadReviewIds.delete(Number(id));
    await loadWorkbench();
}
export function handleLeadReviewSelection(event) {
    const check = event.target.closest(".lead-review-select");
    if (!check)
        return;
    const id = Number(check.dataset.id);
    if (check.checked) {
        state.selectedLeadReviewIds.add(id);
    }
    else {
        state.selectedLeadReviewIds.delete(id);
    }
    updateLeadReviewSelection();
}
export function handleLeadReviewAction(event) {
    const importBtn = event.target.closest(".lead-review-import");
    if (importBtn) {
        importSelectedLeadReviews([Number(importBtn.dataset.id)]).catch(showApiError);
        return;
    }
    const skipBtn = event.target.closest(".lead-review-skip");
    if (skipBtn) {
        skipLeadReview(Number(skipBtn.dataset.id)).catch(showApiError);
    }
}

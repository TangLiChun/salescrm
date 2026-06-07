import { t } from "../../i18n.js";
import * as dom from "../core/dom.js";
import { state } from "../core/state.js";
import { replayAnimation } from "../core/motion.js";
import { switchSettingsCat } from "./settings.js";
import { loadSchedules, startSchedulesAutoRefresh, stopSchedulesAutoRefresh } from "./schedules.js";
import { loadStats } from "./stats.js";
import { loadContacts, renderContacts, renderMailTemplateSelect, renderEmailTemplatesList, loadEmailTemplates } from "./contacts.js";
import { loadSettingsForm } from "./settings.js";
import { renderRows, refreshAsnPreview, updateStats } from "./lookup.js";
import { renderAiLeads, updateAiLeadsStats, loadLlmStatus } from "./leads.js";
import { updatePiAgentStatus, updatePiChatHistoryHint, refreshPiAgentChrome, setPiMobilePanel, settlePiChatAtBottom } from "./pi.js";
import { renderSchedules } from "./schedules.js";
import { loadWorkbench } from "./workbench.js";
import { renderBackgroundJobsBar } from "../jobs/index.js";
import { showApiError } from "../core/api-feedback.js";
const { tabs, workbenchView, lookupView, aiLeadsView, piAgentView, schedulesView, settingsView, contactsView, statsView, pageTitle, statsEl } = dom;
const VIEW_ELEMENTS = {
    workbench: workbenchView,
    lookup: lookupView,
    "ai-leads": aiLeadsView,
    "pi-agent": piAgentView,
    schedules: schedulesView,
    settings: settingsView,
    contacts: contactsView,
    stats: statsView,
};
const MOBILE_OVERFLOW_VIEWS = new Set(["ai-leads", "schedules", "stats", "settings"]);
export const VALID_VIEWS = new Set([
    "workbench",
    "lookup",
    "ai-leads",
    "pi-agent",
    "schedules",
    "settings",
    "contacts",
    "stats",
]);
let suppressHashSync = false;
export function getViewFromHash() {
    const view = window.location.hash.replace(/^#/, "");
    return VALID_VIEWS.has(view) ? view : "workbench";
}
function syncViewHash(view) {
    if (suppressHashSync)
        return;
    const targetHash = view === "workbench" ? "" : `#${view}`;
    const current = window.location.hash;
    if (current === targetHash || (view === "workbench" && !current))
        return;
    const url = `${window.location.pathname}${window.location.search}${targetHash}`;
    window.history.replaceState(null, "", url);
}
export function initViewRouting() {
    window.addEventListener("hashchange", () => {
        const view = getViewFromHash();
        suppressHashSync = true;
        switchView(view, { updateHash: false });
        suppressHashSync = false;
    });
}
function animatePageTitle() {
    if (!pageTitle)
        return;
    replayAnimation(pageTitle, "title-enter");
}
export function closeMobileNavMore() {
    const panel = document.getElementById("mobile-nav-more-panel");
    const btn = document.getElementById("mobile-nav-more-btn");
    panel?.classList.add("hidden");
    btn?.setAttribute("aria-expanded", "false");
}
export function openMobileNavMore() {
    const panel = document.getElementById("mobile-nav-more-panel");
    const btn = document.getElementById("mobile-nav-more-btn");
    panel?.classList.remove("hidden");
    btn?.setAttribute("aria-expanded", "true");
    panel?.querySelector(".mobile-nav-overflow-item")?.focus();
}
function syncMobileNavMore(view) {
    const moreBtn = document.getElementById("mobile-nav-more-btn");
    moreBtn?.classList.toggle("active", MOBILE_OVERFLOW_VIEWS.has(view));
    document.querySelectorAll(".mobile-nav-overflow-item").forEach((item) => {
        item.classList.toggle("active", item.dataset.view === view);
    });
    closeMobileNavMore();
}
export function switchView(view, { updateHash = true } = {}) {
    if (!VALID_VIEWS.has(view))
        view = "workbench";
    tabs.forEach((tab) => {
        tab.classList.toggle("active", tab.dataset.view === view);
    });
    syncMobileNavMore(view);
    if (updateHash)
        syncViewHash(view);
    workbenchView.classList.toggle("hidden", view !== "workbench");
    lookupView.classList.toggle("hidden", view !== "lookup");
    aiLeadsView.classList.toggle("hidden", view !== "ai-leads");
    piAgentView.classList.toggle("hidden", view !== "pi-agent");
    schedulesView.classList.toggle("hidden", view !== "schedules");
    settingsView.classList.toggle("hidden", view !== "settings");
    contactsView.classList.toggle("hidden", view !== "contacts");
    statsView.classList.toggle("hidden", view !== "stats");
    replayAnimation(VIEW_ELEMENTS[view], "motion-enter");
    animatePageTitle();
    if (view === "workbench") {
        pageTitle.textContent = t("page.workbench.title");
        loadWorkbench().catch(showApiError);
    }
    else if (view === "lookup") {
        pageTitle.textContent = t("page.lookup.title");
    }
    else if (view === "ai-leads") {
        pageTitle.textContent = t("page.aiLeads.title");
    }
    else if (view === "pi-agent") {
        pageTitle.textContent = t("page.piAgent.title");
        setPiMobilePanel("chat");
        refreshPiAgentChrome();
        updatePiAgentStatus();
        settlePiChatAtBottom();
    }
    else if (view === "schedules") {
        pageTitle.textContent = t("page.schedules.title");
        loadSchedules().catch(showApiError);
        startSchedulesAutoRefresh();
    }
    else if (view === "settings") {
        switchSettingsCat(state.activeSettingsCat);
        loadSettingsForm().catch(showApiError);
        loadEmailTemplates().catch(showApiError);
    }
    else if (view === "stats") {
        pageTitle.textContent = t("page.stats.title");
        loadStats().catch(showApiError);
    }
    else {
        pageTitle.textContent = t("page.contacts.title");
        loadContacts().catch(showApiError);
        loadEmailTemplates().catch(() => { });
    }
    if (view !== "schedules") {
        stopSchedulesAutoRefresh();
    }
}
export function refreshUiOnLanguageChange() {
    const activeView = document.querySelector(".tab.active")?.dataset.view || "lookup";
    switchView(activeView);
    renderRows();
    renderContacts();
    renderAiLeads();
    renderSchedules();
    renderMailTemplateSelect();
    renderEmailTemplatesList();
    updatePiChatHistoryHint();
    refreshPiAgentChrome();
    updateAiLeadsStats();
    if (state.allRows.length === 0 && statsEl) {
        statsEl.textContent = t("common.notYetQueried");
    }
    else {
        updateStats();
    }
    refreshAsnPreview().catch(() => { });
    if (state.llmConfigured) {
        loadLlmStatus().catch(() => { });
    }
    else {
        updatePiAgentStatus();
    }
    renderBackgroundJobsBar();
    if (activeView === "workbench") {
        loadWorkbench().catch(() => { });
    }
}

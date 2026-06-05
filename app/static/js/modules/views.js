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
import { updatePiAgentStatus, updatePiChatHistoryHint, refreshPiAgentChrome, setPiMobilePanel } from "./pi.js";
import { renderSchedules } from "./schedules.js";
import { renderBackgroundJobsBar } from "../jobs/index.js";

const { tabs, lookupView, aiLeadsView, piAgentView, schedulesView, settingsView, contactsView, statsView, pageTitle, statsEl } = dom;

const VIEW_ELEMENTS = {
  lookup: lookupView,
  "ai-leads": aiLeadsView,
  "pi-agent": piAgentView,
  schedules: schedulesView,
  settings: settingsView,
  contacts: contactsView,
  stats: statsView,
};

function animatePageTitle() {
  if (!pageTitle) return;
  replayAnimation(pageTitle, "title-enter");
}

export function switchView(view) {
  tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === view);
  });

  lookupView.classList.toggle("hidden", view !== "lookup");
  aiLeadsView.classList.toggle("hidden", view !== "ai-leads");
  piAgentView.classList.toggle("hidden", view !== "pi-agent");
  schedulesView.classList.toggle("hidden", view !== "schedules");
  settingsView.classList.toggle("hidden", view !== "settings");
  contactsView.classList.toggle("hidden", view !== "contacts");
  statsView.classList.toggle("hidden", view !== "stats");

  replayAnimation(VIEW_ELEMENTS[view], "motion-enter");
  animatePageTitle();

  if (view === "lookup") {
    pageTitle.textContent = t("page.lookup.title");
  } else if (view === "ai-leads") {
    pageTitle.textContent = t("page.aiLeads.title");
  } else if (view === "pi-agent") {
    pageTitle.textContent = t("page.piAgent.title");
    setPiMobilePanel("chat");
    refreshPiAgentChrome();
    updatePiAgentStatus();
  } else if (view === "schedules") {
    pageTitle.textContent = t("page.schedules.title");
    loadSchedules().catch((error) => alert(error.message));
    startSchedulesAutoRefresh();
  } else if (view === "settings") {
    switchSettingsCat(state.activeSettingsCat);
    loadSettingsForm().catch((error) => alert(error.message));
    loadEmailTemplates().catch((error) => alert(error.message));
  } else if (view === "stats") {
    pageTitle.textContent = t("page.stats.title");
    loadStats().catch((error) => alert(error.message));
  } else {
    pageTitle.textContent = t("page.contacts.title");
    loadContacts().catch((error) => alert(error.message));
    loadEmailTemplates().catch(() => {});
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
  } else {
    updateStats();
  }
  refreshAsnPreview().catch(() => {});
  if (state.llmConfigured) {
    loadLlmStatus().catch(() => {});
  } else {
    updatePiAgentStatus();
  }
  renderBackgroundJobsBar();
}

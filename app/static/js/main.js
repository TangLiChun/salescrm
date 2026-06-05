import { initI18n, t } from "../i18n.js";
import * as dom from "./core/dom.js";
import * as state from "./core/state.js";
import { api, errorMessage } from "./core/utils.js";
import { registerDeps } from "./core/deps.js";
import {
  startJobEventStream,
  resumeBackgroundJobs,
  openJobsPanel,
  closeJobsPanel,
} from "./jobs/index.js";
import {
  runLookup,
  downloadCsv,
  importResults,
  renderRows,
  refreshAsnPreview,
  updateStats,
  ensureRowSelected,
  getSelectedImportableRows,
} from "./modules/lookup.js";
import {
  loadContacts,
  bulkContactsAction,
  openContactEdit,
  closeContactEdit,
  saveContactEdit,
  downloadBackup,
  exportContactsCsv,
  dedupeContacts,
  markContactSent,
  changeContactFollowUpStatus,
  openMailClient,
  openContactNotes,
  closeContactNotes,
  addContactNote,
  deleteContactNote,
  deleteContact,
  renderContacts,
  updateContactsBulkBar,
  syncContactsSelectAllCheckbox,
  closeAllContactActionMenus,
  positionContactActionMenu,
} from "./modules/contacts.js";
import {
  runLeadDiscovery,
  importAiLeads,
  openLeadDetail,
  closeLeadDetail,
  renderAiLeads,
  updateAiLeadsStats,
  loadLlmStatus,
  ensureLeadSelected,
  hideLeadsState,
} from "./modules/leads.js";
import {
  sendPiChat,
  stopPiChat,
  clearPiChat,
  createPiThread,
  switchPiThread,
  deletePiThread,
  savePiThreadsStore,
  openPiAgentForLeads,
  enrichContactViaBackground,
  loadPiChatForUser,
  appendPiChatStatus,
  fetchActivePiThreadHistory,
  restorePiChatUi,
} from "./modules/pi.js";
import {
  createSchedule,
  loadSchedules,
  toggleSchedule,
  deleteSchedule,
  runScheduleNow,
  updateScheduleFormMode,
} from "./modules/schedules.js";
import {
  saveSettings,
  saveEmailTemplate,
  editEmailTemplate,
  deleteEmailTemplate,
  regenerateAgentToken,
  copyAgentToken,
  changePassword,
} from "./modules/settings.js";
import { loadStats } from "./modules/stats.js";
import { switchView, refreshUiOnLanguageChange, switchSettingsCat } from "./modules/views.js";

const {
  asnInput,
  lookupBtn,
  exportBtn,
  importBtn,
  roleFilter,
  resultsBody,
  currentUserEl,
  logoutBtn,
  piChatForm,
  piChatStopBtn,
  piChatClearBtn,
  piThreadNewBtn,
  piThreadListEl,
  discoverBtn,
  discoverViaPiBtn,
  retryDiscoverBtn,
  importLeadsBtn,
  contactStatusFilter,
  contactFollowUpFilter,
  contactSearchInput,
  contactsPageSizeSelect,
  contactsPrevBtn,
  contactsNextBtn,
  contactsSelectAll,
  contactsBody,
  bulkApplyStatusBtn,
  bulkStatusSelect,
  bulkMarkSentBtn,
  bulkDeleteBtn,
  contactEditForm,
  contactEditModal,
  downloadBackupBtn,
  exportContactsBtn,
  dedupeContactsBtn,
  refreshContactsBtn,
  refreshSchedulesBtn,
  refreshStatsBtn,
  scheduleForm,
  scheduleRunModeInput,
  scheduleIntervalPreset,
  settingsForm,
  saveTemplateBtn,
  emailTemplatesListEl,
  contactNoteForm,
  contactNotesModal,
  tabs,
  aiLeadsBody,
  leadDetailModal,
  leadDetailImport,
  backgroundJobsBar,
  jobsPanelEl,
  leadQueryInput,
  scheduleQueryInput,
} = dom;

registerDeps({
  switchView,
  loadContacts,
  switchPiThread,
  fetchActivePiThreadHistory,
  restorePiChatUi,
  appendPiChatStatus,
  renderRows,
  renderAiLeads,
  hideLeadsState,
  ensureRowSelected,
  ensureLeadSelected,
  getSelectedImportableRows,
});

backgroundJobsBar?.addEventListener("click", (event) => {
  if (event.target.closest(".background-jobs-open")) {
    openJobsPanel();
  }
});

jobsPanelEl?.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-jobs-panel]")) {
    closeJobsPanel();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && jobsPanelEl && !jobsPanelEl.classList.contains("hidden")) {
    closeJobsPanel();
  }
});

lookupBtn.addEventListener("click", runLookup);
piChatForm?.addEventListener("submit", (event) => {
  sendPiChat(event).catch((error) => appendPiChatStatus(error.message));
});
piChatStopBtn?.addEventListener("click", stopPiChat);
piChatClearBtn?.addEventListener("click", clearPiChat);
piThreadNewBtn?.addEventListener("click", () => createPiThread());
piThreadListEl?.addEventListener("click", (event) => {
  const deleteBtn = event.target.closest("[data-delete-thread]");
  if (deleteBtn) {
    deletePiThread(deleteBtn.dataset.deleteThread);
    return;
  }
  const threadBtn = event.target.closest(".pi-thread-btn[data-thread-id]");
  if (threadBtn) {
    switchPiThread(threadBtn.dataset.threadId);
  }
});
window.addEventListener("beforeunload", () => {
  savePiThreadsStore();
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    savePiThreadsStore();
  }
});
asnInput.addEventListener("input", () => {
  clearTimeout(state.asnParseTimer);
  state.asnParseTimer = setTimeout(() => {
    refreshAsnPreview().catch(() => {});
  }, 350);
});
exportBtn.addEventListener("click", downloadCsv);
importBtn.addEventListener("click", importResults);
discoverBtn.addEventListener("click", runLeadDiscovery);
discoverViaPiBtn?.addEventListener("click", () => {
  openPiAgentForLeads().catch((error) => alert(errorMessage(error, t("msg.piStartFailed"))));
});
retryDiscoverBtn.addEventListener("click", () => {
  if (state.lastDiscoverQuery) {
    leadQueryInput.value = state.lastDiscoverQuery;
  }
  runLeadDiscovery();
});
importLeadsBtn.addEventListener("click", importAiLeads);
roleFilter.addEventListener("change", renderRows);
contactStatusFilter.addEventListener("change", () => loadContacts(true).catch((error) => alert(error.message)));
contactFollowUpFilter.addEventListener("change", () => loadContacts(true).catch((error) => alert(error.message)));
contactSearchInput.addEventListener("input", () => {
  clearTimeout(state.contactSearchTimer);
  state.contactSearchTimer = setTimeout(() => {
    loadContacts(true).catch((error) => alert(error.message));
  }, 300);
});
contactsPageSizeSelect.addEventListener("change", () => {
  state.contactsPageSize = Number(contactsPageSizeSelect.value) || 50;
  loadContacts(true).catch((error) => alert(error.message));
});
contactsPrevBtn.addEventListener("click", () => {
  if (state.contactsPage > 1) {
    state.contactsPage -= 1;
    loadContacts().catch((error) => alert(error.message));
  }
});
contactsNextBtn.addEventListener("click", () => {
  if (state.contactsPage < state.contactsPages) {
    state.contactsPage += 1;
    loadContacts().catch((error) => alert(error.message));
  }
});
contactsSelectAll.addEventListener("change", () => {
  for (const contact of state.contacts) {
    if (contactsSelectAll.checked) {
      state.selectedContactIds.add(contact.id);
    } else {
      state.selectedContactIds.delete(contact.id);
    }
  }
  renderContacts();
});
contactsBody.addEventListener("change", (event) => {
  const checkbox = event.target.closest(".contact-select");
  if (!checkbox) return;
  const id = Number(checkbox.dataset.id);
  if (checkbox.checked) {
    state.selectedContactIds.add(id);
  } else {
    state.selectedContactIds.delete(id);
  }
  updateContactsBulkBar();
  syncContactsSelectAllCheckbox();
});
bulkApplyStatusBtn.addEventListener("click", () => {
  bulkContactsAction("status", { follow_up_status: bulkStatusSelect.value })
    .then((result) => alert(t("msg.bulkUpdated", { count: result.updated })))
    .catch((error) => alert(error.message));
});
bulkMarkSentBtn.addEventListener("click", () => {
  bulkContactsAction("mark_sent")
    .then((result) => alert(t("msg.bulkMarked", { count: result.updated })))
    .catch((error) => alert(error.message));
});
bulkDeleteBtn.addEventListener("click", () => {
  if (!confirm(t("msg.confirmBulkDeleteContacts"))) return;
  bulkContactsAction("delete")
    .then((result) => alert(t("msg.bulkDeleted", { count: result.deleted })))
    .catch((error) => alert(error.message));
});
contactEditForm.addEventListener("submit", (event) => {
  saveContactEdit(event).catch((error) => alert(error.message));
});
contactEditModal.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-edit]")) {
    closeContactEdit();
  }
});
downloadBackupBtn.addEventListener("click", () => downloadBackup().catch((error) => alert(error.message)));
exportContactsBtn.addEventListener("click", () => exportContactsCsv().catch((error) => alert(error.message)));
dedupeContactsBtn.addEventListener("click", () => dedupeContacts().catch((error) => alert(error.message)));
refreshContactsBtn.addEventListener("click", () => loadContacts().catch((error) => alert(error.message)));
refreshSchedulesBtn.addEventListener("click", () => loadSchedules().catch((error) => alert(error.message)));
refreshStatsBtn.addEventListener("click", () => loadStats().catch((error) => alert(error.message)));
scheduleForm.addEventListener("submit", (event) => createSchedule(event).catch((error) => alert(error.message)));
scheduleRunModeInput?.addEventListener("change", updateScheduleFormMode);
scheduleIntervalPreset?.addEventListener("change", updateScheduleFormMode);
updateScheduleFormMode();
settingsForm.addEventListener("submit", (event) => saveSettings(event).catch((error) => alert(error.message)));
saveTemplateBtn.addEventListener("click", () => saveEmailTemplate().catch((error) => alert(error.message)));
emailTemplatesListEl.addEventListener("click", (event) => {
  const editBtn = event.target.closest(".template-edit");
  if (editBtn) {
    editEmailTemplate(Number(editBtn.dataset.id));
    return;
  }
  const deleteBtn = event.target.closest(".template-delete");
  if (deleteBtn) {
    deleteEmailTemplate(Number(deleteBtn.dataset.id)).catch((error) => alert(error.message));
  }
});
document.getElementById("change-password-btn").addEventListener("click", () => {
  changePassword().catch((error) => alert(error.message));
});
document.getElementById("regenerate-agent-token-btn")?.addEventListener("click", () => {
  if (!confirm(t("msg.confirmRegenerateToken"))) return;
  regenerateAgentToken().catch((error) => alert(error.message));
});
document.getElementById("copy-agent-token-btn")?.addEventListener("click", () => {
  copyAgentToken().catch((error) => alert(error.message));
});

logoutBtn.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

tabs.forEach((tab) => {
  tab.addEventListener("click", () => switchView(tab.dataset.view));
});

document.querySelectorAll(".settings-rail-item").forEach((btn) => {
  btn.addEventListener("click", () => switchSettingsCat(btn.dataset.settingsCat));
});

contactNoteForm.addEventListener("submit", (event) => {
  addContactNote(event).catch((error) => alert(error.message));
});

contactNotesModal.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-notes]")) {
    closeContactNotes();
    return;
  }
  const deleteBtn = event.target.closest(".note-delete");
  if (deleteBtn) {
    deleteContactNote(deleteBtn.dataset.noteId).catch((error) => alert(error.message));
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".contact-action-menu")) {
    closeAllContactActionMenus();
  }
});

contactsBody.addEventListener("click", (event) => {
  const menuToggle = event.target.closest(".action-menu-toggle");
  if (menuToggle) {
    event.stopPropagation();
    const menu = menuToggle.closest(".contact-action-menu");
    const panel = menu?.querySelector(".action-menu-panel");
    const wasOpen = panel && !panel.classList.contains("hidden");
    closeAllContactActionMenus();
    if (!wasOpen && panel) {
      positionContactActionMenu(menuToggle, panel);
      menuToggle.setAttribute("aria-expanded", "true");
    }
    return;
  }

  const editBtn = event.target.closest(".action-edit");
  if (editBtn) {
    closeAllContactActionMenus();
    openContactEdit(editBtn.dataset.id);
    return;
  }
  const notesBtn = event.target.closest(".action-notes");
  if (notesBtn) {
    closeAllContactActionMenus();
    openContactNotes(notesBtn.dataset.id).catch((error) => alert(error.message));
    return;
  }
  const mailBtn = event.target.closest(".action-mail");
  if (mailBtn) {
    closeAllContactActionMenus();
    openMailClient(mailBtn.dataset.id);
    return;
  }
  const statusBtn = event.target.closest(".action-status");
  if (statusBtn) {
    closeAllContactActionMenus();
    changeContactFollowUpStatus(statusBtn.dataset.id, statusBtn.dataset.status).catch((error) =>
      alert(error.message),
    );
    return;
  }
  const markBtn = event.target.closest(".action-mark");
  if (markBtn) {
    closeAllContactActionMenus();
    markContactSent(markBtn.dataset.id, markBtn.dataset.sent === "1").catch((error) => alert(error.message));
    return;
  }
  const enrichBtn = event.target.closest(".action-enrich-pi");
  if (enrichBtn) {
    closeAllContactActionMenus();
    const contact = state.contacts.find((item) => String(item.id) === String(enrichBtn.dataset.id));
    enrichContactViaBackground(contact).catch((error) => alert(errorMessage(error, t("msg.enrichFailed"))));
    return;
  }
  const deleteBtn = event.target.closest(".action-delete");
  if (deleteBtn) {
    closeAllContactActionMenus();
    deleteContact(deleteBtn.dataset.id).catch((error) => alert(error.message));
  }
});

document.querySelector(".contacts-table-wrap")?.addEventListener("scroll", closeAllContactActionMenus, {
  passive: true,
});
window.addEventListener("resize", closeAllContactActionMenus);

document.getElementById("schedules-body")?.addEventListener("click", (event) => {
  const runBtn = event.target.closest(".schedule-run");
  if (runBtn) {
    runScheduleNow(runBtn.dataset.id).catch((error) => alert(error.message));
    return;
  }
  const toggleBtn = event.target.closest(".schedule-toggle");
  if (toggleBtn) {
    toggleSchedule(toggleBtn.dataset.id, toggleBtn.dataset.enabled === "1").catch((error) =>
      alert(error.message),
    );
    return;
  }
  const deleteBtn = event.target.closest(".schedule-delete");
  if (deleteBtn) {
    deleteSchedule(deleteBtn.dataset.id).catch((error) => alert(error.message));
  }
});

aiLeadsBody.addEventListener("click", (event) => {
  const btn = event.target.closest(".lead-detail-btn");
  if (btn) openLeadDetail(Number(btn.dataset.index));
});

aiLeadsBody.addEventListener("change", (event) => {
  const check = event.target.closest(".row-import-check");
  if (!check || check.dataset.kind !== "ai") return;
  const lead = state.aiLeads[Number(check.dataset.index)];
  if (lead) lead._selected = check.checked;
  updateAiLeadsStats();
});

leadDetailModal.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-detail]")) closeLeadDetail();
});

leadDetailImport.addEventListener("change", () => {
  if (state.detailLeadIndex === null) return;
  const lead = state.aiLeads[state.detailLeadIndex];
  if (lead) lead._selected = leadDetailImport.checked;
  renderAiLeads();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !leadDetailModal.classList.contains("hidden")) closeLeadDetail();
});

resultsBody.addEventListener("change", (event) => {
  const check = event.target.closest(".row-import-check");
  if (!check || check.dataset.kind !== "lookup") return;
  const row = state.allRows[Number(check.dataset.index)];
  if (row) row._selected = check.checked;
  importBtn.disabled = getSelectedImportableRows().length === 0;
  updateStats();
});

window.addEventListener("languagechange", refreshUiOnLanguageChange);

async function bootstrap() {
  initI18n();
  try {
    const user = await api("/api/me");
    currentUserEl.textContent = user.username;
    state.currentUserId = user.id;
    await loadPiChatForUser(state.currentUserId);
  } catch {
    window.location.href = "/login";
    return;
  }

  await loadLlmStatus();
  leadQueryInput.value = t("bootstrap.leadQueryDefault");
  scheduleQueryInput.value = leadQueryInput.value;
  await loadContacts();
  await loadSchedules();
  startJobEventStream();
  await resumeBackgroundJobs();
}

bootstrap();

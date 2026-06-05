const asnInput = document.getElementById("asn-input");
const asnParsePreviewEl = document.getElementById("asn-parse-preview");
const delayInput = document.getElementById("delay");
const lookupBtn = document.getElementById("lookup-btn");
const exportBtn = document.getElementById("export-btn");
const importBtn = document.getElementById("import-btn");
const roleFilter = document.getElementById("role-filter");
const resultsBody = document.getElementById("results-body");
const statsEl = document.getElementById("stats");
const progressEl = document.getElementById("progress");
const progressFill = document.getElementById("progress-fill");
const progressText = document.getElementById("progress-text");
const currentUserEl = document.getElementById("current-user");
const logoutBtn = document.getElementById("logout-btn");
const lookupView = document.getElementById("lookup-view");
const aiLeadsView = document.getElementById("ai-leads-view");
const piAgentView = document.getElementById("pi-agent-view");
const piAgentStatusEl = document.getElementById("pi-agent-status");
const piChatMessagesEl = document.getElementById("pi-chat-messages");
const piChatForm = document.getElementById("pi-chat-form");
const piChatInput = document.getElementById("pi-chat-input");
const piChatSendBtn = document.getElementById("pi-chat-send");
const piChatStopBtn = document.getElementById("pi-chat-stop");
const piChatClearBtn = document.getElementById("pi-chat-clear");
const piChatHistoryHintEl = document.getElementById("pi-chat-history-hint");
const piThreadListEl = document.getElementById("pi-thread-list");
const piThreadNewBtn = document.getElementById("pi-thread-new");
const piChatProgressEl = document.getElementById("pi-chat-progress");
const piChatProgressFill = document.getElementById("pi-chat-progress-fill");
const piChatProgressText = document.getElementById("pi-chat-progress-text");
const schedulesView = document.getElementById("schedules-view");
const contactsView = document.getElementById("contacts-view");
const statsView = document.getElementById("stats-view");
const dashboardStatsEl = document.getElementById("dashboard-stats");
const statsSummaryEl = document.getElementById("stats-summary");
const chartFollowUpEl = document.getElementById("chart-follow-up");
const chartSentEl = document.getElementById("chart-sent");
const chartSourceEl = document.getElementById("chart-source");
const chartRecentEl = document.getElementById("chart-recent");
const refreshStatsBtn = document.getElementById("refresh-stats-btn");
const contactsBody = document.getElementById("contacts-body");
const contactsStatsEl = document.getElementById("contacts-stats");
const contactsMetricTotalEl = document.getElementById("contacts-metric-total");
const contactsMetricSentEl = document.getElementById("contacts-metric-sent");
const contactsMetricUnsentEl = document.getElementById("contacts-metric-unsent");
const contactStatusFilter = document.getElementById("contact-status-filter");
const contactFollowUpFilter = document.getElementById("contact-follow-up-filter");
const contactSearchInput = document.getElementById("contact-search");
const exportContactsBtn = document.getElementById("export-contacts-btn");
const dedupeContactsBtn = document.getElementById("dedupe-contacts-btn");
const refreshContactsBtn = document.getElementById("refresh-contacts-btn");
const contactsBulkBar = document.getElementById("contacts-bulk-bar");
const contactsSelectedCountEl = document.getElementById("contacts-selected-count");
const bulkStatusSelect = document.getElementById("bulk-status-select");
const bulkApplyStatusBtn = document.getElementById("bulk-apply-status-btn");
const bulkMarkSentBtn = document.getElementById("bulk-mark-sent-btn");
const bulkDeleteBtn = document.getElementById("bulk-delete-btn");
const contactsSelectAll = document.getElementById("contacts-select-all");
const contactsPagination = document.getElementById("contacts-pagination");
const contactsPrevBtn = document.getElementById("contacts-prev-btn");
const contactsNextBtn = document.getElementById("contacts-next-btn");
const contactsPageInfo = document.getElementById("contacts-page-info");
const contactsPageSizeSelect = document.getElementById("contacts-page-size");
const contactEditModal = document.getElementById("contact-edit-modal");
const contactEditSubtitle = document.getElementById("contact-edit-subtitle");
const contactEditForm = document.getElementById("contact-edit-form");
const contactEditOrg = document.getElementById("contact-edit-org");
const contactEditName = document.getElementById("contact-edit-name");
const contactEditRoles = document.getElementById("contact-edit-roles");
const contactEditNotes = document.getElementById("contact-edit-notes");
const contactEditLinkedin = document.getElementById("contact-edit-linkedin");
const contactEditX = document.getElementById("contact-edit-x");
const contactEditFacebook = document.getElementById("contact-edit-facebook");
const downloadBackupBtn = document.getElementById("download-backup-btn");
const contactNotesModal = document.getElementById("contact-notes-modal");
const contactNotesTitle = document.getElementById("contact-notes-title");
const contactNotesSubtitle = document.getElementById("contact-notes-subtitle");
const contactNotesList = document.getElementById("contact-notes-list");
const contactNoteForm = document.getElementById("contact-note-form");
const contactNoteBody = document.getElementById("contact-note-body");
const schedulesBody = document.getElementById("schedules-body");
const schedulesStatsEl = document.getElementById("schedules-stats");
const scheduleForm = document.getElementById("schedule-form");
const scheduleNameInput = document.getElementById("schedule-name");
const scheduleQueryInput = document.getElementById("schedule-query");
const scheduleIntervalPreset = document.getElementById("schedule-interval-preset");
const scheduleIntervalMinutesInput = document.getElementById("schedule-interval-minutes");
const scheduleIntervalWrap = document.getElementById("schedule-interval-wrap");
const scheduleIntervalCustomWrap = document.getElementById("schedule-interval-custom-wrap");
const scheduleRunModeInput = document.getElementById("schedule-run-mode");
const scheduleCooldownInput = document.getElementById("schedule-cooldown-minutes");
const scheduleCooldownWrap = document.getElementById("schedule-cooldown-wrap");
const schedulerStatusEl = document.getElementById("scheduler-status");
const scheduleMinScoreInput = document.getElementById("schedule-min-score");
const scheduleAutoImportInput = document.getElementById("schedule-auto-import");
const refreshSchedulesBtn = document.getElementById("refresh-schedules-btn");
const settingsView = document.getElementById("settings-view");
const settingsForm = document.getElementById("settings-form");
const settingsStatusEl = document.getElementById("settings-status");
const emailTemplatesListEl = document.getElementById("email-templates-list");
const templateNameInput = document.getElementById("template-name");
const templateSubjectInput = document.getElementById("template-subject");
const templateBodyInput = document.getElementById("template-body");
const saveTemplateBtn = document.getElementById("save-template-btn");
const templateStatusEl = document.getElementById("template-status");
const mailTemplateSelect = document.getElementById("mail-template-select");
const pageTitle = document.getElementById("page-title");
const pageSubtitle = document.getElementById("page-subtitle");
const tabs = document.querySelectorAll(".tab");
const leadQueryInput = document.getElementById("lead-query");
const llmStatusEl = document.getElementById("llm-status");
const minScoreInput = document.getElementById("min-score");
const autoImportInput = document.getElementById("auto-import");
const discoverBtn = document.getElementById("discover-btn");
const discoverViaPiBtn = document.getElementById("discover-via-pi-btn");
const aiPlanEl = document.getElementById("ai-plan");
const aiSourcesEl = document.getElementById("ai-sources");
const aiProgressEl = document.getElementById("ai-progress");
const aiProgressFill = document.getElementById("ai-progress-fill");
const aiProgressText = document.getElementById("ai-progress-text");
const aiStatsEl = document.getElementById("ai-stats");
const aiLeadsBody = document.getElementById("ai-leads-body");
const aiLeadsStateEl = document.getElementById("ai-leads-state");
const aiChannelsEl = document.getElementById("ai-channels");
const importLeadsBtn = document.getElementById("import-leads-btn");
const retryDiscoverBtn = document.getElementById("retry-discover-btn");
const leadDetailModal = document.getElementById("lead-detail-modal");
const leadDetailBody = document.getElementById("lead-detail-body");
const leadDetailImport = document.getElementById("lead-detail-import");
const lookupBackgroundInput = document.getElementById("lookup-background");
const discoverBackgroundInput = document.getElementById("discover-background");
const backgroundJobsBar = document.getElementById("background-jobs-bar");
let detailLeadIndex = null;

const backgroundJobTrackers = new Map();

let allRows = [];
let csvContent = "";
let contacts = [];
let contactsPage = 1;
let contactsPages = 1;
let contactsTotal = 0;
let contactsPageSize = 50;
const selectedContactIds = new Set();
let editingContactId = null;
let notesContactId = null;

const FOLLOW_UP_STATUS_KEYS = ["new", "contacted", "replied", "invalid", "interested"];
let schedules = [];
let scheduleRuns = {};
let schedulerStatus = null;
let schedulesRefreshTimer = null;
let aiLeads = [];
const CHANNEL_DEFS = [
  { key: "peeringdb", nameKey: "channel.peeringdb" },
  { key: "shodan", nameKey: "channel.shodan" },
  { key: "web_search", nameKey: "channel.webSearch" },
  { key: "web_regex", nameKey: "channel.webRegex" },
  { key: "linkedin", nameKey: "channel.linkedin" },
  { key: "x", nameKey: "channel.x" },
  { key: "facebook", nameKey: "channel.facebook" },
  { key: "llm_extract", nameKey: "channel.llmExtract" },
  { key: "arin", nameKey: "channel.arin" },
  { key: "scoring", nameKey: "channel.scoring" },
];
let channelState = {};
let discoverController = null;
let lastDiscoverQuery = "";
let llmConfigured = false;
let currentUserId = null;
const PI_CHAT_STORAGE_VERSION = "v1";
const PI_THREADS_STORAGE_VERSION = "v2";
const PI_CHAT_MAX_STORED = 800;
const PI_THREADS_MAX = 30;
let piThreads = [];
let activePiThreadId = null;
let piChatHistory = [];
let piChatController = null;
let piChatBusy = false;
const PI_LEAD_STREAM_TOOLS = new Set(["discover_leads", "enrich_contact"]);
const PI_CHANNEL_ICON = { idle: "·", active: "◐", done: "✓", failed: "×" };
const PI_SOURCE_CHANNEL_MAP = {
  peeringdb: "peeringdb",
  shodan: "shodan",
  web_search: "web_search",
  web_regex: "web_regex",
  llm_extract: "llm_extract",
  linkedin: "linkedin",
  x: "x",
  facebook: "facebook",
};
let emailTemplates = [];
let editingTemplateId = null;
let contactSearchTimer = null;

async function api(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error(t("msg.loginRequired"));
  }

  if (!response.ok) {
    let detail = t("msg.requestFailed");
    try {
      const error = await response.json();
      detail = formatApiDetail(error.detail) || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  if (response.status === 204) return null;
  return response.json();
}

function formatApiDetail(detail) {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item?.msg) return item.msg;
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (typeof detail === "object") {
    return detail.message || detail.msg || JSON.stringify(detail);
  }
  return String(detail);
}

function errorMessage(error, fallback) {
  if (!error) return fallback;
  if (typeof error === "string") return error;
  if (error.message) return error.message;
  return fallback;
}

function setLoading(isLoading) {
  lookupBtn.disabled = isLoading;
  exportBtn.disabled = isLoading || allRows.length === 0;
  importBtn.disabled = isLoading || getSelectedImportableRows().length === 0;
}

function getImportableRows() {
  return allRows.filter((row) => row.email && !row.error);
}

function ensureRowSelected(row) {
  if (row.email && !row.error && row._selected === undefined) {
    row._selected = true;
  }
}

function getSelectedImportableRows() {
  return getImportableRows().filter((row) => row._selected !== false);
}

function updateStats() {
  const visibleRows = getVisibleRows();
  const uniqueAsns = new Set(visibleRows.map((row) => row.asn)).size;
  const emails = visibleRows.filter((row) => row.email).length;
  const errors = visibleRows.filter((row) => row.error).length;
  const importable = getImportableRows().length;
  const selected = getSelectedImportableRows().length;
  const selection = importable > 0 ? t("msg.lookupStatsSelectionFull", { selected, importable }) : "";
  statsEl.textContent = t("msg.lookupStats", { asns: uniqueAsns, emails, errors, selection });
}

function getVisibleRows() {
  const role = roleFilter.value;
  if (!role) return allRows;
  return allRows.filter((row) => row.roles.includes(role));
}

function renderRows() {
  const rows = getVisibleRows();
  resultsBody.innerHTML = "";

  if (rows.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="9">${allRows.length ? t("msg.filterNoResults") : t("lookup.emptyHint")}</td>`;
    resultsBody.appendChild(tr);
    updateStats();
    importBtn.disabled = getSelectedImportableRows().length === 0;
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    const rowIndex = allRows.indexOf(row);
    const roles = row.roles.map((role) => `<span class="role-tag">${role}</span>`).join("");
    const emailCell = row.email
      ? `<a class="email-link" href="mailto:${row.email}">${row.email}</a>`
      : "—";
    const statusClass = row.error ? "status-error" : row.email ? "status-ok" : "status-warn";
    const statusText = row.error || (row.email ? "OK" : t("msg.noEmail"));
    const importable = Boolean(row.email && !row.error);
    ensureRowSelected(row);
    const selectCell = importable
      ? `<input type="checkbox" class="row-import-check" data-kind="lookup" data-index="${rowIndex}" ${row._selected !== false ? "checked" : ""}>`
      : "—";

    tr.innerHTML = `
      <td class="col-select">${selectCell}</td>
      <td class="mono">AS${row.asn}</td>
      <td>${escapeHtml(row.org || "—")}</td>
      <td>${roles || "—"}</td>
      <td>${escapeHtml(row.name || "—")}</td>
      <td class="col-email">${emailCell}</td>
      <td class="mono">${escapeHtml(row.handle || "—")}</td>
      <td>${escapeHtml(row.rir || "—")}</td>
      <td class="${statusClass}">${escapeHtml(statusText)}</td>
    `;
    resultsBody.appendChild(tr);
  }

  updateStats();
  importBtn.disabled = getSelectedImportableRows().length === 0;
}

function followUpStatusBadge(status) {
  const key = status || "new";
  const label = followUpLabel(key);
  return `<span class="status-badge follow-up-${escapeHtml(key)}">${escapeHtml(label)}</span>`;
}

function closeAllContactActionMenus() {
  document.querySelectorAll(".contact-action-menu .action-menu-panel").forEach((panel) => {
    panel.classList.add("hidden");
    panel.classList.remove("is-floating", "opens-up");
    panel.style.top = "";
    panel.style.left = "";
    panel.style.visibility = "";
  });
  document.querySelectorAll(".contact-action-menu .action-menu-toggle").forEach((toggle) => {
    toggle.setAttribute("aria-expanded", "false");
  });
}

function positionContactActionMenu(toggle, panel) {
  panel.classList.add("is-floating");
  panel.classList.remove("hidden", "opens-up");
  panel.style.visibility = "hidden";
  panel.style.top = "0px";
  panel.style.left = "0px";

  const toggleRect = toggle.getBoundingClientRect();
  const panelRect = panel.getBoundingClientRect();
  const gap = 6;
  const pad = 8;

  let top = toggleRect.bottom + gap;
  let left = toggleRect.right - panelRect.width;

  if (top + panelRect.height > window.innerHeight - pad) {
    top = toggleRect.top - panelRect.height - gap;
    panel.classList.add("opens-up");
  }

  left = Math.max(pad, Math.min(left, window.innerWidth - panelRect.width - pad));
  top = Math.max(pad, Math.min(top, window.innerHeight - panelRect.height - pad));

  panel.style.top = `${Math.round(top)}px`;
  panel.style.left = `${Math.round(left)}px`;
  panel.style.visibility = "";
}

function socialLinksHtml(contact) {
  const links = [];
  if (contact.linkedin) {
    links.push(`<a class="social-link" href="${escapeHtml(contact.linkedin)}" target="_blank" rel="noopener" title="LinkedIn">in</a>`);
  }
  if (contact.x) {
    links.push(`<a class="social-link" href="${escapeHtml(contact.x)}" target="_blank" rel="noopener" title="X">X</a>`);
  }
  if (contact.facebook) {
    links.push(`<a class="social-link" href="${escapeHtml(contact.facebook)}" target="_blank" rel="noopener" title="Facebook">fb</a>`);
  }
  if (!links.length) return "";
  return `<span class="contact-social-links">${links.join("")}</span>`;
}

function contactActionsHtml(contact) {
  const id = contact.id;
  const status = escapeHtml(contact.follow_up_status || "new");
  const sent = contact.email_sent ? "0" : "1";
  const markLabel = contact.email_sent ? t("contacts.actionUnmark") : t("contacts.actionMarkSent");
  const menuItem = (className, label, extra = "") =>
    `<button type="button" class="action-menu-item link-btn ${className}" role="menuitem" data-id="${id}"${extra}>${label}</button>`;

  return `
    <div class="contact-actions">
      <div class="contact-actions-primary">
        <button type="button" class="link-btn action-edit" data-id="${id}">${t("contacts.actionEdit")}</button>
        <button type="button" class="link-btn action-mail" data-id="${id}">${t("contacts.actionMail")}</button>
      </div>
      <div class="contact-action-menu">
        <button type="button" class="action-menu-toggle" aria-label="${t("contacts.moreActions")}" aria-expanded="false" aria-haspopup="menu">⋯</button>
        <div class="action-menu-panel hidden" role="menu">
          ${menuItem("action-enrich-pi", t("contacts.actionEnrich"))}
          ${menuItem("action-edit", t("contacts.actionEdit"))}
          ${menuItem("action-notes", t("contacts.actionTimeline"))}
          ${menuItem("action-mail", t("contacts.actionMail"))}
          ${menuItem("action-status", t("contacts.actionStatus"), ` data-status="${status}"`)}
          ${menuItem("action-mark", markLabel, ` data-sent="${sent}"`)}
          ${menuItem("action-delete", t("contacts.actionDelete"))}
        </div>
      </div>
    </div>
  `;
}

function updateContactsMetrics(total, sentOnPage, unsentOnPage) {
  if (contactsMetricTotalEl) contactsMetricTotalEl.textContent = String(total ?? 0);
  if (contactsMetricSentEl) contactsMetricSentEl.textContent = String(sentOnPage ?? 0);
  if (contactsMetricUnsentEl) contactsMetricUnsentEl.textContent = String(unsentOnPage ?? 0);
}

function renderContacts() {
  contactsBody.innerHTML = "";
  updateContactsBulkBar();

  if (contacts.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="11">${t("msg.contactsEmptyImportHint")}</td>`;
    contactsBody.appendChild(tr);
    contactsStatsEl.textContent = contactsTotal
      ? t("msg.contactsStatsEmptyPage", { total: contactsTotal })
      : t("msg.contactsEmpty");
    updateContactsMetrics(contactsTotal, 0, 0);
    renderContactsPagination();
    return;
  }

  let sentCount = 0;
  for (const contact of contacts) {
    if (contact.email_sent) sentCount += 1;
    const tr = document.createElement("tr");
    if (contact.email_sent) tr.classList.add("row-sent");
    const roles = (contact.roles || "")
      .split(",")
      .filter(Boolean)
      .map((role) => `<span class="role-tag">${escapeHtml(role)}</span>`)
      .join("");
    const statusBadge = followUpStatusBadge(contact.follow_up_status);
    const checked = selectedContactIds.has(contact.id) ? "checked" : "";
    const notesText = contact.notes || "";
    const notesCell = notesText
      ? `<span class="notes-truncate" title="${escapeHtml(notesText)}">${escapeHtml(notesText)}</span>`
      : "—";

    tr.innerHTML = `
      <td class="col-select"><input type="checkbox" class="contact-select" data-id="${contact.id}" ${checked}></td>
      <td>${statusBadge}</td>
      <td class="col-org">${escapeHtml(contact.org || "—")}</td>
      <td class="col-name">${escapeHtml(contact.name || "—")}${socialLinksHtml(contact)}</td>
      <td class="col-email"><a class="email-link" href="mailto:${contact.email}">${escapeHtml(contact.email)}</a></td>
      <td class="col-role">${roles || "—"}</td>
      <td class="col-asn mono">${contact.asn ? `AS${contact.asn}` : "—"}</td>
      <td class="col-source">${escapeHtml(contact.source || "arin")}</td>
      <td class="col-notes">${notesCell}</td>
      <td class="col-imported mono">${escapeHtml(formatTime(contact.email_sent ? contact.email_sent_at : contact.created_at))}</td>
      <td class="action-cell col-actions">${contactActionsHtml(contact)}</td>
    `;
    contactsBody.appendChild(tr);
  }

  contactsStatsEl.textContent = t("msg.contactsStats", {
    total: contactsTotal,
    pageCount: contacts.length,
    sent: sentCount,
    page: contactsPage,
    pages: contactsPages,
  });
  updateContactsMetrics(contactsTotal, sentCount, contacts.length - sentCount);
  renderContactsPagination();
  syncContactsSelectAllCheckbox();
}

function updateContactsBulkBar() {
  const count = selectedContactIds.size;
  contactsBulkBar.classList.toggle("hidden", count === 0);
  contactsSelectedCountEl.textContent = t("msg.contactsSelected", { count });
}

function syncContactsSelectAllCheckbox() {
  if (!contactsSelectAll) return;
  const pageIds = contacts.map((c) => c.id);
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedContactIds.has(id));
  contactsSelectAll.checked = allSelected;
  contactsSelectAll.indeterminate = !allSelected && pageIds.some((id) => selectedContactIds.has(id));
}

function renderContactsPagination() {
  if (contactsTotal === 0) {
    contactsPagination.classList.add("hidden");
    return;
  }
  contactsPagination.classList.remove("hidden");
  contactsPageInfo.textContent = t("msg.contactsPage", {
    page: contactsPage,
    pages: contactsPages,
    total: contactsTotal,
  });
  contactsPrevBtn.disabled = contactsPage <= 1;
  contactsNextBtn.disabled = contactsPage >= contactsPages;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}

function rowsToCsv(rows) {
  const headers = ["asn", "org", "roles", "name", "email", "handle", "rir", "error"];
  const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(
      [
        row.asn,
        row.org,
        row.roles.join(","),
        row.name,
        row.email,
        row.handle,
        row.rir,
        row.error,
      ]
        .map(escape)
        .join(",")
    );
  }
  return lines.join("\n");
}

function downloadCsv() {
  if (!csvContent) return;
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `arin_asn_roles_${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

async function runLookup() {
  const text = asnInput.value.trim();
  if (!text) {
    alert(t("msg.enterAsnList"));
    return;
  }

  if (lookupBackgroundInput?.checked) {
    try {
      const delay = Number(delayInput.value) || 0;
      const data = await api("/api/jobs/lookup", {
        method: "POST",
        body: JSON.stringify({ text, delay, timeout: 20 }),
      });
      trackBackgroundJob(data.job);
      alert(t("msg.jobStartedBackground"));
    } catch (error) {
      alert(errorMessage(error, t("msg.lookupFailed")));
    }
    return;
  }

  allRows = [];
  csvContent = "";
  renderRows();
  setLoading(true);
  progressEl.classList.remove("hidden");
  progressFill.style.width = "0%";
  progressText.textContent = t("msg.lookupStarting");

  const delay = Number(delayInput.value) || 0;

  try {
    const response = await fetch("/api/lookup/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, delay }),
    });

    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    if (!response.ok) {
      const error = await response.json();
      throw new Error(formatApiDetail(error.detail) || t("msg.lookupFailedShort"));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const line = chunk.trim();
        if (!line.startsWith("data: ")) continue;
        const payload = JSON.parse(line.slice(6));

        if (payload.type === "parsed") {
          progressText.textContent = t("msg.lookupDeduped", { total: payload.total });
          renderAsnPreview({
            asns: payload.asns,
            total: payload.total,
            max: 200,
            over_limit: payload.total > 200,
          });
        }

        if (payload.type === "progress") {
          for (const row of payload.rows) {
            ensureRowSelected(row);
          }
          allRows.push(...payload.rows);
          renderRows();
          const percent = Math.round((payload.index / payload.total) * 100);
          progressFill.style.width = `${percent}%`;
          progressText.textContent = t("msg.lookupProgress", {
            asn: payload.asn,
            index: payload.index,
            total: payload.total,
          });
        }

        if (payload.type === "done") {
          progressFill.style.width = "100%";
          progressText.textContent = t("msg.lookupDone");
          csvContent = rowsToCsv(allRows);
          exportBtn.disabled = allRows.length === 0;
          importBtn.disabled = getSelectedImportableRows().length === 0;
        }
      }
    }
  } catch (error) {
    alert(errorMessage(error, t("msg.lookupFailed")));
    progressText.textContent = t("msg.lookupFailedShort");
  } finally {
    setLoading(false);
  }
}

function formatImportResult(result) {
  const filtered = result.filtered ? t("msg.importFiltered", { filtered: result.filtered }) : "";
  return t("msg.importDone", {
    imported: result.imported,
    duplicates: result.duplicates,
    skipped: result.skipped,
    filtered,
  });
}

function normalizeImportRow(row) {
  if (!row || typeof row !== "object") return row;
  const roles = row.roles;
  const normalized = {
    asn: row.asn ?? null,
    org: String(row.org || row.organization || row.company || row.network_name || "").trim(),
    name: String(row.name || row.contact_name || row.contact || row.fn || "").trim(),
    email: String(row.email || "").trim(),
    roles: Array.isArray(roles) ? roles : String(roles || "").split(",").map((part) => part.trim()).filter(Boolean),
    handle: row.handle || "",
    rir: row.rir || "",
    source: row.source || "",
    notes: row.notes || "",
    linkedin: String(row.linkedin || row.linkedin_url || "").trim(),
    x: String(row.x || row.x_url || row.twitter || row.twitter_url || "").trim(),
    facebook: String(row.facebook || row.facebook_url || "").trim(),
    profile_url: String(row.profile_url || "").trim(),
  };
  const source = String(row.source || "").toLowerCase();
  const profileUrl = normalized.profile_url;
  if (profileUrl) {
    if (source === "linkedin" && !normalized.linkedin) normalized.linkedin = profileUrl;
    if (source === "x" && !normalized.x) normalized.x = profileUrl;
    if (source === "facebook" && !normalized.facebook) normalized.facebook = profileUrl;
  }
  return normalized;
}

function normalizeImportRows(rows) {
  return (rows || []).map((row) => normalizeImportRow(row));
}

let asnParseTimer = null;

function renderAsnPreview(data) {
  if (!asnParsePreviewEl) return;
  if (!data || !data.total) {
    asnParsePreviewEl.textContent = data ? t("msg.noValidAsn") : "";
    return;
  }
  const sample = (data.asns || []).slice(0, 8).map((asn) => `AS${asn}`).join(", ");
  const suffix = data.total > 8 ? t("msg.asnPreviewSuffix", { total: data.total }) : "";
  const limitNote = data.over_limit ? t("msg.asnOverLimit", { max: data.max }) : "";
  asnParsePreviewEl.textContent = t("msg.asnPreview", {
    total: data.total,
    sample,
    suffix,
    limitNote,
  });
}

async function refreshAsnPreview() {
  const text = asnInput.value.trim();
  if (!text) {
    renderAsnPreview(null);
    return;
  }
  try {
    const data = await api("/api/lookup/parse", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    renderAsnPreview(data);
  } catch {
    asnParsePreviewEl.textContent = "";
  }
}

async function importResults() {
  const rows = getSelectedImportableRows();
  if (rows.length === 0) {
    alert(t("msg.selectEmailsToImport"));
    return;
  }

  importBtn.disabled = true;
  try {
    const result = await api("/api/contacts/import", {
      method: "POST",
      body: JSON.stringify({ rows: normalizeImportRows(rows) }),
    });
    alert(formatImportResult(result));
    await loadContacts();
    switchView("contacts");
  } catch (error) {
    alert(error.message || t("msg.importFailed"));
  } finally {
    importBtn.disabled = getSelectedImportableRows().length === 0;
  }
}

async function loadContacts(resetPage = false) {
  if (resetPage) contactsPage = 1;
  const status = contactStatusFilter.value || "all";
  const followUp = contactFollowUpFilter.value || "all";
  const params = new URLSearchParams({
    status,
    follow_up_status: followUp,
    page: String(contactsPage),
    page_size: String(contactsPageSize),
  });
  const q = contactSearchInput.value.trim();
  if (q) params.set("q", q);
  const data = await api(`/api/contacts?${params.toString()}`);
  contacts = data.contacts || [];
  contactsTotal = data.total || 0;
  contactsPage = data.page || 1;
  contactsPages = data.pages || 1;
  contactsPageSize = data.page_size || contactsPageSize;
  renderContacts();
}

function getSelectedContactIds() {
  return [...selectedContactIds];
}

async function bulkContactsAction(action, extra = {}) {
  const ids = getSelectedContactIds();
  if (ids.length === 0) {
    alert(t("msg.selectContacts"));
    return;
  }
  const payload = { ids, action, ...extra };
  const result = await api("/api/contacts/bulk", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  selectedContactIds.clear();
  await loadContacts();
  return result;
}

function openContactEdit(contactId) {
  const contact = contacts.find((item) => String(item.id) === String(contactId));
  if (!contact) return;
  editingContactId = contact.id;
  contactEditSubtitle.textContent = contact.email;
  contactEditOrg.value = contact.org || "";
  contactEditName.value = contact.name || "";
  contactEditRoles.value = contact.roles || "";
  contactEditNotes.value = contact.notes || "";
  contactEditLinkedin.value = contact.linkedin || "";
  contactEditX.value = contact.x || "";
  contactEditFacebook.value = contact.facebook || "";
  contactEditModal.classList.remove("hidden");
}

function closeContactEdit() {
  editingContactId = null;
  contactEditModal.classList.add("hidden");
}

async function saveContactEdit(event) {
  event.preventDefault();
  if (!editingContactId) return;
  await api(`/api/contacts/${editingContactId}`, {
    method: "PATCH",
    body: JSON.stringify({
      org: contactEditOrg.value,
      name: contactEditName.value,
      roles: contactEditRoles.value,
      notes: contactEditNotes.value,
      linkedin: contactEditLinkedin.value,
      x: contactEditX.value,
      facebook: contactEditFacebook.value,
    }),
  });
  closeContactEdit();
  await loadContacts();
}

async function downloadBackup() {
  const response = await fetch("/api/backup", { credentials: "same-origin" });
  if (response.status === 401) {
    window.location.href = "/login";
    return;
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || t("msg.backupFailed"));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  link.download = match?.[1] || `salescrm_backup_${new Date().toISOString().slice(0, 10)}.db`;
  link.click();
  URL.revokeObjectURL(url);
}

async function exportContactsCsv() {
  const params = new URLSearchParams({
    status: contactStatusFilter.value || "all",
    follow_up_status: contactFollowUpFilter.value || "all",
  });
  const q = contactSearchInput.value.trim();
  if (q) params.set("q", q);
  const response = await fetch(`/api/contacts/export?${params.toString()}`, {
    credentials: "same-origin",
  });
  if (response.status === 401) {
    window.location.href = "/login";
    return;
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || t("msg.exportFailed"));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `contacts_${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

async function dedupeContacts() {
  const result = await api("/api/contacts/dedupe", { method: "POST" });
  alert(t("msg.dedupeDone", { removed: result.removed, total: result.total }));
  await loadContacts();
}

async function markContactSent(contactId, sent) {
  await api(`/api/contacts/${contactId}/mark-sent`, {
    method: "POST",
    body: JSON.stringify({ sent }),
  });
  await loadContacts();
}

async function changeContactFollowUpStatus(contactId, currentStatus) {
  const options = followUpOptions();
  const currentLabel = followUpLabel(currentStatus);
  const lines = options.map((opt, index) => `${index + 1}. ${followUpLabel(opt)}`).join("\n");
  const input = prompt(`${t("msg.changeStatusCurrent", { label: currentLabel })}\n\n${lines}\n\n${t("msg.changeStatusInput", { max: options.length })}`);
  if (input === null) return;
  const index = Number(input.trim()) - 1;
  if (!Number.isInteger(index) || index < 0 || index >= options.length) {
    alert(t("msg.invalidIndex"));
    return;
  }
  const follow_up_status = options[index];
  await api(`/api/contacts/${contactId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ follow_up_status }),
  });
  await loadContacts();
}

function renderTemplateText(text, contact) {
  const asn = contact.asn ? String(contact.asn) : "";
  return String(text || "")
    .replaceAll("{org}", contact.org || "")
    .replaceAll("{name}", contact.name || "")
    .replaceAll("{email}", contact.email || "")
    .replaceAll("{asn}", asn)
    .replaceAll("{roles}", contact.roles || "");
}

function openMailClient(contactId) {
  const contact = contacts.find((item) => String(item.id) === String(contactId));
  if (!contact?.email) return;

  const templateId = mailTemplateSelect.value;
  const template = emailTemplates.find((item) => String(item.id) === templateId);
  let url = `mailto:${encodeURIComponent(contact.email)}`;
  if (template) {
    const params = new URLSearchParams();
    const subject = renderTemplateText(template.subject, contact);
    const body = renderTemplateText(template.body, contact);
    if (subject) params.set("subject", subject);
    if (body) params.set("body", body);
    const query = params.toString();
    if (query) url += `?${query}`;
  }
  window.location.href = url;
  if (!contact.email_sent && confirm(t("msg.confirmMarkSent"))) {
    markContactSent(contactId, true).catch((error) => alert(error.message));
  }
}

function renderMailTemplateSelect() {
  const current = mailTemplateSelect.value;
  mailTemplateSelect.innerHTML = `<option value="">${t("contacts.noTemplate")}</option>`;
  for (const template of emailTemplates) {
    const option = document.createElement("option");
    option.value = String(template.id);
    option.textContent = template.name;
    mailTemplateSelect.appendChild(option);
  }
  if (current && emailTemplates.some((item) => String(item.id) === current)) {
    mailTemplateSelect.value = current;
  }
}

function renderEmailTemplatesList() {
  emailTemplatesListEl.innerHTML = "";
  if (emailTemplates.length === 0) {
    emailTemplatesListEl.innerHTML = `<p class="stats">${t("msg.noTemplates")}</p>`;
    return;
  }

  for (const template of emailTemplates) {
    const item = document.createElement("div");
    item.className = "template-item";
    item.innerHTML = `
      <div class="template-item-head">
        <strong>${escapeHtml(template.name)}</strong>
        <span class="template-item-actions">
          <button type="button" class="link-btn template-edit" data-id="${template.id}">${t("templates.edit")}</button>
          <button type="button" class="link-btn template-delete" data-id="${template.id}">${t("templates.delete")}</button>
        </span>
      </div>
      <p class="stats">${escapeHtml(template.subject || t("msg.noSubject"))}</p>
    `;
    emailTemplatesListEl.appendChild(item);
  }
}

async function loadEmailTemplates() {
  const data = await api("/api/email-templates");
  emailTemplates = data.templates || [];
  renderMailTemplateSelect();
  renderEmailTemplatesList();
}

function resetTemplateForm() {
  editingTemplateId = null;
  templateNameInput.value = "";
  templateSubjectInput.value = "";
  templateBodyInput.value = "";
  saveTemplateBtn.textContent = t("settings.saveTemplate");
  templateStatusEl.textContent = "";
}

async function saveEmailTemplate() {
  const name = templateNameInput.value.trim();
  if (!name) {
    alert(t("msg.templateNameRequired"));
    return;
  }
  const payload = {
    name,
    subject: templateSubjectInput.value,
    body: templateBodyInput.value,
  };
  if (editingTemplateId) {
    await api(`/api/email-templates/${editingTemplateId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    templateStatusEl.textContent = t("msg.templateUpdated");
  } else {
    await api("/api/email-templates", { method: "POST", body: JSON.stringify(payload) });
    templateStatusEl.textContent = t("msg.templateCreated");
  }
  resetTemplateForm();
  await loadEmailTemplates();
}

async function editEmailTemplate(templateId) {
  const template = emailTemplates.find((item) => item.id === templateId);
  if (!template) return;
  editingTemplateId = templateId;
  templateNameInput.value = template.name || "";
  templateSubjectInput.value = template.subject || "";
  templateBodyInput.value = template.body || "";
  saveTemplateBtn.textContent = t("msg.updateTemplate");
  templateStatusEl.textContent = t("msg.editingTemplate", { name: template.name });
}

async function deleteEmailTemplate(templateId) {
  if (!confirm(t("msg.confirmDeleteTemplate"))) return;
  await api(`/api/email-templates/${templateId}`, { method: "DELETE" });
  if (String(editingTemplateId) === String(templateId)) {
    resetTemplateForm();
  }
  await loadEmailTemplates();
}
function formatScheduleInterval(job) {
  if ((job.run_mode || "interval") === "continuous") {
    return t("msg.scheduleContinuous", { minutes: job.cooldown_minutes || 15 });
  }
  const minutes = job.interval_minutes || (job.interval_hours || 24) * 60;
  if (minutes % 1440 === 0) {
    return t("msg.scheduleDays", { days: minutes / 1440 });
  }
  if (minutes % 60 === 0) {
    return t("msg.scheduleHoursOnly", { hours: minutes / 60 });
  }
  return t("msg.scheduleMinutesOnly", { minutes });
}

function updateScheduleFormMode() {
  const continuous = scheduleRunModeInput?.value === "continuous";
  scheduleIntervalWrap?.classList.toggle("hidden", continuous);
  scheduleIntervalCustomWrap?.classList.toggle("hidden", continuous || scheduleIntervalPreset?.value !== "custom");
  scheduleCooldownWrap?.classList.toggle("hidden", !continuous);
}

function getScheduleIntervalMinutes() {
  if (scheduleIntervalPreset?.value === "custom") {
    return Number(scheduleIntervalMinutesInput?.value) || 1440;
  }
  return Number(scheduleIntervalPreset?.value) || 1440;
}

function renderSchedulerStatus() {
  if (!schedulerStatusEl) return;
  if (!schedulerStatus) {
    schedulerStatusEl.textContent = "";
    return;
  }
  if (!schedulerStatus.enabled) {
    schedulerStatusEl.textContent = t("msg.schedulerDisabledHint");
    schedulerStatusEl.className = "stats scheduler-status warn";
    return;
  }
  if (!schedulerStatus.llm_configured) {
    schedulerStatusEl.textContent = t("msg.schedulerLlmMissing");
    schedulerStatusEl.className = "stats scheduler-status warn";
    return;
  }
  const running = schedulerStatus.active_jobs > 0
    ? t("msg.schedulerRunningJobs", { count: schedulerStatus.active_jobs })
    : t("msg.schedulerIdle");
  schedulerStatusEl.textContent = t("msg.schedulerStatusLine", {
    poll: schedulerStatus.poll_seconds,
    enabled: schedulerStatus.enabled_jobs,
    running,
  });
  schedulerStatusEl.className = "stats scheduler-status ok";
}

function formatJobRunLine(run) {
  const statusLabel = run.status === "ok" ? t("msg.scheduleRunOk") : t("msg.scheduleRunFail");
  const detail =
    run.status === "ok"
      ? t("msg.scheduleRunDetail", { leads: run.leads_found, imported: run.imported })
      : escapeHtml(run.message || statusLabel);
  return `<li><span class="run-time">${escapeHtml(formatTime(run.ran_at))}</span> <span class="run-status run-${escapeHtml(run.status)}">${statusLabel}</span> ${detail}</li>`;
}

function renderSchedules() {
  schedulesBody.innerHTML = "";
  if (schedules.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="7">${t("schedules.empty")}</td>`;
    schedulesBody.appendChild(tr);
    schedulesStatsEl.textContent = t("msg.noSchedules");
    return;
  }

  for (const job of schedules) {
    const tr = document.createElement("tr");
    const enabledBadge = job.enabled
      ? `<span class="status-badge sent">${t("msg.scheduleEnabled")}</span>`
      : `<span class="status-badge unsent">${t("msg.scheduleDisabled")}</span>`;
    const runningBadge = job.running_at
      ? `<span class="status-badge contacted">${t("msg.scheduleRunning")}</span>`
      : "";
    tr.innerHTML = `
      <td>${escapeHtml(job.name)}</td>
      <td class="mono">${escapeHtml(formatScheduleInterval(job))}</td>
      <td>${enabledBadge}${runningBadge}</td>
      <td class="mono">${escapeHtml(formatTime(job.last_run_at))}</td>
      <td class="mono">${escapeHtml(formatTime(job.next_run_at))}</td>
      <td>${escapeHtml(job.last_run_message || job.last_run_status || "—")}</td>
      <td class="action-cell">
        <button type="button" class="link-btn schedule-run" data-id="${job.id}">${t("msg.scheduleRunNow")}</button>
        <button type="button" class="link-btn schedule-toggle" data-id="${job.id}" data-enabled="${job.enabled ? "0" : "1"}">${job.enabled ? t("msg.scheduleToggleOff") : t("msg.scheduleToggleOn")}</button>
        <button type="button" class="link-btn schedule-delete" data-id="${job.id}">${t("contacts.actionDelete")}</button>
      </td>
    `;
    schedulesBody.appendChild(tr);

    const runs = scheduleRuns[job.id] || [];
    if (runs.length > 0) {
      const runsTr = document.createElement("tr");
      runsTr.className = "schedule-runs-row";
      runsTr.innerHTML = `<td colspan="7"><ul class="schedule-runs-list">${runs.map(formatJobRunLine).join("")}</ul></td>`;
      schedulesBody.appendChild(runsTr);
    }
  }
  schedulesStatsEl.textContent = t("msg.schedulesCount", { count: schedules.length });
}

async function loadSchedules() {
  const data = await api("/api/schedules");
  schedules = data.schedules || [];
  schedulerStatus = data.scheduler || null;
  scheduleRuns = {};
  await Promise.all(
    schedules.map(async (job) => {
      const runData = await api(`/api/schedules/${job.id}/runs?limit=5`);
      scheduleRuns[job.id] = runData.runs || [];
    }),
  );
  renderSchedules();
  renderSchedulerStatus();
}

function startSchedulesAutoRefresh() {
  stopSchedulesAutoRefresh();
  schedulesRefreshTimer = window.setInterval(() => {
    loadSchedules().catch(() => {});
  }, 30000);
}

function stopSchedulesAutoRefresh() {
  if (schedulesRefreshTimer) {
    window.clearInterval(schedulesRefreshTimer);
    schedulesRefreshTimer = null;
  }
}

async function createSchedule(event) {
  event.preventDefault();
  const runMode = scheduleRunModeInput?.value || "continuous";
  await api("/api/schedules", {
    method: "POST",
    body: JSON.stringify({
      name: scheduleNameInput.value.trim(),
      query: scheduleQueryInput.value.trim(),
      run_mode: runMode,
      interval_minutes: getScheduleIntervalMinutes(),
      cooldown_minutes: Number(scheduleCooldownInput?.value) || 15,
      min_score: Number(scheduleMinScoreInput.value) || 60,
      auto_import: scheduleAutoImportInput.checked,
      enabled: true,
    }),
  });
  scheduleForm.reset();
  scheduleAutoImportInput.checked = true;
  scheduleMinScoreInput.value = "60";
  if (scheduleRunModeInput) scheduleRunModeInput.value = "continuous";
  if (scheduleIntervalPreset) scheduleIntervalPreset.value = "1440";
  if (scheduleCooldownInput) scheduleCooldownInput.value = "15";
  updateScheduleFormMode();
  await loadSchedules();
}

async function toggleSchedule(jobId, enabled) {
  await api(`/api/schedules/${jobId}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
  await loadSchedules();
}

async function deleteSchedule(jobId) {
  if (!confirm(t("msg.confirmDeleteSchedule"))) return;
  await api(`/api/schedules/${jobId}`, { method: "DELETE" });
  await loadSchedules();
}

async function runScheduleNow(jobId) {
  if (!confirm(t("msg.confirmRunSchedule"))) return;
  const result = await api(`/api/schedules/${jobId}/run`, { method: "POST" });
  if (result.ok) {
    alert(result.message || t("msg.runDone"));
  } else {
    alert(result.message || t("msg.runFailed"));
  }
  await loadSchedules();
  await loadContacts();
}

function setInputValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value ?? "";
}

const SETTINGS_FORM_CATS = new Set(["account", "ai", "import", "automation"]);
let activeSettingsCat = "account";

function switchSettingsCat(cat) {
  activeSettingsCat = cat;
  document.querySelectorAll(".settings-rail-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.settingsCat === cat);
  });
  document.querySelectorAll(".settings-pane").forEach((pane) => {
    pane.classList.toggle("hidden", pane.dataset.settingsPane !== cat);
  });
  const footer = document.getElementById("settings-footer");
  footer.classList.toggle("hidden", !SETTINGS_FORM_CATS.has(cat));
}

function updateSettingsRailDots(data) {
  const aiDot = document.getElementById("rail-dot-ai");
  const aiOn = Boolean(data.llm_api_key_configured);
  aiDot.classList.toggle("on", aiOn);
  aiDot.title = aiOn ? t("msg.llmConfigured") : t("settings.llmNotConfigured");

  const autoDot = document.getElementById("rail-dot-automation");
  const autoOn = data.scheduler_enabled === "1";
  autoDot.classList.toggle("on", autoOn || Boolean(data.agent_api_token_configured));
  const parts = [];
  parts.push(autoOn ? t("msg.automationStatus") : t("msg.automationStatusOff"));
  if (data.agent_api_token_configured) parts.push(t("msg.piAgentConfigured"));
  autoDot.title = parts.join(" · ");
}

async function regenerateAgentToken() {
  const data = await api("/api/settings/agent-token/regenerate", { method: "POST" });
  const el = document.getElementById("setting-agent-api-token");
  el.value = data.agent_api_token;
  el.dataset.revealed = "1";
  document.getElementById("agent-token-status").textContent = t("msg.tokenRegenerated");
}

async function copyAgentToken() {
  const el = document.getElementById("setting-agent-api-token");
  const value = el.value.trim();
  if (!value) {
    alert(t("msg.generateTokenFirst"));
    return;
  }
  await navigator.clipboard.writeText(value);
  document.getElementById("agent-token-status").textContent = t("msg.tokenCopied");
}

async function loadSettingsForm() {
  const data = await api("/api/settings");
  setInputValue("setting-default-admin-user", data.default_admin_user);
  setInputValue("setting-llm-base-url", data.llm_base_url);
  setInputValue("setting-llm-model", data.llm_model);
  setInputValue("setting-zhipu-search-engine", data.zhipu_search_engine || "search_pro");
  setInputValue("setting-brightdata-serp-zone", data.brightdata_serp_zone || "");
  setInputValue("setting-brightdata-serp-format", data.brightdata_serp_data_format || "auto");
  setInputValue("setting-brightdata-linkedin-dataset", data.brightdata_linkedin_dataset_id || "");
  document.getElementById("setting-brightdata-linkedin-enabled").checked =
    (data.brightdata_linkedin_enabled || "0") === "1";
  setInputValue("setting-brightdata-x-dataset", data.brightdata_x_dataset_id || "");
  document.getElementById("setting-brightdata-x-enabled").checked =
    (data.brightdata_x_enabled || "0") === "1";
  setInputValue("setting-brightdata-facebook-dataset", data.brightdata_facebook_dataset_id || "");
  document.getElementById("setting-brightdata-facebook-enabled").checked =
    (data.brightdata_facebook_enabled || "0") === "1";
  document.getElementById("setting-shodan-enabled").checked = (data.shodan_enabled || "0") === "1";
  setInputValue("setting-scheduler-poll-seconds", data.scheduler_poll_seconds);
  document.getElementById("setting-scheduler-enabled").checked = data.scheduler_enabled === "1";

  const agentTokenEl = document.getElementById("setting-agent-api-token");
  if (agentTokenEl && !agentTokenEl.dataset.revealed) {
    agentTokenEl.value = "";
    agentTokenEl.placeholder = data.agent_api_token_configured
      ? t("msg.agentTokenConfigured", { token: data.agent_api_token })
      : t("settings.agentTokenPlaceholder");
  }

  const secretFields = [
    ["setting-default-admin-password", data.default_admin_password, data.default_admin_password_configured],
    ["setting-session-secret", data.session_secret, data.session_secret_configured],
    ["setting-llm-api-key", data.llm_api_key, data.llm_api_key_configured],
    ["setting-tavily-api-key", data.tavily_api_key, data.tavily_api_key_configured],
    ["setting-brightdata-api-key", data.brightdata_api_key, data.brightdata_api_key_configured],
    ["setting-serpapi-key", data.serpapi_key, data.serpapi_key_configured],
    ["setting-brave-search-key", data.brave_search_key, data.brave_search_key_configured],
    ["setting-zhipu-api-key", data.zhipu_api_key, data.zhipu_api_key_configured],
    ["setting-shodan-api-key", data.shodan_api_key, data.shodan_api_key_configured],
  ];
  for (const [id, masked, configured] of secretFields) {
    const el = document.getElementById(id);
    el.value = "";
    el.placeholder = configured ? t("msg.apiKeyConfigured", { masked }) : t("msg.apiKeyNotConfigured");
  }
  settingsStatusEl.textContent = "";
  updateSettingsRailDots(data);
}

async function saveSettings(event) {
  event.preventDefault();
  const payload = {
    default_admin_user: document.getElementById("setting-default-admin-user").value.trim(),
    llm_base_url: document.getElementById("setting-llm-base-url").value.trim(),
    llm_model: document.getElementById("setting-llm-model").value.trim(),
    zhipu_search_engine: document.getElementById("setting-zhipu-search-engine").value.trim(),
    brightdata_serp_zone: document.getElementById("setting-brightdata-serp-zone").value.trim(),
    brightdata_serp_data_format: document.getElementById("setting-brightdata-serp-format").value.trim(),
    brightdata_linkedin_dataset_id: document.getElementById("setting-brightdata-linkedin-dataset").value.trim(),
    brightdata_linkedin_enabled: document.getElementById("setting-brightdata-linkedin-enabled").checked
      ? "1"
      : "0",
    brightdata_x_dataset_id: document.getElementById("setting-brightdata-x-dataset").value.trim(),
    brightdata_x_enabled: document.getElementById("setting-brightdata-x-enabled").checked ? "1" : "0",
    brightdata_facebook_dataset_id: document.getElementById("setting-brightdata-facebook-dataset").value.trim(),
    brightdata_facebook_enabled: document.getElementById("setting-brightdata-facebook-enabled").checked ? "1" : "0",
    shodan_enabled: document.getElementById("setting-shodan-enabled").checked ? "1" : "0",
    scheduler_enabled: document.getElementById("setting-scheduler-enabled").checked ? "1" : "0",
    scheduler_poll_seconds: document.getElementById("setting-scheduler-poll-seconds").value.trim(),
  };

  const secrets = [
    ["default_admin_password", "setting-default-admin-password"],
    ["session_secret", "setting-session-secret"],
    ["llm_api_key", "setting-llm-api-key"],
    ["tavily_api_key", "setting-tavily-api-key"],
    ["brightdata_api_key", "setting-brightdata-api-key"],
    ["serpapi_key", "setting-serpapi-key"],
    ["brave_search_key", "setting-brave-search-key"],
    ["zhipu_api_key", "setting-zhipu-api-key"],
    ["shodan_api_key", "setting-shodan-api-key"],
  ];
  for (const [key, id] of secrets) {
    const value = document.getElementById(id).value.trim();
    if (value) payload[key] = value;
  }

  await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
  settingsStatusEl.textContent = t("msg.settingsSaved");
  await loadLlmStatus();
  await loadSettingsForm();
}

async function deleteContact(contactId) {
  if (!confirm(t("msg.confirmDeleteContact"))) return;
  await api(`/api/contacts/${contactId}`, { method: "DELETE" });
  selectedContactIds.delete(Number(contactId));
  if (String(notesContactId) === String(contactId)) {
    closeContactNotes();
  }
  if (String(editingContactId) === String(contactId)) {
    closeContactEdit();
  }
  await loadContacts();
}

function renderContactNotesList(notes) {
  contactNotesList.innerHTML = "";
  if (!notes.length) {
    const li = document.createElement("li");
    li.className = "empty-note";
    li.textContent = t("msg.noNotesYet");
    contactNotesList.appendChild(li);
    return;
  }
  for (const note of notes) {
    const li = document.createElement("li");
    li.className = "note-item";
    li.innerHTML = `
      <div class="note-item-meta">
        <span>${escapeHtml(formatTime(note.created_at))}</span>
        <button type="button" class="link-btn note-delete" data-note-id="${note.id}">${t("notes.delete")}</button>
      </div>
      <p class="note-item-body">${escapeHtml(note.body)}</p>
    `;
    contactNotesList.appendChild(li);
  }
}

async function loadContactNotes(contactId) {
  const data = await api(`/api/contacts/${contactId}/notes`);
  renderContactNotesList(data.notes || []);
}

function closeContactNotes() {
  notesContactId = null;
  contactNotesModal.classList.add("hidden");
  contactNoteBody.value = "";
}

async function openContactNotes(contactId) {
  const contact = contacts.find((item) => String(item.id) === String(contactId));
  if (!contact) return;
  notesContactId = contact.id;
  contactNotesTitle.textContent = t("contacts.notesTimeline");
  contactNotesSubtitle.textContent = `${contact.name || "—"} · ${contact.email}`;
  contactNoteBody.value = "";
  contactNotesModal.classList.remove("hidden");
  await loadContactNotes(contact.id);
}

async function addContactNote(event) {
  event.preventDefault();
  if (!notesContactId) return;
  const body = contactNoteBody.value.trim();
  if (!body) return;
  await api(`/api/contacts/${notesContactId}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
  contactNoteBody.value = "";
  await loadContactNotes(notesContactId);
}

async function deleteContactNote(noteId) {
  if (!notesContactId) return;
  if (!confirm(t("msg.confirmDeleteNote"))) return;
  await api(`/api/contacts/${notesContactId}/notes/${noteId}`, { method: "DELETE" });
  await loadContactNotes(notesContactId);
}

function renderBarChart(container, items, { getLabel = (k) => k, colors } = {}) {
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

function renderDashboard(data) {
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
      .sort((a, b) => b.count - a.count),
  );
  renderBarChart(
    chartRecentEl,
    (data.recent_imports || []).map((row) => ({ key: row.date, count: row.count })),
  );
}

async function loadStats() {
  dashboardStatsEl.textContent = t("common.loading");
  renderDashboard(await api("/api/stats"));
}

function piChatStorageKey(userId) {
  return `salescrm:pi-chat:${PI_CHAT_STORAGE_VERSION}:${userId}`;
}

function piThreadsStorageKey(userId) {
  return `salescrm:pi-threads:${PI_THREADS_STORAGE_VERSION}:${userId}`;
}

function createPiThreadId() {
  return `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function defaultPiThreadTitle() {
  return t("pi.newThreadTitle");
}

function summarizePiThreadTitle(text) {
  const line = String(text || "")
    .split("\n")
    .map((part) => part.trim())
    .find(Boolean);
  if (!line) return defaultPiThreadTitle();
  return line.length > 42 ? `${line.slice(0, 42)}…` : line;
}

function historyFingerprint(history) {
  if (!Array.isArray(history) || !history.length) return "";
  const firstUser = history.find((item) => item.role === "user");
  return firstUser?.content ? String(firstUser.content).slice(0, 96) : "";
}

function isValidHistoryItem(item) {
  if (!item?.role) return false;
  if (item.role === "user" || item.role === "assistant") {
    return Boolean(String(item.content || "").trim());
  }
  if (item.role === "tool") {
    return Boolean(item.name);
  }
  return false;
}

function normalizeHistoryItems(history) {
  return Array.isArray(history) ? history.filter(isValidHistoryItem) : [];
}

function appendPiHistoryEntry(entry) {
  piChatHistory.push(entry);
  if (piChatHistory.length > PI_CHAT_MAX_STORED) {
    piChatHistory = piChatHistory.slice(-PI_CHAT_MAX_STORED);
  }
  savePiChatHistory();
}

function getActivePiThread() {
  return piThreads.find((thread) => thread.id === activePiThreadId) || null;
}

function syncActivePiThreadHistory() {
  const thread = getActivePiThread();
  if (!thread) return;
  thread.history = piChatHistory.slice(-PI_CHAT_MAX_STORED);
  thread.updatedAt = Date.now();
}

function renderPiThreadList() {
  if (!piThreadListEl) return;
  piThreadListEl.innerHTML = "";
  if (!piThreads.length) {
    const li = document.createElement("li");
    li.className = "pi-thread-empty stats";
    li.textContent = t("pi.noThreads");
    piThreadListEl.appendChild(li);
    return;
  }
  const sorted = [...piThreads].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  for (const thread of sorted) {
    const li = document.createElement("li");
    li.className = "pi-thread-item";
    const count = Array.isArray(thread.history) ? thread.history.length : 0;
    li.innerHTML = `
      <button type="button" class="pi-thread-btn ${thread.id === activePiThreadId ? "active" : ""}" data-thread-id="${thread.id}">
        <span class="pi-thread-title">${escapeHtml(thread.title || defaultPiThreadTitle())}</span>
        <span class="pi-thread-meta">${t("pi.threadMeta", { count })}</span>
      </button>
      <button type="button" class="pi-thread-delete" data-delete-thread="${thread.id}" aria-label="${t("pi.deleteThread")}">×</button>
    `;
    piThreadListEl.appendChild(li);
  }
}

function savePiThreadsStore() {
  savePiThreadsStoreLocal();
  persistActivePiThread().catch(() => {});
}

function migratePiChatV1ToThreads(userId) {
  try {
    const raw = localStorage.getItem(piChatStorageKey(userId));
    if (!raw) return null;
    const data = JSON.parse(raw);
    const history = normalizeHistoryItems(data.history);
    if (!history.length) return null;
    const firstUser = history.find((item) => item.role === "user");
    return {
      id: createPiThreadId(),
      title: summarizePiThreadTitle(firstUser?.content || ""),
      history,
      createdAt: data.updatedAt || Date.now(),
      updatedAt: data.updatedAt || Date.now(),
    };
  } catch {
    return null;
  }
}

function recoverLegacyPiHistory(userId) {
  const legacy = migratePiChatV1ToThreads(userId);
  if (!legacy?.history?.length) return false;

  const legacyFp = historyFingerprint(legacy.history);
  if (
    piThreads.some(
      (thread) => thread.history?.length && historyFingerprint(thread.history) === legacyFp,
    )
  ) {
    return false;
  }

  const emptyMatch = piThreads.find((thread) => {
    if (thread.history?.length) return false;
    if (!thread.title || !legacy.title) return false;
    const a = thread.title.slice(0, 12);
    const b = legacy.title.slice(0, 12);
    return a === b || thread.title.includes(b) || legacy.title.includes(a);
  });
  if (emptyMatch) {
    emptyMatch.history = legacy.history;
    emptyMatch.updatedAt = Date.now();
    if (activePiThreadId === emptyMatch.id) {
      piChatHistory = [...legacy.history];
    }
    savePiThreadsStore();
    return true;
  }

  piThreads.unshift({
    ...legacy,
    id: createPiThreadId(),
    title: legacy.title || t("pi.recoveredThreadTitle"),
    updatedAt: Date.now(),
  });
  if (piThreads.length > PI_THREADS_MAX) {
    piThreads = piThreads.slice(0, PI_THREADS_MAX);
  }
  savePiThreadsStore();
  return true;
}

function mapServerPiThreadSummary(row) {
  return {
    id: row.id,
    title: row.title || "",
    history: [],
    has_context_summary: Boolean(row.has_context_summary || (row.context_summary || "").trim()),
    createdAt: row.created_at ? Date.parse(row.created_at) || Date.now() : Date.now(),
    updatedAt: row.updated_at ? Date.parse(row.updated_at) || Date.now() : Date.now(),
  };
}

function mapServerPiThreadFull(row) {
  return {
    id: row.id,
    title: row.title || "",
    history: normalizeHistoryItems(row.history),
    has_context_summary: Boolean(row.has_context_summary || (row.context_summary || "").trim()),
    createdAt: row.created_at ? Date.parse(row.created_at) || Date.now() : Date.now(),
    updatedAt: row.updated_at ? Date.parse(row.updated_at) || Date.now() : Date.now(),
  };
}

async function refreshActivePiThreadMeta() {
  if (!activePiThreadId) return;
  try {
    const thread = await api(`/api/pi/threads/${encodeURIComponent(activePiThreadId)}`);
    const index = piThreads.findIndex((item) => item.id === activePiThreadId);
    if (index >= 0) {
      piThreads[index].has_context_summary = Boolean((thread.context_summary || "").trim());
    }
    updatePiChatHistoryHint();
  } catch {
    // ignore metadata refresh failures
  }
}

async function fetchActivePiThreadHistory() {
  if (!activePiThreadId) return;
  try {
    const thread = await api(`/api/pi/threads/${encodeURIComponent(activePiThreadId)}`);
    const mapped = mapServerPiThreadFull(thread);
    const index = piThreads.findIndex((item) => item.id === mapped.id);
    if (index >= 0) {
      piThreads[index] = { ...piThreads[index], ...mapped };
    }
    piChatHistory = mapped.history;
  } catch {
    const active = getActivePiThread();
    piChatHistory = normalizeHistoryItems(active?.history);
  }
}

async function syncPiThreadsToServer() {
  if (!currentUserId) return;
  syncActivePiThreadHistory();
  await api("/api/pi/threads/sync", {
    method: "POST",
    body: JSON.stringify({
      threads: piThreads.map((thread) => ({
        id: thread.id,
        title: thread.title || "",
        history: thread.history || [],
      })),
      active_thread_id: activePiThreadId,
    }),
  });
}

async function persistActivePiThread() {
  if (!activePiThreadId) return;
  syncActivePiThreadHistory();
  const thread = getActivePiThread();
  if (!thread) return;
  await api(`/api/pi/threads/${encodeURIComponent(activePiThreadId)}`, {
    method: "PUT",
    body: JSON.stringify({
      title: thread.title || "",
      history: thread.history || [],
    }),
  });
}

async function loadPiChatFromServer(userId) {
  piThreads = [];
  activePiThreadId = null;
  piChatHistory = [];
  try {
    const data = await api("/api/pi/threads");
    piThreads = Array.isArray(data.threads)
      ? data.threads.map(mapServerPiThreadSummary).slice(0, PI_THREADS_MAX)
      : [];
  } catch {
    loadPiThreadsFromStorage(userId);
    restorePiChatUi();
    return;
  }

  if (!piThreads.length) {
    loadPiThreadsFromStorage(userId);
    if (piThreads.length) {
      try {
        await syncPiThreadsToServer();
      } catch {
        // keep local copy if sync fails
      }
    } else {
      beginPiThread();
      return;
    }
  } else {
    recoverLegacyPiHistory(userId);
  }

  if (!activePiThreadId || !piThreads.some((thread) => thread.id === activePiThreadId)) {
    activePiThreadId = piThreads[0]?.id || null;
  }
  await fetchActivePiThreadHistory();
  restorePiChatUi();
  savePiThreadsStoreLocal();
}

function savePiThreadsStoreLocal() {
  if (!currentUserId) return;
  syncActivePiThreadHistory();
  try {
    localStorage.setItem(
      piThreadsStorageKey(currentUserId),
      JSON.stringify({
        activeThreadId: activePiThreadId,
        threads: piThreads.slice(0, PI_THREADS_MAX),
        updatedAt: Date.now(),
      }),
    );
    renderPiThreadList();
    updatePiChatHistoryHint();
  } catch {
    // ignore quota errors
  }
}

function loadPiThreadsFromStorage(userId) {
  piThreads = [];
  activePiThreadId = null;
  piChatHistory = [];
  try {
    const raw = localStorage.getItem(piThreadsStorageKey(userId));
    if (raw) {
      const data = JSON.parse(raw);
      piThreads = Array.isArray(data.threads)
        ? data.threads.filter((thread) => thread?.id).slice(0, PI_THREADS_MAX)
        : [];
      activePiThreadId = data.activeThreadId || piThreads[0]?.id || null;
    }
  } catch {
    piThreads = [];
    activePiThreadId = null;
  }

  if (!piThreads.length) {
    const migrated = migratePiChatV1ToThreads(userId);
    if (migrated) {
      piThreads = [migrated];
      activePiThreadId = migrated.id;
      savePiThreadsStore();
    }
  } else {
    recoverLegacyPiHistory(userId);
  }

  if (!piThreads.length) {
    beginPiThread();
    return;
  }

  if (!activePiThreadId || !piThreads.some((thread) => thread.id === activePiThreadId)) {
    activePiThreadId = piThreads[0].id;
  }
  const active = getActivePiThread();
  piChatHistory = normalizeHistoryItems(active?.history);
}

function beginPiThread(title) {
  if (piChatBusy) {
    alert(t("pi.busySwitch"));
    return null;
  }
  syncActivePiThreadHistory();
  const thread = {
    id: createPiThreadId(),
    title: title || defaultPiThreadTitle(),
    history: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  piThreads.unshift(thread);
  if (piThreads.length > PI_THREADS_MAX) {
    piThreads = piThreads.slice(0, PI_THREADS_MAX);
  }
  activePiThreadId = thread.id;
  piChatHistory = [];
  restorePiChatUi();
  renderPiThreadList();
  updatePiChatHistoryHint();
  return thread;
}

function createPiThread(title) {
  const thread = beginPiThread(title);
  if (thread) {
    savePiThreadsStore();
  }
  return thread;
}

async function switchPiThread(threadId) {
  if (threadId === activePiThreadId) return;
  if (piChatBusy) {
    alert(t("pi.busySwitch"));
    return;
  }
  syncActivePiThreadHistory();
  savePiThreadsStoreLocal();
  activePiThreadId = threadId;
  await fetchActivePiThreadHistory();
  restorePiChatUi();
  savePiThreadsStoreLocal();
}

async function deletePiThread(threadId) {
  if (piChatBusy) {
    alert(t("pi.busySwitch"));
    return;
  }
  if (!window.confirm(t("pi.confirmDeleteThread"))) return;
  try {
    await api(`/api/pi/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
  } catch {
    // still remove locally if server delete fails
  }
  piThreads = piThreads.filter((thread) => thread.id !== threadId);
  if (!piThreads.length) {
    createPiThread();
    return;
  }
  if (activePiThreadId === threadId) {
    activePiThreadId = piThreads[0].id;
    piChatHistory = Array.isArray(piThreads[0].history) ? [...piThreads[0].history] : [];
    restorePiChatUi();
  }
  savePiThreadsStore();
}

function savePiChatHistory() {
  savePiThreadsStore();
}

function loadPiChatHistoryFromStorage(userId) {
  loadPiThreadsFromStorage(userId);
}

async function loadPiChatForUser(userId) {
  await loadPiChatFromServer(userId);
}

function restorePiChatToolEntry(item) {
  const name = item.name || "tool";
  let el;
  if (PI_LEAD_STREAM_TOOLS.has(name)) {
    el = appendPiChatDiscoverTool(name);
  } else if (name === "lookup_asns") {
    el = appendPiChatLookupTool(name);
  } else {
    el = appendPiChatTool(name);
  }
  el.querySelector(".pi-chat-tool-head")?.classList.add("done");
  el.querySelector(".pi-chat-live-panel")?.classList.add("hidden");
  stopPiDiscoverTimer(el);
  const summary = item.summary || "";
  const progressEl = el.querySelector(".pi-chat-tool-progress");
  const pre = el.querySelector(".pi-chat-tool-result");
  if (summary && progressEl) {
    progressEl.textContent = summary;
  }
  if (name === "lookup_asns" && Array.isArray(item.preview)) {
    pre?.classList.add("hidden");
    for (const row of item.preview) {
      appendPiChatLookupRow(el, row);
    }
    if (item.preview.length) {
      el.querySelector(".pi-chat-leads-actions")?.classList.remove("hidden");
    }
  } else if (summary && pre) {
    pre.classList.remove("hidden");
    pre.textContent = summary;
  }
}

function restorePiChatUi() {
  piChatMessagesEl.innerHTML = "";
  if (!piChatHistory.length) {
    piChatMessagesEl.innerHTML = `<div class="pi-chat-empty">${t("pi.emptyHintAlt")}</div>`;
    renderPiThreadList();
    updatePiChatHistoryHint();
    return;
  }
  for (const item of piChatHistory) {
    if (item.role === "user" || item.role === "assistant") {
      appendPiChatBubble(item.role, item.content);
    } else if (item.role === "tool") {
      restorePiChatToolEntry(item);
    }
  }
  renderPiThreadList();
  updatePiChatHistoryHint();
}

function updatePiChatHistoryHint() {
  if (!piChatHistoryHintEl) return;
  const count = piChatHistory.length;
  const threadCount = piThreads.length;
  if (!count) {
    piChatHistoryHintEl.textContent = t("msg.piHistoryLocal");
    return;
  }
  piChatHistoryHintEl.textContent = t("msg.piHistorySavedThreads", { count, threads: threadCount });
  const active = piThreads.find((item) => item.id === activePiThreadId);
  if (active?.has_context_summary) {
    piChatHistoryHintEl.textContent += ` · ${t("msg.piContextCompressed")}`;
  }
}

function buildPiLeadMessage() {
  const query = leadQueryInput.value.trim();
  if (!query) return "";
  const minScore = Number(minScoreInput.value) || 60;
  const lines = [`请帮我找销售线索：${query}`, `最低匹配分 ${minScore}`];
  if (autoImportInput.checked) {
    lines.push(t("pi.autoImportHint"));
  }
  return lines.join("\n");
}

async function openPiAgentForLeads() {
  const message = buildPiLeadMessage();
  if (!message) {
    alert(t("msg.describeLeads"));
    return;
  }
  if (!llmConfigured) {
    alert(t("msg.piNotAvailable"));
    return;
  }
  switchView("pi-agent");
  beginPiThread(summarizePiThreadTitle(message));
  await sendPiChatMessage(message);
}

async function openPiEnrichContact(contact) {
  if (!contact?.id) return;
  if (!llmConfigured) {
    alert(t("msg.piNotAvailable"));
    return;
  }
  const label = contact.org || contact.email || `#${contact.id}`;
  const message = [
    `请为联系人 #${contact.id}（${label}，${contact.email}）查找同一组织/ASN 的其他 role 联系方式。`,
    contact.asn ? `ASN: AS${contact.asn}` : "",
    t("pi.enrichPromptSuffix"),
  ]
    .filter(Boolean)
    .join("\n");
  switchView("pi-agent");
  beginPiThread(t("pi.enrichThreadTitle", { label }));
  await sendPiChatMessage(message);
}

async function enrichContactViaBackground(contact) {
  if (!contact?.id) return;
  if (!llmConfigured) {
    alert(t("msg.piNotAvailable"));
    return;
  }
  try {
    const data = await api("/api/jobs/enrich", {
      method: "POST",
      body: JSON.stringify({
        contact_id: contact.id,
        min_score: 50,
        auto_import: true,
      }),
    });
    trackBackgroundJob(data.job);
    alert(t("msg.jobStartedBackground"));
  } catch (error) {
    alert(errorMessage(error, t("msg.enrichFailed")));
  }
}

function formatPiToolSummary(name, result) {
  if (!result || typeof result !== "object") return "";
  if (result.error) return String(result.error);
  if (name === "discover_leads" || name === "enrich_contact") {
    const parts = [`共 ${result.lead_count ?? 0} 条线索`];
    if (result.contact_id) {
      parts.unshift(`联系人 #${result.contact_id}`);
    }
    if (result.import) {
      parts.push(formatImportResult(result.import));
    } else if (result.message) {
      parts.push(result.message);
    }
    return parts.join(" · ");
  }
  if (name === "lookup_asns") {
    return `识别 ${result.asns?.length ?? 0} 个 ASN · ${result.email_count ?? 0} 条邮箱（全球 RIR 自动路由）`;
  }
  if (name === "list_contacts") {
    return `返回 ${result.contacts?.length ?? 0} 条（总计 ${result.total ?? 0}）`;
  }
  if (name === "get_contact") {
    return result.contact ? `#${result.contact.id} ${result.contact.email || ""}` : "";
  }
  if (name === "update_contact") {
    return result.contact ? `已更新 #${result.contact.id} ${result.contact.email || ""}` : "";
  }
  if (name === "mark_contact_sent") {
    return result.ok
      ? t("pi.contactMarked", {
          id: result.contact_id,
          status: result.sent ? t("pi.markedSent") : t("pi.unmarkedSent"),
        })
      : "";
  }
  if (name === "delete_contacts") {
    return `已删除 ${result.deleted ?? 0} / ${result.requested ?? 0} 条`;
  }
  if (name === "add_contact_note") {
    return result.ok ? t("pi.noteAdded") : "";
  }
  if (name === "dedupe_contacts") {
    return `去重完成：删除 ${result.removed ?? 0} 条，剩余 ${result.total_contacts ?? result.total ?? 0} 条`;
  }
  if (name === "import_leads") {
    return formatImportResult(result);
  }
  if (name === "get_stats") {
    return `联系人 ${result.total ?? 0} · 已发 ${result.sent ?? 0}`;
  }
  if (name === "get_search_config") {
    const active = result.active_web_backend || "duckduckgo";
    const zhipu = result.zhipu_web_search || {};
    const bright = result.brightdata_serp || {};
    if (active === "zhipu") {
      return `当前联网搜索：智谱 ${zhipu.engine || "search_pro"}（${zhipu.configured ? "已配置" : "未配置"}）`;
    }
    if (active === "brightdata") {
      return `当前联网搜索：Bright Data Google SERP（zone ${bright.zone || "未配置"} · ${bright.data_format || "auto"}）`;
    }
    return `当前联网搜索：${active} · 优先级 ${(result.web_backend_priority || []).join(" > ")}`;
  }
  if (name === "web_search") {
    return `${result.backend_used || "search"} · ${result.result_count ?? 0} 条结果 · 邮箱 ${result.emails_found?.length ?? 0} · ASN ${result.asns_found?.length ?? 0}`;
  }
  if (name === "collect_linkedin_profiles") {
    return `LinkedIn · ${result.profile_count ?? 0} 个 profile`;
  }
  if (name === "collect_x_profiles") {
    return `X · ${result.profile_count ?? 0} 个 profile`;
  }
  if (name === "collect_facebook_profiles") {
    return `Facebook · ${result.profile_count ?? 0} 个 profile`;
  }
  if (name === "shodan_search") {
    return `Shodan · ${result.match_count ?? 0} 条 · ${result.networks?.length ?? 0} 个 ASN`;
  }
  return "";
}

function appendPiChatLookupTool(name) {
  const el = appendPiChatTool(name);
  el.classList.add("pi-chat-tool-lookup");
  const lookupWrap = document.createElement("div");
  lookupWrap.className = "pi-chat-leads hidden";
  lookupWrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>RIR</th>
          <th>ASN</th>
          <th>组织</th>
          <th>Role</th>
          <th>邮箱</th>
        </tr>
      </thead>
      <tbody class="pi-chat-lookup-body"></tbody>
    </table>
  `;
  const actionsEl = document.createElement("div");
  actionsEl.className = "pi-chat-leads-actions hidden";
  actionsEl.innerHTML = `<button type="button" class="success-btn pi-chat-import-lookup">${t("pi.importSelectedEmails")}</button>`;
  el.appendChild(lookupWrap);
  el.appendChild(actionsEl);
  el._piLookupRows = [];
  return el;
}

function appendPiChatLookupRow(toolEl, row) {
  if (!toolEl || !row?.email) return;
  const wrap = toolEl.querySelector(".pi-chat-leads");
  const body = toolEl.querySelector(".pi-chat-lookup-body");
  if (!wrap || !body) return;
  wrap.classList.remove("hidden");
  toolEl._piLookupRows = toolEl._piLookupRows || [];
  const index = toolEl._piLookupRows.length;
  toolEl._piLookupRows.push(row);
  const roles = (row.roles || []).join(", ");
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td>${escapeHtml(row.rir || "—")}</td>
    <td class="mono">AS${row.asn}</td>
    <td>${escapeHtml(row.org || "—")}</td>
    <td>${escapeHtml(roles || "—")}</td>
    <td><a class="email-link" href="mailto:${row.email}">${escapeHtml(row.email)}</a></td>
  `;
  tr.dataset.index = String(index);
  tr.classList.add("selected");
  tr.title = t("pi.toggleSelectTitle");
  tr.addEventListener("click", () => tr.classList.toggle("selected"));
  body.appendChild(tr);
  toolEl.querySelector(".pi-chat-leads-actions")?.classList.remove("hidden");
}

async function importPiChatLookup(toolEl) {
  const selectedRows = toolEl?.querySelectorAll("tr.selected") || [];
  const allRows = toolEl?._piLookupRows || [];
  const rows =
    selectedRows.length > 0
      ? Array.from(selectedRows).map((row) => allRows[Number(row.dataset.index)])
      : allRows;
  const payload = normalizeImportRows(
    rows.filter((row) => row?.email).map((row) => ({
      ...row,
      source: row.source || "rdap",
    })),
  );
  if (!payload.length) {
    alert(t("msg.noEmailsToImport"));
    return;
  }
  try {
    const result = await api("/api/contacts/import", {
      method: "POST",
      body: JSON.stringify({ rows: payload }),
    });
    alert(formatImportResult(result));
    await loadContacts();
  } catch (error) {
    alert(errorMessage(error, t("msg.importFailed")));
  }
}

function scrollPiChatToBottom() {
  if (!piChatMessagesEl) return;
  piChatMessagesEl.scrollTo({ top: piChatMessagesEl.scrollHeight, behavior: "smooth" });
}

function stopPiDiscoverTimer(toolEl) {
  if (toolEl?._piDiscoverTimer) {
    clearInterval(toolEl._piDiscoverTimer);
    toolEl._piDiscoverTimer = null;
  }
}

function startPiDiscoverTimer(toolEl) {
  stopPiDiscoverTimer(toolEl);
  if (!toolEl) return;
  toolEl._piDiscoverTimer = setInterval(() => {
    const elapsedEl = toolEl.querySelector(".pi-chat-live-elapsed");
    if (!elapsedEl || !toolEl._piDiscoverStartedAt) return;
    const sec = Math.floor((Date.now() - toolEl._piDiscoverStartedAt) / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    elapsedEl.textContent = `${m}:${String(s).padStart(2, "0")}`;
  }, 1000);
}

function initPiDiscoverChannelState(toolEl) {
  toolEl._piChannelState = {};
  for (const def of CHANNEL_DEFS) {
    toolEl._piChannelState[def.key] = { state: "idle", count: "", preview: "" };
  }
  toolEl._piDiscoverStartedAt = Date.now();
  toolEl._piLeadCount = 0;
}

function renderPiDiscoverLivePanel(toolEl) {
  const channelsEl = toolEl?.querySelector(".pi-chat-live-channels");
  if (!channelsEl || !toolEl._piChannelState) return;
  channelsEl.innerHTML = CHANNEL_DEFS.map((def) => {
    const s = toolEl._piChannelState[def.key] || { state: "idle", count: "", preview: "" };
    return `
      <div class="pi-channel-row state-${s.state}">
        <span class="pi-channel-icon">${PI_CHANNEL_ICON[s.state] || "·"}</span>
        <span class="pi-channel-name">${escapeHtml(t(def.nameKey))}</span>
        <span class="pi-channel-count">${escapeHtml(String(s.count ?? ""))}</span>
        <span class="pi-channel-preview" title="${escapeHtml(s.preview || "")}">${escapeHtml(s.preview || "")}</span>
      </div>`;
  }).join("");
  const leadsEl = toolEl.querySelector(".pi-chat-live-leads");
  if (leadsEl) {
    leadsEl.textContent = t("pi.liveLeadCount", { count: toolEl._piLeadCount || 0 });
  }
  scrollPiChatToBottom();
}

function setPiDiscoverChannel(toolEl, key, patch) {
  if (!toolEl?._piChannelState?.[key]) return;
  Object.assign(toolEl._piChannelState[key], patch);
  renderPiDiscoverLivePanel(toolEl);
}

function pushPiDiscoverTicker(toolEl, message) {
  if (!toolEl || !message) return;
  const ticker = toolEl.querySelector(".pi-chat-live-ticker");
  if (!ticker) return;
  const li = document.createElement("li");
  li.className = "pi-chat-ticker-line";
  li.textContent = message;
  ticker.prepend(li);
  while (ticker.children.length > 10) {
    ticker.lastElementChild?.remove();
  }
  scrollPiChatToBottom();
}

function updatePiDiscoverRdapBar(toolEl, index, total, network) {
  const wrap = toolEl?.querySelector(".pi-chat-rdap-wrap");
  const fill = toolEl?.querySelector(".pi-chat-rdap-fill");
  const text = toolEl?.querySelector(".pi-chat-rdap-text");
  if (!wrap || !fill || !text) return;
  wrap.classList.remove("hidden");
  const safeTotal = Math.max(1, Number(total) || 1);
  const safeIndex = Math.min(Math.max(1, Number(index) || 1), safeTotal);
  const pct = Math.round((safeIndex / safeTotal) * 100);
  fill.style.width = `${pct}%`;
  text.textContent = t("pi.rdapProgress", {
    index: safeIndex,
    total: safeTotal,
    network: network || "",
  });
  setPiDiscoverChannel(toolEl, "arin", {
    state: "active",
    count: `${safeIndex}/${safeTotal}`,
    preview: network || "",
  });
  if (piChatProgressFill) {
    piChatProgressFill.style.width = `${Math.max(35, Math.min(92, 35 + pct * 0.55))}%`;
  }
}

function handlePiDiscoverProgress(toolEl, message) {
  if (!toolEl || !message) return;
  pushPiDiscoverTicker(toolEl, message);
  if (piChatProgressText) {
    piChatProgressText.textContent = message;
  }

  const sourceMatch = message.match(/^([\w]+):\s*(\d+)\s*条/);
  if (sourceMatch) {
    const channelKey = PI_SOURCE_CHANNEL_MAP[sourceMatch[1]] || sourceMatch[1];
    if (toolEl._piChannelState?.[channelKey]) {
      setPiDiscoverChannel(toolEl, channelKey, {
        state: "done",
        count: sourceMatch[2],
        preview: message,
      });
    }
    return;
  }

  if (message.includes("多渠道") || message.includes("搜索中")) {
    for (const key of ["peeringdb", "web_search", "shodan"]) {
      if (toolEl._piChannelState?.[key]?.state === "idle") {
        setPiDiscoverChannel(toolEl, key, { state: "active" });
      }
    }
  }
  if (message.includes("评估")) {
    setPiDiscoverChannel(toolEl, "scoring", { state: "active" });
    setPiDiscoverChannel(toolEl, "arin", { state: "done" });
  }
  if (message.includes("抓取") || message.includes("profile")) {
    for (const key of ["linkedin", "x", "facebook"]) {
      if (message.toLowerCase().includes(key) || message.includes(t(`channel.${key}`))) {
        setPiDiscoverChannel(toolEl, key, { state: "active" });
      }
    }
  }
}

function finalizePiDiscoverTool(toolEl, event) {
  if (!toolEl) return;
  stopPiDiscoverTimer(toolEl);
  toolEl.classList.remove("pi-chat-tool-running");
  toolEl.querySelector(".pi-chat-tool-head")?.classList.add("done");
  if (toolEl._piChannelState) {
    for (const def of CHANNEL_DEFS) {
      const state = toolEl._piChannelState[def.key];
      if (state?.state === "active") {
        setPiDiscoverChannel(toolEl, def.key, { state: "done" });
      }
    }
  }
  toolEl.querySelector(".pi-chat-rdap-wrap")?.classList.add("hidden");
  if (event?.message) {
    pushPiDiscoverTicker(toolEl, event.message);
  }
}

function handlePiDiscoverToolEvent(toolEl, event) {
  if (!toolEl || !event) return;
  switch (event.kind) {
    case "plan":
      renderPiChatPlan(toolEl, event.plan);
      pushPiDiscoverTicker(toolEl, event.plan?.summary || t("pi.planReady"));
      for (const key of ["peeringdb", "web_search", "shodan"]) {
        if (toolEl._piChannelState?.[key]?.state === "idle") {
          setPiDiscoverChannel(toolEl, key, { state: "active" });
        }
      }
      break;
    case "source_result": {
      const channelKey = PI_SOURCE_CHANNEL_MAP[event.source] || event.source;
      const preview = Array.isArray(event.preview) ? event.preview.slice(0, 2).join(" · ") : "";
      if (toolEl._piChannelState?.[channelKey]) {
        setPiDiscoverChannel(toolEl, channelKey, {
          state: "done",
          count: String(event.count ?? ""),
          preview,
        });
      }
      pushPiDiscoverTicker(toolEl, `${event.source}: ${event.count ?? 0} ${t("pi.items")}`);
      break;
    }
    case "progress":
      updatePiDiscoverRdapBar(toolEl, event.index, event.total, event.network || "");
      pushPiDiscoverTicker(toolEl, event.message || `RDAP AS${event.asn}`);
      break;
    case "asn_result":
      pushPiDiscoverTicker(
        toolEl,
        t("pi.asnCandidates", {
          asn: event.asn,
          count: event.candidate_count || 0,
        }),
      );
      break;
    case "phase":
      if (event.phase === "scoring") {
        setPiDiscoverChannel(toolEl, "scoring", { state: "active" });
        setPiDiscoverChannel(toolEl, "arin", { state: "done" });
      }
      break;
    case "status":
      handlePiDiscoverProgress(toolEl, event.message);
      break;
    case "lead":
      appendPiChatLeadRow(toolEl, event.lead);
      toolEl._piLeadCount = (toolEl._piLeadCount || 0) + 1;
      renderPiDiscoverLivePanel(toolEl);
      setPiDiscoverChannel(toolEl, "scoring", {
        state: "active",
        count: String(toolEl._piLeadCount),
      });
      break;
    case "done":
      finalizePiDiscoverTool(toolEl, event);
      break;
    default:
      break;
  }
}

function appendPiChatDiscoverTool(name) {
  const el = appendPiChatTool(name);
  el.classList.add("pi-chat-tool-discover", "pi-chat-tool-running");
  const livePanel = document.createElement("div");
  livePanel.className = "pi-chat-live-panel";
  livePanel.innerHTML = `
    <div class="pi-chat-live-head">
      <span class="pi-chat-live-badge">${t("pi.liveRunning")}</span>
      <span class="pi-chat-live-elapsed">0:00</span>
      <span class="pi-chat-live-leads">${t("pi.liveLeadCount", { count: 0 })}</span>
    </div>
    <div class="pi-chat-live-channels"></div>
    <div class="pi-chat-rdap-wrap hidden">
      <div class="pi-chat-rdap-label">${t("channel.arin")}</div>
      <div class="pi-chat-rdap-bar"><div class="pi-chat-rdap-fill"></div></div>
      <div class="pi-chat-rdap-text"></div>
    </div>
    <ul class="pi-chat-live-ticker" aria-live="polite"></ul>
  `;
  const planEl = document.createElement("div");
  planEl.className = "pi-chat-tool-plan hidden";
  const leadsWrap = document.createElement("div");
  leadsWrap.className = "pi-chat-leads hidden";
  leadsWrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>分数</th>
          <th>组织</th>
          <th>邮箱</th>
          <th>来源</th>
        </tr>
      </thead>
      <tbody class="pi-chat-leads-body"></tbody>
    </table>
  `;
  const actionsEl = document.createElement("div");
  actionsEl.className = "pi-chat-leads-actions hidden";
  actionsEl.innerHTML = `<button type="button" class="success-btn pi-chat-import-leads">${t("pi.importSelectedLeads")}</button>`;
  el.appendChild(livePanel);
  el.appendChild(planEl);
  el.appendChild(leadsWrap);
  el.appendChild(actionsEl);
  el._piLeads = [];
  initPiDiscoverChannelState(el);
  renderPiDiscoverLivePanel(el);
  startPiDiscoverTimer(el);
  return el;
}

function appendPiChatLeadRow(toolEl, lead) {
  if (!toolEl) return;
  const leadsWrap = toolEl.querySelector(".pi-chat-leads");
  const body = toolEl.querySelector(".pi-chat-leads-body");
  if (!leadsWrap || !body) return;
  leadsWrap.classList.remove("hidden");
  toolEl._piLeads = toolEl._piLeads || [];
  const index = toolEl._piLeads.length;
  toolEl._piLeads.push(lead);
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><span class="${scoreBadgeClass(lead.lead_score)}">${lead.lead_score || 0}</span></td>
    <td>${escapeHtml(lead.org || lead.network_name || "—")}</td>
    <td><a class="email-link" href="mailto:${lead.email}">${escapeHtml(lead.email || "—")}</a></td>
    <td>${escapeHtml(formatSource(lead))}</td>
  `;
  tr.dataset.index = String(index);
  tr.classList.add("selected");
  tr.title = t("pi.toggleSelectTitle");
  tr.addEventListener("click", () => {
    tr.classList.toggle("selected");
  });
  body.appendChild(tr);
  tr.classList.add("pi-lead-row-in");
  toolEl.querySelector(".pi-chat-leads-actions")?.classList.remove("hidden");
  scrollPiChatToBottom();
}

function renderPiChatPlan(toolEl, plan) {
  if (!toolEl || !plan) return;
  const planEl = toolEl.querySelector(".pi-chat-tool-plan");
  if (!planEl) return;
  planEl.classList.remove("hidden");
  planEl.innerHTML = `<p><strong>策略：</strong>${escapeHtml(plan.summary || "")}</p>`;
}

async function importPiChatLeads(toolEl) {
  const selectedRows = toolEl?.querySelectorAll("tr.selected") || [];
  const allLeads = toolEl?._piLeads || [];
  const rows =
    selectedRows.length > 0
      ? Array.from(selectedRows).map((row) => allLeads[Number(row.dataset.index)])
      : allLeads;
  const payload = normalizeImportRows(
    rows
      .filter((lead) => lead?.email)
      .map((lead) => ({
        ...lead,
        source: "ai-lead",
        notes: `AI评分 ${lead.lead_score || 0} · ${lead.lead_reason || ""}`.trim(" ·"),
      })),
  );
  if (!payload.length) {
    alert(t("msg.noLeadsToImport"));
    return;
  }
  try {
    const result = await api("/api/contacts/import", {
      method: "POST",
      body: JSON.stringify({ rows: payload }),
    });
    alert(formatImportResult(result));
    await loadContacts();
  } catch (error) {
    alert(errorMessage(error, t("msg.importFailed")));
  }
}

function updatePiAgentStatus() {
  if (!piAgentStatusEl) return;
  const enabled = llmConfigured;
  piChatInput.disabled = !enabled || piChatBusy;
  piChatSendBtn.disabled = !enabled || piChatBusy;
  if (enabled) {
    piAgentStatusEl.className = "llm-status ok";
    piAgentStatusEl.textContent = t("msg.piReady");
  } else {
    piAgentStatusEl.className = "llm-status warn";
    piAgentStatusEl.textContent = t("msg.piNotConfigured");
  }
}

function clearPiChatEmpty() {
  const empty = piChatMessagesEl.querySelector(".pi-chat-empty");
  if (empty) empty.remove();
}

function renderMarkdown(text) {
  if (!text) return "";

  const codeBlocks = [];
  const body = String(text).replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _lang, code) => {
    const index = codeBlocks.length;
    codeBlocks.push(escapeHtml(code.replace(/\n$/, "")));
    return `\x00CB${index}\x00`;
  });

  function inlineMarkdown(line) {
    let html = escapeHtml(line);
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");
    html = html.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    );
    return html;
  }

  const lines = body.split("\n");
  const out = [];
  let listTag = null;

  function closeList() {
    if (!listTag) return;
    out.push(listTag === "ul" ? "</ul>" : "</ol>");
    listTag = null;
  }

  for (const line of lines) {
    const trimmed = line.trimEnd();
    const codeBlockMatch = trimmed.trim().match(/^\x00CB(\d+)\x00$/);
    if (codeBlockMatch) {
      closeList();
      out.push(`<pre><code>${codeBlocks[Number(codeBlockMatch[1])]}</code></pre>`);
      continue;
    }

    const ulMatch = trimmed.match(/^[-*]\s+(.+)/);
    const olMatch = trimmed.match(/^\d+\.\s+(.+)/);
    if (ulMatch) {
      if (listTag !== "ul") {
        closeList();
        out.push("<ul>");
        listTag = "ul";
      }
      out.push(`<li>${inlineMarkdown(ulMatch[1])}</li>`);
      continue;
    }
    if (olMatch) {
      if (listTag !== "ol") {
        closeList();
        out.push("<ol>");
        listTag = "ol";
      }
      out.push(`<li>${inlineMarkdown(olMatch[1])}</li>`);
      continue;
    }

    closeList();
    if (trimmed === "") continue;
    out.push(`<p>${inlineMarkdown(trimmed)}</p>`);
  }

  closeList();
  return out.join("");
}

function sanitizePiAssistantDisplay(text) {
  const raw = String(text || "");
  if (!raw) return "";
  const lower = raw.toLowerCase();
  const markers = [
    "[工具",
    "[tool",
    "tool_calls",
    "tool_call",
    "dsml",
    "<|",
    "```json",
    '{"query',
    '{"queries',
  ];
  let cutAt = raw.length;
  for (const marker of markers) {
    const idx = lower.indexOf(marker.toLowerCase());
    if (idx >= 0) cutAt = Math.min(cutAt, idx);
  }
  return raw.slice(0, cutAt).trim();
}

function appendPiChatBubble(role, text) {
  clearPiChatEmpty();
  const el = document.createElement("div");
  el.className = `pi-chat-bubble ${role}`;
  if (role === "assistant") {
    el.classList.add("markdown");
    el.innerHTML = renderMarkdown(sanitizePiAssistantDisplay(text || ""));
  } else {
    el.textContent = text;
  }
  piChatMessagesEl.appendChild(el);
  piChatMessagesEl.scrollTop = piChatMessagesEl.scrollHeight;
  return el;
}

let piChatStreamRaf = null;

function updatePiChatAssistantBubble(el, text, streaming = false) {
  if (!el) return;
  el.classList.toggle("streaming", streaming);
  if (piChatStreamRaf) cancelAnimationFrame(piChatStreamRaf);
  piChatStreamRaf = requestAnimationFrame(() => {
    el.innerHTML = renderMarkdown(sanitizePiAssistantDisplay(text || ""));
    piChatMessagesEl.scrollTop = piChatMessagesEl.scrollHeight;
    piChatStreamRaf = null;
  });
}

function appendPiChatStatus(text) {
  clearPiChatEmpty();
  const el = document.createElement("div");
  el.className = "pi-chat-status";
  el.textContent = text;
  piChatMessagesEl.appendChild(el);
  piChatMessagesEl.scrollTop = piChatMessagesEl.scrollHeight;
  return el;
}

function appendPiChatTool(name) {
  clearPiChatEmpty();
  const el = document.createElement("div");
  el.className = "pi-chat-tool";
  el.dataset.toolName = name;
  el.innerHTML = `
    <div class="pi-chat-tool-head"><span class="dot"></span><span class="pi-chat-tool-name">${escapeHtml(name)}</span></div>
    <p class="pi-chat-tool-progress"></p>
    <pre class="pi-chat-tool-result hidden"></pre>
  `;
  piChatMessagesEl.appendChild(el);
  piChatMessagesEl.scrollTop = piChatMessagesEl.scrollHeight;
  return el;
}

function setPiChatBusy(busy) {
  piChatBusy = busy;
  piChatStopBtn.classList.toggle("hidden", !busy);
  updatePiAgentStatus();
  piChatProgressEl.classList.toggle("hidden", !busy);
  if (!busy) {
    piChatProgressFill.style.width = "0%";
    piChatProgressText.textContent = "";
  }
}

async function sendPiChatMessage(message) {
  const text = String(message || "").trim();
  if (!text || piChatBusy || !llmConfigured) return;

  piChatInput.value = "";
  appendPiChatBubble("user", text);
  piChatHistory.push({ role: "user", content: text });
  const thread = getActivePiThread();
  if (thread && (thread.title === defaultPiThreadTitle() || !thread.title)) {
    thread.title = summarizePiThreadTitle(text);
  }
  savePiChatHistory();

  setPiChatBusy(true);
  piChatProgressFill.style.width = "12%";
  piChatProgressText.textContent = t("pi.processingShort");
  piChatController = new AbortController();

  let activeToolEl = null;
  let activeAssistantEl = null;
  let assistantStreamText = "";

  try {
    const response = await fetch("/api/agent/chat/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        history: piChatHistory.slice(0, -1),
        thread_id: activePiThreadId,
      }),
      signal: piChatController.signal,
    });

    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (!response.ok) {
      const error = await response.json();
      throw new Error(formatApiDetail(error.detail) || t("pi.requestFailed"));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const line = chunk.trim();
        if (!line.startsWith("data: ")) continue;
        let payload;
        try {
          payload = JSON.parse(line.slice(6));
        } catch {
          continue;
        }

        if (payload.type === "status") {
          piChatProgressText.textContent = payload.message || t("msg.piProcessingShort");
          if (
            activeToolEl?.classList.contains("pi-chat-tool-discover") &&
            payload.message?.includes("仍在执行")
          ) {
            pushPiDiscoverTicker(activeToolEl, payload.message);
          }
        } else if (payload.type === "tool_start") {
          activeToolEl =
            PI_LEAD_STREAM_TOOLS.has(payload.name)
              ? appendPiChatDiscoverTool(payload.name)
              : payload.name === "lookup_asns"
                ? appendPiChatLookupTool(payload.name)
                : appendPiChatTool(payload.name || "tool");
          piChatProgressText.textContent = t("msg.piCallingTool", { name: payload.name });
          piChatProgressFill.style.width = "12%";
          scrollPiChatToBottom();
        } else if (payload.type === "tool_progress") {
          if (activeToolEl) {
            if (PI_LEAD_STREAM_TOOLS.has(payload.name)) {
              handlePiDiscoverProgress(activeToolEl, payload.message || "");
            } else {
              activeToolEl.querySelector(".pi-chat-tool-progress").textContent = payload.message || "";
            }
          }
          if (!PI_LEAD_STREAM_TOOLS.has(payload.name)) {
            piChatProgressText.textContent = payload.message || piChatProgressText.textContent;
            piChatProgressFill.style.width = "65%";
          }
        } else if (payload.type === "tool_event") {
          const event = payload.event || {};
          if (PI_LEAD_STREAM_TOOLS.has(payload.name) && activeToolEl) {
            handlePiDiscoverToolEvent(activeToolEl, event);
          }
        } else if (payload.type === "tool_result") {
          const summary = formatPiToolSummary(payload.name, payload.result);
          const toolEntry = {
            role: "tool",
            name: payload.name || "tool",
            summary: summary || "",
          };
          if (!toolEntry.summary && payload.result && typeof payload.result === "object") {
            try {
              toolEntry.summary = JSON.stringify(payload.result).slice(0, 8000);
            } catch {
              toolEntry.summary = summary || "";
            }
          }
          if (payload.name === "lookup_asns") {
            toolEntry.preview = (payload.result?.rows || payload.result?.preview || []).slice(0, 25);
          }
          if (activeToolEl) {
            if (PI_LEAD_STREAM_TOOLS.has(payload.name)) {
              finalizePiDiscoverTool(activeToolEl, {
                message: summary || payload.result?.message,
              });
            }
            activeToolEl.querySelector(".pi-chat-tool-head").classList.add("done");
            const pre = activeToolEl.querySelector(".pi-chat-tool-result");
            if (PI_LEAD_STREAM_TOOLS.has(payload.name)) {
              pre.classList.add("hidden");
              if (summary) {
                activeToolEl.querySelector(".pi-chat-tool-progress").textContent = summary;
              }
              const importBtn = activeToolEl.querySelector(".pi-chat-import-leads");
              if (importBtn && !importBtn.dataset.bound) {
                importBtn.dataset.bound = "1";
                importBtn.addEventListener("click", () => {
                  importPiChatLeads(activeToolEl).catch((error) => alert(errorMessage(error, t("msg.importFailed"))));
                });
              }
              if (payload.result?.import) {
                activeToolEl.querySelector(".pi-chat-leads-actions")?.classList.add("hidden");
              }
            } else if (payload.name === "lookup_asns") {
              pre.classList.add("hidden");
              if (summary) {
                activeToolEl.querySelector(".pi-chat-tool-progress").textContent = summary;
              }
              for (const row of payload.result?.rows || payload.result?.preview || []) {
                appendPiChatLookupRow(activeToolEl, row);
              }
              const importBtn = activeToolEl.querySelector(".pi-chat-import-lookup");
              if (importBtn && !importBtn.dataset.bound) {
                importBtn.dataset.bound = "1";
                importBtn.addEventListener("click", () => {
                  importPiChatLookup(activeToolEl).catch((error) => alert(errorMessage(error, t("msg.importFailed"))));
                });
              }
            } else if (summary) {
              pre.classList.remove("hidden");
              pre.textContent = summary;
            } else {
              pre.classList.remove("hidden");
              pre.textContent = JSON.stringify(payload.result, null, 2);
              toolEntry.summary = pre.textContent.slice(0, 8000);
            }
          }
          appendPiHistoryEntry(toolEntry);
          activeToolEl = null;
          piChatProgressFill.style.width = "85%";
        } else if (payload.type === "assistant_start") {
          activeAssistantEl = appendPiChatBubble("assistant", "");
          activeAssistantEl.classList.add("streaming");
          assistantStreamText = "";
          piChatProgressFill.style.width = "90%";
        } else if (payload.type === "assistant_delta") {
          assistantStreamText += payload.text || "";
          updatePiChatAssistantBubble(activeAssistantEl, assistantStreamText, true);
        } else if (payload.type === "assistant_done") {
          assistantStreamText = sanitizePiAssistantDisplay(payload.text || assistantStreamText);
          updatePiChatAssistantBubble(activeAssistantEl, assistantStreamText, false);
          if (!activeAssistantEl && assistantStreamText) {
            activeAssistantEl = appendPiChatBubble("assistant", assistantStreamText);
          }
          piChatHistory.push({ role: "assistant", content: assistantStreamText });
          savePiChatHistory();
          activeAssistantEl = null;
          assistantStreamText = "";
          piChatProgressFill.style.width = "100%";
        } else if (payload.type === "assistant") {
          appendPiChatBubble("assistant", payload.text || "");
          appendPiHistoryEntry({ role: "assistant", content: payload.text || "" });
          piChatProgressFill.style.width = "100%";
        } else if (payload.type === "error") {
          appendPiChatStatus(payload.message || t("msg.errorGeneric"));
        } else if (payload.type === "done") {
          piChatProgressText.textContent = t("pi.done");
        }
      }
    }

    if (buffer.trim()) {
      const trailing = buffer.trim();
      if (trailing.startsWith("data: ")) {
        try {
          const payload = JSON.parse(trailing.slice(6));
          if (payload.type === "error") {
            appendPiChatStatus(payload.message || t("msg.errorGeneric"));
          }
        } catch {
          appendPiChatStatus(t("pi.streamInterrupted"));
        }
      }
    }

    if (piChatProgressText.textContent === t("pi.processingShort") && !assistantStreamText) {
      appendPiChatStatus(t("pi.streamInterrupted"));
    }
  } catch (error) {
    if (error.name !== "AbortError") {
      appendPiChatStatus(errorMessage(error, t("pi.requestFailed")));
    } else {
      appendPiChatStatus(t("pi.stopped"));
    }
  } finally {
    piChatController = null;
    setPiChatBusy(false);
    savePiThreadsStore();
    refreshActivePiThreadMeta().catch(() => {});
  }
}

async function sendPiChat(event) {
  event.preventDefault();
  const message = piChatInput.value.trim();
  await sendPiChatMessage(message);
}

function stopPiChat() {
  if (piChatController) {
    piChatController.abort();
  }
}

function clearPiChat() {
  if (piChatHistory.length && !window.confirm(t("pi.confirmClear"))) {
    return;
  }
  piChatHistory = [];
  const thread = getActivePiThread();
  if (thread) {
    thread.history = [];
    thread.title = defaultPiThreadTitle();
    thread.updatedAt = Date.now();
  }
  savePiThreadsStore();
  piChatMessagesEl.innerHTML = `<div class="pi-chat-empty">${t("pi.emptyHintAlt")}</div>`;
  updatePiChatHistoryHint();
  updatePiAgentStatus();
}

function switchView(view) {
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

  if (view === "lookup") {
    pageTitle.textContent = t("page.lookup.title");
    pageSubtitle.textContent = t("page.lookup.subtitle");
  } else if (view === "ai-leads") {
    pageTitle.textContent = t("page.aiLeads.title");
    pageSubtitle.textContent = t("page.aiLeads.subtitle");
  } else if (view === "pi-agent") {
    pageTitle.textContent = t("page.piAgent.title");
    pageSubtitle.textContent = t("page.piAgent.subtitle");
    updatePiAgentStatus();
  } else if (view === "schedules") {
    pageTitle.textContent = t("page.schedules.title");
    pageSubtitle.textContent = t("page.schedules.subtitle");
    loadSchedules().catch((error) => alert(error.message));
    startSchedulesAutoRefresh();
  } else if (view === "settings") {
    pageTitle.textContent = t("page.settings.title");
    pageSubtitle.textContent = t("settings.savedInDb");
    loadSettingsForm().catch((error) => alert(error.message));
    switchSettingsCat(activeSettingsCat);
    loadEmailTemplates().catch((error) => alert(error.message));
  } else if (view === "stats") {
    pageTitle.textContent = t("page.stats.title");
    pageSubtitle.textContent = t("page.stats.subtitle");
    loadStats().catch((error) => alert(error.message));
  } else {
    pageTitle.textContent = t("page.contacts.title");
    pageSubtitle.textContent = t("page.contacts.subtitle");
    loadContacts().catch((error) => alert(error.message));
    loadEmailTemplates().catch(() => {});
  }
  if (view !== "schedules") {
    stopSchedulesAutoRefresh();
  }
}

function ensureLeadSelected(lead) {
  if (lead._selected === undefined) {
    lead._selected = true;
  }
}

function getSelectedAiLeads() {
  return aiLeads.filter((lead) => lead._selected !== false);
}

function updateAiLeadsStats() {
  const total = aiLeads.length;
  const selected = getSelectedAiLeads().length;
  if (total === 0) {
    aiStatsEl.textContent = t("common.notStarted");
    importLeadsBtn.disabled = true;
    return;
  }
  aiStatsEl.textContent = t("msg.aiLeadsStats", { selected, total });
  importLeadsBtn.disabled = selected === 0;
}

function hideLeadsState() {
  aiLeadsStateEl.classList.add("hidden");
  aiLeadsStateEl.innerHTML = "";
}

function showLeadsState(html, isError = false) {
  aiLeadsStateEl.className = `leads-state${isError ? " error" : ""}`;
  aiLeadsStateEl.innerHTML = html;
}

function showLeadsError(message) {
  showLeadsState(`<p>${t("msg.leadsError", { message: escapeHtml(message) })}</p>`, true);
  retryDiscoverBtn.classList.remove("hidden");
}

function showLeadsEmpty() {
  showLeadsState(
    `<p>${t("msg.leadsEmpty")}</p>
     <p class="hint">${t("msg.leadsEmptyHint")}</p>`
  );
  retryDiscoverBtn.classList.remove("hidden");
}

function showLeadsNeedLlm() {
  showLeadsState(
    `<p>${t("msg.leadsNeedLlm")}</p>
     <p class="hint">${t("msg.leadsNeedLlmHint")}</p>
     <button type="button" class="primary-btn" id="leads-state-goto-settings">${t("msg.gotoSettings")}</button>`
  );
  const btn = document.getElementById("leads-state-goto-settings");
  if (btn) {
    btn.addEventListener("click", () => {
      switchView("settings");
      switchSettingsCat("ai");
    });
  }
}

function renderAiLeads() {
  aiLeadsBody.innerHTML = "";
  if (aiLeads.length > 0) hideLeadsState();

  if (aiLeads.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="8">用自然语言描述目标客户，AI 会从多个渠道自动搜索并评分</td>`;
    aiLeadsBody.appendChild(tr);
    updateAiLeadsStats();
    return;
  }

  for (let index = 0; index < aiLeads.length; index += 1) {
    const lead = aiLeads[index];
    ensureLeadSelected(lead);
    const tr = document.createElement("tr");
    const roles = (lead.roles || []).map((role) => `<span class="role-tag">${escapeHtml(role)}</span>`).join("");
    tr.innerHTML = `
      <td class="col-select"><input type="checkbox" class="row-import-check" data-kind="ai" data-index="${index}" ${lead._selected !== false ? "checked" : ""}></td>
      <td><span class="${scoreBadgeClass(lead.lead_score)}">${lead.lead_score || 0}</span></td>
      <td><span class="source-tag">${escapeHtml(formatSource(lead))}</span></td>
      <td>${escapeHtml(lead.org || lead.network_name || "—")}</td>
      <td><a class="email-link" href="mailto:${lead.email}">${escapeHtml(lead.email)}</a></td>
      <td>${roles || "—"}</td>
      <td class="mono">${lead.asn ? `AS${lead.asn}` : "—"}</td>
      <td>
        ${escapeHtml(lead.lead_reason || lead.source_detail || "—")}
        <button type="button" class="link-btn lead-detail-btn" data-index="${index}">${t("common.detail")}</button>
      </td>
    `;
    aiLeadsBody.appendChild(tr);
  }

  updateAiLeadsStats();
}

function formatSource(lead) {
  const source = lead.source || "unknown";
  const map = {
    "web-search": t("source.webSearch"),
    "arin-rdap": t("source.arinRdap"),
    peeringdb: t("channel.peeringdb"),
    "ai-lead": "AI",
  };
  return map[source] || source;
}

function scoreBadgeClass(score) {
  const value = Number(score) || 0;
  if (value >= 80) return "score-badge score-high";
  if (value >= 60) return "score-badge score-mid";
  return "score-badge score-low";
}

function openLeadDetail(index) {
  const lead = aiLeads[index];
  if (!lead) return;
  detailLeadIndex = index;
  const roles = (lead.roles || []).map((r) => `<span class="role-tag">${escapeHtml(r)}</span>`).join(" ") || "—";
  const rows = [
    [t("leadDetail.org"), escapeHtml(lead.org || lead.network_name || "—"), false],
    [t("leadDetail.email"), `<a class="email-link" href="mailto:${lead.email}">${escapeHtml(lead.email || "—")}</a>`, true],
    [t("leadDetail.asn"), lead.asn ? `AS${lead.asn}` : "—", true],
    [t("leadDetail.role"), roles, false],
    [t("leadDetail.source"), escapeHtml(formatSource(lead)), false],
    [t("leadDetail.sourceDetail"), escapeHtml(lead.source_detail || "—"), false],
    [t("leadDetail.networkName"), escapeHtml(lead.network_name || "—"), false],
    [t("leadDetail.matchedKeyword"), escapeHtml(lead.matched_keyword || "—"), true],
    [t("leadDetail.aiScore"), `<span class="${scoreBadgeClass(lead.lead_score)}">${lead.lead_score || 0}</span>`, false],
    [t("leadDetail.aiReason"), escapeHtml(lead.lead_reason || "—"), false],
  ];
  leadDetailBody.innerHTML = rows
    .map(([k, v, mono]) => `<div class="lead-detail-row"><span class="k">${k}</span><span class="v${mono ? " mono" : ""}">${v}</span></div>`)
    .join("");
  ensureLeadSelected(lead);
  leadDetailImport.checked = lead._selected !== false;
  leadDetailModal.classList.remove("hidden");
}

function closeLeadDetail() {
  detailLeadIndex = null;
  leadDetailModal.classList.add("hidden");
}

function renderAiPlan(plan) {
  aiPlanEl.classList.remove("hidden");
  aiPlanEl.innerHTML = `
    <p><strong>搜索策略：</strong>${escapeHtml(plan.summary || "")}</p>
    <p><strong>目标客户：</strong>${escapeHtml(plan.target_profile || "")}</p>
    <p><strong>PeeringDB 关键词：</strong>${escapeHtml((plan.keywords || []).join(", "))}</p>
    <p><strong>搜索引擎查询：</strong>${escapeHtml((plan.web_queries || []).join(" | "))}</p>
    <p><strong>优先 Role：</strong>${escapeHtml((plan.preferred_roles || []).join(", "))}</p>
  `;
}

function renderAiSources(channels) {
  if (!channels) return;
  aiSourcesEl.classList.remove("hidden");
  const web = (channels.web_search || []).join(", ") || "duckduckgo";
  const socialBits = ["linkedin", "x", "facebook"]
    .filter((key) => channels[key])
    .map((key) => (key === "x" ? "X" : key === "linkedin" ? "LinkedIn" : "Facebook"));
  const bits = [`搜索引擎(${escapeHtml(web)})`, "PeeringDB", "全球 RDAP", "LLM 提取/评分"];
  if (channels.shodan) bits.splice(2, 0, "Shodan");
  if (socialBits.length) bits.splice(3, 0, socialBits.join("/"));
  aiSourcesEl.innerHTML = `<p><strong>已启用渠道：</strong>${bits.join(" · ")}</p>`;
}

function resetChannelPanel() {
  channelState = {};
  for (const def of CHANNEL_DEFS) {
    channelState[def.key] = { state: "idle", count: "", preview: "" };
  }
  renderChannelPanel();
}

function setChannel(key, patch) {
  if (!channelState[key]) channelState[key] = { state: "idle", count: "", preview: "" };
  Object.assign(channelState[key], patch);
  renderChannelPanel();
}

const CHANNEL_ICON = { idle: "·", active: "◐", done: "✓", failed: "×" };

function renderChannelPanel() {
  aiChannelsEl.classList.remove("hidden");
  aiChannelsEl.innerHTML = CHANNEL_DEFS.map((def) => {
    const s = channelState[def.key] || { state: "idle", count: "", preview: "" };
    return `
      <div class="ai-channel-row state-${s.state}">
        <span class="ai-channel-icon">${CHANNEL_ICON[s.state]}</span>
        <span class="ai-channel-name">${escapeHtml(t(def.nameKey))}</span>
        <span class="ai-channel-count">${escapeHtml(String(s.count ?? ""))}</span>
        <span class="ai-channel-preview" title="${escapeHtml(s.preview || "")}">${escapeHtml(s.preview || "")}</span>
      </div>`;
  }).join("");
}

async function loadLlmStatus() {
  try {
    const config = await fetch("/api/config").then((response) => response.json());
    llmConfigured = Boolean(config.llm_configured);
    renderAiSources(config.search_channels);
    if (llmConfigured) {
      llmStatusEl.className = "llm-status ok";
      const web = (config.search_channels?.web_search || []).join(", ") || "duckduckgo";
      llmStatusEl.textContent = t("msg.llmConfiguredDetail", {
        model: config.llm_model || "default",
        web,
      });
      discoverBtn.disabled = false;
      if (discoverViaPiBtn) discoverViaPiBtn.disabled = false;
      hideLeadsState();
    } else {
      llmStatusEl.className = "llm-status warn";
      llmStatusEl.textContent = t("msg.llmNotConfiguredDetail");
      discoverBtn.disabled = true;
      if (discoverViaPiBtn) discoverViaPiBtn.disabled = true;
      showLeadsNeedLlm();
    }
  } catch {
    llmStatusEl.className = "llm-status warn";
    llmStatusEl.textContent = t("msg.llmReadFailed");
    discoverBtn.disabled = true;
    if (discoverViaPiBtn) discoverViaPiBtn.disabled = true;
  }
  updatePiAgentStatus();
}

function setDiscoverRunning(running) {
  if (running) {
    discoverBtn.textContent = t("msg.discoverCancel");
    discoverBtn.classList.add("danger-btn");
    discoverBtn.disabled = false;
    if (discoverViaPiBtn) discoverViaPiBtn.disabled = true;
    retryDiscoverBtn.classList.add("hidden");
  } else {
    discoverBtn.textContent = t("aiLeads.discoverDirect");
    discoverBtn.classList.remove("danger-btn");
    discoverBtn.disabled = !llmConfigured;
    if (discoverViaPiBtn) discoverViaPiBtn.disabled = !llmConfigured;
  }
}

async function runLeadDiscovery() {
  if (discoverController) {
    discoverController.abort();
    return;
  }
  const query = leadQueryInput.value.trim();
  if (!query) {
    alert(t("msg.describeLeads"));
    return;
  }
  if (!llmConfigured) {
    alert(t("msg.llmNotConfiguredLeads"));
    return;
  }

  if (discoverBackgroundInput?.checked) {
    try {
      const data = await api("/api/jobs/leads/discover", {
        method: "POST",
        body: JSON.stringify({
          query,
          min_score: Number(minScoreInput.value) || 60,
          delay: 0.5,
          auto_import: autoImportInput.checked,
        }),
      });
      trackBackgroundJob(data.job);
      alert(t("msg.jobStartedBackground"));
    } catch (error) {
      alert(errorMessage(error, t("msg.leadsError", { message: error.message })));
    }
    return;
  }

  aiLeads = [];
  renderAiLeads();
  aiPlanEl.classList.add("hidden");
  aiSourcesEl.classList.add("hidden");
  resetChannelPanel();
  hideLeadsState();
  aiProgressEl.classList.remove("hidden");
  aiProgressFill.style.width = "0%";
  aiProgressText.textContent = t("msg.aiAnalyzing");
  lastDiscoverQuery = query;
  discoverController = new AbortController();
  setDiscoverRunning(true);
  retryDiscoverBtn.classList.add("hidden");
  importLeadsBtn.disabled = true;

  try {
    const response = await fetch("/api/leads/discover/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      signal: discoverController.signal,
      body: JSON.stringify({
        query,
        min_score: Number(minScoreInput.value) || 60,
        delay: 0.5,
        auto_import: autoImportInput.checked,
      }),
    });

    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "AI 线索发现失败");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const line = chunk.trim();
        if (!line.startsWith("data: ")) continue;
        const payload = JSON.parse(line.slice(6));

        if (payload.type === "status") {
          aiProgressText.textContent = payload.message;
        }

        if (payload.type === "status" && /评估|评分/.test(payload.message || "")) {
          setChannel("scoring", { state: "active" });
        }

        if (payload.type === "status" && /提取部分失败/.test(payload.message || "")) {
          setChannel("llm_extract", { state: "failed", preview: payload.message });
        }

        if (payload.type === "plan") {
          renderAiPlan(payload.plan);
          renderAiSources(payload.plan.channels);
        }

        if (payload.type === "source_result") {
          const preview = (payload.preview || []).join(" · ");
          setChannel(payload.source, { state: "done", count: payload.count, preview });
          aiProgressText.textContent = `${payload.source} 返回 ${payload.count} 条`;
        }

        if (payload.type === "progress") {
          const percent = Math.round((payload.index / payload.total) * 100);
          aiProgressFill.style.width = `${percent}%`;
          aiProgressText.textContent = `${payload.message}（${payload.index}/${payload.total}）`;
          setChannel("arin", {
            state: payload.index >= payload.total ? "done" : "active",
            count: `${payload.index}/${payload.total}`,
            preview: payload.network || `AS${payload.asn}`,
          });
        }

        if (payload.type === "lead") {
          ensureLeadSelected(payload.lead);
          aiLeads.push(payload.lead);
          renderAiLeads();
        }

        if (payload.type === "error") {
          throw new Error(payload.message);
        }

        if (payload.type === "done") {
          aiProgressFill.style.width = "100%";
          aiProgressText.textContent = payload.message || t("msg.discoverComplete");
          setChannel("scoring", { state: "done", count: (payload.leads || aiLeads).length });
          if (payload.leads) {
            aiLeads = payload.leads.map((lead) => {
              ensureLeadSelected(lead);
              return lead;
            });
            renderAiLeads();
          }
          if (payload.import) {
            alert(formatImportResult(payload.import));
            await loadContacts();
          }
          if ((payload.leads || aiLeads).length === 0) {
            showLeadsEmpty();
          }
        }
      }
    }
  } catch (error) {
    if (error.name === "AbortError") {
      aiProgressText.textContent = t("msg.discoverCancelled");
    } else {
      aiProgressText.textContent = t("msg.discoverFailed");
      if (typeof showLeadsError === "function") {
        showLeadsError(error.message || "AI 线索发现失败");
      } else {
        alert(error.message || "AI 线索发现失败");
      }
    }
  } finally {
    discoverController = null;
    setDiscoverRunning(false);
  }
}

async function importAiLeads() {
  const selected = getSelectedAiLeads();
  if (selected.length === 0) {
    alert(t("msg.selectLeadsToImport"));
    return;
  }

  const rows = normalizeImportRows(
    selected.map((lead) => ({
      ...lead,
      source: "ai-lead",
      notes: `AI评分 ${lead.lead_score || 0} · ${lead.lead_reason || ""}`.trim(" ·"),
    })),
  );

  try {
    const result = await api("/api/contacts/import", {
      method: "POST",
      body: JSON.stringify({ rows: normalizeImportRows(rows) }),
    });
    alert(formatImportResult(result));
    await loadContacts();
    switchView("contacts");
  } catch (error) {
    alert(error.message || t("msg.importFailed"));
  }
}

async function bootstrap() {
  try {
    const user = await api("/api/me");
    currentUserEl.textContent = user.username;
    currentUserId = user.id;
    await loadPiChatForUser(currentUserId);
  } catch {
    window.location.href = "/login";
    return;
  }

  await loadLlmStatus();
  leadQueryInput.value = t("bootstrap.leadQueryDefault");
  scheduleQueryInput.value = leadQueryInput.value;
  await loadContacts();
  await loadSchedules();
  await resumeBackgroundJobs();
}

function backgroundJobLabel(job) {
  const progress = job.progress || {};
  if (job.job_type === "lookup") {
    if (progress.type === "progress") {
      return t("jobs.lookupRunning", { current: progress.index, total: progress.total });
    }
    return t("jobs.lookupStarting");
  }
  if (job.job_type === "enrich_contact") {
    if (progress.type === "progress") {
      return t("jobs.enrichProgress", {
        current: progress.index,
        total: progress.total,
        asn: progress.asn ? `AS${progress.asn}` : "",
      });
    }
    if (progress.message) {
      return t("jobs.enrichRunning", { message: progress.message });
    }
    return t("jobs.enrichStarting");
  }
  if (progress.message) {
    return t("jobs.leadsProgress", { message: progress.message });
  }
  return t("jobs.leadsRunning");
}

function renderBackgroundJobsBar() {
  if (!backgroundJobsBar) return;
  const active = [...backgroundJobTrackers.values()]
    .map((entry) => entry.job)
    .filter((job) => job && (job.status === "pending" || job.status === "running"));
  if (!active.length) {
    backgroundJobsBar.classList.add("hidden");
    backgroundJobsBar.innerHTML = "";
    return;
  }
  backgroundJobsBar.classList.remove("hidden");
  backgroundJobsBar.innerHTML = active
    .map(
      (job) =>
        `<span class="background-job-chip">${escapeHtml(backgroundJobLabel(job))}</span>`,
    )
    .join("");
}

function applyLookupJobResult(job) {
  const result = job.result || {};
  if (Array.isArray(result.rows)) {
    allRows = result.rows;
    for (const row of allRows) ensureRowSelected(row);
    csvContent = result.csv || "";
    renderRows();
    exportBtn.disabled = allRows.length === 0;
    importBtn.disabled = getSelectedImportableRows().length === 0;
    progressEl.classList.remove("hidden");
    progressFill.style.width = "100%";
    progressText.textContent = t("msg.lookupDone");
  }
  const activeView = document.querySelector(".tab.active")?.dataset.view;
  if (activeView !== "lookup") {
    alert(t("jobs.lookupDone", { emails: result.emails || 0 }));
  }
}

function applyLeadDiscoverJobResult(job) {
  const result = job.result || {};
  if (Array.isArray(result.leads)) {
    aiLeads = result.leads.map((lead) => {
      ensureLeadSelected(lead);
      return lead;
    });
    renderAiLeads();
    hideLeadsState();
    aiProgressEl.classList.add("hidden");
    if (result.import) {
      loadContacts().catch(() => {});
    }
  }
  const activeView = document.querySelector(".tab.active")?.dataset.view;
  if (activeView !== "ai-leads") {
    alert(t("jobs.leadsDone", { count: (result.leads || []).length }));
  }
}

function applyEnrichContactJobResult(job) {
  const result = job.result || {};
  if (result.import) {
    loadContacts().catch(() => {});
  }
  const count = Array.isArray(result.leads) ? result.leads.length : 0;
  const contactId = result.contact_id || "";
  alert(
    t("jobs.enrichDone", {
      count,
      contactId,
      message: result.message || job.message || "",
    }),
  );
}

function finishBackgroundJob(job) {
  if (job.status === "done") {
    if (job.job_type === "lookup") applyLookupJobResult(job);
    else if (job.job_type === "lead_discover") applyLeadDiscoverJobResult(job);
    else if (job.job_type === "enrich_contact") applyEnrichContactJobResult(job);
  } else if (job.status === "error") {
    alert(`${t("jobs.failed")}: ${job.message || ""}`);
  }
  backgroundJobTrackers.delete(job.id);
  renderBackgroundJobsBar();
}

async function pollBackgroundJob(jobId) {
  try {
    const data = await api(`/api/jobs/${jobId}`);
    const job = data.job;
    if (!job) return;
    const entry = backgroundJobTrackers.get(jobId);
    if (entry) entry.job = job;
    renderBackgroundJobsBar();
    if (job.status === "done" || job.status === "error") {
      if (entry?.timer) clearInterval(entry.timer);
      finishBackgroundJob(job);
    }
  } catch {
    // keep polling on transient errors
  }
}

function trackBackgroundJob(job) {
  if (!job?.id) return;
  const existing = backgroundJobTrackers.get(job.id);
  if (existing?.timer) clearInterval(existing.timer);
  const entry = { job, timer: setInterval(() => pollBackgroundJob(job.id), 2000) };
  backgroundJobTrackers.set(job.id, entry);
  renderBackgroundJobsBar();
  if (job.status === "done" || job.status === "error") {
    finishBackgroundJob(job);
  } else {
    pollBackgroundJob(job.id).catch(() => {});
  }
}

async function resumeBackgroundJobs() {
  try {
    const data = await api("/api/jobs?active=true");
    for (const job of data.jobs || []) trackBackgroundJob(job);
  } catch {
    // ignore
  }
}

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
  clearTimeout(asnParseTimer);
  asnParseTimer = setTimeout(() => {
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
  if (lastDiscoverQuery) {
    leadQueryInput.value = lastDiscoverQuery;
  }
  runLeadDiscovery();
});
importLeadsBtn.addEventListener("click", importAiLeads);
roleFilter.addEventListener("change", renderRows);
contactStatusFilter.addEventListener("change", () => loadContacts(true).catch((error) => alert(error.message)));
contactFollowUpFilter.addEventListener("change", () => loadContacts(true).catch((error) => alert(error.message)));
contactSearchInput.addEventListener("input", () => {
  clearTimeout(contactSearchTimer);
  contactSearchTimer = setTimeout(() => {
    loadContacts(true).catch((error) => alert(error.message));
  }, 300);
});
contactsPageSizeSelect.addEventListener("change", () => {
  contactsPageSize = Number(contactsPageSizeSelect.value) || 50;
  loadContacts(true).catch((error) => alert(error.message));
});
contactsPrevBtn.addEventListener("click", () => {
  if (contactsPage > 1) {
    contactsPage -= 1;
    loadContacts().catch((error) => alert(error.message));
  }
});
contactsNextBtn.addEventListener("click", () => {
  if (contactsPage < contactsPages) {
    contactsPage += 1;
    loadContacts().catch((error) => alert(error.message));
  }
});
contactsSelectAll.addEventListener("change", () => {
  for (const contact of contacts) {
    if (contactsSelectAll.checked) {
      selectedContactIds.add(contact.id);
    } else {
      selectedContactIds.delete(contact.id);
    }
  }
  renderContacts();
});
contactsBody.addEventListener("change", (event) => {
  const checkbox = event.target.closest(".contact-select");
  if (!checkbox) return;
  const id = Number(checkbox.dataset.id);
  if (checkbox.checked) {
    selectedContactIds.add(id);
  } else {
    selectedContactIds.delete(id);
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

async function changePassword() {
  const current = document.getElementById("pwd-current").value;
  const newPwd = document.getElementById("pwd-new").value;
  const confirm = document.getElementById("pwd-confirm").value;
  const statusEl = document.getElementById("password-status");
  if (!current || !newPwd) {
    alert(t("msg.passwordFieldsRequired"));
    return;
  }
  if (newPwd !== confirm) {
    alert(t("msg.passwordMismatch"));
    return;
  }
  await api("/api/me/password", {
    method: "POST",
    body: JSON.stringify({ current_password: current, new_password: newPwd }),
  });
  document.getElementById("pwd-current").value = "";
  document.getElementById("pwd-new").value = "";
  document.getElementById("pwd-confirm").value = "";
  statusEl.textContent = t("msg.passwordUpdated");
}
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
      alert(error.message)
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
    const contact = contacts.find((item) => String(item.id) === String(enrichBtn.dataset.id));
    enrichContactViaBackground(contact).catch((error) => alert(errorMessage(error, t("msg.enrichFailed"))));
    return;
  }
  const deleteBtn = event.target.closest(".action-delete");
  if (deleteBtn) {
    closeAllContactActionMenus();
    deleteContact(deleteBtn.dataset.id).catch((error) => alert(error.message));
  }
});

document.querySelector(".contacts-table-wrap")?.addEventListener(
  "scroll",
  closeAllContactActionMenus,
  { passive: true }
);
window.addEventListener("resize", closeAllContactActionMenus);

schedulesBody.addEventListener("click", (event) => {
  const runBtn = event.target.closest(".schedule-run");
  if (runBtn) {
    runScheduleNow(runBtn.dataset.id).catch((error) => alert(error.message));
    return;
  }
  const toggleBtn = event.target.closest(".schedule-toggle");
  if (toggleBtn) {
    toggleSchedule(toggleBtn.dataset.id, toggleBtn.dataset.enabled === "1").catch((error) => alert(error.message));
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
  const lead = aiLeads[Number(check.dataset.index)];
  if (lead) lead._selected = check.checked;
  updateAiLeadsStats();
});

leadDetailModal.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-detail]")) closeLeadDetail();
});

leadDetailImport.addEventListener("change", () => {
  if (detailLeadIndex === null) return;
  const lead = aiLeads[detailLeadIndex];
  if (lead) lead._selected = leadDetailImport.checked;
  renderAiLeads();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !leadDetailModal.classList.contains("hidden")) closeLeadDetail();
});

function refreshUiOnLanguageChange() {
  const activeView = document.querySelector(".tab.active")?.dataset.view || "lookup";
  switchView(activeView);
  renderRows();
  renderContacts();
  renderAiLeads();
  renderSchedules();
  renderMailTemplateSelect();
  renderEmailTemplatesList();
  updatePiChatHistoryHint();
  updateAiLeadsStats();
  if (allRows.length === 0 && statsEl) {
    statsEl.textContent = t("common.notYetQueried");
  } else {
    updateStats();
  }
  refreshAsnPreview().catch(() => {});
  if (llmConfigured) {
    loadLlmStatus().catch(() => {});
  } else {
    updatePiAgentStatus();
  }
  renderBackgroundJobsBar();
}

window.addEventListener("languagechange", refreshUiOnLanguageChange);

bootstrap();

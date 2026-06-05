const asnInput = document.getElementById("asn-input");
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
const scheduleIntervalInput = document.getElementById("schedule-interval");
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
const aiPlanEl = document.getElementById("ai-plan");
const aiSourcesEl = document.getElementById("ai-sources");
const aiProgressEl = document.getElementById("ai-progress");
const aiProgressFill = document.getElementById("ai-progress-fill");
const aiProgressText = document.getElementById("ai-progress-text");
const aiStatsEl = document.getElementById("ai-stats");
const aiLeadsBody = document.getElementById("ai-leads-body");
const aiChannelsEl = document.getElementById("ai-channels");
const importLeadsBtn = document.getElementById("import-leads-btn");
const retryDiscoverBtn = document.getElementById("retry-discover-btn");
const leadDetailModal = document.getElementById("lead-detail-modal");
const leadDetailBody = document.getElementById("lead-detail-body");
const leadDetailImport = document.getElementById("lead-detail-import");
let detailLeadIndex = null;

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

const FOLLOW_UP_STATUS_LABELS = {
  new: "新客户",
  contacted: "已联系",
  replied: "已回复",
  invalid: "无效",
  interested: "有意向",
};
let schedules = [];
let scheduleRuns = {};
let aiLeads = [];
const CHANNEL_DEFS = [
  { key: "peeringdb", name: "PeeringDB" },
  { key: "web_search", name: "搜索引擎" },
  { key: "web_regex", name: "网页解析" },
  { key: "llm_extract", name: "LLM 提取" },
  { key: "arin", name: "ARIN RDAP" },
  { key: "scoring", name: "LLM 评分" },
];
let channelState = {};
let discoverController = null;
let lastDiscoverQuery = "";
let llmConfigured = false;
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
    throw new Error("请先登录");
  }

  if (!response.ok) {
    let detail = "请求失败";
    try {
      const error = await response.json();
      detail = error.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  if (response.status === 204) return null;
  return response.json();
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
  const selection = importable > 0 ? ` · 已选 ${selected} / 共 ${importable}` : "";
  statsEl.textContent = `${uniqueAsns} 个 ASN · ${emails} 条邮箱 · ${errors} 条异常${selection}`;
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
    tr.innerHTML = `<td colspan="8">${allRows.length ? "当前筛选无结果" : "输入 ASN 列表后点击「开始查询」"}</td>`;
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
    const statusText = row.error || (row.email ? "OK" : "无邮箱");
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
      <td>${emailCell}</td>
      <td class="mono">${escapeHtml(row.handle || "—")}</td>
      <td class="${statusClass}">${escapeHtml(statusText)}</td>
    `;
    resultsBody.appendChild(tr);
  }

  updateStats();
  importBtn.disabled = getSelectedImportableRows().length === 0;
}

function followUpStatusBadge(status) {
  const key = status || "new";
  const label = FOLLOW_UP_STATUS_LABELS[key] || key;
  return `<span class="status-badge follow-up-${escapeHtml(key)}">${escapeHtml(label)}</span>`;
}

function renderContacts() {
  contactsBody.innerHTML = "";
  updateContactsBulkBar();

  if (contacts.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="11">暂无联系人，查询 ASN 或 AI 发现后可导入</td>`;
    contactsBody.appendChild(tr);
    contactsStatsEl.textContent = contactsTotal ? `共 ${contactsTotal} 位 · 本页 0 条` : "共 0 位联系人";
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

    tr.innerHTML = `
      <td class="col-select"><input type="checkbox" class="contact-select" data-id="${contact.id}" ${checked}></td>
      <td>${statusBadge}</td>
      <td>${escapeHtml(contact.org || "—")}</td>
      <td>${escapeHtml(contact.name || "—")}</td>
      <td><a class="email-link" href="mailto:${contact.email}">${escapeHtml(contact.email)}</a></td>
      <td>${roles || "—"}</td>
      <td class="mono">${contact.asn ? `AS${contact.asn}` : "—"}</td>
      <td>${escapeHtml(contact.source || "arin")}</td>
      <td>${escapeHtml(contact.notes || "—")}</td>
      <td class="mono">${escapeHtml(formatTime(contact.email_sent ? contact.email_sent_at : contact.created_at))}</td>
      <td class="action-cell">
        <button type="button" class="link-btn action-edit" data-id="${contact.id}">编辑</button>
        <button type="button" class="link-btn action-notes" data-id="${contact.id}">时间线</button>
        <button type="button" class="link-btn action-mail" data-id="${contact.id}">发邮件</button>
        <button type="button" class="link-btn action-status" data-id="${contact.id}" data-status="${escapeHtml(contact.follow_up_status || "new")}">改状态</button>
        <button type="button" class="link-btn action-mark" data-id="${contact.id}" data-sent="${contact.email_sent ? "0" : "1"}">${contact.email_sent ? "取消标记" : "标记已发"}</button>
        <button type="button" class="link-btn action-delete" data-id="${contact.id}">删除</button>
      </td>
    `;
    contactsBody.appendChild(tr);
  }

  contactsStatsEl.textContent = `共 ${contactsTotal} 位 · 本页 ${contacts.length} 位（已发 ${sentCount}）· 第 ${contactsPage}/${contactsPages} 页`;
  renderContactsPagination();
  syncContactsSelectAllCheckbox();
}

function updateContactsBulkBar() {
  const count = selectedContactIds.size;
  contactsBulkBar.classList.toggle("hidden", count === 0);
  contactsSelectedCountEl.textContent = `已选 ${count} 位`;
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
  contactsPageInfo.textContent = `第 ${contactsPage} / ${contactsPages} 页（共 ${contactsTotal} 条）`;
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
    alert("请先输入 ASN 列表");
    return;
  }

  allRows = [];
  csvContent = "";
  renderRows();
  setLoading(true);
  progressEl.classList.remove("hidden");
  progressFill.style.width = "0%";
  progressText.textContent = "开始查询…";

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
      throw new Error(error.detail || "查询失败");
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

        if (payload.type === "progress") {
          for (const row of payload.rows) {
            ensureRowSelected(row);
          }
          allRows.push(...payload.rows);
          renderRows();
          const percent = Math.round((payload.index / payload.total) * 100);
          progressFill.style.width = `${percent}%`;
          progressText.textContent = `正在查询 AS${payload.asn}（${payload.index}/${payload.total}）`;
        }

        if (payload.type === "done") {
          progressFill.style.width = "100%";
          progressText.textContent = "查询完成";
          csvContent = rowsToCsv(allRows);
          exportBtn.disabled = allRows.length === 0;
          importBtn.disabled = getSelectedImportableRows().length === 0;
        }
      }
    }
  } catch (error) {
    alert(error.message || "查询失败，请稍后重试");
    progressText.textContent = "查询失败";
  } finally {
    setLoading(false);
  }
}

function formatImportResult(result) {
  const parts = [
    `新增 ${result.imported} 条`,
    `重复 ${result.duplicates} 条`,
    `跳过 ${result.skipped} 条`,
  ];
  if (result.filtered) {
    parts.push(`过滤 ${result.filtered} 条`);
  }
  return `导入完成：${parts.join("，")}`;
}

async function importResults() {
  const rows = getSelectedImportableRows();
  if (rows.length === 0) {
    alert("请先勾选要导入的邮箱记录");
    return;
  }

  importBtn.disabled = true;
  try {
    const result = await api("/api/contacts/import", {
      method: "POST",
      body: JSON.stringify({ rows }),
    });
    alert(formatImportResult(result));
    await loadContacts();
    switchView("contacts");
  } catch (error) {
    alert(error.message || "导入失败");
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
    alert("请先勾选联系人");
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
    throw new Error(error.detail || "备份下载失败");
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
    throw new Error(error.detail || "导出失败");
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
  alert(`去重完成：删除 ${result.removed} 条重复联系人，剩余 ${result.total} 条`);
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
  const options = Object.keys(FOLLOW_UP_STATUS_LABELS);
  const currentLabel = FOLLOW_UP_STATUS_LABELS[currentStatus] || currentStatus;
  const lines = options.map((opt, index) => `${index + 1}. ${FOLLOW_UP_STATUS_LABELS[opt]}`).join("\n");
  const input = prompt(`当前：${currentLabel}\n\n${lines}\n\n输入序号 1-${options.length}：`);
  if (input === null) return;
  const index = Number(input.trim()) - 1;
  if (!Number.isInteger(index) || index < 0 || index >= options.length) {
    alert("无效序号");
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
  if (!contact.email_sent && confirm("是否同时标记为已发邮件？")) {
    markContactSent(contactId, true).catch((error) => alert(error.message));
  }
}

function renderMailTemplateSelect() {
  const current = mailTemplateSelect.value;
  mailTemplateSelect.innerHTML = `<option value="">无模板</option>`;
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
    emailTemplatesListEl.innerHTML = `<p class="stats">暂无模板，可在下方创建</p>`;
    return;
  }

  for (const template of emailTemplates) {
    const item = document.createElement("div");
    item.className = "template-item";
    item.innerHTML = `
      <div class="template-item-head">
        <strong>${escapeHtml(template.name)}</strong>
        <span class="template-item-actions">
          <button type="button" class="link-btn template-edit" data-id="${template.id}">编辑</button>
          <button type="button" class="link-btn template-delete" data-id="${template.id}">删除</button>
        </span>
      </div>
      <p class="stats">${escapeHtml(template.subject || "（无主题）")}</p>
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
  saveTemplateBtn.textContent = "保存模板";
  templateStatusEl.textContent = "";
}

async function saveEmailTemplate() {
  const name = templateNameInput.value.trim();
  if (!name) {
    alert("请填写模板名称");
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
    templateStatusEl.textContent = "模板已更新";
  } else {
    await api("/api/email-templates", { method: "POST", body: JSON.stringify(payload) });
    templateStatusEl.textContent = "模板已创建";
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
  saveTemplateBtn.textContent = "更新模板";
  templateStatusEl.textContent = `正在编辑：${template.name}`;
}

async function deleteEmailTemplate(templateId) {
  if (!confirm("确定删除该模板？")) return;
  await api(`/api/email-templates/${templateId}`, { method: "DELETE" });
  if (String(editingTemplateId) === String(templateId)) {
    resetTemplateForm();
  }
  await loadEmailTemplates();
}
function formatJobRunLine(run) {
  const statusLabel = run.status === "ok" ? "成功" : "失败";
  const detail =
    run.status === "ok"
      ? `${run.leads_found} 线索 / ${run.imported} 导入`
      : escapeHtml(run.message || statusLabel);
  return `<li><span class="run-time">${escapeHtml(formatTime(run.ran_at))}</span> <span class="run-status run-${escapeHtml(run.status)}">${statusLabel}</span> ${detail}</li>`;
}

function renderSchedules() {
  schedulesBody.innerHTML = "";
  if (schedules.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="7">暂无定时任务</td>`;
    schedulesBody.appendChild(tr);
    schedulesStatsEl.textContent = "暂无定时任务";
    return;
  }

  for (const job of schedules) {
    const tr = document.createElement("tr");
    const enabledBadge = job.enabled
      ? `<span class="status-badge sent">启用</span>`
      : `<span class="status-badge unsent">停用</span>`;
    tr.innerHTML = `
      <td>${escapeHtml(job.name)}</td>
      <td class="mono">${job.interval_hours} 小时</td>
      <td>${enabledBadge}</td>
      <td class="mono">${escapeHtml(formatTime(job.last_run_at))}</td>
      <td class="mono">${escapeHtml(formatTime(job.next_run_at))}</td>
      <td>${escapeHtml(job.last_run_message || job.last_run_status || "—")}</td>
      <td class="action-cell">
        <button type="button" class="link-btn schedule-run" data-id="${job.id}">立即运行</button>
        <button type="button" class="link-btn schedule-toggle" data-id="${job.id}" data-enabled="${job.enabled ? "0" : "1"}">${job.enabled ? "停用" : "启用"}</button>
        <button type="button" class="link-btn schedule-delete" data-id="${job.id}">删除</button>
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
  schedulesStatsEl.textContent = `共 ${schedules.length} 个定时任务`;
}

async function loadSchedules() {
  const data = await api("/api/schedules");
  schedules = data.schedules || [];
  scheduleRuns = {};
  await Promise.all(
    schedules.map(async (job) => {
      const runData = await api(`/api/schedules/${job.id}/runs?limit=5`);
      scheduleRuns[job.id] = runData.runs || [];
    })
  );
  renderSchedules();
}

async function createSchedule(event) {
  event.preventDefault();
  await api("/api/schedules", {
    method: "POST",
    body: JSON.stringify({
      name: scheduleNameInput.value.trim(),
      query: scheduleQueryInput.value.trim(),
      interval_hours: Number(scheduleIntervalInput.value) || 24,
      min_score: Number(scheduleMinScoreInput.value) || 60,
      auto_import: scheduleAutoImportInput.checked,
      enabled: true,
    }),
  });
  scheduleForm.reset();
  scheduleAutoImportInput.checked = true;
  scheduleIntervalInput.value = "24";
  scheduleMinScoreInput.value = "60";
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
  if (!confirm("确定删除该定时任务？")) return;
  await api(`/api/schedules/${jobId}`, { method: "DELETE" });
  await loadSchedules();
}

async function runScheduleNow(jobId) {
  if (!confirm("立即运行该定时任务？可能需要几分钟。")) return;
  const result = await api(`/api/schedules/${jobId}/run`, { method: "POST" });
  if (result.ok) {
    alert(result.message || "运行完成");
  } else {
    alert(result.message || "运行失败");
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
  aiDot.title = aiOn ? "LLM 已配置" : "LLM 未配置";

  const autoDot = document.getElementById("rail-dot-automation");
  const autoOn = data.scheduler_enabled === "1";
  autoDot.classList.toggle("on", autoOn);
  autoDot.title = autoOn ? "定时任务已启用" : "定时任务未启用";
}

async function loadSettingsForm() {
  const data = await api("/api/settings");
  setInputValue("setting-default-admin-user", data.default_admin_user);
  setInputValue("setting-llm-base-url", data.llm_base_url);
  setInputValue("setting-llm-model", data.llm_model);
  setInputValue("setting-scheduler-poll-seconds", data.scheduler_poll_seconds);
  document.getElementById("setting-scheduler-enabled").checked = data.scheduler_enabled === "1";

  const secretFields = [
    ["setting-default-admin-password", data.default_admin_password, data.default_admin_password_configured],
    ["setting-session-secret", data.session_secret, data.session_secret_configured],
    ["setting-llm-api-key", data.llm_api_key, data.llm_api_key_configured],
    ["setting-tavily-api-key", data.tavily_api_key, data.tavily_api_key_configured],
    ["setting-serpapi-key", data.serpapi_key, data.serpapi_key_configured],
    ["setting-bing-search-key", data.bing_search_key, data.bing_search_key_configured],
  ];
  for (const [id, masked, configured] of secretFields) {
    const el = document.getElementById(id);
    el.value = "";
    el.placeholder = configured ? `已配置 ${masked}，留空则不修改` : "未配置";
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
    scheduler_enabled: document.getElementById("setting-scheduler-enabled").checked ? "1" : "0",
    scheduler_poll_seconds: document.getElementById("setting-scheduler-poll-seconds").value.trim(),
  };

  const secrets = [
    ["default_admin_password", "setting-default-admin-password"],
    ["session_secret", "setting-session-secret"],
    ["llm_api_key", "setting-llm-api-key"],
    ["tavily_api_key", "setting-tavily-api-key"],
    ["serpapi_key", "setting-serpapi-key"],
    ["bing_search_key", "setting-bing-search-key"],
  ];
  for (const [key, id] of secrets) {
    const value = document.getElementById(id).value.trim();
    if (value) payload[key] = value;
  }

  await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
  settingsStatusEl.textContent = "设置已保存";
  await loadLlmStatus();
  await loadSettingsForm();
}

async function deleteContact(contactId) {
  if (!confirm("确定删除该联系人？")) return;
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
    li.textContent = "暂无备注，在下方添加第一条。";
    contactNotesList.appendChild(li);
    return;
  }
  for (const note of notes) {
    const li = document.createElement("li");
    li.className = "note-item";
    li.innerHTML = `
      <div class="note-item-meta">
        <span>${escapeHtml(formatTime(note.created_at))}</span>
        <button type="button" class="link-btn note-delete" data-note-id="${note.id}">删除</button>
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
  contactNotesTitle.textContent = "备注时间线";
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
  if (!confirm("确定删除这条备注？")) return;
  await api(`/api/contacts/${notesContactId}/notes/${noteId}`, { method: "DELETE" });
  await loadContactNotes(notesContactId);
}

function renderBarChart(container, items, { getLabel = (k) => k, colors } = {}) {
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = `<p class="stats">暂无数据</p>`;
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
  dashboardStatsEl.textContent = `共 ${data.total} 位联系人 · 已发 ${data.sent} · 未发 ${data.unsent}`;
  statsSummaryEl.innerHTML = `
    <div class="stat-card"><strong>${data.total}</strong><span>联系人总数</span></div>
    <div class="stat-card"><strong>${data.sent}</strong><span>已发邮件</span></div>
    <div class="stat-card"><strong>${data.unsent}</strong><span>未发邮件</span></div>
    <div class="stat-card"><strong>${data.by_follow_up_status.interested || 0}</strong><span>有意向</span></div>
  `;
  renderBarChart(
    chartFollowUpEl,
    Object.entries(data.by_follow_up_status || {}).map(([key, count]) => ({ key, count })),
    { getLabel: (key) => FOLLOW_UP_STATUS_LABELS[key] || key },
  );
  renderBarChart(
    chartSentEl,
    [
      { key: "sent", count: data.sent },
      { key: "unsent", count: data.unsent },
    ],
    { getLabel: (key) => (key === "sent" ? "已发" : "未发"), colors: ["var(--chart-pos)", "var(--chart-neutral)"] },
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
  dashboardStatsEl.textContent = "加载中…";
  renderDashboard(await api("/api/stats"));
}

function switchView(view) {
  tabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === view);
  });

  lookupView.classList.toggle("hidden", view !== "lookup");
  aiLeadsView.classList.toggle("hidden", view !== "ai-leads");
  schedulesView.classList.toggle("hidden", view !== "schedules");
  settingsView.classList.toggle("hidden", view !== "settings");
  contactsView.classList.toggle("hidden", view !== "contacts");
  statsView.classList.toggle("hidden", view !== "stats");

  if (view === "lookup") {
    pageTitle.textContent = "ARIN ASN Role 邮箱查询";
    pageSubtitle.textContent = "批量查询 ARIN 管辖 ASN 的 abuse / technical / administrative / routing 等 role 邮箱";
  } else if (view === "ai-leads") {
    pageTitle.textContent = "AI 线索发现";
    pageSubtitle.textContent = "AI 自动通过搜索引擎、PeeringDB、ARIN RDAP 等多渠道搜索并评分筛选销售线索";
  } else if (view === "schedules") {
    pageTitle.textContent = "定时任务";
    pageSubtitle.textContent = "按设定间隔自动运行 AI 线索发现，并自动导入联系人（按邮箱去重）";
    loadSchedules().catch((error) => alert(error.message));
  } else if (view === "settings") {
    pageTitle.textContent = "系统设置";
    pageSubtitle.textContent = "LLM、搜索引擎、定时任务等配置保存在数据库，Web 界面直接管理";
    loadSettingsForm().catch((error) => alert(error.message));
    switchSettingsCat(activeSettingsCat);
    loadEmailTemplates().catch((error) => alert(error.message));
  } else if (view === "stats") {
    pageTitle.textContent = "统计概览";
    pageSubtitle.textContent = "联系人跟进状态、发信与来源分布，以及近期导入趋势";
    loadStats().catch((error) => alert(error.message));
  } else {
    pageTitle.textContent = "联系人列表";
    pageSubtitle.textContent = "管理联系人状态：标记已发邮件、筛选未联系对象、一键去重";
    loadContacts().catch((error) => alert(error.message));
    loadEmailTemplates().catch(() => {});
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
    aiStatsEl.textContent = "尚未开始";
    importLeadsBtn.disabled = true;
    return;
  }
  aiStatsEl.textContent = `已选 ${selected} / 共 ${total}`;
  importLeadsBtn.disabled = selected === 0;
}

function renderAiLeads() {
  aiLeadsBody.innerHTML = "";

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
      <td><span class="score-badge">${lead.lead_score || 0}</span></td>
      <td><span class="source-tag">${escapeHtml(formatSource(lead))}</span></td>
      <td>${escapeHtml(lead.org || lead.network_name || "—")}</td>
      <td><a class="email-link" href="mailto:${lead.email}">${escapeHtml(lead.email)}</a></td>
      <td>${roles || "—"}</td>
      <td class="mono">${lead.asn ? `AS${lead.asn}` : "—"}</td>
      <td>
        ${escapeHtml(lead.lead_reason || lead.source_detail || "—")}
        <button type="button" class="link-btn lead-detail-btn" data-index="${index}">详情</button>
      </td>
    `;
    aiLeadsBody.appendChild(tr);
  }

  updateAiLeadsStats();
}

function formatSource(lead) {
  const source = lead.source || "unknown";
  const map = {
    "web-search": "搜索引擎",
    "arin-rdap": "ARIN RDAP",
    peeringdb: "PeeringDB",
    "ai-lead": "AI",
  };
  return map[source] || source;
}

function openLeadDetail(index) {
  const lead = aiLeads[index];
  if (!lead) return;
  detailLeadIndex = index;
  const roles = (lead.roles || []).map((r) => `<span class="role-tag">${escapeHtml(r)}</span>`).join(" ") || "—";
  const rows = [
    ["组织", escapeHtml(lead.org || lead.network_name || "—"), false],
    ["邮箱", `<a class="email-link" href="mailto:${lead.email}">${escapeHtml(lead.email || "—")}</a>`, true],
    ["ASN", lead.asn ? `AS${lead.asn}` : "—", true],
    ["Role", roles, false],
    ["来源", escapeHtml(formatSource(lead)), false],
    ["来源详情", escapeHtml(lead.source_detail || "—"), false],
    ["网络名", escapeHtml(lead.network_name || "—"), false],
    ["匹配关键词", escapeHtml(lead.matched_keyword || "—"), true],
    ["AI 评分", `<span class="score-badge">${lead.lead_score || 0}</span>`, false],
    ["AI 理由", escapeHtml(lead.lead_reason || "—"), false],
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
  aiSourcesEl.innerHTML = `
    <p><strong>已启用渠道：</strong>搜索引擎(${escapeHtml(web)}) · PeeringDB · ARIN RDAP · LLM 提取/评分</p>
  `;
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
        <span class="ai-channel-name">${escapeHtml(def.name)}</span>
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
      llmStatusEl.textContent = `LLM 已配置（${config.llm_model || "default"}）· 搜索渠道：${web} + PeeringDB + ARIN`;
      discoverBtn.disabled = false;
    } else {
      llmStatusEl.className = "llm-status warn";
      llmStatusEl.textContent = "LLM 未配置：请在「系统设置」填写 API Key。搜索引擎默认 DuckDuckGo";
      discoverBtn.disabled = true;
    }
  } catch {
    llmStatusEl.className = "llm-status warn";
    llmStatusEl.textContent = "无法读取 LLM 配置";
    discoverBtn.disabled = true;
  }
}

function setDiscoverRunning(running) {
  if (running) {
    discoverBtn.textContent = "取消";
    discoverBtn.classList.add("danger-btn");
    discoverBtn.disabled = false;
    retryDiscoverBtn.classList.add("hidden");
  } else {
    discoverBtn.textContent = "AI 开始找线索";
    discoverBtn.classList.remove("danger-btn");
    discoverBtn.disabled = !llmConfigured;
  }
}

async function runLeadDiscovery() {
  if (discoverController) {
    discoverController.abort();
    return;
  }
  const query = leadQueryInput.value.trim();
  if (!query) {
    alert("请先描述你要找的销售线索");
    return;
  }
  if (!llmConfigured) {
    alert("LLM 未配置，无法使用 AI 线索发现");
    return;
  }

  aiLeads = [];
  renderAiLeads();
  aiPlanEl.classList.add("hidden");
  aiSourcesEl.classList.add("hidden");
  resetChannelPanel();
  aiProgressEl.classList.remove("hidden");
  aiProgressFill.style.width = "0%";
  aiProgressText.textContent = "AI 正在分析需求…";
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
          aiProgressText.textContent = payload.message || "完成";
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
        }
      }
    }
  } catch (error) {
    if (error.name === "AbortError") {
      aiProgressText.textContent = "已取消";
    } else {
      aiProgressText.textContent = "失败";
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
    alert("请先勾选要导入的线索");
    return;
  }

  const rows = selected.map((lead) => ({
    ...lead,
    source: "ai-lead",
    notes: `AI评分 ${lead.lead_score || 0} · ${lead.lead_reason || ""}`.trim(" ·"),
  }));

  try {
    const result = await api("/api/contacts/import", {
      method: "POST",
      body: JSON.stringify({ rows }),
    });
    alert(formatImportResult(result));
    await loadContacts();
    switchView("contacts");
  } catch (error) {
    alert(error.message || "导入失败");
  }
}

async function bootstrap() {
  try {
    const user = await api("/api/me");
    currentUserEl.textContent = user.username;
  } catch {
    window.location.href = "/login";
    return;
  }

  await loadLlmStatus();
  asnInput.value = "15169\n7922\n3320";
  leadQueryInput.value = "找美国大型 ISP 和有线电视运营商，优先 networking / peering 相关联系人";
  scheduleQueryInput.value = leadQueryInput.value;
  await loadContacts();
  await loadSchedules();
}

lookupBtn.addEventListener("click", runLookup);
exportBtn.addEventListener("click", downloadCsv);
importBtn.addEventListener("click", importResults);
discoverBtn.addEventListener("click", runLeadDiscovery);
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
    .then((result) => alert(`已更新 ${result.updated} 位联系人`))
    .catch((error) => alert(error.message));
});
bulkMarkSentBtn.addEventListener("click", () => {
  bulkContactsAction("mark_sent")
    .then((result) => alert(`已标记 ${result.updated} 位联系人`))
    .catch((error) => alert(error.message));
});
bulkDeleteBtn.addEventListener("click", () => {
  if (!confirm("确定删除选中的联系人？")) return;
  bulkContactsAction("delete")
    .then((result) => alert(`已删除 ${result.deleted} 位联系人`))
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

async function changePassword() {
  const current = document.getElementById("pwd-current").value;
  const newPwd = document.getElementById("pwd-new").value;
  const confirm = document.getElementById("pwd-confirm").value;
  const statusEl = document.getElementById("password-status");
  if (!current || !newPwd) {
    alert("请填写当前密码和新密码");
    return;
  }
  if (newPwd !== confirm) {
    alert("两次输入的新密码不一致");
    return;
  }
  await api("/api/me/password", {
    method: "POST",
    body: JSON.stringify({ current_password: current, new_password: newPwd }),
  });
  document.getElementById("pwd-current").value = "";
  document.getElementById("pwd-new").value = "";
  document.getElementById("pwd-confirm").value = "";
  statusEl.textContent = "密码已更新";
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

contactsBody.addEventListener("click", (event) => {
  const editBtn = event.target.closest(".action-edit");
  if (editBtn) {
    openContactEdit(editBtn.dataset.id);
    return;
  }
  const notesBtn = event.target.closest(".action-notes");
  if (notesBtn) {
    openContactNotes(notesBtn.dataset.id).catch((error) => alert(error.message));
    return;
  }
  const mailBtn = event.target.closest(".action-mail");
  if (mailBtn) {
    openMailClient(mailBtn.dataset.id);
    return;
  }
  const statusBtn = event.target.closest(".action-status");
  if (statusBtn) {
    changeContactFollowUpStatus(statusBtn.dataset.id, statusBtn.dataset.status).catch((error) =>
      alert(error.message)
    );
    return;
  }
  const markBtn = event.target.closest(".action-mark");
  if (markBtn) {
    markContactSent(markBtn.dataset.id, markBtn.dataset.sent === "1").catch((error) => alert(error.message));
    return;
  }
  const deleteBtn = event.target.closest(".action-delete");
  if (deleteBtn) {
    deleteContact(deleteBtn.dataset.id).catch((error) => alert(error.message));
  }
});

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

bootstrap();

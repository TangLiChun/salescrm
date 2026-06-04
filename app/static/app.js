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
const contactsBody = document.getElementById("contacts-body");
const contactsStatsEl = document.getElementById("contacts-stats");
const contactStatusFilter = document.getElementById("contact-status-filter");
const contactFollowUpFilter = document.getElementById("contact-follow-up-filter");
const dedupeContactsBtn = document.getElementById("dedupe-contacts-btn");
const refreshContactsBtn = document.getElementById("refresh-contacts-btn");
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
const importLeadsBtn = document.getElementById("import-leads-btn");

let allRows = [];
let csvContent = "";
let contacts = [];

const FOLLOW_UP_STATUS_LABELS = {
  new: "新客户",
  contacted: "已联系",
  replied: "已回复",
  invalid: "无效",
  interested: "有意向",
};
let schedules = [];
let aiLeads = [];
let llmConfigured = false;

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
      <td>AS${row.asn}</td>
      <td>${escapeHtml(row.org || "—")}</td>
      <td>${roles || "—"}</td>
      <td>${escapeHtml(row.name || "—")}</td>
      <td>${emailCell}</td>
      <td>${escapeHtml(row.handle || "—")}</td>
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

  if (contacts.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="10">暂无联系人，查询 ASN 或 AI 发现后可导入</td>`;
    contactsBody.appendChild(tr);
    contactsStatsEl.textContent = "共 0 位联系人";
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

    tr.innerHTML = `
      <td>${statusBadge}</td>
      <td>${escapeHtml(contact.org || "—")}</td>
      <td>${escapeHtml(contact.name || "—")}</td>
      <td><a class="email-link" href="mailto:${contact.email}">${escapeHtml(contact.email)}</a></td>
      <td>${roles || "—"}</td>
      <td>${contact.asn ? `AS${contact.asn}` : "—"}</td>
      <td>${escapeHtml(contact.source || "arin")}</td>
      <td>${escapeHtml(contact.notes || "—")}</td>
      <td>${escapeHtml(formatTime(contact.email_sent ? contact.email_sent_at : contact.created_at))}</td>
      <td class="action-cell">
        <button type="button" class="link-btn action-mail" data-email="${escapeHtml(contact.email)}">发邮件</button>
        <button type="button" class="link-btn action-status" data-id="${contact.id}" data-status="${escapeHtml(contact.follow_up_status || "new")}">改状态</button>
        <button type="button" class="link-btn action-mark" data-id="${contact.id}" data-sent="${contact.email_sent ? "0" : "1"}">${contact.email_sent ? "取消标记" : "标记已发"}</button>
        <button type="button" class="link-btn action-delete" data-id="${contact.id}">删除</button>
      </td>
    `;
    contactsBody.appendChild(tr);
  }

  contactsStatsEl.textContent = `共 ${contacts.length} 位 · 已发 ${sentCount} · 未发 ${contacts.length - sentCount}`;
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
    alert(`导入完成：新增 ${result.imported} 条，重复 ${result.duplicates} 条，跳过 ${result.skipped} 条`);
    await loadContacts();
    switchView("contacts");
  } catch (error) {
    alert(error.message || "导入失败");
  } finally {
    importBtn.disabled = getSelectedImportableRows().length === 0;
  }
}

async function loadContacts() {
  const status = contactStatusFilter.value || "all";
  const followUp = contactFollowUpFilter.value || "all";
  const params = new URLSearchParams({ status, follow_up_status: followUp });
  const data = await api(`/api/contacts?${params.toString()}`);
  contacts = data.contacts || [];
  renderContacts();
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

function openMailClient(email) {
  window.location.href = `mailto:${email}`;
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
      <td>${job.interval_hours} 小时</td>
      <td>${enabledBadge}</td>
      <td>${escapeHtml(formatTime(job.last_run_at))}</td>
      <td>${escapeHtml(formatTime(job.next_run_at))}</td>
      <td>${escapeHtml(job.last_run_message || job.last_run_status || "—")}</td>
      <td class="action-cell">
        <button type="button" class="link-btn schedule-toggle" data-id="${job.id}" data-enabled="${job.enabled ? "0" : "1"}">${job.enabled ? "停用" : "启用"}</button>
        <button type="button" class="link-btn schedule-delete" data-id="${job.id}">删除</button>
      </td>
    `;
    schedulesBody.appendChild(tr);
  }
  schedulesStatsEl.textContent = `共 ${schedules.length} 个定时任务`;
}

async function loadSchedules() {
  const data = await api("/api/schedules");
  schedules = data.schedules || [];
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

function setInputValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value ?? "";
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
  await loadContacts();
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
  } else {
    pageTitle.textContent = "联系人列表";
    pageSubtitle.textContent = "管理联系人状态：标记已发邮件、筛选未联系对象、一键去重";
    loadContacts().catch((error) => alert(error.message));
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
      <td>${lead.asn ? `AS${lead.asn}` : "—"}</td>
      <td>${escapeHtml(lead.lead_reason || lead.source_detail || "—")}</td>
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

async function runLeadDiscovery() {
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
  aiProgressEl.classList.remove("hidden");
  aiProgressFill.style.width = "0%";
  aiProgressText.textContent = "AI 正在分析需求…";
  discoverBtn.disabled = true;
  importLeadsBtn.disabled = true;

  try {
    const response = await fetch("/api/leads/discover/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
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

        if (payload.type === "plan") {
          renderAiPlan(payload.plan);
          renderAiSources(payload.plan.channels);
        }

        if (payload.type === "source_result") {
          aiProgressText.textContent = `${payload.source} 返回 ${payload.count} 条`;
        }

        if (payload.type === "networks") {
          aiProgressText.textContent = `找到 ${payload.total} 个候选网络，开始查询 ARIN…`;
        }

        if (payload.type === "progress") {
          const percent = Math.round((payload.index / payload.total) * 100);
          aiProgressFill.style.width = `${percent}%`;
          aiProgressText.textContent = `${payload.message}（${payload.index}/${payload.total}）`;
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
          if (payload.leads) {
            aiLeads = payload.leads.map((lead) => {
              ensureLeadSelected(lead);
              return lead;
            });
            renderAiLeads();
          }
          if (payload.import) {
            alert(
              `已自动导入：新增 ${payload.import.imported} 条，重复 ${payload.import.duplicates} 条`
            );
            await loadContacts();
          }
        }
      }
    }
  } catch (error) {
    alert(error.message || "AI 线索发现失败");
    aiProgressText.textContent = "失败";
  } finally {
    discoverBtn.disabled = !llmConfigured;
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
    alert(`导入完成：新增 ${result.imported} 条，重复 ${result.duplicates} 条，跳过 ${result.skipped} 条`);
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
importLeadsBtn.addEventListener("click", importAiLeads);
roleFilter.addEventListener("change", renderRows);
contactStatusFilter.addEventListener("change", () => loadContacts().catch((error) => alert(error.message)));
contactFollowUpFilter.addEventListener("change", () => loadContacts().catch((error) => alert(error.message)));
dedupeContactsBtn.addEventListener("click", () => dedupeContacts().catch((error) => alert(error.message)));
refreshContactsBtn.addEventListener("click", () => loadContacts().catch((error) => alert(error.message)));
refreshSchedulesBtn.addEventListener("click", () => loadSchedules().catch((error) => alert(error.message)));
scheduleForm.addEventListener("submit", (event) => createSchedule(event).catch((error) => alert(error.message)));
settingsForm.addEventListener("submit", (event) => saveSettings(event).catch((error) => alert(error.message)));
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

contactsBody.addEventListener("click", (event) => {
  const mailBtn = event.target.closest(".action-mail");
  if (mailBtn) {
    openMailClient(mailBtn.dataset.email);
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

bootstrap();

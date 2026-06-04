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
const contactsView = document.getElementById("contacts-view");
const contactsBody = document.getElementById("contacts-body");
const contactsStatsEl = document.getElementById("contacts-stats");
const refreshContactsBtn = document.getElementById("refresh-contacts-btn");
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
  importBtn.disabled = isLoading || getImportableRows().length === 0;
}

function getImportableRows() {
  return allRows.filter((row) => row.email && !row.error);
}

function updateStats() {
  const visibleRows = getVisibleRows();
  const uniqueAsns = new Set(visibleRows.map((row) => row.asn)).size;
  const emails = visibleRows.filter((row) => row.email).length;
  const errors = visibleRows.filter((row) => row.error).length;
  statsEl.textContent = `${uniqueAsns} 个 ASN · ${emails} 条邮箱 · ${errors} 条异常 · 可导入 ${getImportableRows().length} 条`;
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
    tr.innerHTML = `<td colspan="7">${allRows.length ? "当前筛选无结果" : "输入 ASN 列表后点击「开始查询」"}</td>`;
    resultsBody.appendChild(tr);
    updateStats();
    importBtn.disabled = getImportableRows().length === 0;
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    const roles = row.roles.map((role) => `<span class="role-tag">${role}</span>`).join("");
    const emailCell = row.email
      ? `<a class="email-link" href="mailto:${row.email}">${row.email}</a>`
      : "—";
    const statusClass = row.error ? "status-error" : row.email ? "status-ok" : "status-warn";
    const statusText = row.error || (row.email ? "OK" : "无邮箱");

    tr.innerHTML = `
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
  importBtn.disabled = getImportableRows().length === 0;
}

function renderContacts() {
  contactsBody.innerHTML = "";

  if (contacts.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="9">暂无联系人，查询 ASN 后可导入</td>`;
    contactsBody.appendChild(tr);
    contactsStatsEl.textContent = "共 0 位联系人";
    return;
  }

  for (const contact of contacts) {
    const tr = document.createElement("tr");
    const roles = (contact.roles || "")
      .split(",")
      .filter(Boolean)
      .map((role) => `<span class="role-tag">${escapeHtml(role)}</span>`)
      .join("");

    tr.innerHTML = `
      <td>${escapeHtml(contact.org || "—")}</td>
      <td>${escapeHtml(contact.name || "—")}</td>
      <td><a class="email-link" href="mailto:${contact.email}">${escapeHtml(contact.email)}</a></td>
      <td>${roles || "—"}</td>
      <td>${contact.asn ? `AS${contact.asn}` : "—"}</td>
      <td>${escapeHtml(contact.source || "arin")}</td>
      <td>${escapeHtml(contact.notes || "—")}</td>
      <td>${escapeHtml(formatTime(contact.created_at))}</td>
      <td><button type="button" class="link-btn" data-id="${contact.id}">删除</button></td>
    `;
    contactsBody.appendChild(tr);
  }

  contactsStatsEl.textContent = `共 ${contacts.length} 位联系人`;
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
          importBtn.disabled = getImportableRows().length === 0;
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
  const rows = getImportableRows();
  if (rows.length === 0) {
    alert("没有可导入的邮箱记录");
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
    importBtn.disabled = getImportableRows().length === 0;
  }
}

async function loadContacts() {
  const data = await api("/api/contacts");
  contacts = data.contacts || [];
  renderContacts();
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
  contactsView.classList.toggle("hidden", view !== "contacts");

  if (view === "lookup") {
    pageTitle.textContent = "ARIN ASN Role 邮箱查询";
    pageSubtitle.textContent = "批量查询 ARIN 管辖 ASN 的 abuse / technical / administrative / routing 等 role 邮箱";
  } else if (view === "ai-leads") {
    pageTitle.textContent = "AI 线索发现";
    pageSubtitle.textContent = "AI 自动通过搜索引擎、PeeringDB、ARIN RDAP 等多渠道搜索并评分筛选销售线索";
  } else {
    pageTitle.textContent = "联系人列表";
    pageSubtitle.textContent = "从 ASN 查询或 AI 线索发现导入的联系人";
    loadContacts().catch((error) => alert(error.message));
  }
}

function renderAiLeads() {
  aiLeadsBody.innerHTML = "";

  if (aiLeads.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="7">用自然语言描述目标客户，AI 会从多个渠道自动搜索并评分</td>`;
    aiLeadsBody.appendChild(tr);
    aiStatsEl.textContent = "尚未开始";
    importLeadsBtn.disabled = true;
    return;
  }

  for (const lead of aiLeads) {
    const tr = document.createElement("tr");
    const roles = (lead.roles || []).map((role) => `<span class="role-tag">${escapeHtml(role)}</span>`).join("");
    tr.innerHTML = `
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

  aiStatsEl.textContent = `共 ${aiLeads.length} 条高匹配线索`;
  importLeadsBtn.disabled = aiLeads.length === 0;
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
      llmStatusEl.textContent = "LLM 未配置：请设置 LLM_API_KEY。搜索引擎默认 DuckDuckGo，也可配 Tavily/SerpAPI/Bing";
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
            aiLeads = payload.leads;
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
  if (aiLeads.length === 0) return;

  const rows = aiLeads.map((lead) => ({
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
  await loadContacts();
}

lookupBtn.addEventListener("click", runLookup);
exportBtn.addEventListener("click", downloadCsv);
importBtn.addEventListener("click", importResults);
discoverBtn.addEventListener("click", runLeadDiscovery);
importLeadsBtn.addEventListener("click", importAiLeads);
roleFilter.addEventListener("change", renderRows);
refreshContactsBtn.addEventListener("click", () => loadContacts().catch((error) => alert(error.message)));
logoutBtn.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

tabs.forEach((tab) => {
  tab.addEventListener("click", () => switchView(tab.dataset.view));
});

contactsBody.addEventListener("click", (event) => {
  const button = event.target.closest("[data-id]");
  if (!button) return;
  deleteContact(button.dataset.id).catch((error) => alert(error.message));
});

bootstrap();

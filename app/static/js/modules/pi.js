import { t } from "../../i18n.js";
import * as dom from "../core/dom.js";
import * as state from "../core/state.js";
import {
  CHANNEL_DEFS,
  PI_LEAD_STREAM_TOOLS,
  PI_CHANNEL_ICON,
  PI_SOURCE_CHANNEL_MAP,
  PI_CHAT_STORAGE_VERSION,
  PI_THREADS_STORAGE_VERSION,
  PI_CHAT_MAX_STORED,
  PI_THREADS_MAX,
} from "../core/state.js";
import { api, escapeHtml, errorMessage, formatApiDetail, formatImportResult, normalizeImportRows } from "../core/utils.js";
import { notifyInfo } from "../core/toast.js";
import { deps } from "../core/deps.js";
import { trackBackgroundJob } from "../jobs/index.js";
import { scoreBadgeClass, formatSource } from "./leads.js";

const {
  piChatMessagesEl, piChatForm, piChatInput, piChatSendBtn, piChatStopBtn, piChatClearBtn,
  piChatHistoryHintEl, piChatBackgroundInput, piThreadListEl, piChatProgressEl, piChatProgressFill,
  piChatProgressText, leadQueryInput, minScoreInput, autoImportInput,
} = dom;
export function piChatStorageKey(userId) {
  return `salescrm:pi-chat:${PI_CHAT_STORAGE_VERSION}:${userId}`;
}

export function piThreadsStorageKey(userId) {
  return `salescrm:pi-threads:${PI_THREADS_STORAGE_VERSION}:${userId}`;
}

export function createPiThreadId() {
  return `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function defaultPiThreadTitle() {
  return t("pi.newThreadTitle");
}

export function summarizePiThreadTitle(text) {
  const line = String(text || "")
    .split("\n")
    .map((part) => part.trim())
    .find(Boolean);
  if (!line) return defaultPiThreadTitle();
  return line.length > 42 ? `${line.slice(0, 42)}…` : line;
}

export function historyFingerprint(history) {
  if (!Array.isArray(history) || !history.length) return "";
  const firstUser = history.find((item) => item.role === "user");
  return firstUser?.content ? String(firstUser.content).slice(0, 96) : "";
}

export function isValidHistoryItem(item) {
  if (!item?.role) return false;
  if (item.role === "user" || item.role === "assistant") {
    return Boolean(String(item.content || "").trim());
  }
  if (item.role === "tool") {
    return Boolean(item.name);
  }
  return false;
}

export function normalizeHistoryItems(history) {
  return Array.isArray(history) ? history.filter(isValidHistoryItem) : [];
}

export function appendPiHistoryEntry(entry) {
  state.piChatHistory.push(entry);
  if (state.piChatHistory.length > PI_CHAT_MAX_STORED) {
    state.piChatHistory = state.piChatHistory.slice(-PI_CHAT_MAX_STORED);
  }
  savePiChatHistory();
}

export function getActivePiThread() {
  return state.piThreads.find((thread) => thread.id === state.activePiThreadId) || null;
}

export function syncActivePiThreadHistory() {
  const thread = getActivePiThread();
  if (!thread) return;
  thread.history = state.piChatHistory.slice(-PI_CHAT_MAX_STORED);
  thread.updatedAt = Date.now();
}

export function renderPiThreadList() {
  if (!piThreadListEl) return;
  piThreadListEl.innerHTML = "";
  if (!state.piThreads.length) {
    const li = document.createElement("li");
    li.className = "pi-thread-empty stats";
    li.textContent = t("pi.noThreads");
    piThreadListEl.appendChild(li);
    return;
  }
  const sorted = [...state.piThreads].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
  for (const thread of sorted) {
    const li = document.createElement("li");
    li.className = "pi-thread-item";
    const count = Array.isArray(thread.history) ? thread.history.length : 0;
    li.innerHTML = `
      <button type="button" class="pi-thread-btn ${thread.id === state.activePiThreadId ? "active" : ""}" data-thread-id="${thread.id}">
        <span class="pi-thread-title">${escapeHtml(thread.title || defaultPiThreadTitle())}</span>
        <span class="pi-thread-meta">${t("pi.threadMeta", { count })}</span>
      </button>
      <button type="button" class="pi-thread-delete" data-delete-thread="${thread.id}" aria-label="${t("pi.deleteThread")}">×</button>
    `;
    piThreadListEl.appendChild(li);
  }
}

export function savePiThreadsStore() {
  savePiThreadsStoreLocal();
  persistActivePiThread().catch(() => {});
}

export function migratePiChatV1ToThreads(userId) {
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

export function recoverLegacyPiHistory(userId) {
  const legacy = migratePiChatV1ToThreads(userId);
  if (!legacy?.history?.length) return false;

  const legacyFp = historyFingerprint(legacy.history);
  if (
    state.piThreads.some(
      (thread) => thread.history?.length && historyFingerprint(thread.history) === legacyFp,
    )
  ) {
    return false;
  }

  const emptyMatch = state.piThreads.find((thread) => {
    if (thread.history?.length) return false;
    if (!thread.title || !legacy.title) return false;
    const a = thread.title.slice(0, 12);
    const b = legacy.title.slice(0, 12);
    return a === b || thread.title.includes(b) || legacy.title.includes(a);
  });
  if (emptyMatch) {
    emptyMatch.history = legacy.history;
    emptyMatch.updatedAt = Date.now();
    if (state.activePiThreadId === emptyMatch.id) {
      state.piChatHistory = [...legacy.history];
    }
    savePiThreadsStore();
    return true;
  }

  state.piThreads.unshift({
    ...legacy,
    id: createPiThreadId(),
    title: legacy.title || t("pi.recoveredThreadTitle"),
    updatedAt: Date.now(),
  });
  if (state.piThreads.length > PI_THREADS_MAX) {
    state.piThreads = state.piThreads.slice(0, PI_THREADS_MAX);
  }
  savePiThreadsStore();
  return true;
}

export function mapServerPiThreadSummary(row) {
  return {
    id: row.id,
    title: row.title || "",
    history: [],
    has_context_summary: Boolean(row.has_context_summary || (row.context_summary || "").trim()),
    createdAt: row.created_at ? Date.parse(row.created_at) || Date.now() : Date.now(),
    updatedAt: row.updated_at ? Date.parse(row.updated_at) || Date.now() : Date.now(),
  };
}

export function mapServerPiThreadFull(row) {
  return {
    id: row.id,
    title: row.title || "",
    history: normalizeHistoryItems(row.history),
    has_context_summary: Boolean(row.has_context_summary || (row.context_summary || "").trim()),
    createdAt: row.created_at ? Date.parse(row.created_at) || Date.now() : Date.now(),
    updatedAt: row.updated_at ? Date.parse(row.updated_at) || Date.now() : Date.now(),
  };
}

export async function refreshActivePiThreadMeta() {
  if (!state.activePiThreadId) return;
  try {
    const thread = await api(`/api/pi/threads/${encodeURIComponent(state.activePiThreadId)}`);
    const index = state.piThreads.findIndex((item) => item.id === state.activePiThreadId);
    if (index >= 0) {
      state.piThreads[index].has_context_summary = Boolean((thread.context_summary || "").trim());
    }
    updatePiChatHistoryHint();
  } catch {
    // ignore metadata refresh failures
  }
}

export async function fetchActivePiThreadHistory() {
  if (!state.activePiThreadId) return;
  try {
    const thread = await api(`/api/pi/threads/${encodeURIComponent(state.activePiThreadId)}`);
    const mapped = mapServerPiThreadFull(thread);
    const index = state.piThreads.findIndex((item) => item.id === mapped.id);
    if (index >= 0) {
      state.piThreads[index] = { ...state.piThreads[index], ...mapped };
    }
    state.piChatHistory = mapped.history;
  } catch {
    const active = getActivePiThread();
    state.piChatHistory = normalizeHistoryItems(active?.history);
  }
}

export async function syncPiThreadsToServer() {
  if (!state.currentUserId) return;
  syncActivePiThreadHistory();
  await api("/api/pi/threads/sync", {
    method: "POST",
    body: JSON.stringify({
      threads: state.piThreads.map((thread) => ({
        id: thread.id,
        title: thread.title || "",
        history: thread.history || [],
      })),
      active_thread_id: state.activePiThreadId,
    }),
  });
}

export async function persistActivePiThread() {
  if (!state.activePiThreadId) return;
  syncActivePiThreadHistory();
  const thread = getActivePiThread();
  if (!thread) return;
  await api(`/api/pi/threads/${encodeURIComponent(state.activePiThreadId)}`, {
    method: "PUT",
    body: JSON.stringify({
      title: thread.title || "",
      history: thread.history || [],
    }),
  });
}

export async function loadPiChatFromServer(userId) {
  state.piThreads = [];
  state.activePiThreadId = null;
  state.piChatHistory = [];
  try {
    const data = await api("/api/pi/threads");
    state.piThreads = Array.isArray(data.threads)
      ? data.threads.map(mapServerPiThreadSummary).slice(0, PI_THREADS_MAX)
      : [];
  } catch {
    loadPiThreadsFromStorage(userId);
    restorePiChatUi();
    return;
  }

  if (!state.piThreads.length) {
    loadPiThreadsFromStorage(userId);
    if (state.piThreads.length) {
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

  if (!state.activePiThreadId || !state.piThreads.some((thread) => thread.id === state.activePiThreadId)) {
    state.activePiThreadId = state.piThreads[0]?.id || null;
  }
  await fetchActivePiThreadHistory();
  restorePiChatUi();
  savePiThreadsStoreLocal();
}

export function savePiThreadsStoreLocal() {
  if (!state.currentUserId) return;
  syncActivePiThreadHistory();
  try {
    localStorage.setItem(
      piThreadsStorageKey(state.currentUserId),
      JSON.stringify({
        activeThreadId: state.activePiThreadId,
        threads: state.piThreads.slice(0, PI_THREADS_MAX),
        updatedAt: Date.now(),
      }),
    );
    renderPiThreadList();
    updatePiChatHistoryHint();
  } catch {
    // ignore quota errors
  }
}

export function loadPiThreadsFromStorage(userId) {
  state.piThreads = [];
  state.activePiThreadId = null;
  state.piChatHistory = [];
  try {
    const raw = localStorage.getItem(piThreadsStorageKey(userId));
    if (raw) {
      const data = JSON.parse(raw);
      state.piThreads = Array.isArray(data.threads)
        ? data.threads.filter((thread) => thread?.id).slice(0, PI_THREADS_MAX)
        : [];
      state.activePiThreadId = data.activeThreadId || state.piThreads[0]?.id || null;
    }
  } catch {
    state.piThreads = [];
    state.activePiThreadId = null;
  }

  if (!state.piThreads.length) {
    const migrated = migratePiChatV1ToThreads(userId);
    if (migrated) {
      state.piThreads = [migrated];
      state.activePiThreadId = migrated.id;
      savePiThreadsStore();
    }
  } else {
    recoverLegacyPiHistory(userId);
  }

  if (!state.piThreads.length) {
    beginPiThread();
    return;
  }

  if (!state.activePiThreadId || !state.piThreads.some((thread) => thread.id === state.activePiThreadId)) {
    state.activePiThreadId = state.piThreads[0].id;
  }
  const active = getActivePiThread();
  state.piChatHistory = normalizeHistoryItems(active?.history);
}

export function beginPiThread(title) {
  if (state.piChatBusy) {
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
  state.piThreads.unshift(thread);
  if (state.piThreads.length > PI_THREADS_MAX) {
    state.piThreads = state.piThreads.slice(0, PI_THREADS_MAX);
  }
  state.activePiThreadId = thread.id;
  state.piChatHistory = [];
  restorePiChatUi();
  renderPiThreadList();
  updatePiChatHistoryHint();
  return thread;
}

export function createPiThread(title) {
  const thread = beginPiThread(title);
  if (thread) {
    savePiThreadsStore();
  }
  return thread;
}

export async function switchPiThread(threadId) {
  if (threadId === state.activePiThreadId) return;
  if (state.piChatBusy) {
    alert(t("pi.busySwitch"));
    return;
  }
  syncActivePiThreadHistory();
  savePiThreadsStoreLocal();
  state.activePiThreadId = threadId;
  await fetchActivePiThreadHistory();
  restorePiChatUi();
  savePiThreadsStoreLocal();
}

export async function deletePiThread(threadId) {
  if (state.piChatBusy) {
    alert(t("pi.busySwitch"));
    return;
  }
  if (!window.confirm(t("pi.confirmDeleteThread"))) return;
  try {
    await api(`/api/pi/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
  } catch {
    // still remove locally if server delete fails
  }
  state.piThreads = state.piThreads.filter((thread) => thread.id !== threadId);
  if (!state.piThreads.length) {
    createPiThread();
    return;
  }
  if (state.activePiThreadId === threadId) {
    state.activePiThreadId = state.piThreads[0].id;
    state.piChatHistory = Array.isArray(state.piThreads[0].history) ? [...state.piThreads[0].history] : [];
    restorePiChatUi();
  }
  savePiThreadsStore();
}

export function savePiChatHistory() {
  savePiThreadsStore();
}

export function loadPiChatHistoryFromStorage(userId) {
  loadPiThreadsFromStorage(userId);
}

export async function loadPiChatForUser(userId) {
  await loadPiChatFromServer(userId);
}

export function restorePiChatToolEntry(item) {
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

export function restorePiChatUi() {
  piChatMessagesEl.innerHTML = "";
  if (!state.piChatHistory.length) {
    piChatMessagesEl.innerHTML = `<div class="pi-chat-empty">${t("pi.emptyHint")}</div>`;
    renderPiThreadList();
    updatePiChatHistoryHint();
    return;
  }
  for (const item of state.piChatHistory) {
    if (item.role === "user" || item.role === "assistant") {
      appendPiChatBubble(item.role, item.content);
    } else if (item.role === "tool") {
      restorePiChatToolEntry(item);
    }
  }
  renderPiThreadList();
  updatePiChatHistoryHint();
}

export function updatePiChatHistoryHint() {
  if (!piChatHistoryHintEl) return;
  const count = state.piChatHistory.length;
  const threadCount = state.piThreads.length;
  if (!count) {
    piChatHistoryHintEl.textContent = t("msg.piHistoryLocal");
    return;
  }
  piChatHistoryHintEl.textContent = t("msg.piHistorySavedThreads", { count, threads: threadCount });
  const active = state.piThreads.find((item) => item.id === state.activePiThreadId);
  if (active?.has_context_summary) {
    piChatHistoryHintEl.textContent += ` · ${t("msg.piContextCompressed")}`;
  }
}

export function buildPiLeadMessage() {
  const query = leadQueryInput.value.trim();
  if (!query) return "";
  const minScore = Number(minScoreInput.value) || 60;
  const lines = [`请帮我找销售线索：${query}`, `最低匹配分 ${minScore}`];
  if (autoImportInput.checked) {
    lines.push(t("pi.autoImportHint"));
  }
  return lines.join("\n");
}

export async function openPiAgentForLeads() {
  const message = buildPiLeadMessage();
  if (!message) {
    alert(t("msg.describeLeads"));
    return;
  }
  if (!state.llmConfigured) {
    alert(t("msg.piNotAvailable"));
    return;
  }
  deps.switchView("pi-agent");
  beginPiThread(summarizePiThreadTitle(message));
  await sendPiChatMessage(message);
}

export async function openPiEnrichContact(contact) {
  if (!contact?.id) return;
  if (!state.llmConfigured) {
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
  deps.switchView("pi-agent");
  beginPiThread(t("pi.enrichThreadTitle", { label }));
  await sendPiChatMessage(message);
}

export async function enrichContactViaBackground(contact) {
  if (!contact?.id) return;
  if (!state.llmConfigured) {
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
    notifyInfo(t("msg.jobStartedBackground"));
  } catch (error) {
    alert(errorMessage(error, t("msg.enrichFailed")));
  }
}

export function formatPiToolSummary(name, result) {
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

export function appendPiChatLookupTool(name) {
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

export function appendPiChatLookupRow(toolEl, row) {
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

export async function importPiChatLookup(toolEl) {
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
    await deps.loadContacts();
  } catch (error) {
    alert(errorMessage(error, t("msg.importFailed")));
  }
}

export function scrollPiChatToBottom() {
  if (!piChatMessagesEl) return;
  piChatMessagesEl.scrollTo({ top: piChatMessagesEl.scrollHeight, behavior: "smooth" });
}

export function stopPiDiscoverTimer(toolEl) {
  if (toolEl?._piDiscoverTimer) {
    clearInterval(toolEl._piDiscoverTimer);
    toolEl._piDiscoverTimer = null;
  }
}

export function startPiDiscoverTimer(toolEl) {
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

export function initPiDiscoverChannelState(toolEl) {
  toolEl._piChannelState = {};
  for (const def of CHANNEL_DEFS) {
    toolEl._piChannelState[def.key] = { state: "idle", count: "", preview: "" };
  }
  toolEl._piDiscoverStartedAt = Date.now();
  toolEl._piLeadCount = 0;
}

export function renderPiDiscoverLivePanel(toolEl) {
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

export function setPiDiscoverChannel(toolEl, key, patch) {
  if (!toolEl?._piChannelState?.[key]) return;
  Object.assign(toolEl._piChannelState[key], patch);
  renderPiDiscoverLivePanel(toolEl);
}

export function pushPiDiscoverTicker(toolEl, message) {
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

export function updatePiDiscoverRdapBar(toolEl, index, total, network) {
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

export function handlePiDiscoverProgress(toolEl, message) {
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

export function finalizePiDiscoverTool(toolEl, event) {
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

export function handlePiDiscoverToolEvent(toolEl, event) {
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

export function appendPiChatDiscoverTool(name) {
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

export function appendPiChatLeadRow(toolEl, lead) {
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

export function renderPiChatPlan(toolEl, plan) {
  if (!toolEl || !plan) return;
  const planEl = toolEl.querySelector(".pi-chat-tool-plan");
  if (!planEl) return;
  planEl.classList.remove("hidden");
  planEl.innerHTML = `<p><strong>策略：</strong>${escapeHtml(plan.summary || "")}</p>`;
}

export async function importPiChatLeads(toolEl) {
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
    await deps.loadContacts();
  } catch (error) {
    alert(errorMessage(error, t("msg.importFailed")));
  }
}

export function updatePiAgentStatus() {
  const enabled = state.llmConfigured;
  piChatInput.disabled = !enabled || state.piChatBusy;
  piChatSendBtn.disabled = !enabled || state.piChatBusy;
}

export function clearPiChatEmpty() {
  const empty = piChatMessagesEl.querySelector(".pi-chat-empty");
  if (empty) empty.remove();
}

export function renderMarkdown(text) {
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

export function sanitizePiAssistantDisplay(text) {
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

export function appendPiChatBubble(role, text) {
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

export let piChatStreamRaf = null;

export function updatePiChatAssistantBubble(el, text, streaming = false) {
  if (!el) return;
  el.classList.toggle("streaming", streaming);
  if (piChatStreamRaf) cancelAnimationFrame(piChatStreamRaf);
  piChatStreamRaf = requestAnimationFrame(() => {
    el.innerHTML = renderMarkdown(sanitizePiAssistantDisplay(text || ""));
    piChatMessagesEl.scrollTop = piChatMessagesEl.scrollHeight;
    piChatStreamRaf = null;
  });
}

export function appendPiChatStatus(text) {
  clearPiChatEmpty();
  const el = document.createElement("div");
  el.className = "pi-chat-status";
  el.textContent = text;
  piChatMessagesEl.appendChild(el);
  piChatMessagesEl.scrollTop = piChatMessagesEl.scrollHeight;
  return el;
}

export function appendPiChatTool(name) {
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

export function setPiChatBusy(busy) {
  state.piChatBusy = busy;
  piChatStopBtn.classList.toggle("hidden", !busy);
  updatePiAgentStatus();
  piChatProgressEl.classList.toggle("hidden", !busy);
  if (!busy) {
    piChatProgressFill.style.width = "0%";
    piChatProgressText.textContent = "";
  }
}

export async function sendPiChatMessage(message) {
  const text = String(message || "").trim();
  if (!text || state.piChatBusy || !state.llmConfigured) return;

  piChatInput.value = "";
  appendPiChatBubble("user", text);
  state.piChatHistory.push({ role: "user", content: text });
  const thread = getActivePiThread();
  if (thread && (thread.title === defaultPiThreadTitle() || !thread.title)) {
    thread.title = summarizePiThreadTitle(text);
  }
  savePiChatHistory();

  if (piChatBackgroundInput?.checked) {
    try {
      await persistActivePiThread();
      const data = await api("/api/jobs/pi-agent", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          thread_id: state.activePiThreadId,
        }),
      });
      trackBackgroundJob(data.job);
      notifyInfo(t("msg.jobStartedBackground"));
      savePiThreadsStore();
      refreshActivePiThreadMeta().catch(() => {});
    } catch (error) {
      appendPiChatStatus(errorMessage(error, t("pi.requestFailed")));
    }
    return;
  }

  setPiChatBusy(true);
  piChatProgressFill.style.width = "12%";
  piChatProgressText.textContent = t("pi.processingShort");
  state.piChatController = new AbortController();

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
        history: state.piChatHistory.slice(0, -1),
        thread_id: state.activePiThreadId,
      }),
      signal: state.piChatController.signal,
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
          state.piChatHistory.push({ role: "assistant", content: assistantStreamText });
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
    state.piChatController = null;
    setPiChatBusy(false);
    savePiThreadsStore();
    refreshActivePiThreadMeta().catch(() => {});
  }
}

export async function sendPiChat(event) {
  event.preventDefault();
  const message = piChatInput.value.trim();
  await sendPiChatMessage(message);
}

export function stopPiChat() {
  if (state.piChatController) {
    state.piChatController.abort();
  }
}

export function clearPiChat() {
  if (state.piChatHistory.length && !window.confirm(t("pi.confirmClear"))) {
    return;
  }
  state.piChatHistory = [];
  const thread = getActivePiThread();
  if (thread) {
    thread.history = [];
    thread.title = defaultPiThreadTitle();
    thread.updatedAt = Date.now();
  }
  savePiThreadsStore();
  piChatMessagesEl.innerHTML = `<div class="pi-chat-empty">${t("pi.emptyHint")}</div>`;
  updatePiChatHistoryHint();
  updatePiAgentStatus();
}

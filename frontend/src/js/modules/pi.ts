import { t } from "../../i18n.js";
import * as dom from "../core/dom.js";
import { state } from "../core/state.js";
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
import { notifyError, notifyInfo } from "../core/toast.js";
import { showApiError, showApiSuccess } from "../core/api-feedback.js";
import { deps } from "../core/deps.js";
import { trackBackgroundJob, cancelBackgroundJob } from "../jobs/index.js";
import { scoreBadgeClass, formatSource } from "./leads.js";
import { switchSettingsCat } from "./settings.js";
import { resetProgressFill, setProgressFill } from "../core/progress.js";

const {
  piChatMessagesEl, piChatForm, piChatInput, piChatSendBtn, piChatStopBtn, piChatClearBtn,
  piChatHistoryHintEl, piChatContextMeterEl, piChatContextMeterFillEl, piChatContextMeterLabelEl,
  piChatBackgroundInput, piThreadListEl, piChatProgressEl, piChatProgressFill,
  piChatProgressText, piChatJumpBtn, piChatStatusLiveEl, leadQueryInput, minScoreInput, autoImportInput,
  piChatShellEl, piLlmSetupEl, piGotoLlmSettingsBtn, piInputHintEl,
  piMobileTabChatBtn, piMobileTabThreadsBtn,
} = dom;

const PI_EXAMPLE_PROMPTS = [
  { labelKey: "pi.exampleDiscover", messageKey: "pi.exampleDiscover" },
  { labelKey: "pi.exampleLookup", messageKey: "pi.exampleLookup" },
  { labelKey: "pi.examplePrefs", messageKey: "pi.examplePrefs" },
];

export function piSendModKey() {
  return /Mac|iPhone|iPad/i.test(navigator.platform || "") ? "⌘" : "Ctrl";
}

export function formatPiToolLabel(name) {
  const key = `pi.tool.${name}`;
  const label = t(key);
  return label !== key ? label : String(name || "tool").replace(/_/g, " ");
}

export function renderPiEmptyStateHtml() {
  if (!state.llmConfigured) {
    return `
      <div class="pi-chat-empty pi-chat-empty-state">
        <p class="pi-chat-empty-lead">${escapeHtml(t("pi.emptyHintAlt"))}</p>
      </div>`;
  }
  const chips = PI_EXAMPLE_PROMPTS.map(
    ({ labelKey, messageKey }) =>
      `<button type="button" class="pi-example-chip" data-pi-example="${escapeHtml(t(messageKey))}">${escapeHtml(t(labelKey))}</button>`,
  ).join("");
  return `
    <div class="pi-chat-empty pi-chat-empty-state">
      <p class="pi-chat-empty-lead">${escapeHtml(t("pi.emptyHint"))}</p>
      <div class="pi-example-prompts">
        <span class="pi-example-label">${escapeHtml(t("pi.exampleLabel"))}</span>
        <div class="pi-example-chips">${chips}</div>
      </div>
    </div>`;
}

export function mountPiEmptyState() {
  if (!piChatMessagesEl) return;
  piChatMessagesEl.innerHTML = renderPiEmptyStateHtml();
}

export function updatePiInputHint() {
  if (!piInputHintEl) return;
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    piInputHintEl.textContent = t("pi.offlineBanner");
    piInputHintEl.classList.add("pi-input-hint-offline");
    return;
  }
  piInputHintEl.classList.remove("pi-input-hint-offline");
  piInputHintEl.textContent = t("pi.inputHint", { mod: piSendModKey() });
}

export function setPiMobilePanel(panel) {
  if (!piChatShellEl) return;
  const threads = panel === "threads";
  piChatShellEl.classList.toggle("pi-mobile-panel-threads", threads);
  piChatShellEl.classList.toggle("pi-mobile-panel-chat", !threads);
  piMobileTabChatBtn?.classList.toggle("active", !threads);
  piMobileTabThreadsBtn?.classList.toggle("active", threads);
  piMobileTabChatBtn?.setAttribute("aria-selected", threads ? "false" : "true");
  piMobileTabThreadsBtn?.setAttribute("aria-selected", threads ? "true" : "false");
  if (!threads) {
    settlePiChatAtBottom();
  }
}

export function refreshPiToolLabelsInDom() {
  piChatMessagesEl?.querySelectorAll(".pi-chat-tool[data-tool-name]").forEach((el) => {
    const labelEl = el.querySelector(".pi-chat-tool-name");
    const name = el.dataset.toolName;
    if (labelEl && name) labelEl.textContent = formatPiToolLabel(name);
  });
}

export function refreshPiAgentChrome() {
  updatePiInputHint();
  piLlmSetupEl?.classList.toggle("hidden", state.llmConfigured);
  if (piChatMessagesEl && !state.piChatHistory.length && !piChatMessagesEl.querySelector(".pi-chat-bubble")) {
    mountPiEmptyState();
  }
  refreshPiToolLabelsInDom();
  updatePiAgentStatus();
}

export function initPiAgentUi() {
  updatePiInputHint();
  resizePiChatInput();
  piLlmSetupEl?.classList.toggle("hidden", state.llmConfigured);
  if (piChatMessagesEl && !piChatMessagesEl.children.length) {
    mountPiEmptyState();
  }
  piChatInput?.addEventListener("input", () => {
    resizePiChatInput();
    updatePiAgentStatus();
  });
  piGotoLlmSettingsBtn?.addEventListener("click", () => {
    deps.switchView?.("settings");
    switchSettingsCat("ai");
  });
  piMobileTabChatBtn?.addEventListener("click", () => setPiMobilePanel("chat"));
  piMobileTabThreadsBtn?.addEventListener("click", () => setPiMobilePanel("threads"));
  piChatMessagesEl?.addEventListener("click", (event) => {
    const chip = event.target.closest(".pi-example-chip");
    if (!chip || !piChatInput || state.piChatBusy || !state.llmConfigured) return;
    piChatInput.value = chip.dataset.piExample || chip.textContent || "";
    resizePiChatInput();
    updatePiAgentStatus();
    piChatInput.focus();
    setPiMobilePanel("chat");
  });
  piChatMessagesEl?.addEventListener("scroll", handlePiChatScroll, { passive: true });
  piChatJumpBtn?.addEventListener("click", jumpPiChatToLatest);
  window.addEventListener("online", updatePiInputHint);
  window.addEventListener("offline", updatePiInputHint);
}

export function handlePiChatInputKeydown(event) {
  if (event.key !== "Enter") return;
  if (!(event.metaKey || event.ctrlKey)) return;
  event.preventDefault();
  if (piChatSendBtn?.disabled) return;
  piChatForm?.requestSubmit();
}
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

export function historyPayloadForApi(history) {
  return normalizeHistoryItems(history).map((item) => {
    if (item.role === "user" || item.role === "assistant") {
      return { role: item.role, content: String(item.content || "") };
    }
    return {
      role: "tool",
      name: String(item.name || "tool"),
      summary: String(item.summary || ""),
    };
  });
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
      <button type="button" class="pi-thread-btn ${thread.id === state.activePiThreadId ? "active" : ""} ${state.piChatBusy && thread.id === state.activePiThreadId ? "running" : ""}" data-thread-id="${thread.id}">
        <span class="pi-thread-title">${escapeHtml(thread.title || defaultPiThreadTitle())}</span>
        <span class="pi-thread-meta">${state.piChatBusy && thread.id === state.activePiThreadId ? escapeHtml(t("pi.threadRunning")) : t("pi.threadMeta", { count })}</span>
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
    const thread = await api(`/api/pi/threads/${encodeURIComponent(state.activePiThreadId)}`, {
      redirectOn401: false,
    });
    const index = state.piThreads.findIndex((item) => item.id === state.activePiThreadId);
    if (index >= 0) {
      state.piThreads[index].has_context_summary = Boolean((thread.context_summary || "").trim());
    }
    applyPiContextStats(thread.context_stats);
  } catch {
    // ignore metadata refresh failures
  }
}

export async function fetchActivePiThreadHistory() {
  if (!state.activePiThreadId) return;
  try {
    const thread = await api(`/api/pi/threads/${encodeURIComponent(state.activePiThreadId)}`, {
      redirectOn401: false,
    });
    const mapped = mapServerPiThreadFull(thread);
    const index = state.piThreads.findIndex((item) => item.id === mapped.id);
    if (index >= 0) {
      state.piThreads[index] = { ...state.piThreads[index], ...mapped };
    }
    state.piChatHistory = mapped.history;
    applyPiContextStats(thread.context_stats);
  } catch {
    const active = getActivePiThread();
    state.piChatHistory = normalizeHistoryItems(active?.history);
    state.piContextStats = null;
    updatePiContextMeter();
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
    const data = await api("/api/pi/threads", { redirectOn401: false });
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

export function beginPiThread(title?: string) {
  if (state.piChatBusy) {
    notifyInfo(t("pi.busySwitch"));
    return null;
  }
  clearPiTurnError();
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

export function createPiThread(title?: string) {
  const thread = beginPiThread(title);
  if (thread) {
    savePiThreadsStore();
  }
  return thread;
}

export async function switchPiThread(threadId) {
  if (threadId === state.activePiThreadId) return;
  if (state.piChatBusy) {
    notifyInfo(t("pi.busySwitch"));
    return;
  }
  clearPiTurnError();
  syncActivePiThreadHistory();
  savePiThreadsStoreLocal();
  state.activePiThreadId = threadId;
  await fetchActivePiThreadHistory();
  restorePiChatUi();
  savePiThreadsStoreLocal();
  setPiMobilePanel("chat");
}

export async function deletePiThread(threadId) {
  if (state.piChatBusy) {
    notifyInfo(t("pi.busySwitch"));
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
  try {
    await loadPiChatFromServer(userId);
  } catch (error) {
    console.warn("Pi chat init failed:", error);
    try {
      loadPiThreadsFromStorage(userId);
      restorePiChatUi();
    } catch {
      // ignore secondary failures
    }
  }
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
    if (/^[[{]/.test(summary.trim()) && summary.length > 120) {
      showPiToolRawDetail(el, summary);
    } else {
      pre.classList.remove("hidden");
      pre.textContent = summary;
    }
  }
  applyPiDestructiveHint(el, name);
}

export function restorePiChatUi() {
  if (!piChatMessagesEl) return;
  piChatMessagesEl.innerHTML = "";
  if (!state.piChatHistory.length) {
    mountPiEmptyState();
    renderPiThreadList();
    applyPiContextStats(null);
    settlePiChatAtBottom();
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
  if (piLastError) renderPiChatError(piLastError.message, piLastError.retryText);
  settlePiChatAtBottom();
}

export function applyPiContextStats(stats) {
  state.piContextStats = stats && typeof stats === "object" ? stats : null;
  updatePiContextMeter();
  updatePiChatHistoryHint();
}

export function formatPiContextTokens(value) {
  const n = Math.max(0, Number(value) || 0);
  if (n >= 1_000_000) {
    const millions = n / 1_000_000;
    return Number.isInteger(millions) ? `${millions}M` : `${millions.toFixed(1)}M`;
  }
  if (n >= 1000) return `${Math.round(n / 1000)}k`;
  return String(n);
}

export function updatePiContextMeter() {
  if (!piChatContextMeterEl || !piChatContextMeterFillEl || !piChatContextMeterLabelEl) return;
  const stats = state.piContextStats;
  if (!stats || !state.piChatHistory.length) {
    piChatContextMeterEl.classList.add("hidden");
    return;
  }
  piChatContextMeterEl.classList.remove("hidden");
  piChatContextMeterEl.title = t("pi.contextTooltip");
  const pct = Math.max(0, Math.min(100, Number(stats.usage_percent) || 0));
  piChatContextMeterFillEl.style.transform = `scaleX(${pct / 100})`;
  piChatContextMeterFillEl.classList.toggle("warn", pct >= 75);
  piChatContextMeterFillEl.classList.toggle("danger", pct >= 90);
  const parts = [
    t("msg.piContextUsage", {
      pct,
      tokens: formatPiContextTokens(stats.token_estimate),
      limit: formatPiContextTokens(stats.context_limit),
    }),
  ];
  if (stats.compressed) parts.push(t("msg.piContextCompressed"));
  else if (stats.needs_compression) parts.push(t("msg.piContextNeedsCompress"));
  if (pct >= 75) parts.push(t("msg.piContextHigh"));
  piChatContextMeterLabelEl.textContent = parts.join(" · ");
}

export function updatePiChatHistoryHint() {
  if (!piChatHistoryHintEl) return;
  const count = state.piChatHistory.length;
  const threadCount = state.piThreads.length;
  if (!count) {
    piChatHistoryHintEl.textContent = t("msg.piHistoryLocal");
    piChatHistoryHintEl.classList.add("hidden");
    return;
  }
  piChatHistoryHintEl.classList.remove("hidden");
  piChatHistoryHintEl.textContent = t("msg.piHistorySavedThreads", { count, threads: threadCount });
  const stats = state.piContextStats;
  if (stats?.llm_message_count) {
    piChatHistoryHintEl.textContent += ` · LLM ${stats.llm_message_count} 条`;
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
    notifyInfo(t("msg.describeLeads"));
    return;
  }
  if (!state.llmConfigured) {
    notifyError(t("msg.piNotAvailable"));
    return;
  }
  deps.switchView("pi-agent");
  beginPiThread(summarizePiThreadTitle(message));
  await sendPiChatMessage(message);
}

export async function openPiEnrichContact(contact) {
  if (!contact?.id) return;
  if (!state.llmConfigured) {
    notifyError(t("msg.piNotAvailable"));
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
    notifyError(t("msg.piNotAvailable"));
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
    showApiError(error, t("msg.enrichFailed"));
  }
}

function countImportFilterPatterns(patterns, text) {
  if (Array.isArray(patterns)) return patterns.length;
  let count = 0;
  for (const line of String(text || "").split("\n")) {
    const trimmed = line.trim().toLowerCase();
    if (trimmed && !trimmed.startsWith("#")) count++;
  }
  return count;
}

function formatImportFiltersSummary(result) {
  const blockCount = countImportFilterPatterns(result.blocklist_patterns, result.blocklist);
  const allowCount = countImportFilterPatterns(result.allowlist_patterns, result.allowlist);
  const parts = [`黑名单 ${blockCount} 条`, `白名单 ${allowCount} 条`];
  if (result.message) parts.push(result.message);
  return parts.join(" · ");
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
  if (name === "list_contact_notes") {
    return `联系人 #${result.contact_id ?? ""} · ${result.count ?? result.notes?.length ?? 0} 条备注`;
  }
  if (name === "get_lead_preferences") {
    const summary = result.summary || "";
    if (summary) return summary.split("\n")[0];
    const stats = result.preferences?.stats || {};
    return `偏好 · 导入 ${stats.imports ?? 0} · 无效 ${stats.invalid ?? 0}`;
  }
  if (name === "reset_lead_preferences") {
    return result.ok ? "已重置线索偏好" : "";
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
  if (name === "fetch_web_pages") {
    return `Web Unlocker · ${result.page_count ?? 0} 页 · 邮箱 ${result.emails_found?.length ?? 0}`;
  }
  if (name === "search_hosting_forums") {
    return `论坛 · ${(result.forums_searched || []).join("+") || "—"} · ${result.result_count ?? 0} 条`;
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
  if (name === "get_import_filters" || name === "update_import_filters") {
    return formatImportFiltersSummary(result);
  }
  if (name === "list_schedules") {
    const schedules = result.schedules || [];
    const count = result.count ?? schedules.length;
    const names = schedules
      .slice(0, 3)
      .map((s) => s?.name || (s?.id != null ? `#${s.id}` : ""))
      .filter(Boolean);
    const parts = [`${count} 个定时任务`];
    if (names.length) parts.push(names.join("、"));
    return parts.join(" · ");
  }
  if (name === "create_schedule" || name === "update_schedule") {
    const schedule = result.schedule || {};
    const label = [schedule.name, schedule.id != null ? `#${schedule.id}` : ""].filter(Boolean).join(" ");
    const action = name === "create_schedule" ? "已创建" : "已更新";
    return label ? `${action} ${label}` : result.ok ? action : "";
  }
  return "";
}

export function piSelectableRows(toolEl): HTMLElement[] {
  return Array.from(toolEl?.querySelectorAll(".pi-chat-leads-body tr, .pi-chat-lookup-body tr") || []) as HTMLElement[];
}

export function piRowCheckbox(tr) {
  return tr?.querySelector?.(".pi-row-check") || null;
}

export function updatePiSelectionUi(toolEl) {
  if (!toolEl) return;
  const rows = piSelectableRows(toolEl);
  const total = rows.length;
  const selected = rows.filter((tr) => piRowCheckbox(tr)?.checked).length;
  const countEl = toolEl.querySelector(".pi-sel-count");
  if (countEl) countEl.textContent = total ? t("pi.selectedCount", { n: selected, total }) : "";
  const all = toolEl.querySelector(".pi-sel-all");
  if (all) {
    all.checked = total > 0 && selected === total;
    all.indeterminate = selected > 0 && selected < total;
  }
  const importBtn = toolEl.querySelector(".pi-chat-import-leads, .pi-chat-import-lookup");
  if (importBtn) importBtn.disabled = selected === 0;
}

// Real checkboxes (keyboard-reachable, aria-labelled) drive selection, with a
// header select-all. Row clicks toggle the row's checkbox for mouse convenience.
export function wirePiSelection(toolEl) {
  const body = toolEl?.querySelector(".pi-chat-leads-body, .pi-chat-lookup-body");
  if (body && !body.dataset.selBound) {
    body.dataset.selBound = "1";
    body.addEventListener("change", (event) => {
      const cb = (event.target as HTMLElement | null)?.closest(".pi-row-check") as HTMLInputElement | null;
      if (!cb) return;
      cb.closest("tr")?.classList.toggle("selected", cb.checked);
      updatePiSelectionUi(toolEl);
    });
    body.addEventListener("click", (event) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("a, input, label, button")) return;
      const cb = piRowCheckbox(target?.closest("tr"));
      if (!cb) return;
      cb.checked = !cb.checked;
      cb.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }
  const all = toolEl?.querySelector(".pi-sel-all");
  if (all && !all.dataset.selBound) {
    all.dataset.selBound = "1";
    all.addEventListener("change", () => {
      for (const tr of piSelectableRows(toolEl)) {
        const cb = piRowCheckbox(tr);
        if (cb) {
          cb.checked = all.checked;
          tr.classList.toggle("selected", all.checked);
        }
      }
      updatePiSelectionUi(toolEl);
    });
  }
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
          <th class="pi-sel-th"><input type="checkbox" class="pi-sel-all" aria-label="${escapeHtml(t("pi.selectAll"))}" checked></th>
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
  actionsEl.innerHTML = `
    <span class="pi-sel-count" aria-live="polite"></span>
    <button type="button" class="success-btn pi-chat-import-lookup">${t("pi.importSelectedEmails")}</button>
  `;
  el.appendChild(lookupWrap);
  el.appendChild(actionsEl);
  el._piLookupRows = [];
  wirePiSelection(el);
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
    <td class="pi-sel-cell"><input type="checkbox" class="pi-row-check" checked aria-label="${escapeHtml(t("pi.selectRowAria"))}"></td>
    <td>${escapeHtml(row.rir || "—")}</td>
    <td class="mono">AS${row.asn}</td>
    <td>${escapeHtml(row.org || "—")}</td>
    <td>${escapeHtml(roles || "—")}</td>
    <td><a class="email-link" href="mailto:${row.email}">${escapeHtml(row.email)}</a></td>
  `;
  tr.dataset.index = String(index);
  tr.classList.add("selected");
  body.appendChild(tr);
  toolEl.querySelector(".pi-chat-leads-actions")?.classList.remove("hidden");
  updatePiSelectionUi(toolEl);
}

export async function importPiChatLookup(toolEl) {
  const allRows = toolEl?._piLookupRows || [];
  const rows = piSelectableRows(toolEl)
    .filter((tr) => piRowCheckbox(tr)?.checked)
    .map((tr) => allRows[Number((tr as HTMLElement).dataset.index)]);
  const payload = normalizeImportRows(
    rows.filter((row) => row?.email).map((row) => ({
      ...row,
      source: row.source || "rdap",
    })),
  );
  if (!payload.length) {
    notifyInfo(t("msg.noEmailsToImport"));
    return;
  }
  try {
    const result = await api("/api/contacts/import", {
      method: "POST",
      body: JSON.stringify({ rows: payload }),
    });
    showApiSuccess(formatImportResult(result));
    await deps.loadContacts();
  } catch (error) {
    showApiError(error, t("msg.importFailed"));
  }
}

const PI_SCROLL_STICK_THRESHOLD = 96;
let piFollowBottom = true;

export function isPiChatNearBottom() {
  if (!piChatMessagesEl) return true;
  const gap = piChatMessagesEl.scrollHeight - piChatMessagesEl.scrollTop - piChatMessagesEl.clientHeight;
  return gap <= PI_SCROLL_STICK_THRESHOLD;
}

export function setPiChatJumpVisible(visible) {
  piChatJumpBtn?.classList.toggle("hidden", !visible);
}

export function resumePiChatFollow() {
  piFollowBottom = true;
  setPiChatJumpVisible(false);
}

export function handlePiChatScroll() {
  piFollowBottom = isPiChatNearBottom();
  if (piFollowBottom) setPiChatJumpVisible(false);
}

// Follow the conversation bottom only while the user is already near it. If they
// have scrolled up to read, leave their position alone and surface a
// jump-to-latest button instead of yanking them down on every stream delta.
export function scrollPiChatToBottom() {
  if (!piChatMessagesEl) return;
  if (piFollowBottom) {
    piChatMessagesEl.scrollTop = piChatMessagesEl.scrollHeight;
    setPiChatJumpVisible(false);
  } else {
    setPiChatJumpVisible(true);
  }
}

export function jumpPiChatToLatest() {
  if (!piChatMessagesEl) return;
  piFollowBottom = true;
  setPiChatJumpVisible(false);
  piChatMessagesEl.scrollTo({ top: piChatMessagesEl.scrollHeight, behavior: "smooth" });
}

export function settlePiChatAtBottom() {
  if (!piChatMessagesEl) return;
  piFollowBottom = true;
  setPiChatJumpVisible(false);
  const scroll = () => {
    piChatMessagesEl.scrollTo({ top: piChatMessagesEl.scrollHeight, behavior: "auto" });
  };
  scroll();
  requestAnimationFrame(() => {
    scroll();
    requestAnimationFrame(scroll);
  });
  setTimeout(scroll, 120);
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
  setProgressFill(fill, pct);
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
    setProgressFill(piChatProgressFill, Math.max(35, Math.min(92, 35 + pct * 0.55)));
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
    for (const key of ["peeringdb", "web_search", "web_unlocker", "lowendtalk", "webhostingtalk", "shodan"]) {
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
  markPiChatToolDone(toolEl);
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
  if (!toolEl._piLeads?.length && !toolEl.querySelector(".pi-chat-empty-leads")) {
    const note = document.createElement("p");
    note.className = "pi-chat-empty-leads";
    note.textContent = t("pi.emptyLeadsRelax");
    toolEl.appendChild(note);
  }
}

export function handlePiDiscoverToolEvent(toolEl, event) {
  if (!toolEl || !event) return;
  switch (event.kind) {
    case "plan":
      renderPiChatPlan(toolEl, event.plan);
      pushPiDiscoverTicker(toolEl, event.plan?.summary || t("pi.planReady"));
      for (const key of ["peeringdb", "web_search", "web_unlocker", "lowendtalk", "webhostingtalk", "shodan"]) {
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
          <th class="pi-sel-th"><input type="checkbox" class="pi-sel-all" aria-label="${escapeHtml(t("pi.selectAll"))}" checked></th>
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
  actionsEl.innerHTML = `
    <span class="pi-sel-count" aria-live="polite"></span>
    <button type="button" class="success-btn pi-chat-import-leads">${t("pi.importSelectedLeads")}</button>
  `;
  el.appendChild(livePanel);
  el.appendChild(planEl);
  el.appendChild(leadsWrap);
  el.appendChild(actionsEl);
  el._piLeads = [];
  wirePiSelection(el);
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
    <td class="pi-sel-cell"><input type="checkbox" class="pi-row-check" checked aria-label="${escapeHtml(t("pi.selectRowAria"))}"></td>
    <td><span class="${scoreBadgeClass(lead.lead_score)}">${lead.lead_score || 0}</span></td>
    <td>${escapeHtml(lead.org || lead.network_name || "—")}</td>
    <td><a class="email-link" href="mailto:${lead.email}">${escapeHtml(lead.email || "—")}</a></td>
    <td>${escapeHtml(formatSource(lead))}</td>
  `;
  tr.dataset.index = String(index);
  tr.classList.add("selected");
  body.appendChild(tr);
  tr.classList.add("pi-lead-row-in");
  toolEl.querySelector(".pi-chat-leads-actions")?.classList.remove("hidden");
  updatePiSelectionUi(toolEl);
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
  const allLeads = toolEl?._piLeads || [];
  const rows = piSelectableRows(toolEl)
    .filter((tr) => piRowCheckbox(tr)?.checked)
    .map((tr) => allLeads[Number((tr as HTMLElement).dataset.index)]);
  const payload = normalizeImportRows(
    rows
      .filter((lead) => lead?.email)
      .map((lead) => ({
        ...lead,
        source: "ai-lead",
        notes: [`AI评分 ${lead.lead_score || 0}`, lead.lead_reason || ""].filter(Boolean).join(" · "),
      })),
  );
  if (!payload.length) {
    notifyInfo(t("msg.noLeadsToImport"));
    return;
  }
  try {
    const result = await api("/api/contacts/import", {
      method: "POST",
      body: JSON.stringify({ rows: payload }),
    });
    showApiSuccess(formatImportResult(result));
    await deps.loadContacts();
  } catch (error) {
    showApiError(error, t("msg.importFailed"));
  }
}

export function piChatInputText() {
  return String(piChatInput?.value || "").trim();
}

export function resizePiChatInput() {
  if (!piChatInput) return;
  piChatInput.style.height = "auto";
  const minHeight = 72;
  const maxHeight = 192;
  const nextHeight = Math.min(maxHeight, Math.max(minHeight, piChatInput.scrollHeight || minHeight));
  piChatInput.style.height = `${nextHeight}px`;
  piChatInput.style.overflowY = nextHeight >= maxHeight ? "auto" : "hidden";
}

export function updatePiAgentStatus() {
  const enabled = state.llmConfigured;
  const canType = enabled && !state.piChatBusy;
  const canSend = canType && Boolean(piChatInputText());
  piChatInput.disabled = !canType;
  piChatSendBtn.disabled = !canSend;
  if (piChatBackgroundInput) {
    piChatBackgroundInput.disabled = !enabled || state.piChatBusy;
  }
  resizePiChatInput();
  piLlmSetupEl?.classList.toggle("hidden", enabled);
  if (
    enabled &&
    piChatMessagesEl &&
    !state.piChatHistory.length &&
    !piChatMessagesEl.querySelector(".pi-chat-bubble") &&
    !piChatMessagesEl.querySelector(".pi-chat-tool")
  ) {
    mountPiEmptyState();
  }
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
  // Narrow markers that begin a leaked machine tool-call payload. Bare keys
  // ('"name":' etc.) and the old "\n[" / startsWith("[") rules were removed:
  // they truncated ordinary prose (markdown links, "[1]" lists, bracketed
  // labels), which made replies appear cut off mid-stream.
  const markers = [
    "[{",
    "[工具",
    "[tool",
    "tool_calls",
    "tool_call",
    "dsml",
    "<|",
    "<｜",
    "```json",
    '{"query',
    '{"queries',
    '{"name"',
    '{"function"',
  ];
  let cutAt = raw.length;
  for (const marker of markers) {
    const idx = lower.indexOf(marker.toLowerCase());
    if (idx >= 0) cutAt = Math.min(cutAt, idx);
  }
  let trimmed = raw.slice(0, cutAt).trim();
  if (trimmed.endsWith("[")) trimmed = trimmed.slice(0, -1).trim();
  if (!trimmed || /^[\[{(,]+$/.test(trimmed)) return "";
  if (/^[\[{]\s*["[{]/.test(trimmed) && trimmed.length < 24) return "";
  return trimmed;
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
  scrollPiChatToBottom();
  return el;
}

export let piChatStreamRaf = null;

export function updatePiChatAssistantBubble(el, text, streaming = false) {
  if (!el) return;
  el.classList.toggle("streaming", streaming);
  if (piChatStreamRaf) cancelAnimationFrame(piChatStreamRaf);
  piChatStreamRaf = requestAnimationFrame(() => {
    el.innerHTML = renderMarkdown(sanitizePiAssistantDisplay(text || ""));
    scrollPiChatToBottom();
    piChatStreamRaf = null;
  });
}

// Announce only meaningful state to screen readers via one polite region,
// instead of leaving the whole transcript live (which reads every stream delta).
export function announcePi(message) {
  if (!piChatStatusLiveEl) return;
  const text = String(message || "").trim();
  if (!text) return;
  piChatStatusLiveEl.textContent = "";
  requestAnimationFrame(() => {
    if (piChatStatusLiveEl) piChatStatusLiveEl.textContent = text;
  });
}

export function appendPiChatStatus(text) {
  clearPiChatEmpty();
  const el = document.createElement("div");
  el.className = "pi-chat-status";
  el.textContent = text;
  piChatMessagesEl.appendChild(el);
  scrollPiChatToBottom();
  return el;
}

const PI_DESTRUCTIVE_TOOLS = new Set([
  "delete_contacts",
  "dedupe_contacts",
  "reset_lead_preferences",
]);

// Destructive tool results carry a clear, non-color-only danger marker so the
// operator can never miss that Pi just deleted/reset data on their behalf.
export function applyPiDestructiveHint(toolEl, name) {
  if (!toolEl || !PI_DESTRUCTIVE_TOOLS.has(name)) return;
  toolEl.classList.add("pi-chat-tool-destructive");
  if (toolEl.querySelector(".pi-chat-destructive-note")) return;
  const note = document.createElement("p");
  note.className = "pi-chat-destructive-note";
  note.innerHTML = `<span class="pi-destructive-badge">${escapeHtml(t("pi.destructiveLabel"))}</span><span>${escapeHtml(t("pi.irreversible"))}</span>`;
  const head = toolEl.querySelector(".pi-chat-tool-head");
  if (head?.nextSibling) {
    toolEl.insertBefore(note, head.nextSibling);
  } else {
    toolEl.appendChild(note);
  }
}

// Collapse raw JSON tool dumps behind a "show details" disclosure instead of a
// wall of machine output.
export function showPiToolRawDetail(toolEl, text) {
  if (!toolEl || !text) return;
  let details = toolEl.querySelector(".pi-chat-tool-raw") as HTMLDetailsElement | null;
  if (!details) {
    details = document.createElement("details");
    details.className = "pi-chat-tool-raw";
    const summary = document.createElement("summary");
    summary.textContent = t("pi.expandDetail");
    const pre = document.createElement("pre");
    pre.className = "pi-chat-tool-result-raw";
    details.appendChild(summary);
    details.appendChild(pre);
    toolEl.appendChild(details);
  }
  const preEl = details.querySelector("pre");
  if (preEl) preEl.textContent = text;
}

// Undo a destructive op live in-session: re-import captured contacts, or write
// the captured lead-preferences blob back. (Undo is best-effort, current session.)
export function addPiUndoButton(toolEl, result) {
  if (!toolEl || !result?.undo_payload || toolEl.querySelector(".pi-undo-btn")) return;
  const host = toolEl.querySelector(".pi-chat-destructive-note") || toolEl;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "secondary-btn pi-undo-btn";
  btn.textContent = t("pi.undo");
  btn.addEventListener("click", () => {
    undoPiDestructive(result, btn).catch(() => {});
  });
  host.appendChild(btn);
}

export async function undoPiDestructive(result, btn) {
  if (!result?.undo_payload) return;
  btn.disabled = true;
  try {
    if (result.undo_kind === "prefs") {
      await api("/api/pi/restore-prefs", {
        method: "POST",
        body: JSON.stringify({ preferences: result.undo_payload }),
      });
      showApiSuccess(t("pi.undonePrefs"));
    } else {
      const rows = normalizeImportRows(result.undo_payload || []);
      const res = await api("/api/contacts/import", {
        method: "POST",
        body: JSON.stringify({ rows }),
      });
      showApiSuccess(t("pi.undone", { n: res?.imported ?? rows.length }));
      await deps.loadContacts?.();
    }
    btn.textContent = t("pi.undoneState");
    btn.classList.add("pi-undo-done");
  } catch (error) {
    btn.disabled = false;
    showApiError(error, t("pi.undoFailed"));
  }
}

// Execute-before-confirm: when a destructive tool returns confirm_required, turn
// its card into a confirm/cancel prompt. Confirming hits a dedicated endpoint
// (the only path that may execute it); the model can never self-confirm.
export function renderPiConfirmCard(toolEl, name, summary, pendingArgs) {
  if (!toolEl) return;
  stopPiDiscoverTimer(toolEl);
  toolEl.classList.remove("pi-chat-tool-running");
  toolEl.classList.add("pi-chat-tool-confirm");
  toolEl.querySelector(".pi-chat-tool-head")?.classList.add("confirm");
  toolEl.querySelector(".pi-chat-live-panel")?.classList.add("hidden");
  const progress = toolEl.querySelector(".pi-chat-tool-progress") as HTMLElement | null;
  if (progress) {
    progress.style.display = "";
    progress.textContent = summary || t("pi.confirmPrompt");
  }
  const actions = document.createElement("div");
  actions.className = "pi-chat-confirm-actions";
  const yes = document.createElement("button");
  yes.type = "button";
  yes.className = "danger-btn pi-confirm-yes";
  yes.textContent = t("pi.confirmYes");
  const no = document.createElement("button");
  no.type = "button";
  no.className = "secondary-btn pi-confirm-no";
  no.textContent = t("pi.confirmNo");
  yes.addEventListener("click", () => {
    confirmPiTool(toolEl, name, pendingArgs || {}).catch(() => {});
  });
  no.addEventListener("click", () => cancelPiConfirm(toolEl));
  actions.appendChild(yes);
  actions.appendChild(no);
  toolEl.appendChild(actions);
  announcePi(summary || t("pi.confirmPrompt"));
  scrollPiChatToBottom();
}

export async function confirmPiTool(toolEl, name, args) {
  const actions = toolEl.querySelector(".pi-chat-confirm-actions");
  actions?.querySelectorAll("button").forEach((b) => {
    (b as HTMLButtonElement).disabled = true;
  });
  try {
    const data = await api("/api/pi/confirm-tool", {
      method: "POST",
      body: JSON.stringify({ thread_id: state.activePiThreadId, name, args }),
    });
    const result = data?.result || {};
    actions?.remove();
    toolEl.classList.remove("pi-chat-tool-confirm");
    toolEl.querySelector(".pi-chat-tool-head")?.classList.remove("confirm");
    if (result.error) {
      markPiChatToolFailed(toolEl, String(result.error));
      announcePi(String(result.error));
      return;
    }
    markPiChatToolDone(toolEl);
    const sum = formatPiToolSummary(name, result);
    const progress = toolEl.querySelector(".pi-chat-tool-progress");
    if (progress && sum) progress.textContent = sum;
    applyPiDestructiveHint(toolEl, name);
    if (result.undo_payload) addPiUndoButton(toolEl, result);
    appendPiHistoryEntry({ role: "tool", name, summary: sum || "" });
    announcePi(sum || t("pi.done"));
    if (name === "delete_contacts" || name === "dedupe_contacts") deps.loadContacts?.();
  } catch (error) {
    actions?.querySelectorAll("button").forEach((b) => {
      (b as HTMLButtonElement).disabled = false;
    });
    showApiError(error, t("pi.requestFailed"));
  }
}

export function cancelPiConfirm(toolEl) {
  const actions = toolEl.querySelector(".pi-chat-confirm-actions");
  if (actions) {
    actions.innerHTML = `<span class="pi-confirm-cancelled">${escapeHtml(t("pi.confirmCancelled"))}</span>`;
  }
  toolEl.classList.remove("pi-chat-tool-confirm");
  toolEl.querySelector(".pi-chat-tool-head")?.classList.remove("confirm");
  announcePi(t("pi.confirmCancelled"));
}

export function appendPiChatTool(name) {
  clearPiChatEmpty();
  const el = document.createElement("div");
  el.className = "pi-chat-tool";
  el.dataset.toolName = name;
  const label = formatPiToolLabel(name);
  el.innerHTML = `
    <div class="pi-chat-tool-head"><span class="dot" aria-hidden="true"></span><span class="pi-chat-tool-name">${escapeHtml(label)}</span></div>
    <p class="pi-chat-tool-progress" aria-live="polite" aria-atomic="true"></p>
    <pre class="pi-chat-tool-result hidden"></pre>
  `;
  piChatMessagesEl.appendChild(el);
  scrollPiChatToBottom();
  return el;
}

export function markPiChatToolDone(toolEl) {
  if (!toolEl) return;
  stopPiDiscoverTimer(toolEl);
  toolEl.classList.remove("pi-chat-tool-running", "pi-chat-tool-failed");
  toolEl.querySelector(".pi-chat-tool-head")?.classList.remove("failed");
  toolEl.querySelector(".pi-chat-tool-head")?.classList.add("done");
}

export function markPiChatToolFailed(toolEl, message) {
  if (!toolEl) return;
  stopPiDiscoverTimer(toolEl);
  toolEl.classList.remove("pi-chat-tool-running");
  toolEl.classList.add("pi-chat-tool-failed");
  const head = toolEl.querySelector(".pi-chat-tool-head");
  head?.classList.add("done", "failed");
  const progressEl = toolEl.querySelector(".pi-chat-tool-progress");
  if (progressEl && message) {
    progressEl.textContent = message;
  }
  if (toolEl._piChannelState) {
    for (const def of CHANNEL_DEFS) {
      const state = toolEl._piChannelState[def.key];
      if (state?.state === "active") {
        setPiDiscoverChannel(toolEl, def.key, { state: "failed" });
      }
    }
  }
  if (message) {
    pushPiDiscoverTicker(toolEl, message);
  }
}

export function setPiChatBusy(busy) {
  state.piChatBusy = busy;
  const showStop = busy || Boolean(state.piBackgroundJobId);
  piChatStopBtn.classList.toggle("hidden", !showStop);
  updatePiAgentStatus();
  piChatProgressEl.classList.toggle("hidden", !busy);
  if (!busy) {
    resetProgressFill(piChatProgressFill);
    piChatProgressText.textContent = "";
  }
}

let piBackgroundActiveToolEl = null;

export function startPiBackgroundWatch(job) {
  if (!job?.id) return;
  state.piBackgroundJobId = job.id;
  state.piBackgroundRenderedEvents = 0;
  piBackgroundActiveToolEl = null;
  setPiChatBusy(true);
  piChatProgressText.textContent = job.message || t("jobs.piStarting");
  setProgressFill(piChatProgressFill, 12);
  renderPiThreadList();
}

export function stopPiBackgroundWatch() {
  state.piBackgroundJobId = null;
  state.piBackgroundRenderedEvents = 0;
  piBackgroundActiveToolEl = null;
  setPiChatBusy(false);
}

function piBackgroundThreadMatches(job) {
  const threadId = job.params?.thread_id || job.result?.thread_id;
  if (!threadId) return true;
  return state.activePiThreadId === threadId;
}

function applyPiBackgroundEvent(event) {
  const type = event.type || "status";
  const message = event.message || "";
  if (type === "tool_start") {
    const name = event.name || "tool";
    if (PI_LEAD_STREAM_TOOLS.has(name)) {
      piBackgroundActiveToolEl = appendPiChatDiscoverTool(name);
    } else if (name === "lookup_asns") {
      piBackgroundActiveToolEl = appendPiChatLookupTool(name);
    } else {
      piBackgroundActiveToolEl = appendPiChatTool(name);
    }
    if (message) piChatProgressText.textContent = message;
    setProgressFill(piChatProgressFill, 40);
    scrollPiChatToBottom();
    return;
  }
  if (type === "tool_progress") {
    if (piBackgroundActiveToolEl) {
      const progressEl = piBackgroundActiveToolEl.querySelector(".pi-chat-tool-progress");
      if (progressEl) progressEl.textContent = message;
    }
    if (message) piChatProgressText.textContent = message;
    setProgressFill(piChatProgressFill, 65);
    return;
  }
  if (type === "tool_result") {
    if (!piBackgroundActiveToolEl && event.name) {
      piBackgroundActiveToolEl = appendPiChatTool(event.name);
    }
    if (piBackgroundActiveToolEl) {
      markPiChatToolDone(piBackgroundActiveToolEl);
      const progressEl = piBackgroundActiveToolEl.querySelector(".pi-chat-tool-progress");
      if (progressEl && message) progressEl.textContent = message;
      piBackgroundActiveToolEl = null;
    }
    setProgressFill(piChatProgressFill, 85);
    return;
  }
  if (type === "assistant_done") {
    piBackgroundActiveToolEl = null;
    if (message) {
      appendPiChatBubble("assistant", message);
      appendPiHistoryEntry({ role: "assistant", content: message });
      announcePi(message);
    }
    setProgressFill(piChatProgressFill, 100);
    return;
  }
  if (message) {
    piChatProgressText.textContent = message;
  }
}

async function finalizePiBackgroundJob(job) {
  if (state.piBackgroundJobId !== job.id) return;
  piBackgroundActiveToolEl = null;
  stopPiBackgroundWatch();
  if (!piBackgroundThreadMatches(job)) return;
  if (job.status === "cancelled") {
    appendPiChatStatus(t("jobs.cancelledInline"));
  }
  try {
    await fetchActivePiThreadHistory();
    restorePiChatUi();
  } catch {
    // keep partial UI if refresh fails
  }
  savePiThreadsStore();
  refreshActivePiThreadMeta().catch(() => {});
}

export async function syncPiBackgroundJob(job) {
  if (!job || job.job_type !== "pi_agent") return;
  if (!piBackgroundThreadMatches(job)) return;

  if (state.piBackgroundJobId !== job.id) {
    if (isPiBackgroundActive(job)) {
      startPiBackgroundWatch(job);
    } else if (job.status === "cancelled" || job.status === "done" || job.status === "error") {
      return;
    }
  }

  const events = job.progress?.events || [];
  const from = state.piBackgroundRenderedEvents || 0;
  for (let i = from; i < events.length; i += 1) {
    applyPiBackgroundEvent(events[i]);
  }
  state.piBackgroundRenderedEvents = events.length;

  if (job.message && (job.status === "pending" || job.status === "running")) {
    piChatProgressText.textContent = job.message;
  }

  if (job.status === "cancelled" || job.status === "done" || job.status === "error") {
    await finalizePiBackgroundJob(job);
    if (job.status === "error" && job.message) {
      appendPiChatStatus(job.message);
    }
  }
}

function isPiBackgroundActive(job) {
  return job.status === "pending" || job.status === "running";
}

let piLastError: { message: string; retryText: string } | null = null;

export function renderPiChatError(message, retryText) {
  if (!piChatMessagesEl) return null;
  clearPiChatEmpty();
  const el = document.createElement("div");
  el.className = "pi-chat-status pi-chat-error";
  el.setAttribute("role", "alert");
  const msg = document.createElement("span");
  msg.className = "pi-chat-error-msg";
  msg.textContent = message;
  el.appendChild(msg);
  if (retryText) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "secondary-btn pi-chat-retry-btn";
    btn.textContent = t("pi.retry");
    btn.addEventListener("click", () => {
      retryLastPiTurn().catch(() => {});
    });
    el.appendChild(btn);
  }
  piChatMessagesEl.appendChild(el);
  scrollPiChatToBottom();
  return el;
}

export function showPiTurnError(message, retryText?) {
  piLastError = { message: String(message || t("msg.errorGeneric")), retryText: retryText || "" };
  renderPiChatError(piLastError.message, piLastError.retryText);
}

export function clearPiTurnError() {
  piLastError = null;
  piChatMessagesEl?.querySelectorAll(".pi-chat-error").forEach((el) => el.remove());
}

// Re-run the last user turn after a network/stream failure: drop the failed
// partial tail, then re-stream without appending a duplicate user message.
export async function retryLastPiTurn() {
  if (state.piChatBusy || !state.llmConfigured) return;
  let idx = -1;
  for (let i = state.piChatHistory.length - 1; i >= 0; i -= 1) {
    if (state.piChatHistory[i]?.role === "user") {
      idx = i;
      break;
    }
  }
  if (idx < 0) return;
  const text = String(state.piChatHistory[idx].content || "").trim();
  if (!text) return;
  state.piChatHistory = state.piChatHistory.slice(0, idx + 1);
  clearPiTurnError();
  restorePiChatUi();
  resumePiChatFollow();
  await streamPiTurn(text);
}

export async function sendPiChatMessage(message) {
  const text = String(message || "").trim();
  if (!text) return;
  if (state.piChatBusy) {
    appendPiChatStatus(t("pi.threadBusy"));
    return;
  }
  if (!state.llmConfigured) {
    appendPiChatStatus(t("pi.llmSetupHint"));
    return;
  }

  piChatInput.value = "";
  resizePiChatInput();
  updatePiAgentStatus();
  resumePiChatFollow();
  clearPiTurnError();
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
      startPiBackgroundWatch(data.job);
      notifyInfo(t("msg.jobStartedBackground"));
      savePiThreadsStore();
      refreshActivePiThreadMeta().catch(() => {});
    } catch (error) {
      appendPiChatStatus(errorMessage(error, t("pi.requestFailed")));
    }
    return;
  }

  await streamPiTurn(text);
}

export async function streamPiTurn(text) {
  clearPiTurnError();
  setPiChatBusy(true);
  setProgressFill(piChatProgressFill, 12);
  piChatProgressText.textContent = t("pi.processingShort");
  renderPiThreadList();
  state.piChatController = new AbortController();

  let activeToolEl = null;
  let activeAssistantEl = null;
  let assistantStreamText = "";
  let streamEnded = false;

  const settlePendingAssistantBubble = () => {
    const visibleText = sanitizePiAssistantDisplay(assistantStreamText);
    if (activeAssistantEl) {
      if (visibleText) {
        updatePiChatAssistantBubble(activeAssistantEl, visibleText, false);
        const last = state.piChatHistory[state.piChatHistory.length - 1];
        if (!(last?.role === "assistant" && last.content === visibleText)) {
          appendPiHistoryEntry({ role: "assistant", content: visibleText });
        }
      } else {
        activeAssistantEl.remove();
      }
    }
    activeAssistantEl = null;
    assistantStreamText = "";
  };

  const failActiveTool = (message) => {
    if (!activeToolEl) return;
    markPiChatToolFailed(activeToolEl, message);
    activeToolEl = null;
  };

  try {
    await persistActivePiThread();
    const response = await fetch("/api/agent/chat/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        history: historyPayloadForApi(state.piChatHistory.slice(0, -1)),
        thread_id: state.activePiThreadId || null,
      }),
      signal: state.piChatController.signal,
    });

    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (response.status === 409) {
      const error = await response.json().catch(() => ({}));
      throw new Error(formatApiDetail(error.detail) || t("pi.threadBusy"));
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

        if (payload.type === "context") {
          applyPiContextStats(payload.stats);
        } else if (payload.type === "status") {
          piChatProgressText.textContent = payload.message || t("msg.piProcessingShort");
          if (payload.message?.includes("正在重试")) {
            if (activeAssistantEl) {
              activeAssistantEl.remove();
              activeAssistantEl = null;
              assistantStreamText = "";
            }
          }
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
          setProgressFill(piChatProgressFill, 12);
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
            setProgressFill(piChatProgressFill, 65);
          }
        } else if (payload.type === "tool_event") {
          const event = payload.event || {};
          if (PI_LEAD_STREAM_TOOLS.has(payload.name) && activeToolEl) {
            handlePiDiscoverToolEvent(activeToolEl, event);
          }
        } else if (payload.type === "tool_result") {
          if (payload.result?.confirm_required) {
            if (activeToolEl) {
              renderPiConfirmCard(
                activeToolEl,
                payload.name,
                payload.result.summary,
                payload.result.pending_args || {},
              );
              activeToolEl = null;
            }
            setProgressFill(piChatProgressFill, 85);
            continue;
          }
          const summary = formatPiToolSummary(payload.name, payload.result);
          const toolEntry: AnyRecord = {
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
            const toolEl = activeToolEl;
            const toolFailed = Boolean(payload.result?.error);
            if (toolFailed) {
              markPiChatToolFailed(toolEl, summary || String(payload.result?.error || t("msg.errorGeneric")));
            } else if (PI_LEAD_STREAM_TOOLS.has(payload.name)) {
              finalizePiDiscoverTool(toolEl, {
                message: summary || payload.result?.message,
              });
            } else {
              markPiChatToolDone(toolEl);
            }
            const pre = toolEl.querySelector(".pi-chat-tool-result");
            if (PI_LEAD_STREAM_TOOLS.has(payload.name)) {
              pre.classList.add("hidden");
              if (summary) {
                toolEl.querySelector(".pi-chat-tool-progress").textContent = summary;
              }
              const importBtn = toolEl.querySelector(".pi-chat-import-leads");
              if (importBtn && !importBtn.dataset.bound) {
                importBtn.dataset.bound = "1";
                importBtn.addEventListener("click", () => {
                  importPiChatLeads(toolEl).catch((error) => showApiError(error, t("msg.importFailed")));
                });
              }
              if (payload.result?.import) {
                toolEl.querySelector(".pi-chat-leads-actions")?.classList.add("hidden");
              }
            } else if (payload.name === "lookup_asns") {
              pre.classList.add("hidden");
              if (summary) {
                toolEl.querySelector(".pi-chat-tool-progress").textContent = summary;
              }
              for (const row of payload.result?.rows || payload.result?.preview || []) {
                appendPiChatLookupRow(toolEl, row);
              }
              const importBtn = toolEl.querySelector(".pi-chat-import-lookup");
              if (importBtn && !importBtn.dataset.bound) {
                importBtn.dataset.bound = "1";
                importBtn.addEventListener("click", () => {
                  importPiChatLookup(toolEl).catch((error) => showApiError(error, t("msg.importFailed")));
                });
              }
            } else if (summary) {
              pre.classList.remove("hidden");
              pre.textContent = summary;
            } else {
              const raw = JSON.stringify(payload.result, null, 2);
              showPiToolRawDetail(toolEl, raw);
              toolEntry.summary = raw.slice(0, 8000);
            }
            if (!toolFailed) {
              applyPiDestructiveHint(toolEl, payload.name);
              if (payload.result?.undo_payload) addPiUndoButton(toolEl, payload.result);
            }
          }
          appendPiHistoryEntry(toolEntry);
          activeToolEl = null;
          setProgressFill(piChatProgressFill, 85);
        } else if (payload.type === "assistant_start") {
          settlePendingAssistantBubble();
          assistantStreamText = "";
          setProgressFill(piChatProgressFill, 90);
        } else if (payload.type === "assistant_delta") {
          assistantStreamText += payload.text || "";
          const visibleText = sanitizePiAssistantDisplay(assistantStreamText);
          if (visibleText) {
            if (!activeAssistantEl) {
              activeAssistantEl = appendPiChatBubble("assistant", visibleText);
              activeAssistantEl.classList.add("streaming");
            } else {
              updatePiChatAssistantBubble(activeAssistantEl, visibleText, true);
            }
          }
        } else if (payload.type === "assistant_done") {
          assistantStreamText = sanitizePiAssistantDisplay(payload.text || assistantStreamText);
          if (assistantStreamText) {
            if (activeAssistantEl) {
              updatePiChatAssistantBubble(activeAssistantEl, assistantStreamText, false);
            } else {
              activeAssistantEl = appendPiChatBubble("assistant", assistantStreamText);
            }
            appendPiHistoryEntry({ role: "assistant", content: assistantStreamText });
            announcePi(assistantStreamText);
          }
          activeAssistantEl = null;
          assistantStreamText = "";
          setProgressFill(piChatProgressFill, 100);
        } else if (payload.type === "assistant") {
          const assistantText = sanitizePiAssistantDisplay(payload.text || "");
          if (assistantText) {
            appendPiChatBubble("assistant", assistantText);
            appendPiHistoryEntry({ role: "assistant", content: assistantText });
            announcePi(assistantText);
            setProgressFill(piChatProgressFill, 100);
          }
        } else if (payload.type === "error") {
          streamEnded = true;
          settlePendingAssistantBubble();
          failActiveTool(payload.message || t("msg.errorGeneric"));
          showPiTurnError(payload.message || t("msg.errorGeneric"), text);
        } else if (payload.type === "done") {
          streamEnded = true;
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
            streamEnded = true;
            settlePendingAssistantBubble();
            failActiveTool(payload.message || t("msg.errorGeneric"));
            showPiTurnError(payload.message || t("msg.errorGeneric"), text);
          }
        } catch {
          if (!streamEnded) {
            settlePendingAssistantBubble();
            failActiveTool(t("pi.streamInterrupted"));
            showPiTurnError(t("pi.streamInterrupted"), text);
          }
        }
      }
    }

    if (!streamEnded) {
      settlePendingAssistantBubble();
      failActiveTool(t("pi.streamInterrupted"));
      showPiTurnError(t("pi.streamInterrupted"), text);
    }
  } catch (error) {
    settlePendingAssistantBubble();
    if (error.name === "AbortError") {
      failActiveTool(t("pi.stopped"));
      appendPiChatStatus(t("pi.stopped"));
    } else {
      const failMsg = !navigator.onLine
        ? t("pi.errorOffline")
        : error instanceof TypeError
          ? t("pi.errorNetwork")
          : errorMessage(error, t("pi.requestFailed"));
      failActiveTool(failMsg);
      showPiTurnError(failMsg, text);
    }
  } finally {
    state.piChatController = null;
    if (state.activePiThreadId) {
      try {
        await fetchActivePiThreadHistory();
        restorePiChatUi();
        await refreshActivePiThreadMeta();
      } catch {
        // keep local UI if refresh fails
      }
    }
    setPiChatBusy(false);
    renderPiThreadList();
    savePiThreadsStore();
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
    return;
  }
  if (state.piBackgroundJobId) {
    cancelBackgroundJob(state.piBackgroundJobId).catch(() => {});
  }
}

export function clearPiChat() {
  if (state.piChatHistory.length && !window.confirm(t("pi.confirmClear"))) {
    return;
  }
  clearPiTurnError();
  state.piChatHistory = [];
  const thread = getActivePiThread();
  if (thread) {
    thread.history = [];
    thread.title = defaultPiThreadTitle();
    thread.updatedAt = Date.now();
  }
  savePiThreadsStore();
  mountPiEmptyState();
  updatePiChatHistoryHint();
  updatePiAgentStatus();
}

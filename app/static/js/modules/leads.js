import { t } from "../../i18n.js";
import * as dom from "../core/dom.js";
import * as state from "../core/state.js";
import { CHANNEL_DEFS } from "../core/state.js";
import { api, escapeHtml, errorMessage, formatImportResult, normalizeImportRows } from "../core/utils.js";
import { notifyInfo } from "../core/toast.js";
import { deps } from "../core/deps.js";
import { trackBackgroundJob } from "../jobs/index.js";

const {
  leadQueryInput,
  minScoreInput,
  autoImportInput,
  discoverBtn,
  discoverViaPiBtn,
  aiProgressEl,
  aiProgressFill,
  aiProgressText,
  aiStatsEl,
  aiLeadsBody,
  aiLeadsStateEl,
  aiChannelsEl,
  importLeadsBtn,
  retryDiscoverBtn,
  leadDetailModal,
  leadDetailBody,
  leadDetailImport,
  discoverBackgroundInput,
} = dom;

export function ensureLeadSelected(lead) {
  if (lead._selected === undefined) {
    lead._selected = true;
  }
}

export function getSelectedAiLeads() {
  return state.aiLeads.filter((lead) => lead._selected !== false);
}

export function updateAiLeadsStats() {
  const total = state.aiLeads.length;
  const selected = getSelectedAiLeads().length;
  if (total === 0) {
    aiStatsEl.textContent = t("common.notStarted");
    importLeadsBtn.disabled = true;
    return;
  }
  aiStatsEl.textContent = t("msg.aiLeadsStats", { selected, total });
  importLeadsBtn.disabled = selected === 0;
}

export function hideLeadsState() {
  aiLeadsStateEl.classList.add("hidden");
  aiLeadsStateEl.innerHTML = "";
}

export function showLeadsState(html, isError = false) {
  aiLeadsStateEl.className = `leads-state${isError ? " error" : ""}`;
  aiLeadsStateEl.innerHTML = html;
}

export function showLeadsError(message) {
  showLeadsState(`<p>${t("msg.leadsError", { message: escapeHtml(message) })}</p>`, true);
  retryDiscoverBtn.classList.remove("hidden");
}

export function showLeadsEmpty() {
  showLeadsState(`<p>${t("msg.leadsEmpty")}</p>`);
  retryDiscoverBtn.classList.remove("hidden");
}

export function renderAiLeads() {
  aiLeadsBody.innerHTML = "";
  if (state.aiLeads.length > 0) hideLeadsState();

  if (state.aiLeads.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="8">用自然语言描述目标客户，AI 会从多个渠道自动搜索并评分</td>`;
    aiLeadsBody.appendChild(tr);
    updateAiLeadsStats();
    return;
  }

  for (let index = 0; index < state.aiLeads.length; index += 1) {
    const lead = state.aiLeads[index];
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

export function formatSource(lead) {
  const source = lead.source || "unknown";
  const map = {
    "web-search": t("source.webSearch"),
    "arin-rdap": t("source.arinRdap"),
    peeringdb: t("channel.peeringdb"),
    "ai-lead": "AI",
  };
  return map[source] || source;
}

export function scoreBadgeClass(score) {
  const value = Number(score) || 0;
  if (value >= 80) return "score-badge score-high";
  if (value >= 60) return "score-badge score-mid";
  return "score-badge score-low";
}

export function openLeadDetail(index) {
  const lead = state.aiLeads[index];
  if (!lead) return;
  state.detailLeadIndex = index;
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

export function closeLeadDetail() {
  state.detailLeadIndex = null;
  leadDetailModal.classList.add("hidden");
}

export function resetChannelPanel() {
  state.channelState = {};
  for (const def of CHANNEL_DEFS) {
    state.channelState[def.key] = { state: "idle", count: "", preview: "" };
  }
  renderChannelPanel();
}

export function setChannel(key, patch) {
  if (!state.channelState[key]) state.channelState[key] = { state: "idle", count: "", preview: "" };
  Object.assign(state.channelState[key], patch);
  renderChannelPanel();
}

export const CHANNEL_ICON = { idle: "·", active: "◐", done: "✓", failed: "×" };

export function renderChannelPanel() {
  aiChannelsEl.classList.remove("hidden");
  aiChannelsEl.innerHTML = CHANNEL_DEFS.map((def) => {
    const s = state.channelState[def.key] || { state: "idle", count: "", preview: "" };
    return `
      <div class="ai-channel-row state-${s.state}">
        <span class="ai-channel-icon">${CHANNEL_ICON[s.state]}</span>
        <span class="ai-channel-name">${escapeHtml(t(def.nameKey))}</span>
        <span class="ai-channel-count">${escapeHtml(String(s.count ?? ""))}</span>
        <span class="ai-channel-preview" title="${escapeHtml(s.preview || "")}">${escapeHtml(s.preview || "")}</span>
      </div>`;
  }).join("");
}

export async function loadLlmStatus() {
  try {
    const config = await fetch("/api/config").then((response) => response.json());
    state.llmConfigured = Boolean(config.llm_configured);
    if (state.llmConfigured) {
      discoverBtn.disabled = false;
      if (discoverViaPiBtn) discoverViaPiBtn.disabled = false;
      hideLeadsState();
    } else {
      discoverBtn.disabled = true;
      if (discoverViaPiBtn) discoverViaPiBtn.disabled = true;
      hideLeadsState();
    }
  } catch {
    discoverBtn.disabled = true;
    if (discoverViaPiBtn) discoverViaPiBtn.disabled = true;
  }
  updatePiAgentStatus();
}

export function setDiscoverRunning(running) {
  if (running) {
    discoverBtn.textContent = t("msg.discoverCancel");
    discoverBtn.classList.add("danger-btn");
    discoverBtn.disabled = false;
    if (discoverViaPiBtn) discoverViaPiBtn.disabled = true;
    retryDiscoverBtn.classList.add("hidden");
  } else {
    discoverBtn.textContent = t("aiLeads.discoverDirect");
    discoverBtn.classList.remove("danger-btn");
    discoverBtn.disabled = !state.llmConfigured;
    if (discoverViaPiBtn) discoverViaPiBtn.disabled = !state.llmConfigured;
  }
}

export async function runLeadDiscovery() {
  if (state.discoverController) {
    state.discoverController.abort();
    return;
  }
  const query = leadQueryInput.value.trim();
  if (!query) {
    alert(t("msg.describeLeads"));
    return;
  }
  if (!state.llmConfigured) {
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
      notifyInfo(t("msg.jobStartedBackground"));
    } catch (error) {
      alert(errorMessage(error, t("msg.leadsError", { message: error.message })));
    }
    return;
  }

  state.aiLeads = [];
  renderAiLeads();
  resetChannelPanel();
  hideLeadsState();
  aiProgressEl.classList.remove("hidden");
  aiProgressFill.style.width = "0%";
  aiProgressText.textContent = t("msg.aiAnalyzing");
  state.lastDiscoverQuery = query;
  state.discoverController = new AbortController();
  setDiscoverRunning(true);
  retryDiscoverBtn.classList.add("hidden");
  importLeadsBtn.disabled = true;

  try {
    const response = await fetch("/api/leads/discover/stream", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      signal: state.discoverController.signal,
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
          state.aiLeads.push(payload.lead);
          renderAiLeads();
        }

        if (payload.type === "error") {
          throw new Error(payload.message);
        }

        if (payload.type === "done") {
          aiProgressFill.style.width = "100%";
          aiProgressText.textContent = payload.message || t("msg.discoverComplete");
          setChannel("scoring", { state: "done", count: (payload.leads || state.aiLeads).length });
          if (payload.leads) {
            state.aiLeads = payload.leads.map((lead) => {
              ensureLeadSelected(lead);
              return lead;
            });
            renderAiLeads();
          }
          if (payload.import) {
            alert(formatImportResult(payload.import));
            await loadContacts();
          }
          if ((payload.leads || state.aiLeads).length === 0) {
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
    state.discoverController = null;
    setDiscoverRunning(false);
  }
}

export async function importAiLeads() {
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
    deps.switchView("contacts");
  } catch (error) {
    alert(error.message || t("msg.importFailed"));
  }
}

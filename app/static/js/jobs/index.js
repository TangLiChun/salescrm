import { t } from "../../i18n.js";
import * as dom from "../core/dom.js";
import { state } from "../core/state.js";
import { api, escapeHtml, errorMessage } from "../core/utils.js";
import { replayAnimation, staggerChildren } from "../core/motion.js";
import {
  notifySuccess,
  notifyError,
  jobTypeLabel,
  jobStatusLabel,
  formatJobTime,
} from "../core/toast.js";
import { deps } from "../core/deps.js";

const {
  backgroundJobsBar,
  jobsPanelEl,
  jobsPanelListEl,
  progressEl,
  progressFill,
  progressText,
  exportBtn,
  importBtn,
  aiProgressEl,
} = dom;

export const backgroundJobTrackers = new Map();

let jobsEventSource = null;
let jobsSseConnected = false;

export function openJobsPanel() {
  if (!jobsPanelEl) return;
  jobsPanelEl.classList.remove("hidden");
  replayAnimation(jobsPanelEl.querySelector(".jobs-panel-backdrop"), "motion-fade-in");
  replayAnimation(jobsPanelEl.querySelector(".jobs-panel-sheet"), "motion-sheet-enter");
  loadJobsPanelList().catch(() => {});
}

export function closeJobsPanel() {
  jobsPanelEl?.classList.add("hidden");
}

export async function loadJobsPanelList() {
  if (!jobsPanelListEl) return;
  const data = await api("/api/jobs");
  const jobs = data.jobs || [];
  if (!jobs.length) {
    jobsPanelListEl.innerHTML = `<li class="jobs-panel-empty">${escapeHtml(t("jobs.emptyList"))}</li>`;
    return;
  }
  jobsPanelListEl.innerHTML = jobs
    .map((job) => {
      const status = job.status || "pending";
      const msg = job.message || backgroundJobLabel(job) || "";
      const time = formatJobTime(job.updated_at || job.created_at);
      return `
        <li class="jobs-panel-item">
          <div class="jobs-panel-item-head">
            <span class="jobs-panel-item-type">${escapeHtml(jobTypeLabel(job.job_type))}</span>
            <span class="jobs-panel-item-status ${escapeHtml(status)}">${escapeHtml(jobStatusLabel(status))}</span>
          </div>
          <div class="jobs-panel-item-msg">${escapeHtml(msg)}</div>
          <div class="jobs-panel-item-time">${escapeHtml(time)}</div>
        </li>`;
    })
    .join("");
  staggerChildren(jobsPanelListEl, ".jobs-panel-item");
}

export async function navigateForCompletedJob(job) {
  if (!job || job.status !== "done") return;
  if (job.job_type === "pi_agent") {
    const threadId = job.result?.thread_id;
    deps.switchView?.("pi-agent");
    if (threadId && state.piThreads.some((thread) => thread.id === threadId)) {
      await deps.switchPiThread?.(threadId);
    }
    return;
  }
  if (job.job_type === "lead_discover") {
    deps.switchView?.("ai-leads");
    return;
  }
  if (job.job_type === "lookup") {
    deps.switchView?.("lookup");
  }
}

export function backgroundJobLabel(job) {
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
  if (job.job_type === "pi_agent") {
    if (progress.name && progress.message) {
      return t("jobs.piProgress", { name: progress.name, message: progress.message });
    }
    if (progress.message) {
      return t("jobs.piRunning", { message: progress.message });
    }
    return t("jobs.piStarting");
  }
  if (job.job_type === "lead_discover") {
    if (progress.type === "progress") {
      return t("jobs.leadsRdap", {
        current: progress.index,
        total: progress.total,
        asn: progress.asn ? `AS${progress.asn}` : "",
      });
    }
    if (progress.message) {
      return t("jobs.leadsProgress", { message: progress.message });
    }
    return t("jobs.leadsRunning");
  }
  if (progress.message) {
    return t("jobs.leadsProgress", { message: progress.message });
  }
  return t("jobs.leadsRunning");
}

export function renderBackgroundJobsBar() {
  if (!backgroundJobsBar) return;
  const wasHidden = backgroundJobsBar.classList.contains("hidden");
  const active = [...backgroundJobTrackers.values()]
    .map((entry) => entry.job)
    .filter((job) => job && (job.status === "pending" || job.status === "running"));
  if (!active.length) {
    backgroundJobsBar.classList.add("hidden");
    backgroundJobsBar.innerHTML = "";
    return;
  }
  backgroundJobsBar.classList.remove("hidden");
  backgroundJobsBar.innerHTML = `
    <span class="background-jobs-summary">${escapeHtml(t("jobs.activeCount", { count: active.length }))}</span>
    ${active
      .map(
        (job) =>
          `<span class="background-job-chip">${escapeHtml(backgroundJobLabel(job))}</span>`,
      )
      .join("")}
    <button type="button" class="secondary-btn background-jobs-open">${escapeHtml(t("jobs.viewAll"))}</button>`;
  if (wasHidden) {
    replayAnimation(backgroundJobsBar, "motion-bar-enter");
    staggerChildren(backgroundJobsBar, ".background-job-chip");
  }
}

function applyLookupJobResult(job) {
  const result = job.result || {};
  if (Array.isArray(result.rows)) {
    state.allRows = result.rows;
    for (const row of state.allRows) deps.ensureRowSelected?.(row);
    state.csvContent = result.csv || "";
    deps.renderRows?.();
    exportBtn.disabled = state.allRows.length === 0;
    importBtn.disabled = (deps.getSelectedImportableRows?.() || []).length === 0;
    progressEl.classList.remove("hidden");
    progressFill.style.width = "100%";
    progressText.textContent = t("msg.lookupDone");
  }
  const activeView = document.querySelector(".tab.active")?.dataset.view;
  if (activeView !== "lookup") {
    notifySuccess(t("jobs.lookupDone", { emails: result.emails || 0 }), {
      actionLabel: t("jobs.viewLookup"),
      onAction: () => deps.switchView?.("lookup"),
    });
  }
}

function applyLeadDiscoverJobResult(job) {
  const result = job.result || {};
  if (Array.isArray(result.leads)) {
    state.aiLeads = result.leads.map((lead) => {
      deps.ensureLeadSelected?.(lead);
      return lead;
    });
    deps.renderAiLeads?.();
    deps.hideLeadsState?.();
    aiProgressEl.classList.add("hidden");
    if (result.import) {
      deps.loadContacts?.().catch(() => {});
    }
  }
  const activeView = document.querySelector(".tab.active")?.dataset.view;
  if (activeView !== "ai-leads") {
    notifySuccess(t("jobs.leadsDone", { count: (result.leads || []).length }), {
      actionLabel: t("jobs.viewLeads"),
      onAction: () => deps.switchView?.("ai-leads"),
    });
  }
}

function applyEnrichContactJobResult(job) {
  const result = job.result || {};
  if (result.import) {
    deps.loadContacts?.().catch(() => {});
  }
  const count = Array.isArray(result.leads) ? result.leads.length : 0;
  const contactId = result.contact_id || "";
  notifySuccess(
    t("jobs.enrichDone", {
      count,
      contactId,
      message: result.message || job.message || "",
    }),
    {
      actionLabel: t("jobs.viewContacts"),
      onAction: () => deps.switchView?.("contacts"),
    },
  );
}

async function applyPiAgentJobResult(job) {
  const result = job.result || {};
  const threadId = result.thread_id;
  if (threadId && state.piThreads.some((thread) => thread.id === threadId)) {
    if (state.activePiThreadId === threadId) {
      await deps.fetchActivePiThreadHistory?.();
      deps.restorePiChatUi?.();
    }
  }
  deps.loadContacts?.().catch(() => {});
  const snippet = String(result.assistant || job.message || "").trim().slice(0, 120);
  const activeView = document.querySelector(".tab.active")?.dataset.view;
  if (activeView !== "pi-agent") {
    notifySuccess(t("jobs.piDone", { snippet: snippet || t("jobs.piDoneFallback") }), {
      actionLabel: t("jobs.viewPi"),
      onAction: () => {
        navigateForCompletedJob(job).catch(() => {});
      },
    });
  } else if (snippet) {
    deps.appendPiChatStatus?.(t("jobs.piDoneInline", { snippet }));
  }
}

export function finishBackgroundJob(job) {
  if (job.status === "done") {
    if (job.job_type === "lookup") applyLookupJobResult(job);
    else if (job.job_type === "lead_discover") applyLeadDiscoverJobResult(job);
    else if (job.job_type === "enrich_contact") applyEnrichContactJobResult(job);
    else if (job.job_type === "pi_agent") {
      applyPiAgentJobResult(job).catch(() => {
        notifySuccess(t("jobs.piDone", { snippet: job.message || t("jobs.piDoneFallback") }), {
          actionLabel: t("jobs.viewPi"),
          onAction: () => {
            navigateForCompletedJob(job).catch(() => {});
          },
        });
      });
    }
  } else if (job.status === "error") {
    notifyError(`${t("jobs.failed")}: ${job.message || ""}`, {
      actionLabel: t("jobs.viewAll"),
      onAction: openJobsPanel,
    });
  }
  backgroundJobTrackers.delete(job.id);
  renderBackgroundJobsBar();
  if (jobsPanelEl && !jobsPanelEl.classList.contains("hidden")) {
    loadJobsPanelList().catch(() => {});
  }
}

export async function pollBackgroundJob(jobId) {
  try {
    const data = await api(`/api/jobs/${jobId}`);
    const job = data.job;
    if (!job) return;
    const entry = backgroundJobTrackers.get(jobId);
    if (entry) entry.job = job;
    renderBackgroundJobsBar();
    if (jobsPanelEl && !jobsPanelEl.classList.contains("hidden")) {
      loadJobsPanelList().catch(() => {});
    }
    if (job.status === "done" || job.status === "error") {
      if (entry?.timer) clearInterval(entry.timer);
      finishBackgroundJob(job);
    }
  } catch {
    // keep polling on transient errors
  }
}

function startPollingForJob(jobId) {
  const entry = backgroundJobTrackers.get(jobId);
  if (!entry || entry.timer || jobsSseConnected) return;
  entry.timer = setInterval(() => pollBackgroundJob(jobId), 2000);
}

export function trackBackgroundJob(job, options = {}) {
  if (!job?.id) return;
  const existing = backgroundJobTrackers.get(job.id);
  if (existing?.timer) clearInterval(existing.timer);
  const entry = { job, timer: null };
  backgroundJobTrackers.set(job.id, entry);
  renderBackgroundJobsBar();
  if (job.status === "done" || job.status === "error") {
    finishBackgroundJob(job);
    return;
  }
  if (!options.fromSse || !jobsSseConnected) {
    startPollingForJob(job.id);
  }
  if (!options.fromSse) {
    pollBackgroundJob(job.id).catch(() => {});
  }
}

export async function resumeBackgroundJobs() {
  try {
    const data = await api("/api/jobs?active=true");
    for (const job of data.jobs || []) trackBackgroundJob(job);
  } catch {
    // ignore
  }
}

export function startJobEventStream() {
  if (jobsEventSource) return;
  jobsEventSource = new EventSource("/api/jobs/events", { withCredentials: true });
  jobsEventSource.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "job" && payload.job) handleJobEvent(payload.job);
    } catch {
      // ignore malformed events
    }
  };
  jobsEventSource.onerror = () => {
    jobsSseConnected = false;
    for (const [jobId] of backgroundJobTrackers) {
      startPollingForJob(jobId);
    }
  };
  jobsEventSource.onopen = () => {
    jobsSseConnected = true;
    for (const entry of backgroundJobTrackers.values()) {
      if (entry.timer) {
        clearInterval(entry.timer);
        entry.timer = null;
      }
    }
  };
}

function handleJobEvent(job) {
  let entry = backgroundJobTrackers.get(job.id);
  if (!entry && (job.status === "pending" || job.status === "running")) {
    trackBackgroundJob(job, { fromSse: true });
    return;
  }
  if (!entry) return;
  entry.job = job;
  renderBackgroundJobsBar();
  if (jobsPanelEl && !jobsPanelEl.classList.contains("hidden")) {
    loadJobsPanelList().catch(() => {});
  }
  if (job.status === "done" || job.status === "error") {
    if (entry.timer) {
      clearInterval(entry.timer);
      entry.timer = null;
    }
    finishBackgroundJob(job);
  }
}

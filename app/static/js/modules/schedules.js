import { t } from "../../i18n.js";
import * as dom from "../core/dom.js";
import { state } from "../core/state.js";
import { api, escapeHtml, formatTime } from "../core/utils.js";
import { deps } from "../core/deps.js";
import { showApiError, showApiSuccess } from "../core/api-feedback.js";
const { schedulesBody, schedulesStatsEl, scheduleForm, scheduleNameInput, scheduleQueryInput, scheduleIntervalPreset, scheduleIntervalMinutesInput, scheduleIntervalWrap, scheduleIntervalCustomWrap, scheduleRunModeInput, scheduleCooldownInput, scheduleCooldownWrap, schedulerStatusEl, scheduleMinScoreInput, scheduleAutoImportInput, } = dom;
export function formatScheduleInterval(job) {
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
export function updateScheduleFormMode() {
    const continuous = scheduleRunModeInput?.value === "continuous";
    scheduleIntervalWrap?.classList.toggle("hidden", continuous);
    scheduleIntervalCustomWrap?.classList.toggle("hidden", continuous || scheduleIntervalPreset?.value !== "custom");
    scheduleCooldownWrap?.classList.toggle("hidden", !continuous);
}
export function getScheduleIntervalMinutes() {
    if (scheduleIntervalPreset?.value === "custom") {
        return Number(scheduleIntervalMinutesInput?.value) || 1440;
    }
    return Number(scheduleIntervalPreset?.value) || 1440;
}
export function renderSchedulerStatus() {
    if (!schedulerStatusEl)
        return;
    if (!state.schedulerStatus) {
        schedulerStatusEl.textContent = "";
        return;
    }
    if (!state.schedulerStatus.enabled) {
        schedulerStatusEl.textContent = t("msg.schedulerDisabledHint");
        schedulerStatusEl.className = "stats scheduler-status warn";
        return;
    }
    if (!state.schedulerStatus.llm_configured) {
        schedulerStatusEl.textContent = t("msg.schedulerLlmMissing");
        schedulerStatusEl.className = "stats scheduler-status warn";
        return;
    }
    const running = state.schedulerStatus.active_jobs > 0
        ? t("msg.schedulerRunningJobs", { count: state.schedulerStatus.active_jobs })
        : t("msg.schedulerIdle");
    schedulerStatusEl.textContent = t("msg.schedulerStatusLine", {
        poll: state.schedulerStatus.poll_seconds,
        enabled: state.schedulerStatus.enabled_jobs,
        running,
    });
    schedulerStatusEl.className = "stats scheduler-status ok";
}
export function formatJobRunLine(run) {
    const statusLabel = run.status === "ok" ? t("msg.scheduleRunOk") : t("msg.scheduleRunFail");
    const detail = run.status === "ok"
        ? t("msg.scheduleRunDetail", { leads: run.leads_found, imported: run.imported })
        : escapeHtml(run.message || statusLabel);
    return `<li><span class="run-time">${escapeHtml(formatTime(run.ran_at))}</span> <span class="run-status run-${escapeHtml(run.status)}">${statusLabel}</span> ${detail}</li>`;
}
export function renderSchedules() {
    schedulesBody.innerHTML = "";
    if (state.schedules.length === 0) {
        const tr = document.createElement("tr");
        tr.className = "empty-row";
        tr.innerHTML = `<td colspan="7">${t("schedules.empty")}</td>`;
        schedulesBody.appendChild(tr);
        schedulesStatsEl.textContent = t("msg.noSchedules");
        return;
    }
    for (const job of state.schedules) {
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
        const runs = state.scheduleRuns[job.id] || [];
        if (runs.length > 0) {
            const runsTr = document.createElement("tr");
            runsTr.className = "schedule-runs-row";
            runsTr.innerHTML = `<td colspan="7"><ul class="schedule-runs-list">${runs.map(formatJobRunLine).join("")}</ul></td>`;
            schedulesBody.appendChild(runsTr);
        }
    }
    schedulesStatsEl.textContent = t("msg.schedulesCount", { count: state.schedules.length });
}
export async function loadSchedules() {
    const data = await api("/api/schedules");
    state.schedules = data.schedules || [];
    state.schedulerStatus = data.scheduler || null;
    state.scheduleRuns = {};
    await Promise.all(state.schedules.map(async (job) => {
        const runData = await api(`/api/schedules/${job.id}/runs?limit=5`);
        state.scheduleRuns[job.id] = runData.runs || [];
    }));
    renderSchedules();
    renderSchedulerStatus();
}
export function startSchedulesAutoRefresh() {
    stopSchedulesAutoRefresh();
    state.schedulesRefreshTimer = window.setInterval(() => {
        loadSchedules().catch(() => { });
    }, 30000);
}
export function stopSchedulesAutoRefresh() {
    if (state.schedulesRefreshTimer) {
        window.clearInterval(state.schedulesRefreshTimer);
        state.schedulesRefreshTimer = null;
    }
}
export async function createSchedule(event) {
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
    if (scheduleRunModeInput)
        scheduleRunModeInput.value = "continuous";
    if (scheduleIntervalPreset)
        scheduleIntervalPreset.value = "1440";
    if (scheduleCooldownInput)
        scheduleCooldownInput.value = "15";
    updateScheduleFormMode();
    await loadSchedules();
}
export async function toggleSchedule(jobId, enabled) {
    await api(`/api/schedules/${jobId}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
    });
    await loadSchedules();
}
export async function deleteSchedule(jobId) {
    if (!confirm(t("msg.confirmDeleteSchedule")))
        return;
    await api(`/api/schedules/${jobId}`, { method: "DELETE" });
    await loadSchedules();
}
export async function runScheduleNow(jobId) {
    if (!confirm(t("msg.confirmRunSchedule")))
        return;
    const result = await api(`/api/schedules/${jobId}/run`, { method: "POST" });
    if (result.ok) {
        showApiSuccess(result.message || t("msg.runDone"));
    }
    else {
        showApiError(null, result.message || t("msg.runFailed"));
    }
    await loadSchedules();
    deps.loadContacts?.().catch(() => { });
}

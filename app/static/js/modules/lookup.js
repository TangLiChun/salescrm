import { t } from "../../i18n.js";
import * as dom from "../core/dom.js";
import * as state from "../core/state.js";
import { api, escapeHtml, errorMessage, formatApiDetail, formatImportResult, normalizeImportRows, rowsToCsv } from "../core/utils.js";
import { notifyInfo } from "../core/toast.js";
import { deps } from "../core/deps.js";
import { trackBackgroundJob } from "../jobs/index.js";

const {
  asnInput, asnParsePreviewEl, delayInput, lookupBtn, exportBtn, importBtn, roleFilter,
  resultsBody, statsEl, progressEl, progressFill, progressText, lookupBackgroundInput,
} = dom;

export function setLoading(isLoading) {
  lookupBtn.disabled = isLoading;
  exportBtn.disabled = isLoading || state.allRows.length === 0;
  importBtn.disabled = isLoading || getSelectedImportableRows().length === 0;
}

export function getImportableRows() {
  return state.allRows.filter((row) => row.email && !row.error);
}

export function ensureRowSelected(row) {
  if (row.email && !row.error && row._selected === undefined) {
    row._selected = true;
  }
}

export function getSelectedImportableRows() {
  return getImportableRows().filter((row) => row._selected !== false);
}

export function updateStats() {
  const visibleRows = getVisibleRows();
  const uniqueAsns = new Set(visibleRows.map((row) => row.asn)).size;
  const emails = visibleRows.filter((row) => row.email).length;
  const errors = visibleRows.filter((row) => row.error).length;
  const importable = getImportableRows().length;
  const selected = getSelectedImportableRows().length;
  const selection = importable > 0 ? t("msg.lookupStatsSelectionFull", { selected, importable }) : "";
  statsEl.textContent = t("msg.lookupStats", { asns: uniqueAsns, emails, errors, selection });
}

export function getVisibleRows() {
  const role = roleFilter.value;
  if (!role) return state.allRows;
  return state.allRows.filter((row) => row.roles.includes(role));
}

export function renderRows() {
  const rows = getVisibleRows();
  resultsBody.innerHTML = "";

  if (rows.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="9">${state.allRows.length ? t("msg.filterNoResults") : t("lookup.emptyHint")}</td>`;
    resultsBody.appendChild(tr);
    updateStats();
    importBtn.disabled = getSelectedImportableRows().length === 0;
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    const rowIndex = state.allRows.indexOf(row);
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

export async function runLookup() {
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
      notifyInfo(t("msg.jobStartedBackground"));
    } catch (error) {
      alert(errorMessage(error, t("msg.lookupFailed")));
    }
    return;
  }

  state.allRows = [];
  state.csvContent = "";
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
          state.allRows.push(...payload.rows);
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
          state.csvContent = rowsToCsv(state.allRows);
          exportBtn.disabled = state.allRows.length === 0;
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

export function formatImportResult(result) {
  const filtered = result.filtered ? t("msg.importFiltered", { filtered: result.filtered }) : "";
  return t("msg.importDone", {
    imported: result.imported,
    duplicates: result.duplicates,
    skipped: result.skipped,
    filtered,
  });
}

export function normalizeImportRow(row) {
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

export function normalizeImportRows(rows) {
  return (rows || []).map((row) => normalizeImportRow(row));
}

export let state.asnParseTimer = null;

export function renderAsnPreview(data) {
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

export async function refreshAsnPreview() {
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

export async function importResults() {
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
    deps.switchView("contacts");
  } catch (error) {
    alert(error.message || t("msg.importFailed"));
  } finally {
    importBtn.disabled = getSelectedImportableRows().length === 0;
  }
}

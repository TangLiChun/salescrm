import { t, followUpLabel, followUpOptions } from "../../i18n.js";
import * as dom from "../core/dom.js";
import { state } from "../core/state.js";
import { api, escapeHtml, errorMessage, formatTime } from "../core/utils.js";
import { deps } from "../core/deps.js";

const {
  contactsBody,
  contactsStatsEl,
  contactsMetricTotalEl,
  contactsMetricSentEl,
  contactsMetricUnsentEl,
  contactsBulkBar,
  contactsSelectedCountEl,
  contactsSelectAll,
  contactsPagination,
  contactsPrevBtn,
  contactsNextBtn,
  contactsPageInfo,
  contactStatusFilter,
  contactFollowUpFilter,
  contactSearchInput,
  contactEditModal,
  contactEditSubtitle,
  contactEditForm,
  contactEditOrg,
  contactEditName,
  contactEditRoles,
  contactEditNotes,
  contactEditLinkedin,
  contactEditX,
  contactEditFacebook,
  contactNotesModal,
  contactNotesTitle,
  contactNotesSubtitle,
  contactNotesList,
  contactNoteForm,
  contactNoteBody,
  mailTemplateSelect,
  emailTemplatesListEl,
  templateNameInput,
  templateSubjectInput,
  templateBodyInput,
  saveTemplateBtn,
  templateStatusEl,
} = dom;

export function followUpStatusBadge(status) {
  const key = status || "new";
  const label = followUpLabel(key);
  return `<span class="status-badge follow-up-${escapeHtml(key)}">${escapeHtml(label)}</span>`;
}

export function closeAllContactActionMenus() {
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

export function positionContactActionMenu(toggle, panel) {
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

export function socialLinksHtml(contact) {
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

export function contactActionsHtml(contact) {
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

export function updateContactsMetrics(total, sentOnPage, unsentOnPage) {
  if (contactsMetricTotalEl) contactsMetricTotalEl.textContent = String(total ?? 0);
  if (contactsMetricSentEl) contactsMetricSentEl.textContent = String(sentOnPage ?? 0);
  if (contactsMetricUnsentEl) contactsMetricUnsentEl.textContent = String(unsentOnPage ?? 0);
}

export function renderContacts() {
  contactsBody.innerHTML = "";
  updateContactsBulkBar();

  if (state.contacts.length === 0) {
    const tr = document.createElement("tr");
    tr.className = "empty-row";
    tr.innerHTML = `<td colspan="11">${t("msg.contactsEmptyImportHint")}</td>`;
    contactsBody.appendChild(tr);
    contactsStatsEl.textContent = state.contactsTotal
      ? t("msg.contactsStatsEmptyPage", { total: state.contactsTotal })
      : t("msg.contactsEmpty");
    updateContactsMetrics(state.contactsTotal, 0, 0);
    renderContactsPagination();
    return;
  }

  let sentCount = 0;
  for (const contact of state.contacts) {
    if (contact.email_sent) sentCount += 1;
    const tr = document.createElement("tr");
    if (contact.email_sent) tr.classList.add("row-sent");
    const roles = (contact.roles || "")
      .split(",")
      .filter(Boolean)
      .map((role) => `<span class="role-tag">${escapeHtml(role)}</span>`)
      .join("");
    const statusBadge = followUpStatusBadge(contact.follow_up_status);
    const checked = state.selectedContactIds.has(contact.id) ? "checked" : "";
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
    total: state.contactsTotal,
    pageCount: state.contacts.length,
    sent: sentCount,
    page: state.contactsPage,
    pages: state.contactsPages,
  });
  updateContactsMetrics(state.contactsTotal, sentCount, state.contacts.length - sentCount);
  renderContactsPagination();
  syncContactsSelectAllCheckbox();
}

export function updateContactsBulkBar() {
  const count = state.selectedContactIds.size;
  contactsBulkBar.classList.toggle("hidden", count === 0);
  contactsSelectedCountEl.textContent = t("msg.contactsSelected", { count });
}

export function syncContactsSelectAllCheckbox() {
  if (!contactsSelectAll) return;
  const pageIds = state.contacts.map((c) => c.id);
  const allSelected = pageIds.length > 0 && pageIds.every((id) => state.selectedContactIds.has(id));
  contactsSelectAll.checked = allSelected;
  contactsSelectAll.indeterminate = !allSelected && pageIds.some((id) => state.selectedContactIds.has(id));
}

export function renderContactsPagination() {
  if (state.contactsTotal === 0) {
    contactsPagination.classList.add("hidden");
    return;
  }
  contactsPagination.classList.remove("hidden");
  contactsPageInfo.textContent = t("msg.contactsPage", {
    page: state.contactsPage,
    pages: state.contactsPages,
    total: state.contactsTotal,
  });
  contactsPrevBtn.disabled = state.contactsPage <= 1;
  contactsNextBtn.disabled = state.contactsPage >= state.contactsPages;
}

export async function loadContacts(resetPage = false) {
  if (resetPage) state.contactsPage = 1;
  const status = contactStatusFilter.value || "all";
  const followUp = contactFollowUpFilter.value || "all";
  const params = new URLSearchParams({
    status,
    follow_up_status: followUp,
    page: String(state.contactsPage),
    page_size: String(state.contactsPageSize),
  });
  const q = contactSearchInput.value.trim();
  if (q) params.set("q", q);
  const data = await api(`/api/contacts?${params.toString()}`);
  state.contacts = data.contacts || [];
  state.contactsTotal = data.total || 0;
  state.contactsPage = data.page || 1;
  state.contactsPages = data.pages || 1;
  state.contactsPageSize = data.page_size || state.contactsPageSize;
  renderContacts();
}

export function getSelectedContactIds() {
  return [...state.selectedContactIds];
}

export async function bulkContactsAction(action, extra = {}) {
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
  state.selectedContactIds.clear();
  await loadContacts();
  return result;
}

export function openContactEdit(contactId) {
  const contact = state.contacts.find((item) => String(item.id) === String(contactId));
  if (!contact) return;
  state.editingContactId = contact.id;
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

export function closeContactEdit() {
  state.editingContactId = null;
  contactEditModal.classList.add("hidden");
}

export async function saveContactEdit(event) {
  event.preventDefault();
  if (!state.editingContactId) return;
  await api(`/api/contacts/${state.editingContactId}`, {
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

export async function downloadBackup() {
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

export async function exportContactsCsv() {
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

export async function dedupeContacts() {
  const result = await api("/api/contacts/dedupe", { method: "POST" });
  alert(t("msg.dedupeDone", { removed: result.removed, total: result.total }));
  await loadContacts();
}

export async function markContactSent(contactId, sent) {
  await api(`/api/contacts/${contactId}/mark-sent`, {
    method: "POST",
    body: JSON.stringify({ sent }),
  });
  await loadContacts();
}

export async function changeContactFollowUpStatus(contactId, currentStatus) {
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

export function renderTemplateText(text, contact) {
  const asn = contact.asn ? String(contact.asn) : "";
  return String(text || "")
    .replaceAll("{org}", contact.org || "")
    .replaceAll("{name}", contact.name || "")
    .replaceAll("{email}", contact.email || "")
    .replaceAll("{asn}", asn)
    .replaceAll("{roles}", contact.roles || "");
}

export function openMailClient(contactId) {
  const contact = state.contacts.find((item) => String(item.id) === String(contactId));
  if (!contact?.email) return;

  const templateId = mailTemplateSelect.value;
  const template = state.emailTemplates.find((item) => String(item.id) === templateId);
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

export function renderMailTemplateSelect() {
  const current = mailTemplateSelect.value;
  mailTemplateSelect.innerHTML = `<option value="">${t("contacts.noTemplate")}</option>`;
  for (const template of state.emailTemplates) {
    const option = document.createElement("option");
    option.value = String(template.id);
    option.textContent = template.name;
    mailTemplateSelect.appendChild(option);
  }
  if (current && state.emailTemplates.some((item) => String(item.id) === current)) {
    mailTemplateSelect.value = current;
  }
}

export function renderEmailTemplatesList() {
  emailTemplatesListEl.innerHTML = "";
  if (state.emailTemplates.length === 0) {
    emailTemplatesListEl.innerHTML = `<p class="stats">${t("msg.noTemplates")}</p>`;
    return;
  }

  for (const template of state.emailTemplates) {
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

export async function loadEmailTemplates() {
  const data = await api("/api/email-templates");
  state.emailTemplates = data.templates || [];
  renderMailTemplateSelect();
  renderEmailTemplatesList();
}

export function resetTemplateForm() {
  state.editingTemplateId = null;
  templateNameInput.value = "";
  templateSubjectInput.value = "";
  templateBodyInput.value = "";
  saveTemplateBtn.textContent = t("settings.saveTemplate");
  templateStatusEl.textContent = "";
}

export async function saveEmailTemplate() {
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
  if (state.editingTemplateId) {
    await api(`/api/email-templates/${state.editingTemplateId}`, {
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

export async function editEmailTemplate(templateId) {
  const template = state.emailTemplates.find((item) => item.id === templateId);
  if (!template) return;
  state.editingTemplateId = templateId;
  templateNameInput.value = template.name || "";
  templateSubjectInput.value = template.subject || "";
  templateBodyInput.value = template.body || "";
  saveTemplateBtn.textContent = t("msg.updateTemplate");
  templateStatusEl.textContent = t("msg.editingTemplate", { name: template.name });
}

export async function deleteEmailTemplate(templateId) {
  if (!confirm(t("msg.confirmDeleteTemplate"))) return;
  await api(`/api/email-templates/${templateId}`, { method: "DELETE" });
  if (String(state.editingTemplateId) === String(templateId)) {
    resetTemplateForm();
  }
  await loadEmailTemplates();
}

export async function deleteContact(contactId) {
  if (!confirm(t("msg.confirmDeleteContact"))) return;
  await api(`/api/contacts/${contactId}`, { method: "DELETE" });
  state.selectedContactIds.delete(Number(contactId));
  if (String(state.notesContactId) === String(contactId)) {
    closeContactNotes();
  }
  if (String(state.editingContactId) === String(contactId)) {
    closeContactEdit();
  }
  await loadContacts();
}

export function renderContactNotesList(notes) {
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

export async function loadContactNotes(contactId) {
  const data = await api(`/api/contacts/${contactId}/notes`);
  renderContactNotesList(data.notes || []);
}

export function closeContactNotes() {
  state.notesContactId = null;
  contactNotesModal.classList.add("hidden");
  contactNoteBody.value = "";
}

export async function openContactNotes(contactId) {
  const contact = state.contacts.find((item) => String(item.id) === String(contactId));
  if (!contact) return;
  state.notesContactId = contact.id;
  contactNotesTitle.textContent = t("contacts.notesTimeline");
  contactNotesSubtitle.textContent = `${contact.name || "—"} · ${contact.email}`;
  contactNoteBody.value = "";
  contactNotesModal.classList.remove("hidden");
  await loadContactNotes(contact.id);
}

export async function addContactNote(event) {
  event.preventDefault();
  if (!state.notesContactId) return;
  const body = contactNoteBody.value.trim();
  if (!body) return;
  await api(`/api/contacts/${state.notesContactId}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
  contactNoteBody.value = "";
  await loadContactNotes(state.notesContactId);
}

export async function deleteContactNote(noteId) {
  if (!state.notesContactId) return;
  if (!confirm(t("msg.confirmDeleteNote"))) return;
  await api(`/api/contacts/${state.notesContactId}/notes/${noteId}`, { method: "DELETE" });
  await loadContactNotes(state.notesContactId);
}

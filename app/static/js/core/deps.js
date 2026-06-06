/** Late-bound callbacks to break circular imports between jobs and feature modules. */
export const deps = {
  switchView: null,
  loadContacts: null,
  switchPiThread: null,
  fetchActivePiThreadHistory: null,
  restorePiChatUi: null,
  appendPiChatStatus: null,
  syncPiBackgroundJob: null,
  renderRows: null,
  renderAiLeads: null,
  hideLeadsState: null,
  ensureRowSelected: null,
  ensureLeadSelected: null,
  getSelectedImportableRows: null,
};

export function registerDeps(partial) {
  Object.assign(deps, partial);
}

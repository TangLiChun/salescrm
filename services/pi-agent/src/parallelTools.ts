export const PARALLEL_SAFE_TOOLS = new Set([
  "list_contacts",
  "get_contact",
  "get_stats",
  "list_contact_notes",
  "get_lead_preferences",
  "get_import_filters",
  "get_search_config",
  "list_schedules",
  "get_workbench",
  "list_email_templates",
  "preview_email",
  "list_lead_reviews",
]);

export function canParallelizeToolBatch(names: string[]): boolean {
  return names.length >= 2 && names.every((name) => PARALLEL_SAFE_TOOLS.has(name));
}

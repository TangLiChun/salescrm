export let detailLeadIndex = null;

export let allRows = [];
export let csvContent = "";
export let contacts = [];
export let contactsPage = 1;
export let contactsPages = 1;
export let contactsTotal = 0;
export let contactsPageSize = 50;
export const selectedContactIds = new Set();
export let editingContactId = null;
export let notesContactId = null;

export const FOLLOW_UP_STATUS_KEYS = ["new", "contacted", "replied", "invalid", "interested"];
export let schedules = [];
export let scheduleRuns = {};
export let schedulerStatus = null;
export let schedulesRefreshTimer = null;
export let aiLeads = [];
export const CHANNEL_DEFS = [
  { key: "peeringdb", nameKey: "channel.peeringdb" },
  { key: "shodan", nameKey: "channel.shodan" },
  { key: "web_search", nameKey: "channel.webSearch" },
  { key: "web_regex", nameKey: "channel.webRegex" },
  { key: "linkedin", nameKey: "channel.linkedin" },
  { key: "x", nameKey: "channel.x" },
  { key: "facebook", nameKey: "channel.facebook" },
  { key: "llm_extract", nameKey: "channel.llmExtract" },
  { key: "arin", nameKey: "channel.arin" },
  { key: "scoring", nameKey: "channel.scoring" },
];
export let channelState = {};
export let discoverController = null;
export let lastDiscoverQuery = "";
export let llmConfigured = false;
export let currentUserId = null;
export const PI_CHAT_STORAGE_VERSION = "v1";
export const PI_THREADS_STORAGE_VERSION = "v2";
export const PI_CHAT_MAX_STORED = 800;
export const PI_THREADS_MAX = 30;
export let piThreads = [];
export let activePiThreadId = null;
export let piChatHistory = [];
export let piChatController = null;
export let piChatBusy = false;
export const PI_LEAD_STREAM_TOOLS = new Set(["discover_leads", "enrich_contact"]);
export const PI_CHANNEL_ICON = { idle: "·", active: "◐", done: "✓", failed: "×" };
export const PI_SOURCE_CHANNEL_MAP = {
  peeringdb: "peeringdb",
  shodan: "shodan",
  web_search: "web_search",
  web_regex: "web_regex",
  llm_extract: "llm_extract",
  linkedin: "linkedin",
  x: "x",
  facebook: "facebook",
};
export let emailTemplates = [];
export let editingTemplateId = null;
export let contactSearchTimer = null;

export let asnParseTimer = null;

export const SETTINGS_FORM_CATS = new Set(["account", "ai", "import", "automation"]);
export let activeSettingsCat = "account";


export const state: AnyRecord = {
  detailLeadIndex: null,
  allRows: [],
  csvContent: "",
  contacts: [],
  contactsPage: 1,
  contactsPages: 1,
  contactsTotal: 0,
  contactsPageSize: 50,
  selectedContactIds: new Set(),
  editingContactId: null,
  notesContactId: null,
  contactViewMode: "list",
  contactOrganizations: [],
  schedules: [],
  scheduleRuns: {},
  schedulerStatus: null,
  schedulesRefreshTimer: null,
  aiLeads: [],
  leadReviews: [],
  selectedLeadReviewIds: new Set(),
  channelState: {},
  discoverController: null,
  lastDiscoverQuery: "",
  llmConfigured: false,
  currentUserId: null,
  piThreads: [],
  activePiThreadId: null,
  piChatHistory: [],
  piContextStats: null,
  piChatController: null,
  piChatBusy: false,
  piBackgroundJobId: null,
  piBackgroundRenderedEvents: 0,
  emailTemplates: [],
  editingTemplateId: null,
  contactSearchTimer: null,
  asnParseTimer: null,
  activeSettingsCat: "account",
};

export const FOLLOW_UP_STATUS_KEYS = ["new", "contacted", "replied", "invalid", "interested"];

export const CHANNEL_DEFS: AnyRecord[] = [
  { key: "peeringdb", nameKey: "channel.peeringdb" },
  { key: "shodan", nameKey: "channel.shodan" },
  { key: "web_search", nameKey: "channel.webSearch" },
  { key: "web_unlocker", nameKey: "channel.webUnlocker" },
  { key: "lowendtalk", nameKey: "channel.lowendtalk" },
  { key: "webhostingtalk", nameKey: "channel.webhostingtalk" },
  { key: "web_regex", nameKey: "channel.webRegex" },
  { key: "linkedin", nameKey: "channel.linkedin" },
  { key: "x", nameKey: "channel.x" },
  { key: "facebook", nameKey: "channel.facebook" },
  { key: "llm_extract", nameKey: "channel.llmExtract" },
  { key: "arin", nameKey: "channel.arin" },
  { key: "scoring", nameKey: "channel.scoring" },
];

export const PI_CHAT_STORAGE_VERSION = "v1";
export const PI_THREADS_STORAGE_VERSION = "v2";
export const PI_CHAT_MAX_STORED = 800;
export const PI_THREADS_MAX = 30;
export const PI_LEAD_STREAM_TOOLS = new Set(["discover_leads", "enrich_contact"]);
export const PI_CHANNEL_ICON = { idle: "·", active: "◐", done: "✓", failed: "×" };
export const PI_SOURCE_CHANNEL_MAP = {
  peeringdb: "peeringdb",
  shodan: "shodan",
  web_search: "web_search",
  web_unlocker: "web_unlocker",
  lowendtalk: "lowendtalk",
  webhostingtalk: "webhostingtalk",
  web_regex: "web_regex",
  llm_extract: "llm_extract",
  linkedin: "linkedin",
  x: "x",
  facebook: "facebook",
};

export const SETTINGS_FORM_CATS = new Set(["account", "ai", "import", "automation"]);

import { t } from "../../i18n.js";
import * as dom from "../core/dom.js";
import * as state from "../core/state.js";
import { activeSettingsCat, SETTINGS_FORM_CATS } from "../core/state.js";
import { api, setInputValue } from "../core/utils.js";
import { loadLlmStatus } from "./leads.js";

const { settingsView, pageTitle, settingsStatusEl } = dom;

export const SETTINGS_CAT_TITLE_KEYS = {
  account: "settings.cat.account",
  ai: "settings.cat.ai",
  import: "settings.cat.import",
  automation: "settings.cat.automation",
  templates: "settings.cat.templates",
  backup: "settings.cat.backup",
};

export function switchSettingsCat(cat) {
  state.activeSettingsCat = cat;
  document.querySelectorAll(".settings-rail-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.settingsCat === cat);
  });
  document.querySelectorAll(".settings-pane").forEach((pane) => {
    pane.classList.toggle("hidden", pane.dataset.settingsPane !== cat);
  });
  const footer = document.getElementById("settings-footer");
  footer.classList.toggle("hidden", !SETTINGS_FORM_CATS.has(cat));
  if (!settingsView.classList.contains("hidden")) {
    pageTitle.textContent = t(SETTINGS_CAT_TITLE_KEYS[cat] || "page.settings.title");
  }
}

export async function regenerateAgentToken() {
  const data = await api("/api/settings/agent-token/regenerate", { method: "POST" });
  const el = document.getElementById("setting-agent-api-token");
  el.value = data.agent_api_token;
  el.dataset.revealed = "1";
  document.getElementById("agent-token-status").textContent = t("msg.tokenRegenerated");
}

export async function copyAgentToken() {
  const el = document.getElementById("setting-agent-api-token");
  const value = el.value.trim();
  if (!value) {
    alert(t("msg.generateTokenFirst"));
    return;
  }
  await navigator.clipboard.writeText(value);
  document.getElementById("agent-token-status").textContent = t("msg.tokenCopied");
}

export async function loadSettingsForm() {
  const data = await api("/api/settings");
  setInputValue("setting-default-admin-user", data.default_admin_user);
  setInputValue("setting-llm-base-url", data.llm_base_url);
  setInputValue("setting-llm-model", data.llm_model);
  setInputValue("setting-zhipu-search-engine", data.zhipu_search_engine || "search_pro");
  setInputValue("setting-brightdata-serp-zone", data.brightdata_serp_zone || "");
  setInputValue("setting-brightdata-serp-format", data.brightdata_serp_data_format || "auto");
  setInputValue("setting-brightdata-linkedin-dataset", data.brightdata_linkedin_dataset_id || "");
  document.getElementById("setting-brightdata-linkedin-enabled").checked =
    (data.brightdata_linkedin_enabled || "0") === "1";
  setInputValue("setting-brightdata-x-dataset", data.brightdata_x_dataset_id || "");
  document.getElementById("setting-brightdata-x-enabled").checked =
    (data.brightdata_x_enabled || "0") === "1";
  setInputValue("setting-brightdata-facebook-dataset", data.brightdata_facebook_dataset_id || "");
  document.getElementById("setting-brightdata-facebook-enabled").checked =
    (data.brightdata_facebook_enabled || "0") === "1";
  document.getElementById("setting-shodan-enabled").checked = (data.shodan_enabled || "0") === "1";
  setInputValue("setting-scheduler-poll-seconds", data.scheduler_poll_seconds);
  document.getElementById("setting-scheduler-enabled").checked = data.scheduler_enabled === "1";

  const agentTokenEl = document.getElementById("setting-agent-api-token");
  if (agentTokenEl && !agentTokenEl.dataset.revealed) {
    agentTokenEl.value = "";
    agentTokenEl.placeholder = data.agent_api_token_configured
      ? t("msg.agentTokenConfigured", { token: data.agent_api_token })
      : t("settings.agentTokenPlaceholder");
  }

  const secretFields = [
    ["setting-default-admin-password", data.default_admin_password, data.default_admin_password_configured],
    ["setting-session-secret", data.session_secret, data.session_secret_configured],
    ["setting-llm-api-key", data.llm_api_key, data.llm_api_key_configured],
    ["setting-tavily-api-key", data.tavily_api_key, data.tavily_api_key_configured],
    ["setting-brightdata-api-key", data.brightdata_api_key, data.brightdata_api_key_configured],
    ["setting-serpapi-key", data.serpapi_key, data.serpapi_key_configured],
    ["setting-brave-search-key", data.brave_search_key, data.brave_search_key_configured],
    ["setting-zhipu-api-key", data.zhipu_api_key, data.zhipu_api_key_configured],
    ["setting-shodan-api-key", data.shodan_api_key, data.shodan_api_key_configured],
  ];
  for (const [id, masked, configured] of secretFields) {
    const el = document.getElementById(id);
    el.value = "";
    el.placeholder = configured ? t("msg.apiKeyConfigured", { masked }) : t("msg.apiKeyNotConfigured");
  }
  settingsStatusEl.textContent = "";
}

export async function saveSettings(event) {
  event.preventDefault();
  const payload = {
    default_admin_user: document.getElementById("setting-default-admin-user").value.trim(),
    llm_base_url: document.getElementById("setting-llm-base-url").value.trim(),
    llm_model: document.getElementById("setting-llm-model").value.trim(),
    zhipu_search_engine: document.getElementById("setting-zhipu-search-engine").value.trim(),
    brightdata_serp_zone: document.getElementById("setting-brightdata-serp-zone").value.trim(),
    brightdata_serp_data_format: document.getElementById("setting-brightdata-serp-format").value.trim(),
    brightdata_linkedin_dataset_id: document.getElementById("setting-brightdata-linkedin-dataset").value.trim(),
    brightdata_linkedin_enabled: document.getElementById("setting-brightdata-linkedin-enabled").checked
      ? "1"
      : "0",
    brightdata_x_dataset_id: document.getElementById("setting-brightdata-x-dataset").value.trim(),
    brightdata_x_enabled: document.getElementById("setting-brightdata-x-enabled").checked ? "1" : "0",
    brightdata_facebook_dataset_id: document.getElementById("setting-brightdata-facebook-dataset").value.trim(),
    brightdata_facebook_enabled: document.getElementById("setting-brightdata-facebook-enabled").checked ? "1" : "0",
    shodan_enabled: document.getElementById("setting-shodan-enabled").checked ? "1" : "0",
    scheduler_enabled: document.getElementById("setting-scheduler-enabled").checked ? "1" : "0",
    scheduler_poll_seconds: document.getElementById("setting-scheduler-poll-seconds").value.trim(),
  };

  const secrets = [
    ["default_admin_password", "setting-default-admin-password"],
    ["session_secret", "setting-session-secret"],
    ["llm_api_key", "setting-llm-api-key"],
    ["tavily_api_key", "setting-tavily-api-key"],
    ["brightdata_api_key", "setting-brightdata-api-key"],
    ["serpapi_key", "setting-serpapi-key"],
    ["brave_search_key", "setting-brave-search-key"],
    ["zhipu_api_key", "setting-zhipu-api-key"],
    ["shodan_api_key", "setting-shodan-api-key"],
  ];
  for (const [key, id] of secrets) {
    const value = document.getElementById(id).value.trim();
    if (value) payload[key] = value;
  }

  await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
  settingsStatusEl.textContent = t("msg.settingsSaved");
  await loadLlmStatus();
  await loadSettingsForm();
}

export async function changePassword() {
  const current = document.getElementById("pwd-current").value;
  const newPwd = document.getElementById("pwd-new").value;
  const confirm = document.getElementById("pwd-confirm").value;
  const statusEl = document.getElementById("password-status");
  if (!current || !newPwd) {
    alert(t("msg.passwordFieldsRequired"));
    return;
  }
  if (newPwd !== confirm) {
    alert(t("msg.passwordMismatch"));
    return;
  }
  await api("/api/me/password", {
    method: "POST",
    body: JSON.stringify({ current_password: current, new_password: newPwd }),
  });
  document.getElementById("pwd-current").value = "";
  document.getElementById("pwd-new").value = "";
  document.getElementById("pwd-confirm").value = "";
  statusEl.textContent = t("msg.passwordUpdated");
}

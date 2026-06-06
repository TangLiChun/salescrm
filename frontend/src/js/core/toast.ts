import { t } from "../../i18n.js";
import * as dom from "./dom.js";

const { toastStackEl } = dom;

export function showToast(message: any, options: AnyRecord = {}) {
  const {
    type = "info",
    duration = 6000,
    actionLabel = null,
    onAction = null,
  } = options;
  const text = String(message || "").trim();
  if (!text) return;
  if (!toastStackEl) {
    window.alert(text);
    return;
  }

  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  const msgEl = document.createElement("span");
  msgEl.className = "toast-message";
  msgEl.textContent = text;
  el.appendChild(msgEl);

  let timerId: ReturnType<typeof setTimeout> | null = null;
  const dismiss = () => {
    if (timerId) clearTimeout(timerId);
    el.classList.add("toast-out");
    setTimeout(() => el.remove(), 180);
  };

  if (actionLabel && typeof onAction === "function") {
    const actionBtn = document.createElement("button");
    actionBtn.type = "button";
    actionBtn.className = "toast-action";
    actionBtn.textContent = actionLabel;
    actionBtn.addEventListener("click", () => {
      onAction();
      dismiss();
    });
    el.appendChild(actionBtn);
  }

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "toast-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
  closeBtn.textContent = "×";
  closeBtn.addEventListener("click", dismiss);
  el.appendChild(closeBtn);

  toastStackEl.appendChild(el);
  if (duration > 0) {
    timerId = setTimeout(dismiss, duration);
  }
}

export function notifySuccess(message: any, options: AnyRecord = {}) {
  showToast(message, { type: "success", ...options });
}

export function notifyError(message: any, options: AnyRecord = {}) {
  showToast(message, { type: "error", duration: 8000, ...options });
}

export function notifyInfo(message: any, options: AnyRecord = {}) {
  showToast(message, { type: "info", ...options });
}

export function jobTypeLabel(jobType: string) {
  const key = `jobs.type.${jobType}`;
  const label = t(key);
  return label !== key ? label : jobType;
}

export function jobStatusLabel(status: string) {
  const key = `jobs.status.${status}`;
  const label = t(key);
  return label !== key ? label : status;
}

export function formatJobTime(value: any) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return "";
  }
}

import { t } from "../../i18n.js";
export async function api(url, options = {}) {
    const { redirectOn401 = true, ...fetchOptions } = options;
    const response = await fetch(url, {
        credentials: "same-origin",
        ...fetchOptions,
        headers: {
            "Content-Type": "application/json",
            ...(fetchOptions.headers || {}),
        },
    });
    if (response.status === 401) {
        if (redirectOn401) {
            window.location.href = "/login";
        }
        throw new Error(t("msg.loginRequired"));
    }
    if (!response.ok) {
        let detail = t("msg.requestFailed");
        try {
            const error = await response.json();
            detail = formatApiDetail(error.detail) || detail;
        }
        catch {
            // ignore
        }
        throw new Error(detail);
    }
    if (response.status === 204)
        return null;
    return response.json();
}
export function formatApiDetail(detail) {
    if (detail == null)
        return "";
    if (typeof detail === "string")
        return detail;
    if (Array.isArray(detail)) {
        return detail
            .map((item) => {
            if (typeof item === "string")
                return item;
            if (item?.msg)
                return item.msg;
            return JSON.stringify(item);
        })
            .join("; ");
    }
    if (typeof detail === "object") {
        return detail.message || detail.msg || JSON.stringify(detail);
    }
    return String(detail);
}
export function errorMessage(error, fallback) {
    if (!error)
        return fallback;
    if (typeof error === "string")
        return error;
    if (error.message)
        return error.message;
    return fallback;
}
export function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}
export function formatTime(value) {
    if (!value)
        return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime()))
        return value;
    return date.toLocaleString("zh-CN");
}
export function rowsToCsv(rows) {
    const headers = ["asn", "org", "roles", "name", "email", "handle", "rir", "error"];
    const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    const lines = [headers.join(",")];
    for (const row of rows) {
        lines.push([
            row.asn,
            row.org,
            row.roles.join(","),
            row.name,
            row.email,
            row.handle,
            row.rir,
            row.error,
        ]
            .map(escape)
            .join(","));
    }
    return lines.join("\n");
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
    if (!row || typeof row !== "object")
        return row;
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
        if (source === "linkedin" && !normalized.linkedin)
            normalized.linkedin = profileUrl;
        if (source === "x" && !normalized.x)
            normalized.x = profileUrl;
        if (source === "facebook" && !normalized.facebook)
            normalized.facebook = profileUrl;
    }
    return normalized;
}
export function normalizeImportRows(rows) {
    return (rows || []).map((row) => normalizeImportRow(row));
}
export function setInputValue(id, value) {
    const el = document.getElementById(id);
    if (el)
        el.value = value ?? "";
}

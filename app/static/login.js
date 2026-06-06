import { initI18n, t } from "./i18n.js";
const form = document.getElementById("login-form");
const errorEl = document.getElementById("login-error");
const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
initI18n();
form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.classList.add("hidden");
    try {
        const response = await fetch("/api/login", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: usernameInput.value.trim(),
                password: passwordInput.value,
            }),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || t("login.failed"));
        }
        window.location.href = "/";
    }
    catch (error) {
        errorEl.textContent = error instanceof Error ? error.message : t("login.failed");
        errorEl.classList.remove("hidden");
    }
});

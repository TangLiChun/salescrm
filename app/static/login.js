const form = document.getElementById("login-form");
const errorEl = document.getElementById("login-error");
const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const defaultUserEl = document.getElementById("default-user");
const defaultPassEl = document.getElementById("default-pass");

async function loadDefaults() {
  try {
    const response = await fetch("/api/config");
    if (!response.ok) return;
    const config = await response.json();
    defaultUserEl.textContent = config.default_username;
    defaultPassEl.textContent = config.default_password_hint;
    if (!usernameInput.value) usernameInput.value = config.default_username;
    if (!passwordInput.value) passwordInput.value = config.default_password_hint;
  } catch {
    // keep static defaults
  }
}

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
  } catch (error) {
    errorEl.textContent = error.message || t("login.failed");
    errorEl.classList.remove("hidden");
  }
});

loadDefaults();

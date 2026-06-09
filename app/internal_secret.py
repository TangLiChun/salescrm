"""Validation for the PI internal API shared secret.

The internal routes (/api/internal/pi/*) live on the same public port as the
rest of the app, so a guessable secret is an authentication bypass: anyone who
sends the default header value can run tools as any user_id. A secret that is
missing, a known placeholder, or too short is treated as "not configured" —
the internal API stays disabled and Pi falls back to the in-process loop.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

MIN_INTERNAL_SECRET_LENGTH = 16

WEAK_INTERNAL_SECRETS = {
    "change-me-in-production",
    "change-me",
    "changeme",
    "dev-secret",
    "secret",
    "password",
    "internal-secret",
    "pi-internal-secret",
    "salescrm",
    "123456",
    "test",
}


def raw_internal_secret() -> str:
    return os.environ.get("PI_INTERNAL_SECRET", "").strip()


def internal_secret_problem(secret: str | None = None) -> str | None:
    """Return why the secret is unusable, or None if it is acceptable."""
    value = raw_internal_secret() if secret is None else (secret or "").strip()
    if not value:
        return "未设置 PI_INTERNAL_SECRET"
    if value.lower() in WEAK_INTERNAL_SECRETS:
        return "PI_INTERNAL_SECRET 是已知占位符/弱口令"
    if len(value) < MIN_INTERNAL_SECRET_LENGTH:
        return f"PI_INTERNAL_SECRET 过短（至少 {MIN_INTERNAL_SECRET_LENGTH} 字符）"
    return None


def usable_internal_secret() -> str | None:
    """The configured secret, or None when missing/weak (internal API disabled)."""
    value = raw_internal_secret()
    return None if internal_secret_problem(value) else value

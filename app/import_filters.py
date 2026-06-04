from __future__ import annotations

from fnmatch import fnmatch

from app.settings_store import get_setting


def parse_patterns(text: str) -> list[str]:
    patterns: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def email_matches_pattern(email: str, pattern: str) -> bool:
    email = (email or "").strip().lower()
    pattern = (pattern or "").strip().lower()
    if not email or not pattern:
        return False

    if pattern.startswith("@"):
        pattern = pattern[1:]

    if "*" in pattern or "?" in pattern or "@" in pattern:
        return fnmatch(email, pattern)

    domain = email.rsplit("@", 1)[-1]
    return domain == pattern or domain.endswith(f".{pattern}")


def is_email_allowed(
    email: str,
    *,
    blocklist: list[str] | None = None,
    allowlist: list[str] | None = None,
) -> bool:
    if allowlist:
        if not any(email_matches_pattern(email, pattern) for pattern in allowlist):
            return False
    if blocklist:
        if any(email_matches_pattern(email, pattern) for pattern in blocklist):
            return False
    return True


def email_allowed_for_import(email: str) -> bool:
    blocklist = parse_patterns(get_setting("import_blocklist", ""))
    allowlist = parse_patterns(get_setting("import_allowlist", ""))
    return is_email_allowed(email, blocklist=blocklist, allowlist=allowlist)

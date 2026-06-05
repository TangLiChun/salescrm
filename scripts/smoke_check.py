#!/usr/bin/env python3
"""Post-deploy smoke check — run inside the container via check.sh / deploy.sh."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# docker exec python scripts/smoke_check.py puts scripts/ on sys.path, not /app
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.auth import authenticate_user
from app.database import (
    check_db,
    check_schema,
    get_contact_stats,
    list_email_templates,
    list_scheduled_jobs,
)


def main() -> int:
    errors: list[str] = []

    if not check_db():
        errors.append("database connection failed")
    if not check_schema():
        errors.append("database schema incomplete (missing required tables)")

    username = os.environ.get("SMOKE_USER", "admin")
    password = os.environ.get("SMOKE_PASSWORD", "admin123")
    user = authenticate_user(username, password)

    if not user:
        print(
            "WARN: skip API smoke — cannot log in as "
            f"{username!r} (password may have been changed)",
            file=sys.stderr,
        )
    else:
        checks = (
            ("email_templates", lambda: list_email_templates(user["id"])),
            ("schedules", lambda: list_scheduled_jobs(user["id"])),
            ("stats", lambda: get_contact_stats(user["id"])),
        )
        for name, fn in checks:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — smoke test should report any failure
                errors.append(f"{name}: {exc}")

    if errors:
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

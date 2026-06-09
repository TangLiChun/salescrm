from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.database import get_user_by_id, get_user_by_username
from app.security import verify_password
from app.settings_store import get_setting

SESSION_USER_KEY = "user_id"


def authenticate_user(username: str, password: str) -> dict | None:
    row = get_user_by_username(username)
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"]}


def get_current_user(request: Request) -> dict:
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")

    user = get_user_by_id(user_id)
    if not user:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录"
        )

    return {"id": user["id"], "username": user["username"]}


# Generated once per process: used only when the settings table has not been
# seeded yet. A random ephemeral secret (sessions reset on restart) is strictly
# safer than a publicly-known constant, which would make session cookies
# forgeable.
_EPHEMERAL_SESSION_SECRET = secrets.token_hex(32)


def session_secret() -> str:
    value = get_setting("session_secret")
    return value or _EPHEMERAL_SESSION_SECRET


CurrentUser = Annotated[dict, Depends(get_current_user)]

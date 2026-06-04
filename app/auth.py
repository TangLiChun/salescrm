from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.database import get_user_by_id, get_user_by_username
from app.security import verify_password

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")

    return {"id": user["id"], "username": user["username"]}


def session_secret() -> str:
    return os.getenv("SESSION_SECRET", "salescrm-dev-secret-change-me")


CurrentUser = Annotated[dict, Depends(get_current_user)]

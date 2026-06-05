from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.database import get_agent_owner_user_id, get_user_by_id
from app.settings_store import get_agent_api_token


def _extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def verify_agent_token(token: str) -> bool:
    expected = get_agent_api_token()
    if not expected or not token:
        return False
    return secrets.compare_digest(token, expected)


def get_agent_user(request: Request) -> dict:
    token = _extract_bearer_token(request)
    if not verify_agent_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Agent API Token",
        )

    user_id = get_agent_owner_user_id()
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未找到 Agent 绑定用户",
        )

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent 绑定用户不存在",
        )

    return {"id": user["id"], "username": user["username"]}


AgentUser = Annotated[dict, Depends(get_agent_user)]

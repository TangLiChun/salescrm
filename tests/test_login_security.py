"""Login brute-force limiting, session fixation reset, default-password flag."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import app.auth as auth
import app.database as database
import app.settings_store as settings_store
from app.rate_limit import SlidingWindowLimiter

# app.main 在 import 时初始化 DB 与会话密钥——与 test_pi_stream_route 相同的打桩方式。
database.init_db = lambda: None
settings_store.get_setting = lambda key, default="": default
auth.session_secret = lambda: "test-secret"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeClient:
    host = "203.0.113.9"


class FakeRequest:
    def __init__(self) -> None:
        self.session: dict = {"stale": "attacker-data"}
        self.client = FakeClient()


# ── SlidingWindowLimiter 单元 ──────────────────────────────────────────


def test_limiter_blocks_after_max_failures_and_recovers():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(max_failures=3, window_seconds=60, clock=clock)

    for _ in range(3):
        assert limiter.retry_after("k") == 0
        limiter.record_failure("k")

    blocked = limiter.retry_after("k")
    assert blocked > 0

    clock.now += 61
    assert limiter.retry_after("k") == 0


def test_limiter_reset_clears_failures():
    limiter = SlidingWindowLimiter(max_failures=2, window_seconds=60, clock=FakeClock())
    limiter.record_failure("k")
    limiter.record_failure("k")
    assert limiter.retry_after("k") > 0
    limiter.reset("k")
    assert limiter.retry_after("k") == 0


def test_limiter_keys_are_independent():
    limiter = SlidingWindowLimiter(max_failures=1, window_seconds=60, clock=FakeClock())
    limiter.record_failure("a")
    assert limiter.retry_after("a") > 0
    assert limiter.retry_after("b") == 0


def test_limiter_key_cap_does_not_evict_active_counters():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(max_failures=1, window_seconds=60, clock=clock, max_keys=2)
    limiter.record_failure("active1")
    limiter.record_failure("active2")
    limiter.record_failure("overflow")  # 容量已满且无过期桶 → 拒绝增长
    assert limiter.retry_after("active1") > 0
    assert limiter.retry_after("overflow") == 0


# ── 登录路由 ──────────────────────────────────────────────────────────


@pytest.fixture()
def login_env(monkeypatch):
    from app import main

    limiter = SlidingWindowLimiter(max_failures=3, window_seconds=60, clock=FakeClock())
    monkeypatch.setattr(main, "login_limiter", limiter)
    monkeypatch.setattr(main, "get_setting", lambda key, default="": "admin123")
    return main, limiter


def test_login_rate_limited_after_failures(login_env, monkeypatch):
    main, _ = login_env
    monkeypatch.setattr(main, "authenticate_user", lambda u, p: None)

    body = main.LoginRequest(username="admin", password="wrong")
    for _ in range(3):
        with pytest.raises(HTTPException) as exc:
            main.login(body, FakeRequest())
        assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        main.login(body, FakeRequest())
    assert exc.value.status_code == 429
    assert "Retry-After" in (exc.value.headers or {})


def test_login_success_resets_limiter_and_session(login_env, monkeypatch):
    main, limiter = login_env
    attempts = {"n": 0}

    def auth(username, password):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return None
        return {"id": 1, "username": "admin"}

    monkeypatch.setattr(main, "authenticate_user", auth)

    body = main.LoginRequest(username="admin", password="pw-not-default")
    for _ in range(2):
        with pytest.raises(HTTPException):
            main.login(body, FakeRequest())

    request = FakeRequest()
    result = main.login(body, request)
    assert result["id"] == 1
    # 会话固定防护：登录前的 session 内容必须被清掉
    assert "stale" not in request.session
    assert request.session["user_id"] == 1
    # 成功后限速计数清零
    assert limiter.retry_after(f"{FakeClient.host}:admin") == 0


def test_login_with_default_password_flags_must_change(login_env, monkeypatch):
    main, _ = login_env
    monkeypatch.setattr(main, "authenticate_user", lambda u, p: {"id": 1, "username": "admin"})

    result = main.login(main.LoginRequest(username="admin", password="admin123"), FakeRequest())
    assert result.get("must_change_password") is True

    result = main.login(main.LoginRequest(username="admin", password="changed-pw"), FakeRequest())
    assert "must_change_password" not in result

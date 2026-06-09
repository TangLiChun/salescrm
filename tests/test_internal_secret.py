"""PI internal API secret hardening.

The internal routes share the public port, so weak/placeholder secrets must be
treated as "not configured" (503) instead of being accepted.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.internal_secret import (
    MIN_INTERNAL_SECRET_LENGTH,
    internal_secret_problem,
    usable_internal_secret,
)


def test_missing_secret_is_a_problem(monkeypatch):
    monkeypatch.delenv("PI_INTERNAL_SECRET", raising=False)
    assert internal_secret_problem() is not None
    assert usable_internal_secret() is None


@pytest.mark.parametrize(
    "weak",
    [
        "change-me-in-production",
        "CHANGE-ME-IN-PRODUCTION",
        "dev-secret",
        "secret",
        "short-1234",  # < 16 chars
    ],
)
def test_weak_or_short_secrets_rejected(monkeypatch, weak):
    monkeypatch.setenv("PI_INTERNAL_SECRET", weak)
    assert internal_secret_problem() is not None
    assert usable_internal_secret() is None


def test_strong_secret_accepted(monkeypatch):
    strong = "a" * MIN_INTERNAL_SECRET_LENGTH
    monkeypatch.setenv("PI_INTERNAL_SECRET", strong)
    assert internal_secret_problem() is None
    assert usable_internal_secret() == strong


class _FakeRequest:
    def __init__(self, secret: str | None):
        self.headers = {"X-Internal-Secret": secret} if secret is not None else {}


def test_internal_route_returns_503_for_weak_secret(monkeypatch):
    from app.pi_internal_routes import _verify_internal

    monkeypatch.setenv("PI_INTERNAL_SECRET", "change-me-in-production")
    with pytest.raises(HTTPException) as exc:
        _verify_internal(_FakeRequest("change-me-in-production"))
    assert exc.value.status_code == 503


def test_internal_route_rejects_wrong_header(monkeypatch):
    from app.pi_internal_routes import _verify_internal

    monkeypatch.setenv("PI_INTERNAL_SECRET", "x" * 32)
    with pytest.raises(HTTPException) as exc:
        _verify_internal(_FakeRequest("wrong-value-here-123"))
    assert exc.value.status_code == 403
    # 正确密钥放行
    _verify_internal(_FakeRequest("x" * 32))


def test_proxy_url_disabled_when_secret_weak(monkeypatch):
    import app.pi_agent_proxy as proxy

    monkeypatch.setenv("PI_AGENT_SERVICE_URL", "http://pi-agent:8001")
    monkeypatch.setenv("PI_INTERNAL_SECRET", "change-me-in-production")
    monkeypatch.setattr(proxy, "_warned_secret_problem", False)
    assert proxy.pi_agent_service_url() == ""
    assert proxy.pi_internal_secret() == ""


def test_proxy_url_enabled_with_strong_secret(monkeypatch):
    import app.pi_agent_proxy as proxy

    monkeypatch.setenv("PI_AGENT_SERVICE_URL", "http://pi-agent:8001/")
    monkeypatch.setenv("PI_INTERNAL_SECRET", "y" * 32)
    assert proxy.pi_agent_service_url() == "http://pi-agent:8001"
    assert proxy.pi_internal_secret() == "y" * 32

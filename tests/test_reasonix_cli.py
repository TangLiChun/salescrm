import importlib.util
import io
import json
import pathlib
import urllib.error
from importlib.machinery import SourceFileLoader

import pytest

CLI_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "integrations" / "reasonix" / "bin" / "salescrm"
)


def _load_cli():
    loader = SourceFileLoader("salescrm_cli", str(CLI_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


cli = _load_cli()


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture(captured, payload=None):
    def _open(req):
        captured["req"] = req
        return FakeResp(payload if payload is not None else {"ok": True})

    return _open


def test_health_builds_authed_get(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    monkeypatch.setenv("SALESCRM_URL", "http://crm:9000")
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"ok": True}))

    assert cli.main(["health"]) == 0
    req = captured["req"]
    assert req.get_method() == "GET"
    assert req.full_url == "http://crm:9000/api/agent/health"
    assert req.get_header("Authorization") == "Bearer T"


def test_missing_token_errors(monkeypatch):
    monkeypatch.delenv("SALESCRM_TOKEN", raising=False)
    with pytest.raises(SystemExit) as ei:
        cli.main(["health"])
    assert "SALESCRM_TOKEN" in str(ei.value)


def test_http_error_surfaces_status_and_detail(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    body = io.BytesIO(json.dumps({"detail": "未配置 LLM API Key"}).encode())
    err = urllib.error.HTTPError("http://x/api/agent/health", 503, "Unavailable", {}, body)

    def boom(req):
        raise err

    monkeypatch.setattr(cli, "_open", boom)
    with pytest.raises(SystemExit) as ei:
        cli.main(["health"])
    assert "503" in str(ei.value) and "LLM" in str(ei.value)


def test_url_error_surfaces_connect_failure(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")

    def boom(req):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(cli, "_open", boom)
    with pytest.raises(SystemExit) as ei:
        cli.main(["health"])
    assert "无法连接" in str(ei.value)

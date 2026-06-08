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


def test_contacts_passes_query_params(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    monkeypatch.setenv("SALESCRM_URL", "http://crm:9000")
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"contacts": [], "total": 0}))

    cli.main(["contacts", "--status", "unsent", "--limit", "10", "--q", "isp"])
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(captured["req"].full_url)
    q = parse_qs(parsed.query)
    assert parsed.path == "/api/agent/contacts"
    assert q["status"] == ["unsent"] and q["limit"] == ["10"] and q["q"] == ["isp"]
    assert "follow_up_status" not in q


def test_import_leads_array_from_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    p = tmp_path / "rows.json"
    p.write_text(json.dumps([{"email": "a@b.com"}]), encoding="utf-8")
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"imported": 1}))

    cli.main(["import-leads", str(p), "--source", "scrape"])
    req = captured["req"]
    assert req.get_method() == "POST"
    assert req.full_url.endswith("/api/agent/leads/import")
    body = json.loads(req.data.decode())
    assert body["rows"] == [{"email": "a@b.com"}]
    assert body["source"] == "scrape"


def test_import_leads_rows_wrapper_from_stdin_default_source(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(json.dumps({"rows": [{"email": "x@y.com"}]})))
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"imported": 1}))

    cli.main(["import-leads", "-"])
    body = json.loads(captured["req"].data.decode())
    assert body["rows"] == [{"email": "x@y.com"}]
    assert body["source"] == "reasonix-agent"


def test_discover_builds_post_body(monkeypatch):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    captured = {}
    monkeypatch.setattr(cli, "_open", _capture(captured, {"imported": 0}))

    cli.main(["discover", "find US ISP peering", "--min-score", "70", "--auto-import"])
    req = captured["req"]
    assert req.full_url.endswith("/api/agent/leads/discover")
    body = json.loads(req.data.decode())
    assert body == {
        "query": "find US ISP peering",
        "min_score": 70,
        "delay": 0.5,
        "auto_import": True,
    }


def test_import_leads_missing_file_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    with pytest.raises(SystemExit) as ei:
        cli.main(["import-leads", str(tmp_path / "nope.json")])
    assert "错误" in str(ei.value)


def test_import_leads_bad_json_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("SALESCRM_TOKEN", "T")
    p = tmp_path / "bad.json"
    p.write_text("{bad", encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        cli.main(["import-leads", str(p)])
    assert "错误" in str(ei.value)

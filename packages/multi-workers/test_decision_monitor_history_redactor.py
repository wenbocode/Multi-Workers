"""T20 authorized startup snapshot: synthetic credentials, no decision transport."""
from __future__ import annotations

import dataclasses
import json
import socket

import pytest

import decision
import decision_backends
import decision_monitor
import decision_wire
import test_decision_dashboard_assets as assets
import test_decision_history_feedback as feedback
import test_decision_monitor as monitor

_isolated_environment = feedback._isolated_environment
CONFIG_SECRET = "fixture-startup-exact-config-credential"
AUTH_SECRET = "fixture-startup-exact-auth-credential"


@pytest.fixture(autouse=True)
def _fake_credentials_and_no_model(tmp_path, monkeypatch):
    auth = tmp_path / "fake-auth.json"
    auth.write_text(json.dumps({"timi": {"key": AUTH_SECRET}}), encoding="utf-8")
    monkeypatch.setattr(decision_backends, "_auth_json_path", lambda: auth)

    def no_model(*args, **kwargs):
        pytest.fail("startup and history must not call a model")

    monkeypatch.setattr(decision_backends.TimiDecisionsBackend, "decide", no_model)


def _ports():
    with socket.socket() as sock:
        sock.bind((decision_monitor.HOST, 0))
        port = sock.getsockname()[1]
    return (port, port)


def _config(root):
    path = root / ".mw" / "decide.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"enabled": False, "api_key": CONFIG_SECRET}), encoding="utf-8")
    return path


def test_default_startup_resolves_once_before_serving_and_history_stays_read_only(tmp_path, monkeypatch):
    root, record = feedback._record(tmp_path)
    config = _config(root)
    before = config.read_bytes()
    auth = decision_backends._auth_json_path()
    auth_before = auth.read_bytes()
    ledger = decision_wire.production_lifecycle_sink(root)
    ledger_before = ledger.read_bytes()
    reads = []
    original = decision.credential_snapshot

    def snapshot(*args, **kwargs):
        assert instance._server is None and instance.identity is None
        reads.append("startup")
        return original(*args, **kwargs)

    monkeypatch.setattr(decision, "credential_snapshot", snapshot)
    deps = decision_monitor.default_monitor_deps()
    instance = decision_monitor.MonitorInstance(root, deps=deps, port_range=_ports())
    assert reads == [] and deps.redactor is None
    try:
        instance.start()
        assert reads == ["startup"]
        assert instance.deps.redactor is not None
        assert instance.deps.playground is None and instance.deps._resolved_playgrounds == {}
        # Startup owns the frozen response snapshot, not a health/GET request.
        instance.start()
        token = monitor._page_token(instance)
        for _ in range(3):
            listing = assets._capture(instance, "/api/history", token)
            detail = assets._capture(instance, f"/api/history/{record.opaque_id}", token)
            assets._capture(instance, "/api/health", instance.control_token)
            assets._capture(instance, "/api/dps", token)
        assert listing["data"]["records"][0]["workbench"]["selection"] == "research"
        assert listing["data"]["redaction"]["enabled"] is True
        nodes = {n["id"]: n for n in detail["data"]["workbench"]["nodes"]}
        assert nodes["receipt"]["detail"]["consumed"]["answer"] == "research"
        assert nodes["receipt"]["detail"]["consumed"]["reason"] == "PM received the suggestion"
        assert nodes["action"]["detail"]["executed"][0]["result"] == "kept-type:research"
        assert reads == ["startup"] and instance.deps._resolved_playgrounds == {}
        assert config.read_bytes() == before and auth.read_bytes() == auth_before
        assert ledger.read_bytes() == ledger_before
    finally:
        instance.stop()


def test_default_startup_http_response_reaches_shipped_dom(tmp_path):
    root, record = feedback._record(tmp_path)
    _config(root)
    with monitor._running(root, deps=decision_monitor.default_monitor_deps(), port_range=_ports()) as instance:
        token = monitor._page_token(instance)
        listing = assets._capture(instance, "/api/history", token)
        detail = assets._capture(instance, f"/api/history/{record.opaque_id}", token)
    scenario = {
        "hash": "#boot=t20-startup",
        "bootstrap": {"status": 200, "body": feedback.ui._envelope({"page_token": "synthetic-page-token"})},
        "history": {"status": 200, "body": listing},
        "detailByOpaque": {record.opaque_id: {"status": 200, "body": detail}},
        "steps": [{"type": "click", "target": '[data-testid="record-dag-open"]'}] + [
            {"type": "click", "target": f'[data-testid="dag-node"][data-node-id="{node}"]', "snapshot": node}
            for node in ("receipt", "action", "decide")],
    }
    result = feedback.ui._run_dom(tmp_path, scenario)
    assert "research" in feedback.ui._snapshot(result, "boot")["rows"][0]
    receipt = feedback.ui._snapshot(result, "receipt")["nodeDetail"]
    assert "research" in receipt and "PM received the suggestion" in receipt
    assert "接收不代表采纳或处理完成" in receipt
    assert "explicit role retained" in feedback.ui._snapshot(result, "action")["nodeDetail"]
    assert "模型建议（不代表已采纳或执行）" in feedback.ui._snapshot(result, "decide")["nodeDetail"]
    assert result["storageWrites"] == []
    assert all(c["method"] == "GET" or c["url"] == "/api/bootstrap" for c in result["fetchCalls"])


def test_default_startup_known_set_redacts_config_and_fake_auth_values(tmp_path):
    root, record = feedback._record(tmp_path)
    _config(root)
    # Synthetic stored prose intentionally includes both credential sources.
    ledger = decision_wire.production_lifecycle_sink(root)
    ledger.write_bytes(ledger.read_bytes().replace(b"PM received the suggestion", (CONFIG_SECRET + " " + AUTH_SECRET).encode()))
    before = ledger.read_bytes()
    # Real response redactor includes both configured and legacy timi legs.
    with monitor._running(root, deps=decision_monitor.default_monitor_deps(), port_range=_ports()) as instance:
        assert instance.deps.redactor is not None
        redacted = instance.deps.redactor.redact(CONFIG_SECRET + " " + AUTH_SECRET).text
        assert CONFIG_SECRET not in redacted and AUTH_SECRET not in redacted
        assert "<redacted>" in redacted.lower()
        assert CONFIG_SECRET not in repr(instance.deps.redactor)
        token = monitor._page_token(instance)
        detail = assets._capture(instance, f"/api/history/{record.opaque_id}", token)
        rendered = json.dumps(detail)
        assert "research" in rendered
        assert CONFIG_SECRET not in rendered and AUTH_SECRET not in rendered
        assert detail["data"]["redaction"]["substitutions"] > 0
        assert ledger.read_bytes() == before


@pytest.mark.parametrize("failure", ["raise", "none", "discovery"])
def test_startup_redactor_failure_stays_closed_without_credential_retry(tmp_path, monkeypatch, failure):
    root, record = feedback._record(tmp_path)
    calls = []
    deps = decision_monitor.default_monitor_deps()
    if failure == "discovery":
        def broken_discovery(*args, **kwargs):
            calls.append("discovery")
            raise OSError(AUTH_SECRET)
        monkeypatch.setattr(decision_backends, "resolve_timi_api_key", broken_discovery)
    else:
        def broken_factory(path):
            calls.append("factory")
            if failure == "raise":
                raise RuntimeError(AUTH_SECRET)
            return None
        deps.redactor_factory = broken_factory
    with monitor._running(root, deps=deps, port_range=_ports()) as instance:
        assert len(calls) == 1, "failure must be handled once during startup, not on a GET"
        token = monitor._page_token(instance)
        for _ in range(3):
            listing = assets._capture(instance, "/api/history", token)
            detail = assets._capture(instance, f"/api/history/{record.opaque_id}", token)
            status, _, payload, _ = monitor._http(instance.port, "GET", "/api/test/history", token=token)
            assert status == 503 and payload["error"]["code"] == "playground-redactor-unavailable"
        assert len(calls) == 1
        assert listing["data"]["records"][0]["workbench"]["selection"] is None
        assert listing["data"]["redaction"]["enabled"] is False
        assert detail["data"]["redaction"]["omitted_fields"] > 0
        assert AUTH_SECRET not in json.dumps(detail) + json.dumps(payload)
        assert instance.deps._resolved_playgrounds == {}


def test_bare_dependencies_do_not_resolve_on_start_or_history(tmp_path):
    root, record = feedback._record(tmp_path)
    calls = []
    deps = decision_monitor.MonitorDeps(redactor_factory=lambda path: calls.append(path))
    with monitor._running(root, deps=deps, port_range=_ports()) as instance:
        token = monitor._page_token(instance)
        listing = assets._capture(instance, "/api/history", token)
        assert listing["data"]["records"][0]["workbench"]["selection"] is None
        assert calls == []


def test_explicit_redactor_wins_without_startup_discovery(tmp_path):
    root, _ = feedback._record(tmp_path)
    calls = []
    redactor = decision_wire.SubstringRedactor((AUTH_SECRET,))
    deps = dataclasses.replace(decision_monitor.default_monitor_deps(), redactor=redactor,
        redactor_factory=lambda path: calls.append(path))
    with monitor._running(root, deps=deps, port_range=_ports()) as instance:
        assert instance.deps.redactor is redactor and calls == []
        token = monitor._page_token(instance)
        assets._capture(instance, "/api/history", token)
        assert calls == []


def test_shared_dependency_template_does_not_mix_project_snapshots(tmp_path):
    first, _ = feedback._record(tmp_path / "first")
    second, _ = feedback._record(tmp_path / "second")
    template = decision_monitor.default_monitor_deps()
    calls = []
    def factory(root):
        calls.append(root)
        return decision_wire.SubstringRedactor((root.parent.name,))
    template.redactor_factory = factory
    with monitor._running(first, deps=template, port_range=_ports()) as one:
        with monitor._running(second, deps=template, port_range=_ports()) as two:
            assert calls == [first.resolve(), second.resolve()]
            assert one.deps.redactor is not two.deps.redactor
            assert template.redactor is None
            assert one.deps.redactor.redact(first.parent.name).hits == 1
            assert two.deps.redactor.redact(second.parent.name).hits == 1
            assert one.deps.redactor.redact(second.parent.name).hits == 0


def test_compatible_reuse_does_not_reload_startup_credentials(tmp_path):
    root, _ = feedback._record(tmp_path)
    _config(root)
    template = decision_monitor.default_monitor_deps()
    calls = []
    original = template.redactor_factory
    def factory(path):
        calls.append(path)
        return original(path)
    template.redactor_factory = factory
    instance = decision_monitor.ensure_instance(root, deps=template, port_range=_ports())
    try:
        assert len(calls) == 1
        attached = decision_monitor.ensure_instance(root, deps=template, port_range=_ports())
        assert isinstance(attached, decision_monitor.AttachedInstance)
        assert len(calls) == 1
    finally:
        instance.stop()


def test_playground_uses_same_snapshot_after_startup_without_resolving_credentials(tmp_path):
    root, _ = feedback._record(tmp_path)
    calls = []
    class Provider:
        def history(self):
            return {"records": [], "warning": AUTH_SECRET}
    deps = decision_monitor.default_monitor_deps()
    def factory(path):
        calls.append(path)
        return decision_wire.SubstringRedactor((AUTH_SECRET,))
    deps.redactor_factory = factory
    deps.playground = Provider()
    with monitor._running(root, deps=deps, port_range=_ports()) as instance:
        token = monitor._page_token(instance)
        for _ in range(3):
            data = assets._capture(instance, "/api/test/history", token)
            assert AUTH_SECRET not in json.dumps(data)
        assert len(calls) == 1

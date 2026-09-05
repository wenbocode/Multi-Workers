"""
test_common.py — mw_common unit tests (T-01/T-02).

All fixtures inject their own providers.json / credential files; nothing reads
the real user home or real env credentials (AC-009 hermeticity).
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
from mw_common import (
    archive_stale_entries,
    credential_env_names,
    credential_inject_env,
    describe_missing,
    load_providers,
    parse_workers_file,
    resolve_credential,
    route_for,
    route_precheck,
    serialize_entry,
    update_status,
)

_REPO_PROVIDERS = pathlib.Path(__file__).parent / "providers.json"


# ── Config loading ────────────────────────────────────────────────────────────

class TestLoadProviders:
    def test_shipped_schema_loads(self):
        config = load_providers(_REPO_PROVIDERS)
        assert set(config["credentials"]) == {"anthropic", "anthropic-auth", "deepseek", "timi"}
        assert set(config["providers"]) == {"claude", "claude-cli", "deepseek", "timi"}
        timi = config["providers"]["timi"]
        assert "port" not in timi
        assert timi["credential"] == "timi"

    def test_missing_file_falls_back_to_defaults(self, tmp_path):
        config = load_providers(tmp_path / "nope.json")
        assert config["providers"]["claude"]["port"] == 7001
        assert config["credentials"]["timi"]["sources"][0]["env"] == "TIMI_API_KEY"

    def test_invalid_json_falls_back_to_defaults(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        config = load_providers(bad)
        assert config["providers"]["claude-cli"]["port"] == 7003

    def test_legacy_flat_map_upgraded(self, tmp_path):
        legacy = tmp_path / "legacy.json"
        legacy.write_text(json.dumps({
            "claude": {"port": 7001, "base_url_env": "A", "api_key_env": "K"},
        }), encoding="utf-8")
        config = load_providers(legacy)
        assert config["providers"]["claude"]["credential"] == "claude-key"
        assert config["credentials"]["claude-key"]["sources"] == [{"env": "K"}]


# ── Credential resolution ─────────────────────────────────────────────────────

class TestResolveCredential:
    def test_env_source(self):
        cred = {"sources": [{"env": "X_KEY"}]}
        value, source = resolve_credential(cred, {"X_KEY": "v1"})
        assert value == "v1"
        assert source == {"kind": "env", "name": "X_KEY"}

    def test_env_missing_returns_none(self):
        value, source = resolve_credential({"sources": [{"env": "X_KEY"}]}, {})
        assert value is None
        assert source == {}

    def test_file_fallback_toml_dotted_field(self, tmp_path):
        cfg_file = tmp_path / "cred.toml"
        cfg_file.write_text('[auth]\napi_key = "file-key"\n', encoding="utf-8")
        cred = {"sources": [
            {"env": "X_KEY"},
            {"file": str(cfg_file), "format": "toml", "field": "auth.api_key"},
        ]}
        value, source = resolve_credential(cred, {})
        assert value == "file-key"
        assert source["kind"] == "file"
        assert source["field"] == "auth.api_key"

    def test_file_json_dotted_field(self, tmp_path):
        cfg_file = tmp_path / "cred.json"
        cfg_file.write_text(json.dumps({"auth": {"api_key": "json-key"}}), encoding="utf-8")
        cred = {"sources": [{"file": str(cfg_file), "format": "json", "field": "auth.api_key"}]}
        value, _ = resolve_credential(cred, {})
        assert value == "json-key"

    def test_file_plain_whole_content(self, tmp_path):
        cfg_file = tmp_path / "key.txt"
        cfg_file.write_text("plain-key\n", encoding="utf-8")
        cred = {"sources": [{"file": str(cfg_file), "format": "plain"}]}
        value, _ = resolve_credential(cred, {})
        assert value == "plain-key"

    def test_env_wins_over_file(self, tmp_path):
        cfg_file = tmp_path / "cred.toml"
        cfg_file.write_text('[auth]\napi_key = "file-key"\n', encoding="utf-8")
        cred = {"sources": [
            {"env": "X_KEY"},
            {"file": str(cfg_file), "format": "toml", "field": "auth.api_key"},
        ]}
        value, source = resolve_credential(cred, {"X_KEY": "env-key"})
        assert value == "env-key"
        assert source["kind"] == "env"

    def test_all_sources_missing(self, tmp_path):
        cred = {"sources": [
            {"env": "X_KEY"},
            {"file": str(tmp_path / "nope.toml"), "format": "toml", "field": "a.b"},
        ]}
        value, source = resolve_credential(cred, {})
        assert value is None and source == {}

    def test_missing_file_path_returns_none(self):
        cred = {"sources": [{"file": "~/definitely-not-a-real-file-xyz.toml", "format": "toml", "field": "a"}]}
        assert resolve_credential(cred, {})[0] is None

    def test_none_config(self):
        assert resolve_credential(None, {})[0] is None

    def test_home_expansion(self, tmp_path, monkeypatch):
        # A file source using ~ must expand against HOME/USERPROFILE.
        home = tmp_path / "home"
        home.mkdir()
        (home / "key.txt").write_text("home-key", encoding="utf-8")
        monkeypatch.setenv("USERPROFILE" if sys.platform == "win32" else "HOME", str(home))
        cred = {"sources": [{"file": "~/key.txt", "format": "plain"}]}
        assert resolve_credential(cred, {})[0] == "home-key"


class TestCredentialHelpers:
    def test_env_names(self):
        config = load_providers(_REPO_PROVIDERS)
        names = credential_env_names(config)
        assert {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "DEEPSEEK_API_KEY", "TIMI_API_KEY"} <= names

    def test_inject_env_first_declared(self):
        cred = {"sources": [{"env": "FIRST"}, {"env": "SECOND"}]}
        assert credential_inject_env(cred) == "FIRST"

    def test_inject_env_none(self):
        assert credential_inject_env(None) is None

    def test_describe_missing(self):
        cred = {"sources": [{"env": "A"}, {"file": "~/x.toml"}]}
        assert "env A unset" in describe_missing(cred)
        assert "file ~/x.toml unreadable" in describe_missing(cred)


# ── Route resolution ──────────────────────────────────────────────────────────

class TestRouteFor:
    def test_pi_empty_provider_defaults_to_claude(self):
        config = load_providers(_REPO_PROVIDERS)
        route = route_for(config, "pi", "")
        assert route["provider_key"] == "claude"
        assert route["port"] == 7001
        assert route["api_key_env"] == "ANTHROPIC_API_KEY"

    def test_pi_timi_direct(self):
        config = load_providers(_REPO_PROVIDERS)
        route = route_for(config, "pi", "timi")
        assert route["provider_key"] == "timi"
        assert route["api_key_env"] == "TIMI_API_KEY"

    def test_claude_defaults_to_claude_cli(self):
        config = load_providers(_REPO_PROVIDERS)
        route = route_for(config, "claude", "")
        assert route["provider_key"] == "claude-cli"
        assert route["port"] == 7003
        assert route["api_key_env"] == "ANTHROPIC_AUTH_TOKEN"

    def test_explicit_provider(self):
        config = load_providers(_REPO_PROVIDERS)
        route = route_for(config, "pi", "deepseek")
        assert route["provider_key"] == "deepseek"
        assert route["port"] == 7004


# ── Route precheck ────────────────────────────────────────────────────────────

class TestRoutePrecheck:
    def test_all_missing(self, tmp_path, monkeypatch):
        # Isolate HOME so the real ~/.pi/agent/auth.json never leaks in.
        empty_home = tmp_path / "empty-home"
        empty_home.mkdir()
        monkeypatch.setenv("USERPROFILE" if sys.platform == "win32" else "HOME", str(empty_home))
        config = load_providers(_REPO_PROVIDERS)
        monkeypatch.setattr(mw_common.shutil, "which", lambda name: None)
        result = route_precheck(config, {})
        assert result["all_missing"] is True
        routes = {r["route"]: r for r in result["routes"]}
        assert routes["claude-cli"]["missing"] == "env ANTHROPIC_AUTH_TOKEN unset"

    def test_partial_availability(self):
        config = load_providers(_REPO_PROVIDERS)
        result = route_precheck(config, {"TIMI_API_KEY": "k"})
        routes = {r["route"]: r for r in result["routes"]}
        assert routes["timi"]["available"] is True
        assert routes["timi"]["source"] == {"kind": "env", "name": "TIMI_API_KEY"}
        assert routes["claude"]["available"] is False
        assert result["all_missing"] is False

    def test_file_source_counts_as_available(self, tmp_path, monkeypatch):
        # Provide the exact file source declared for timi (pi's own auth.json)
        # under an isolated HOME.
        pi_dir = tmp_path / "home" / ".pi" / "agent"
        pi_dir.mkdir(parents=True)
        (pi_dir / "auth.json").write_text(
            json.dumps({"timi": {"type": "api_key", "key": "k"}}), encoding="utf-8"
        )
        monkeypatch.setenv("USERPROFILE" if sys.platform == "win32" else "HOME", str(tmp_path / "home"))
        monkeypatch.setattr(mw_common.shutil, "which", lambda name: None)
        config = load_providers(_REPO_PROVIDERS)
        result = route_precheck(config, {})
        routes = {r["route"]: r for r in result["routes"]}
        assert routes["timi"]["available"] is True
        assert routes["timi"]["source"]["kind"] == "file"
        assert result["all_missing"] is False

    def test_codex_native_via_path(self, monkeypatch):
        config = load_providers(_REPO_PROVIDERS)
        monkeypatch.setattr(mw_common.shutil, "which", lambda name: "/bin/codex" if name == "codex" else None)
        result = route_precheck(config, {})
        routes = {r["route"]: r for r in result["routes"]}
        assert routes["codex-native"]["available"] is True
        assert result["all_missing"] is False

    def test_one_route_per_provider(self):
        config = load_providers(_REPO_PROVIDERS)
        result = route_precheck(config, {})
        assert len(result["routes"]) == len(config["providers"]) + 1  # + codex-native

    def test_undeclared_credential(self, tmp_path):
        cfg = tmp_path / "p.json"
        cfg.write_text(json.dumps({
            "credentials": {},
            "providers": {"ghost": {"port": 1, "credential": "nope"}},
        }), encoding="utf-8")
        result = route_precheck(load_providers(cfg), {})
        routes = {r["route"]: r for r in result["routes"]}
        assert "not declared" in routes["ghost"]["missing"]


# ── File bus ──────────────────────────────────────────────────────────────────

def _make_project(tmp_path: pathlib.Path, rows: list[str]) -> pathlib.Path:
    agentic = tmp_path / ".agenticdoc"
    agentic.mkdir(exist_ok=True)
    (agentic / "_workers.parallel").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return tmp_path


class TestArchiveStaleEntries:
    def test_archives_missing_task_md(self, tmp_path):
        task = tmp_path / "t1" / "task.md"
        task.parent.mkdir()
        task.write_text("type: coding\nx", encoding="utf-8")
        proj = _make_project(tmp_path, [
            "t1 | pending | pi | timi | " + str(task).replace("|", "\\|") + " | a | b | m",
            "t2 | pending | pi | timi | " + str(tmp_path / "gone" / "task.md") + " | a | b | m",
        ])
        archived = archive_stale_entries(proj)
        assert archived == ["t2"]
        remaining = parse_workers_file(mw_common.workers_path(proj))
        assert [e["task_key"] for e in remaining] == ["t1"]
        stale_rows = mw_common.stale_path(proj).read_text(encoding="utf-8").splitlines()
        assert len(stale_rows) == 1
        assert stale_rows[0].startswith("t2 | pending")
        assert mw_common.STALE_REASON in stale_rows[0]
        assert " | " in stale_rows[0]  # archived_at + reason appended

    def test_running_entry_also_archived(self, tmp_path):
        proj = _make_project(tmp_path, [
            "t3 | running | claude |  | " + str(tmp_path / "gone" / "task.md") + " | a | b |",
        ])
        assert archive_stale_entries(proj) == ["t3"]

    def test_terminal_entry_not_archived(self, tmp_path):
        # done/failed rows are history: a missing task.md there is harmless and
        # must NOT be archived (would churn on every poll after task cleanup).
        proj = _make_project(tmp_path, [
            "t4 | done | pi | timi | " + str(tmp_path / "gone" / "task.md") + " | a | b |",
            "t5 | failed | pi |  | " + str(tmp_path / "gone" / "task.md") + " | a | b |",
        ])
        assert archive_stale_entries(proj) == []
        assert len(parse_workers_file(mw_common.workers_path(proj))) == 2

    def test_no_stale_is_noop(self, tmp_path):
        task = tmp_path / "t1" / "task.md"
        task.parent.mkdir()
        task.write_text("x", encoding="utf-8")
        proj = _make_project(tmp_path, [
            "t1 | done | pi | timi | " + str(task) + " | a | b |",
        ])
        before = (mw_common.workers_path(proj)).read_text(encoding="utf-8")
        assert archive_stale_entries(proj) == []
        assert (mw_common.workers_path(proj)).read_text(encoding="utf-8") == before
        assert not mw_common.stale_path(proj).exists()

    def test_missing_file_returns_empty(self, tmp_path):
        assert archive_stale_entries(tmp_path) == []

    def test_append_only_archive(self, tmp_path):
        # Two successive archives must append, never truncate.
        proj = _make_project(tmp_path, [
            "t1 | pending | pi |  | " + str(tmp_path / "g1" / "task.md") + " | a | b |",
        ])
        archive_stale_entries(proj)
        _make_project(tmp_path, [
            "t2 | pending | pi |  | " + str(tmp_path / "g2" / "task.md") + " | a | b |",
        ])
        archive_stale_entries(proj)
        rows = mw_common.stale_path(proj).read_text(encoding="utf-8").splitlines()
        assert len(rows) == 2


class TestUpdateStatus:
    def test_update_creates_dirs_and_preserves_model(self, tmp_path):
        task = tmp_path / "t1" / "task.md"
        task.parent.mkdir()
        task.write_text("x", encoding="utf-8")
        proj = _make_project(tmp_path, [
            "t1 | pending | pi | timi | " + str(task) + " | a | b | keep-me",
        ])
        update_status(proj, "t1", "done")
        entries = parse_workers_file(mw_common.workers_path(proj))
        assert entries[0]["status"] == "done"
        assert entries[0]["model"] == "keep-me"
        assert entries[0]["updated_at"] != "b"

    def test_update_on_missing_dir_creates_file(self, tmp_path):
        # No .agenticdoc pre-created: update_status must not crash (T-03 lesson).
        update_status(tmp_path, "ghost", "failed")
        assert mw_common.workers_path(tmp_path).exists()

    def test_serialize_round_trip(self):
        entry = {
            "task_key": "t1", "status": "done", "cli": "pi", "provider": "timi",
            "task_path": "/p/task.md", "dispatched_at": "a", "updated_at": "b", "model": "m1",
        }
        assert serialize_entry(entry).split(" | ") == ["t1", "done", "pi", "timi", "/p/task.md", "a", "b", "m1"]

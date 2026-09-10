"""
test_common.py — mw_common unit tests (T-01/T-02).

All fixtures inject their own providers.json / credential files; nothing reads
the real user home or real env credentials (AC-009 hermeticity).
"""
import datetime
import json
import os
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
from mw_common import (
    launcher_beat_write,
    orphan_dead_after,
    other_live_launcher,
    parse_end_exit,
    task_dir_last_activity,
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


# ── Terminal evidence / launcher beat (T-02: D-007/D-008) ─────────────────────

def _emit_verify(capsys: pytest.CaptureFixture[str], line: str) -> None:
    """Print a [VERIFY] line for quality-gate extraction, bypassing pytest capture."""
    with capsys.disabled():
        print(line)


def _write_trace(task_dir: pathlib.Path, lines: list[str]) -> pathlib.Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    trace = task_dir / "trace.log"
    trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return trace


class TestParseEndExit:
    def test_exit_codes_0_1_2(self, tmp_path, capsys):
        # Same shape as the TS END_LINE_RE consumers (AC-012: 0->done,
        # 2->needs-clarification, other->failed; the mapping itself is T-08).
        for code in (0, 1, 2):
            trace = _write_trace(tmp_path / f"wtl-{code}", [
                "[START] 2026-09-10T07:00:00.000Z task=t type=coding phases=-",
                "[HEARTBEAT] 2026-09-10T07:10:00.000Z task=t phase=1/2",
                f"[END] 2026-09-10T07:30:00.000Z exit={code} elapsed=120s tools=10 phases=1/2/3",
            ])
            assert parse_end_exit(trace.parent) == code
            _emit_verify(capsys, f"[VERIFY] VC-012: parse_end_exit={code}")

    def test_last_end_line_wins(self, tmp_path):
        # Mirrors the TS parse loop: later [END] lines overwrite earlier ones.
        trace = _write_trace(tmp_path, [
            "[END] 2026-09-10T07:30:00.000Z exit=0 elapsed=120s tools=10 phases=1",
            "[END] 2026-09-10T08:30:00.000Z exit=2 elapsed=60s tools=3 phases=-",
        ])
        assert parse_end_exit(trace.parent) == 2

    def test_no_end_line_returns_none(self, tmp_path, capsys):
        trace = _write_trace(tmp_path, [
            "[START] 2026-09-10T07:00:00.000Z task=t type=coding phases=-",
            "[HEARTBEAT] 2026-09-10T07:10:00.000Z task=t phase=1/2",
        ])
        assert parse_end_exit(trace.parent) is None
        _emit_verify(capsys, "[VERIFY] VC-012: parse_end_exit=None")

    def test_missing_trace_returns_none(self, tmp_path):
        assert parse_end_exit(tmp_path / "never-started") is None

    def test_empty_trace_returns_none(self, tmp_path):
        trace = _write_trace(tmp_path, [])
        assert parse_end_exit(trace.parent) is None

    def test_malformed_end_lines_do_not_match(self, tmp_path):
        # Near-misses must not count as terminal evidence.
        trace = _write_trace(tmp_path, [
            "[END] 2026-09-10T07:30:00.000Z exit=0 elapsed=120 tools=10 phases=1",  # missing s
            "[END] 2026-09-10T07:30:00.000Z exit=0 elapsed=120s tools=10",  # missing phases
            "[END] 2026-09-10T07:30:00.000Z exit=x elapsed=120s tools=10 phases=1",  # non-numeric
            "[END] 2026-09-10T07:30:00.000Z exit=0 elapsed=120s tools=10 phases=1 extra",  # trailing
        ])
        assert parse_end_exit(trace.parent) is None

    def test_end_within_tail_window_found(self, tmp_path):
        # >64KB of prior content; the [END] line sits inside the last 64KB
        # and the tail-only read must still hit it (design section 9).
        filler = ["[FLOW] 2026-09-10T00:00:00.000Z tool_call read"] * 2000
        trace = _write_trace(tmp_path, filler + [
            "[END] 2026-09-10T07:30:00.000Z exit=1 elapsed=120s tools=10 phases=1/2",
        ])
        assert trace.stat().st_size > 64 * 1024
        assert parse_end_exit(trace.parent) == 1

    def test_end_beyond_tail_window_not_found(self, tmp_path):
        # An [END] line buried under >64KB of later content is outside the
        # tail window: unread, returns None (perf contract of the tail read).
        filler = ["[FLOW] 2026-09-10T00:00:00.000Z tool_call read"] * 2000
        trace = _write_trace(tmp_path, [
            "[END] 2026-09-10T07:30:00.000Z exit=0 elapsed=120s tools=10 phases=1/2",
        ] + filler)
        assert trace.stat().st_size > 64 * 1024
        assert parse_end_exit(trace.parent) is None


class TestLauncherBeat:
    def test_write_creates_single_ts_line(self, tmp_path):
        launcher_beat_write(tmp_path, 4242)
        beat = tmp_path / ".mw" / "launcher-beat.4242"
        content = beat.read_text(encoding="utf-8")
        assert content.count("\n") == 1
        assert content.startswith("ts=")
        ts = mw_common._parse_heartbeat_ts(content.strip()[len("ts="):])
        assert ts.utcoffset() == datetime.timedelta(0)  # UTC (spec 2.1)

    def test_rewrite_overwrites_in_place(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mw_common, "iso_now", lambda: "2026-09-10T00:00:00+00:00")
        launcher_beat_write(tmp_path, 100)
        monkeypatch.setattr(mw_common, "iso_now", lambda: "2026-09-10T00:05:00+00:00")
        launcher_beat_write(tmp_path, 100)
        beat = tmp_path / ".mw" / "launcher-beat.100"
        assert beat.read_text(encoding="utf-8") == "ts=2026-09-10T00:05:00+00:00\n"

    def test_own_beat_skipped(self, tmp_path):
        launcher_beat_write(tmp_path, 100)
        assert other_live_launcher(tmp_path, 100) is False

    def test_other_launcher_fresh_and_alive(self, tmp_path, monkeypatch, capsys):
        launcher_beat_write(tmp_path, 200)  # another launcher, just beat
        monkeypatch.setattr(mw_common, "_is_alive", lambda pid: True)
        guard = other_live_launcher(tmp_path, 100)
        assert guard is True
        _emit_verify(
            capsys,
            f"[VERIFY] VC-013: beat_guard={guard}, window={orphan_dead_after({})}",
        )

    def test_expired_beat_not_live(self, tmp_path, monkeypatch):
        beat = tmp_path / ".mw" / "launcher-beat.200"
        beat.parent.mkdir(parents=True)
        beat.write_text("ts=2020-01-01T00:00:00+00:00\n", encoding="utf-8")
        monkeypatch.setattr(mw_common, "_is_alive", lambda pid: True)
        assert other_live_launcher(tmp_path, 100) is False

    def test_review_s2_expired_dead_beat_pruned(self, tmp_path, monkeypatch):
        # Review S2: an expired beat whose pid is dead is unlinked along the
        # way; the verdict is False either way (expired beats are ignored).
        beat = tmp_path / ".mw" / "launcher-beat.200"
        beat.parent.mkdir(parents=True)
        beat.write_text("ts=2020-01-01T00:00:00+00:00\n", encoding="utf-8")
        monkeypatch.setattr(mw_common, "_is_alive", lambda pid: False)
        assert other_live_launcher(tmp_path, 100) is False
        assert not beat.exists()

    def test_review_s2_expired_alive_beat_kept(self, tmp_path, monkeypatch):
        # Expired but pid alive (e.g. suspended launcher): not live, and the
        # beat file is kept — pruning only touches proven-dead launchers.
        beat = tmp_path / ".mw" / "launcher-beat.200"
        beat.parent.mkdir(parents=True)
        beat.write_text("ts=2020-01-01T00:00:00+00:00\n", encoding="utf-8")
        monkeypatch.setattr(mw_common, "_is_alive", lambda pid: True)
        assert other_live_launcher(tmp_path, 100) is False
        assert beat.exists()

    def test_dead_pid_not_live(self, tmp_path, monkeypatch):
        launcher_beat_write(tmp_path, 200)
        monkeypatch.setattr(mw_common, "_is_alive", lambda pid: False)
        assert other_live_launcher(tmp_path, 100) is False

    def test_no_beat_dir_false(self, tmp_path):
        assert other_live_launcher(tmp_path, 100) is False

    def test_malformed_beat_files_ignored(self, tmp_path, monkeypatch):
        beat_dir = tmp_path / ".mw"
        beat_dir.mkdir()
        (beat_dir / "launcher-beat.notapid").write_text(
            f"ts={mw_common.iso_now()}\n", encoding="utf-8")
        (beat_dir / "launcher-beat.300").write_text("garbage\n", encoding="utf-8")
        (beat_dir / "launcher-beat.301").write_text("ts=not-a-date\n", encoding="utf-8")
        monkeypatch.setattr(mw_common, "_is_alive", lambda pid: True)
        assert other_live_launcher(tmp_path, 100) is False


class TestOrphanDeadAfter:
    def test_default_90(self, monkeypatch):
        monkeypatch.delenv("PI_WORKER_ORPHAN_DEAD_MIN", raising=False)
        assert orphan_dead_after({}) == 90
        assert orphan_dead_after(None) == 90

    def test_env_override(self):
        assert orphan_dead_after({"PI_WORKER_ORPHAN_DEAD_MIN": "1"}) == 1
        assert orphan_dead_after({"PI_WORKER_ORPHAN_DEAD_MIN": "30"}) == 30

    def test_reads_process_env_when_none(self, monkeypatch):
        monkeypatch.setenv("PI_WORKER_ORPHAN_DEAD_MIN", "45")
        assert orphan_dead_after(None) == 45

    def test_invalid_values_fall_back(self):
        for bad in ("0", "-5", "abc", "", "1.5", "  "):
            assert orphan_dead_after({"PI_WORKER_ORPHAN_DEAD_MIN": bad}) == 90


class TestTaskDirLastActivity:
    def test_max_mtime_across_files(self, tmp_path):
        task_dir = tmp_path / "wtl-x"
        task_dir.mkdir()
        (task_dir / "task.md").write_text("x", encoding="utf-8")
        old = time.time() - 3600
        os.utime(task_dir / "task.md", (old, old))
        (task_dir / "trace.log").write_text("y", encoding="utf-8")
        (task_dir / "worker.log").write_text("z", encoding="utf-8")
        newest = task_dir_last_activity(task_dir)
        mtimes = {name: (task_dir / name).stat().st_mtime for name in ("task.md", "trace.log", "worker.log")}
        assert newest == pytest.approx(max(mtimes.values()))
        assert newest > old

    def test_subdirectories_ignored(self, tmp_path):
        task_dir = tmp_path / "wtl-x"
        task_dir.mkdir()
        (task_dir / "task.md").write_text("x", encoding="utf-8")
        sub = task_dir / "nested"
        sub.mkdir()
        (sub / "newer.log").write_text("y", encoding="utf-8")
        newest = task_dir_last_activity(task_dir)
        assert newest == pytest.approx((task_dir / "task.md").stat().st_mtime)

    def test_empty_dir_returns_none(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert task_dir_last_activity(empty) is None

    def test_missing_dir_returns_none(self, tmp_path):
        assert task_dir_last_activity(tmp_path / "nope") is None

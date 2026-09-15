"""
test_launcher.py — launcher routing, env isolation, and spawn isolation tests.

mw-dispatch-reliability: the providers fixture is fully hermetic (env-only
credential sources written to a tmp providers.json) so no test ever reads the
real ~/.pi/agent/auth.json (AC-009).
"""
import datetime
import json
import os
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher
import mw_common
from launcher import (
    _build_command,
    _build_env,
    _load_providers,
    _parse_workers_file,
    _poll_once,
    _reconcile_orphans,
    _resolve_cli,
    _serialize_entry,
    _starter_prompt,
    _spawn,
    _update_status,
    _validate_task_path,
)

_HERMETIC_CONFIG = {
    "credentials": {
        "anthropic": {"sources": [{"env": "ANTHROPIC_API_KEY"}]},
        "anthropic-auth": {"sources": [{"env": "ANTHROPIC_AUTH_TOKEN"}]},
        "deepseek": {"sources": [{"env": "DEEPSEEK_API_KEY"}]},
        "timi": {"sources": [{"env": "TIMI_API_KEY"}]},
    },
    "providers": {
        "claude": {
            "port": 7001, "base_url_env": "ANTHROPIC_BASE_URL",
            "api_key_env": "ANTHROPIC_API_KEY", "credential": "anthropic",
        },
        "claude-cli": {
            "port": 7003, "base_url_env": "ANTHROPIC_BASE_URL",
            "api_key_env": "ANTHROPIC_AUTH_TOKEN", "credential": "anthropic-auth",
        },
        "deepseek": {
            "port": 7004, "base_url_env": "DEEPSEEK_BASE_URL",
            "api_key_env": "DEEPSEEK_API_KEY", "credential": "deepseek",
        },
        "timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"},
    },
}


@pytest.fixture()
def task_file(tmp_path: pathlib.Path) -> pathlib.Path:
    # Real convention: .agenticdoc/{key}/workers/<task_key>/task.md (4 levels).
    t = tmp_path / ".agenticdoc" / "test-key" / "workers" / "t001" / "task.md"
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text("type: coding\nDo something useful.", encoding="utf-8")
    return t


@pytest.fixture()
def providers(tmp_path: pathlib.Path) -> dict:
    p = tmp_path / "providers.json"
    p.write_text(json.dumps(_HERMETIC_CONFIG), encoding="utf-8")
    return _load_providers(p)


@pytest.fixture()
def queue_file(tmp_path: pathlib.Path) -> pathlib.Path:
    agentic = tmp_path / ".agenticdoc"
    agentic.mkdir(exist_ok=True)
    return agentic / "_workers.parallel"


def _entry(task_file: pathlib.Path, **overrides) -> dict[str, str]:
    entry = {
        "cli": "pi", "provider": "timi", "task_path": str(task_file),
        "task_key": "t001", "status": "pending",
        "dispatched_at": "2026-08-14T00:00:00+00:00",
        "updated_at": "2026-08-14T00:00:00+00:00",
        "model": "",
    }
    entry.update(overrides)
    return entry


def _emit_verify(capsys: pytest.CaptureFixture[str], line: str) -> None:
    """Print a [VERIFY] line for quality-gate extraction, bypassing pytest capture."""
    with capsys.disabled():
        print(line)


# ── VC-008: Pi + timi ─────────────────────────────────────────────────────────

class TestPiTimiRouting:
    def test_command(self, task_file):
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["pi", "--provider", "timi", "--model", "glm-5.3", "-p", starter]

    def test_env_has_timi_key(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.delenv("TIMI_BASE_URL", raising=False)
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert env["TIMI_API_KEY"] == "test-timi-key"
        assert "TIMI_BASE_URL" not in env

    def test_env_optional_base_url(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setenv("TIMI_BASE_URL", "https://custom.timi.example.com")
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert env["TIMI_BASE_URL"] == "https://custom.timi.example.com"

    def test_env_no_anthropic_base_url(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:7001")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "some-key")
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert "ANTHROPIC_BASE_URL" not in env
        assert "ANTHROPIC_API_KEY" not in env

    def test_env_pi_worker_task(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert env["PI_WORKER_TASK"] == str(task_file.resolve())

    def test_env_no_openai_api_key(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-leaked-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://openai-proxy")
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert "OPENAI_API_KEY" not in env
        assert "OPENAI_BASE_URL" not in env

    def test_env_missing_timi_key_raises(self, task_file, providers, monkeypatch):
        # Hermetic: the fixture's timi chain has NO file source, so the real
        # ~/.pi/agent/auth.json can never satisfy this (AC-009).
        monkeypatch.delenv("TIMI_API_KEY", raising=False)
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        with pytest.raises(RuntimeError, match="TIMI_API_KEY"):
            _build_env(entry, providers)


# ── VC-009: Pi + empty provider ───────────────────────────────────────────────

class TestPiEmptyProvider:
    def test_command(self, task_file):
        entry = {"cli": "pi", "provider": "", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["pi", "-p", starter]

    def test_env_anthropic_base_url(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        entry = {"cli": "pi", "provider": "", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert env["ANTHROPIC_BASE_URL"] == "http://localhost:7001"

    def test_env_pi_worker_task(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        entry = {"cli": "pi", "provider": "", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert env["PI_WORKER_TASK"] == str(task_file.resolve())

    def test_env_no_timi_api_key(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        entry = {"cli": "pi", "provider": "", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert "TIMI_API_KEY" not in env


# ── VC-010: Codex routing ─────────────────────────────────────────────────────

class TestCodexRouting:
    def test_command_empty_provider(self, task_file):
        entry = {"cli": "codex", "provider": "", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["codex", "exec", "-m", "gpt-5.6-sol", starter]

    def test_command_codex_provider(self, task_file):
        entry = {"cli": "codex", "provider": "codex", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["codex", "exec", "-m", "gpt-5.6-sol", starter]

    def test_command_invalid_provider_raises(self, task_file):
        entry = {"cli": "codex", "provider": "timi", "task_path": str(task_file)}
        with pytest.raises(RuntimeError, match="timi"):
            _build_command(entry)

    def test_env_removes_openai_base_url(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8080")
        entry = {"cli": "codex", "provider": "", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert "OPENAI_BASE_URL" not in env

    def test_env_removes_openai_api_key(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-some-key")
        entry = {"cli": "codex", "provider": "", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert "OPENAI_API_KEY" not in env

    def test_env_removes_timi_api_key(self, task_file, providers, monkeypatch):
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        entry = {"cli": "codex", "provider": "", "task_path": str(task_file)}
        env = _build_env(entry, providers)
        assert "TIMI_API_KEY" not in env

    def test_env_invalid_provider_raises(self, task_file, providers):
        entry = {"cli": "codex", "provider": "timi", "task_path": str(task_file)}
        with pytest.raises(RuntimeError, match="timi"):
            _build_env(entry, providers)


# ── Spawn isolation (design D-001, AC-001) ────────────────────────────────────

class TestSpawnIsolation:
    """A task with unresolvable credentials is marked failed with the reason in
    worker.log — the launcher never treats it as fatal."""

    def test_missing_credential_marks_task_failed(
        self, task_file: pathlib.Path, tmp_path: pathlib.Path, providers: dict,
        queue_file: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TIMI_API_KEY", raising=False)
        entry = _entry(task_file)
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")

        running: dict = {}
        _spawn(entry, tmp_path, providers, running)

        entries = _parse_workers_file(queue_file)
        assert entries[0]["status"] == "failed"
        worker_log = task_file.parent / "worker.log"
        log_text = worker_log.read_text(encoding="utf-8")
        assert "TIMI_API_KEY" in log_text
        assert "t001" not in running  # nothing spawned

    def test_missing_route_credential_names_env_var(
        self, task_file: pathlib.Path, tmp_path: pathlib.Path, providers: dict,
        queue_file: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # claude task with no ANTHROPIC_AUTH_TOKEN: the reason must name it (VC-002).
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        entry = _entry(task_file, cli="claude", provider="")
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")

        running: dict = {}
        _spawn(entry, tmp_path, providers, running)

        entries = _parse_workers_file(queue_file)
        assert entries[0]["status"] == "failed"
        log_text = (task_file.parent / "worker.log").read_text(encoding="utf-8")
        assert "ANTHROPIC_AUTH_TOKEN" in log_text

    def test_missing_task_md_marks_failed(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
    ) -> None:
        entry = _entry(tmp_path / "nowhere" / "task.md")
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
        running: dict = {}
        _spawn(entry, tmp_path, providers, running)
        entries = _parse_workers_file(queue_file)
        assert entries[0]["status"] == "failed"

    def test_spawn_failure_does_not_raise(
        self, task_file: pathlib.Path, tmp_path: pathlib.Path, providers: dict,
        queue_file: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TIMI_API_KEY", raising=False)
        entry = _entry(task_file)
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
        running: dict = {}
        # Must not raise even if the status update itself fails.
        monkeypatch.setattr(launcher, "_update_status", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        _spawn(entry, tmp_path, providers, running)  # no exception


# ── Stale archive wired into the poll cycle (design D-004, AC-004) ───────────

class TestPollOnceArchivesStale:
    def test_stale_pending_archived_and_not_spawned(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
    ) -> None:
        entry = _entry(tmp_path / "gone" / "task.md")  # task.md does not exist
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")

        running: dict = {}
        _poll_once(tmp_path, providers, running, {}, [], None)

        assert _parse_workers_file(queue_file) == []
        stale_rows = (tmp_path / ".agenticdoc" / "_workers.stale.parallel").read_text(encoding="utf-8")
        assert "t001" in stale_rows
        assert running == {}

    def test_live_pending_untouched_by_archive(
        self, task_file: pathlib.Path, tmp_path: pathlib.Path, providers: dict,
        queue_file: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A real pending task must NOT be archived just because the poll ran.
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        entry = _entry(task_file)
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")

        class _FakeProc:
            returncode = None
            def poll(self):
                return None

        captured: dict = {}
        monkeypatch.setattr(launcher.subprocess, "Popen", lambda cmd, **kw: (captured.__setitem__("cmd", cmd), _FakeProc())[1])
        running: dict = {}
        _poll_once(tmp_path, providers, running, {}, [], None)

        assert len(_parse_workers_file(queue_file)) == 1
        assert "t001" in running


# ── CLI binary resolution (Windows npm .cmd shims) ────────────────────────────

class _FakeProc:
    returncode = None

    def poll(self) -> None:
        return None


class TestCliResolution:
    """Regression: worker CLIs are npm `.cmd` shims on Windows. A bare name like
    "codex" fails CreateProcess (only .exe is appended) -> FileNotFoundError ->
    every worker marked failed. _spawn must resolve cmd[0] to a full path first."""

    def test_resolve_missing_raises(self) -> None:
        with pytest.raises(RuntimeError, match="not found on PATH"):
            _resolve_cli("definitely-not-a-real-cli-xyz-123")

    def test_resolve_returns_full_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(launcher.shutil, "which", lambda name: r"C:\npm\codex.CMD")
        assert _resolve_cli("codex") == r"C:\npm\codex.CMD"

    def test_spawn_resolves_bare_name_to_full_path(
        self, task_file: pathlib.Path, providers: dict, tmp_path: pathlib.Path,
        queue_file: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        fake_path = str(tmp_path / "pi.CMD")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: fake_path)

        captured: dict = {}

        def fake_popen(cmd, **kwargs):  # noqa: ANN001, ANN202
            captured["cmd"] = cmd
            return _FakeProc()

        monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
        entry = _entry(task_file, cli="pi", provider="")
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
        running: dict = {}
        _spawn(entry, tmp_path, providers, running)

        # cmd[0] must be the resolved full path, never the bare "pi".
        assert captured["cmd"][0] == fake_path
        assert "t001" in running  # process was actually spawned (not marked failed)


# ── Per-task model selection ──────────────────────────────────────────────────

class TestModelSelection:
    def test_pi_timi_uses_model(self, task_file):
        entry = {"cli": "pi", "provider": "timi", "model": "some-timi-model", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["pi", "--provider", "timi", "--model", "some-timi-model", "-p", starter]

    def test_pi_timi_default_model_when_empty(self, task_file):
        entry = {"cli": "pi", "provider": "timi", "model": "", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["pi", "--provider", "timi", "--model", "glm-5.3", "-p", starter]

    def test_pi_empty_provider_with_model(self, task_file):
        entry = {"cli": "pi", "provider": "", "model": "claude-x", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["pi", "--model", "claude-x", "-p", starter]

    def test_pi_empty_provider_without_model(self, task_file):
        entry = {"cli": "pi", "provider": "", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["pi", "-p", starter]

    def test_codex_uses_model(self, task_file):
        entry = {"cli": "codex", "provider": "", "model": "gpt-x", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["codex", "exec", "-m", "gpt-x", starter]

    def test_claude_with_model(self, task_file):
        entry = {"cli": "claude", "provider": "", "model": "claude-y", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["claude", "--model", "claude-y", "-p", starter]

    def test_claude_without_model(self, task_file):
        entry = {"cli": "claude", "provider": "", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd == ["claude", "-p", starter]


# ── _workers.parallel column layout (7<->8, backward compat) ──────────────────

class TestWorkersFileColumns:
    def test_parse_legacy_7_columns(self, tmp_path: pathlib.Path):
        wf = tmp_path / "_workers.parallel"
        wf.write_text(
            "t1 | pending | pi | timi | /p/task.md | 2026-08-14T00:00:00+00:00 | 2026-08-14T00:00:00+00:00\n",
            encoding="utf-8",
        )
        entries = _parse_workers_file(wf)
        assert len(entries) == 1
        assert entries[0]["model"] == ""
        assert entries[0]["task_key"] == "t1"

    def test_parse_8_columns(self, tmp_path: pathlib.Path):
        wf = tmp_path / "_workers.parallel"
        wf.write_text(
            "t1 | pending | pi | timi | /p/task.md | 2026-08-14T00:00:00+00:00 | 2026-08-14T00:00:00+00:00 | my-model\n",
            encoding="utf-8",
        )
        entries = _parse_workers_file(wf)
        assert len(entries) == 1
        assert entries[0]["model"] == "my-model"

    def test_parse_rejects_wrong_column_count(self, tmp_path: pathlib.Path):
        wf = tmp_path / "_workers.parallel"
        wf.write_text("t1 | pending | pi\n", encoding="utf-8")  # 3 cols
        assert _parse_workers_file(wf) == []

    def test_serialize_round_trip_8_columns(self):
        entry = {
            "task_key": "t1", "status": "done", "cli": "pi", "provider": "timi",
            "task_path": "/p/task.md", "dispatched_at": "a", "updated_at": "b", "model": "m1",
        }
        line = _serialize_entry(entry)
        assert line.split(" | ") == ["t1", "done", "pi", "timi", "/p/task.md", "a", "b", "m1"]

    def test_serialize_missing_model_is_empty(self):
        entry = {
            "task_key": "t1", "status": "done", "cli": "pi", "provider": "timi",
            "task_path": "/p/task.md", "dispatched_at": "a", "updated_at": "b",
        }
        assert _serialize_entry(entry).endswith(" | ")  # trailing empty model column

    def test_update_status_preserves_model(self, tmp_path: pathlib.Path):
        (tmp_path / ".agenticdoc").mkdir()
        wf = tmp_path / ".agenticdoc" / "_workers.parallel"
        wf.write_text(
            "t1 | pending | pi | timi | /p/task.md | 2026-08-14T00:00:00+00:00 | 2026-08-14T00:00:00+00:00 | keep-me\n",
            encoding="utf-8",
        )
        _update_status(tmp_path, "t1", "done")
        entries = _parse_workers_file(wf)
        assert entries[0]["status"] == "done"
        assert entries[0]["model"] == "keep-me"  # model column survived the rewrite


# ── VC-031: task body never travels through argv (npm .cmd shim re-expansion) ──

class TestPromptShimSafety:
    """OverCode pch-migration-s1 incident: a task body containing
    `rg -n "pch_out_dir.*" ...` re-tokenized through the npm .cmd shim's %*
    expansion; cmd.exe executed the fragment ('pch_out_dir.*' 不是内部或外部命令)
    and the worker received a truncated prompt, replied 请提供具体任务 and idled.
    The command must carry only a short starter naming the task file."""

    @staticmethod
    def _dangerous_task(tmp_path: pathlib.Path) -> pathlib.Path:
        t = tmp_path / "task.md"
        t.write_text(
            'type: coding\n先跑 `rg -n "pch_out_dir" tools/index/build_collection_pch.py` '
            '核对 `rg -n "pch_out_dir.*" tools/` 清零 && echo DONE 验证: pytest -q > /dev/null 2>&1',
            encoding="utf-8",
        )
        return t

    def test_pi_command_carries_starter_not_body(self, tmp_path: pathlib.Path):
        t = self._dangerous_task(tmp_path)
        cmd = _build_command({"cli": "pi", "provider": "timi", "task_path": str(t)})
        prompt = cmd[-1]
        assert str(t.resolve()) in prompt  # worker can find its task file
        assert "pch_out_dir" not in prompt  # body fragments never on the argv
        assert '"' not in prompt and "&" not in prompt and "|" not in prompt

    def test_missing_task_file_raises(self, tmp_path: pathlib.Path):
        with pytest.raises(RuntimeError, match="task.md not found"):
            _build_command({"cli": "pi", "provider": "timi", "task_path": str(tmp_path / "nope.md")})


# ── Worker-task location contract (OverCode pch-migration-s1: root-level dirs) ──

class TestTaskLocationContract:
    def test_validator_accepts_key_workers(self, tmp_path: pathlib.Path):
        p = tmp_path / ".agenticdoc" / "my-key" / "workers" / "t1" / "task.md"
        _validate_task_path(tmp_path, str(p))  # no raise

    def test_validator_accepts_scratch_workers(self, tmp_path: pathlib.Path):
        p = tmp_path / ".agenticdoc" / "_scratch" / "workers" / "t1" / "task.md"
        _validate_task_path(tmp_path, str(p))  # no raise

    def test_validator_rejects_root_level(self, tmp_path: pathlib.Path):
        (tmp_path / ".agenticdoc").mkdir(exist_ok=True)
        p = tmp_path / ".agenticdoc" / "some-task" / "task.md"
        with pytest.raises(RuntimeError, match="invalid worker-task location"):
            _validate_task_path(tmp_path, str(p))

    def test_validator_rejects_outside_agenticdoc(self, tmp_path: pathlib.Path):
        (tmp_path / ".agenticdoc").mkdir(exist_ok=True)
        p = tmp_path / "elsewhere" / "task.md"
        with pytest.raises(RuntimeError, match="outside .agenticdoc"):
            _validate_task_path(tmp_path, str(p))

    def test_poll_rejects_root_level_task(
        self, tmp_path: pathlib.Path, providers: dict,
        queue_file: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # OverCode incident shape: hand-written task.md + queue row at the
        # .agenticdoc root must be marked failed with the reason, never spawned.
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        bad = tmp_path / ".agenticdoc" / "root-task" / "task.md"
        bad.parent.mkdir(parents=True)
        bad.write_text("type: coding\nwork", encoding="utf-8")
        entry = _entry(bad)
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")

        running: dict = {}
        _poll_once(tmp_path, providers, running, {}, [], None)

        assert running == {}
        assert _parse_workers_file(queue_file)[0]["status"] == "failed"
        log = (bad.parent / "worker.log").read_text(encoding="utf-8")
        assert "invalid worker-task location" in log


# ── T-04 (AC-009 source half): starter one-line conclusion directive ─────────

class TestStarterConclusionDirective:
    """The starter is the single cross-CLI behavior-guidance injection point
    (design D-005): it must direct the worker to open its final reply with a
    one-line conclusion (status + key result or blocker) so the done-row
    TL;DR is model-authored at the source. Headline normalization for old
    output.md files is the writeOutput fallback (T-03), not this file."""

    def test_starter_prompt_contains_conclusion_directive(self, task_file):
        starter = _starter_prompt(str(task_file))
        assert "one-line conclusion" in starter

    def test_pi_branch_last_arg_ends_with_starter(self, task_file):
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd[-1] == starter
        assert "one-line conclusion" in cmd[-1]

    def test_claude_branch_last_arg_ends_with_starter(self, task_file):
        entry = {"cli": "claude", "provider": "", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd[-1] == starter
        assert "one-line conclusion" in cmd[-1]

    def test_codex_branch_last_arg_ends_with_starter(self, task_file):
        entry = {"cli": "codex", "provider": "", "task_path": str(task_file)}
        cmd = _build_command(entry)
        starter = _starter_prompt(str(task_file))
        assert cmd[-1] == starter
        assert "one-line conclusion" in cmd[-1]

    def test_vc009_starter_directive_beacon(self, task_file, capsys):
        starter = _starter_prompt(str(task_file))
        assert "one-line conclusion" in starter
        _emit_verify(capsys, "[VERIFY] VC-009: starter_directive=present")


# ── T-08 (AC-012/AC-013): orphaned running-row reconcile ─────────────────────

def _make_worker_dir(tmp_path: pathlib.Path, key: str) -> pathlib.Path:
    """Worker task dir with a real task.md (queue-row convention)."""
    d = tmp_path / ".agenticdoc" / "test-key" / "workers" / key
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.md").write_text("type: coding\nDo something useful.", encoding="utf-8")
    return d


def _end_line(code: int) -> str:
    """A full [END] trace.log line (must satisfy _END_LINE_RE in mw_common)."""
    return f"[END] 2026-09-10T00:00:00+00:00 exit={code} elapsed=120s tools=6 phases=1>2>3"


def _age_task_dir(task_dir: pathlib.Path, seconds: float) -> None:
    """Push every file mtime in a task dir back by `seconds`."""
    cut = time.time() - seconds
    for p in task_dir.iterdir():
        os.utime(p, (cut, cut))


def _iso_minutes_ago(minutes: float) -> str:
    """UTC ISO timestamp (`+00:00` form) `minutes` in the past."""
    return (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    ).isoformat(timespec="seconds")


def _aged_orphan_entry(task_dir: pathlib.Path, key: str, age_min: float) -> dict[str, str]:
    """Running orphan row with no terminal evidence, aged `age_min` minutes."""
    return _entry(
        task_dir / "task.md",
        status="running",
        task_key=key,
        dispatched_at=_iso_minutes_ago(age_min),
        updated_at=_iso_minutes_ago(age_min),
    )


class TestReconcilePositiveEvidence:
    """VC-012: an orphaned running row (task_key not in running_procs) whose
    trace.log carries [END] converges to the exit-mapped terminal status in
    one reconcile pass, unconditionally — the beat guard never gates it
    (D-008)."""

    @pytest.mark.parametrize(
        ("code", "status"),
        [(0, "done"), (1, "failed"), (2, "needs-clarification"), (3, "failed")],
    )
    def test_end_exit_maps_to_terminal_status(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path, code: int, status: str,
    ) -> None:
        d = _make_worker_dir(tmp_path, "t001")
        (d / "trace.log").write_text(_end_line(code) + "\n", encoding="utf-8")
        entry = _entry(d / "task.md", status="running")
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")

        _reconcile_orphans(tmp_path, {})

        assert _parse_workers_file(queue_file)[0]["status"] == status
        log_text = (d / "worker.log").read_text(encoding="utf-8")
        assert "[launcher] reconcile (" in log_text
        assert f"exit={code}" in log_text
        assert "(orphaned row)" in log_text

    def test_output_md_without_end_failed_unverifiable(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
    ) -> None:
        # Old bundle: completed (output.md exists) but no [END] marker.
        d = _make_worker_dir(tmp_path, "t001")
        (d / "output.md").write_text("# Result\nold bundle, no trace END\n", encoding="utf-8")
        entry = _entry(d / "task.md", status="running")
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")

        _reconcile_orphans(tmp_path, {})

        assert _parse_workers_file(queue_file)[0]["status"] == "failed"
        log_text = (d / "worker.log").read_text(encoding="utf-8")
        assert "[launcher] reconcile (" in log_text
        assert "unverifiable" in log_text

    def test_own_running_row_never_touched(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
    ) -> None:
        # Own row: task_key in running_procs — untouched even with [END]
        # evidence present (the reap path owns its status transition).
        d = _make_worker_dir(tmp_path, "t001")
        (d / "trace.log").write_text(_end_line(0) + "\n", encoding="utf-8")
        entry = _entry(d / "task.md", status="running")
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")

        running: dict = {"t001": _FakeProc()}
        _reconcile_orphans(tmp_path, running)

        assert _parse_workers_file(queue_file)[0]["status"] == "running"
        assert not (d / "worker.log").exists()

    def test_vc012_three_mappings_plus_own_row(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path, capsys,
    ) -> None:
        dirs: dict[str, pathlib.Path] = {}
        lines: list[str] = []
        for key, code in (("t001", 0), ("t002", 1), ("t003", 2)):
            d = _make_worker_dir(tmp_path, key)
            (d / "trace.log").write_text(_end_line(code) + "\n", encoding="utf-8")
            dirs[key] = d
            lines.append(_serialize_entry(_entry(d / "task.md", status="running", task_key=key)))
        own = _make_worker_dir(tmp_path, "t004")
        (own / "trace.log").write_text(_end_line(0) + "\n", encoding="utf-8")
        lines.append(_serialize_entry(_entry(own / "task.md", status="running", task_key="t004")))
        queue_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        _reconcile_orphans(tmp_path, {"t004": _FakeProc()})

        rows = {e["task_key"]: e["status"] for e in _parse_workers_file(queue_file)}
        assert rows == {
            "t001": "done", "t002": "failed", "t003": "needs-clarification", "t004": "running",
        }
        for key in ("t001", "t002", "t003"):
            assert "[launcher] reconcile (" in (dirs[key] / "worker.log").read_text(encoding="utf-8")
        assert not (own / "worker.log").exists()
        _emit_verify(capsys, "[VERIFY] VC-012: map=0-done,1-failed,2-nc, own_row=untouched")


class TestReconcileSilenceRule:
    """VC-013: an orphaned running row with no terminal evidence fails only
    once its last activity (task-dir mtimes AND row updated_at) is older than
    the silence window (default 90m, PI_WORKER_ORPHAN_DEAD_MIN override).
    Any fresher evidence keeps it running; another live launcher's fresh beat
    makes the silence rule yield (D-008)."""

    def test_stale_orphan_failed_presumed_dead(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
    ) -> None:
        d = _make_worker_dir(tmp_path, "t001")
        queue_file.write_text(
            _serialize_entry(_aged_orphan_entry(d, "t001", 95)) + "\n", encoding="utf-8"
        )
        _age_task_dir(d, 95 * 60)

        _reconcile_orphans(tmp_path, {})

        assert _parse_workers_file(queue_file)[0]["status"] == "failed"
        log_text = (d / "worker.log").read_text(encoding="utf-8")
        assert "[launcher] reconcile (" in log_text
        assert "presumed dead" in log_text
        assert "no activity for 95m" in log_text

    def test_fresh_orphan_stays_running(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
    ) -> None:
        d = _make_worker_dir(tmp_path, "t001")
        queue_file.write_text(
            _serialize_entry(_aged_orphan_entry(d, "t001", 5)) + "\n", encoding="utf-8"
        )
        _age_task_dir(d, 5 * 60)

        _reconcile_orphans(tmp_path, {})

        assert _parse_workers_file(queue_file)[0]["status"] == "running"
        assert not (d / "worker.log").exists()

    def test_fresh_dir_activity_beats_old_updated_at(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
    ) -> None:
        # AC-013: ANY evidence fresher than the window keeps the row running —
        # task.md mtime stays fresh while updated_at is 95m old.
        d = _make_worker_dir(tmp_path, "t001")
        queue_file.write_text(
            _serialize_entry(_aged_orphan_entry(d, "t001", 95)) + "\n", encoding="utf-8"
        )

        _reconcile_orphans(tmp_path, {})

        assert _parse_workers_file(queue_file)[0]["status"] == "running"
        assert not (d / "worker.log").exists()

    def test_silence_window_env_override(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PI_WORKER_ORPHAN_DEAD_MIN", "1")
        d = _make_worker_dir(tmp_path, "t001")
        queue_file.write_text(
            _serialize_entry(_aged_orphan_entry(d, "t001", 5)) + "\n", encoding="utf-8"
        )
        _age_task_dir(d, 5 * 60)

        _reconcile_orphans(tmp_path, {})

        assert _parse_workers_file(queue_file)[0]["status"] == "failed"
        assert "presumed dead" in (d / "worker.log").read_text(encoding="utf-8")

    def test_updated_at_z_suffix_parsed(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
    ) -> None:
        # spec §5: updated_at may carry `Z` (TS side) or `+00:00` (Python side).
        d = _make_worker_dir(tmp_path, "t001")
        z_ts = _iso_minutes_ago(95).replace("+00:00", "Z")
        entry = _entry(
            d / "task.md", status="running", dispatched_at=z_ts, updated_at=z_ts,
        )
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
        _age_task_dir(d, 95 * 60)

        _reconcile_orphans(tmp_path, {})

        assert _parse_workers_file(queue_file)[0]["status"] == "failed"
        assert "presumed dead" in (d / "worker.log").read_text(encoding="utf-8")

    def test_updated_at_fallback_to_dispatched_at(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
    ) -> None:
        d = _make_worker_dir(tmp_path, "t001")
        entry = _entry(
            d / "task.md", status="running",
            updated_at="not-a-timestamp", dispatched_at=_iso_minutes_ago(95),
        )
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
        _age_task_dir(d, 95 * 60)

        _reconcile_orphans(tmp_path, {})

        assert _parse_workers_file(queue_file)[0]["status"] == "failed"
        assert "presumed dead" in (d / "worker.log").read_text(encoding="utf-8")

    def test_unparseable_row_timestamps_skip_row(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
    ) -> None:
        # Both row timestamps garbage: the silence rule never guesses, even
        # though the task-dir files are 95m old.
        d = _make_worker_dir(tmp_path, "t001")
        entry = _entry(
            d / "task.md", status="running",
            updated_at="not-a-timestamp", dispatched_at="also-garbage",
        )
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
        _age_task_dir(d, 95 * 60)

        _reconcile_orphans(tmp_path, {})

        assert _parse_workers_file(queue_file)[0]["status"] == "running"
        assert not (d / "worker.log").exists()

    def test_beat_guard_skips_silence_but_not_evidence(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch, capsys,
    ) -> None:
        # Another live launcher holds a fresh beat: the silence rule yields,
        # but positive [END] evidence still applies (D-008).
        stale = _make_worker_dir(tmp_path, "t001")
        ended = _make_worker_dir(tmp_path, "t002")
        (ended / "trace.log").write_text(_end_line(0) + "\n", encoding="utf-8")
        queue_file.write_text(
            _serialize_entry(_aged_orphan_entry(stale, "t001", 95)) + "\n"
            + _serialize_entry(_entry(ended / "task.md", status="running", task_key="t002")) + "\n",
            encoding="utf-8",
        )
        _age_task_dir(stale, 95 * 60)

        beat_dir = tmp_path / ".mw"
        beat_dir.mkdir(exist_ok=True)
        (beat_dir / f"launcher-beat.{os.getpid() + 1}").write_text(
            f"ts={mw_common.iso_now()}\n", encoding="utf-8"
        )
        monkeypatch.setattr(mw_common, "_is_alive", lambda pid: True)

        _reconcile_orphans(tmp_path, {})

        rows = {e["task_key"]: e["status"] for e in _parse_workers_file(queue_file)}
        assert rows["t001"] == "running"  # silence rule yielded
        assert rows["t002"] == "done"  # evidence applied unconditionally
        assert not (stale / "worker.log").exists()
        assert "another live launcher" in capsys.readouterr().err

    def test_vc013_silence_fresh_and_beat_guard(
        self, tmp_path: pathlib.Path, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch, capsys,
    ) -> None:
        # One stale orphan (95m, no evidence) + one fresh orphan (5m).
        stale_a = _make_worker_dir(tmp_path, "t001")
        fresh = _make_worker_dir(tmp_path, "t002")
        queue_file.write_text(
            _serialize_entry(_aged_orphan_entry(stale_a, "t001", 95)) + "\n"
            + _serialize_entry(_aged_orphan_entry(fresh, "t002", 5)) + "\n",
            encoding="utf-8",
        )
        _age_task_dir(stale_a, 95 * 60)
        _age_task_dir(fresh, 5 * 60)

        # Pass 1 (no other launcher): the stale orphan fails.
        _reconcile_orphans(tmp_path, {})
        assert _parse_workers_file(queue_file)[0]["status"] == "failed"

        # Pass 2: a new stale orphan appears while another live launcher
        # holds a fresh beat -> the silence rule yields to it.
        stale_b = _make_worker_dir(tmp_path, "t003")
        with queue_file.open("a", encoding="utf-8") as fh:
            fh.write(_serialize_entry(_aged_orphan_entry(stale_b, "t003", 95)) + "\n")
        _age_task_dir(stale_b, 95 * 60)
        beat_dir = tmp_path / ".mw"
        beat_dir.mkdir(exist_ok=True)
        (beat_dir / f"launcher-beat.{os.getpid() + 1}").write_text(
            f"ts={mw_common.iso_now()}\n", encoding="utf-8"
        )
        monkeypatch.setattr(mw_common, "_is_alive", lambda pid: True)

        _reconcile_orphans(tmp_path, {})

        rows = {e["task_key"]: e["status"] for e in _parse_workers_file(queue_file)}
        assert rows["t001"] == "failed"  # silence_failed=1
        assert rows["t002"] == "running"  # fresh_untouched=1
        assert rows["t003"] == "running"  # beat_guard=skipped
        assert "presumed dead" in (stale_a / "worker.log").read_text(encoding="utf-8")
        assert not (fresh / "worker.log").exists()
        assert not (stale_b / "worker.log").exists()
        _emit_verify(capsys, "[VERIFY] VC-013: silence_failed=1, fresh_untouched=1, beat_guard=skipped")


class TestPollOnceReconcileIntegration:
    def test_poll_beat_reconcile_and_spawn_ordering(
        self, tmp_path: pathlib.Path, providers: dict, queue_file: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # One poll: orphan running row with [END] converges, own running row
        # is untouched, pending row is discovered and spawned, and the beat
        # file is refreshed (D-008).
        orphan = _make_worker_dir(tmp_path, "t001")
        (orphan / "trace.log").write_text(_end_line(0) + "\n", encoding="utf-8")
        own = _make_worker_dir(tmp_path, "t002")
        (own / "trace.log").write_text(_end_line(1) + "\n", encoding="utf-8")
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        pending = _make_worker_dir(tmp_path, "t003")
        rows = (
            _entry(orphan / "task.md", status="running", task_key="t001"),
            _entry(own / "task.md", status="running", task_key="t002"),
            _entry(pending / "task.md", status="pending", task_key="t003"),
        )
        queue_file.write_text("\n".join(_serialize_entry(e) for e in rows) + "\n", encoding="utf-8")

        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        monkeypatch.setattr(launcher.subprocess, "Popen", lambda cmd, **kw: _FakeProc())
        running: dict = {"t002": _FakeProc()}
        _poll_once(tmp_path, providers, running, {}, [], None)

        statuses = {e["task_key"]: e["status"] for e in _parse_workers_file(queue_file)}
        assert statuses["t001"] == "done"  # orphan converged by reconcile
        assert statuses["t002"] == "running"  # own row untouched
        assert statuses["t003"] == "running"  # pending discovered and spawned
        assert "t003" in running
        assert "[launcher] reconcile (" in (orphan / "worker.log").read_text(encoding="utf-8")
        assert (tmp_path / ".mw" / f"launcher-beat.{os.getpid()}").exists()


# ── Dual-workspace spawn cwd (mw-dual-workspace D-001, VC-004) ────────────────

class TestDualWorkspaceSpawnCwd:
    """VC-004: dual mode spawns with cwd=game root; single keeps project_dir;
    an unusable target.yml refuses the spawn (fail-closed, per-task isolation).
    List args / no shell / absolute PI_WORKER_TASK all unchanged (AC-023/D-001)."""

    @staticmethod
    def _capture_popen(monkeypatch: pytest.MonkeyPatch) -> dict:
        captured: dict = {}

        def fake_popen(cmd, **kwargs):  # noqa: ANN001, ANN202
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return _FakeProc()

        monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
        return captured

    def test_single_mode_cwd_is_project_dir(
        self, task_file: pathlib.Path, tmp_path: pathlib.Path, providers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("MW_TARGET_GAME", raising=False)
        monkeypatch.delenv("MW_TARGET_ENGINE", raising=False)
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured = self._capture_popen(monkeypatch)

        running: dict = {}
        _spawn(_entry(task_file), tmp_path, providers, running)
        assert "t001" in running
        assert captured["kwargs"]["cwd"] == str(tmp_path)
        # D-001 zero-new-env invariant: PI_WORKER_TASK is absolute.
        assert pathlib.Path(captured["kwargs"]["env"]["PI_WORKER_TASK"]).is_absolute()

    def test_dual_mode_cwd_is_game_root(
        self, task_file: pathlib.Path, tmp_path: pathlib.Path, providers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("MW_TARGET_GAME", raising=False)
        monkeypatch.delenv("MW_TARGET_ENGINE", raising=False)
        game = tmp_path / "game"
        game.mkdir()
        (tmp_path / ".agenticdoc" / "target.yml").write_text(
            f"mode: dual\ngame: '{game}'\n", encoding="utf-8"
        )
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured = self._capture_popen(monkeypatch)

        running: dict = {}
        _spawn(_entry(task_file), tmp_path, providers, running)
        assert "t001" in running
        assert captured["kwargs"]["cwd"] == str(game.resolve())
        print(f"[VERIFY] VC-004: spawn-cwd={captured['kwargs']['cwd']}")

    def test_broken_target_yml_refuses_spawn(
        self, task_file: pathlib.Path, tmp_path: pathlib.Path, providers: dict,
        queue_file: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("MW_TARGET_GAME", raising=False)
        monkeypatch.delenv("MW_TARGET_ENGINE", raising=False)
        (tmp_path / ".agenticdoc" / "target.yml").write_text(
            "mode: [unclosed\n", encoding="utf-8"
        )
        monkeypatch.setenv("TIMI_API_KEY", "test-timi-key")
        self._capture_popen(monkeypatch)

        entry = _entry(task_file)
        queue_file.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
        running: dict = {}
        _spawn(entry, tmp_path, providers, running)  # no exception (D-001 isolation)
        assert "t001" not in running  # refused, not spawned
        worker_log = (task_file.parent / "worker.log").read_text(encoding="utf-8")
        assert "target.yml" in worker_log
        statuses = {e["task_key"]: e["status"] for e in _parse_workers_file(queue_file)}
        assert statuses["t001"] == "failed"  # fail-closed, visible in the queue

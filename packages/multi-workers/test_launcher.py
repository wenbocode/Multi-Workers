"""
test_launcher.py — launcher routing, env isolation, and spawn isolation tests.

mw-dispatch-reliability: the providers fixture is fully hermetic (env-only
credential sources written to a tmp providers.json) so no test ever reads the
real ~/.pi/agent/auth.json (AC-009).
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher
from launcher import (
    _build_command,
    _build_env,
    _load_providers,
    _parse_workers_file,
    _poll_once,
    _resolve_cli,
    _serialize_entry,
    _starter_prompt,
    _spawn,
    _update_status,
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
    t = tmp_path / "task.md"
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

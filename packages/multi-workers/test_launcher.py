"""
test_launcher.py — VC-008/009/010: launcher routing and env isolation tests.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from launcher import _FatalLauncherError, _build_command, _build_env, _load_providers, _spawn

_PROVIDERS_JSON = pathlib.Path(__file__).parent / "providers.json"


@pytest.fixture()
def task_file(tmp_path: pathlib.Path) -> pathlib.Path:
    t = tmp_path / "task.md"
    t.write_text("type: coding\nDo something useful.", encoding="utf-8")
    return t


@pytest.fixture()
def providers() -> dict:
    return _load_providers(_PROVIDERS_JSON)


# ── VC-008: Pi + timi ─────────────────────────────────────────────────────────

class TestPiTimiRouting:
    def test_command(self, task_file):
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        cmd = _build_command(entry)
        task_content = task_file.read_text(encoding="utf-8").strip()
        assert cmd == ["pi", "--provider", "timi", "--model", "gpt-5.6-sol", "-p", task_content]

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
        monkeypatch.delenv("TIMI_API_KEY", raising=False)
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        with pytest.raises(RuntimeError, match="TIMI_API_KEY"):
            _build_env(entry, providers)


# ── VC-009: Pi + empty provider ───────────────────────────────────────────────

class TestPiEmptyProvider:
    def test_command(self, task_file):
        entry = {"cli": "pi", "provider": "", "task_path": str(task_file)}
        cmd = _build_command(entry)
        task_content = task_file.read_text(encoding="utf-8").strip()
        assert cmd == ["pi", "-p", task_content]

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
        task_content = task_file.read_text(encoding="utf-8").strip()
        assert cmd == ["codex", "exec", "-m", "gpt-5.6-sol", task_content]

    def test_command_codex_provider(self, task_file):
        entry = {"cli": "codex", "provider": "codex", "task_path": str(task_file)}
        cmd = _build_command(entry)
        task_content = task_file.read_text(encoding="utf-8").strip()
        assert cmd == ["codex", "exec", "-m", "gpt-5.6-sol", task_content]

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


# ── Spawn fatal error propagation ─────────────────────────────────────────────

class TestSpawnFatalError:
    def test_missing_timi_key_raises_fatal_launcher_error(
        self, task_file: pathlib.Path, tmp_path: pathlib.Path, providers: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TIMI_API_KEY", raising=False)
        entry = {
            "cli": "pi", "provider": "timi", "task_path": str(task_file),
            "task_key": "t001", "status": "pending",
            "dispatched_at": "2026-08-14T00:00:00+00:00",
            "updated_at": "2026-08-14T00:00:00+00:00",
        }
        with pytest.raises(_FatalLauncherError, match="TIMI_API_KEY"):
            _spawn(entry, tmp_path, providers, {})

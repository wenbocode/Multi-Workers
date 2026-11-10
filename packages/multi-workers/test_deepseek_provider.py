"""DeepSeek shipped credential configuration and native pi launch path; no real keys."""
import json
import pathlib

import pytest

import launcher
import mw_common


def test_shipped_credential_chain_and_direct_worker(monkeypatch, tmp_path):
    shipped = pathlib.Path(__file__).with_name("providers.json")
    config = mw_common.load_providers(shipped)
    assert config["credentials"]["deepseek"] == mw_common._DEFAULT_CONFIG["credentials"]["deepseek"]
    home = tmp_path / "home"
    auth = home / ".pi/agent/auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(json.dumps({"deepseek": {"type": "api_key", "key": "fake-file-key"}}), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-env-key")
    monkeypatch.setenv("TIMI_API_KEY", "fake-other-key")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    task = tmp_path / ".agenticdoc/key/workers/task/task.md"
    task.parent.mkdir(parents=True)
    task.write_text("type: coding\n", encoding="utf-8")
    entry = launcher._effective_entry({"cli": "pi", "provider": "timi", "task_path": str(task)}, "deepseek/deepseek-flash")
    env = launcher._build_env(entry, config)
    assert env["DEEPSEEK_API_KEY"] == "fake-env-key"
    assert "TIMI_API_KEY" not in env
    assert "DEEPSEEK_BASE_URL" not in env
    assert env["PI_WORKER_TASK"] == str(task.resolve())
    argv = launcher._build_command(entry)
    assert argv[argv.index("--provider") + 1] == "deepseek"
    assert argv[argv.index("--model") + 1] == "deepseek-flash"
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    assert launcher._build_env(entry, config)["DEEPSEEK_API_KEY"] == "fake-file-key"
    auth.unlink()
    with pytest.raises(RuntimeError, match="credential is not available"):
        launcher._build_env(entry, config)


def test_config_sample_has_no_secret():
    config = json.loads((pathlib.Path(__file__).parent / "config/deepseek.json").read_text(encoding="utf-8"))
    assert config == {"version": 1, "baseUrl": "https://api.deepseek.com", "models": ["deepseek-flash", "deepseek-v4-pro"]}

"""OpenAI dispatch prefix, CLI persistence and isolated native worker routing."""
import argparse
import json
import pathlib

import pytest

import launcher
import mw
import mw_common


@pytest.mark.parametrize("role", ["main", "coding", "review", "research", "decide_prepare"])
def test_model_set_and_worker_resolution(tmp_path, role):
    value = "openai/gpt-6.1-sol"
    args = argparse.Namespace(project=str(tmp_path), model_action="set", role=role, value=value, force=False)
    assert mw.cmd_model(args) == 0
    config, error = mw_common.load_dispatch_config(tmp_path)
    assert error is None
    assert config["models"][role] == value
    task = tmp_path / ".agenticdoc/key/workers/task/task.md"
    task.parent.mkdir(parents=True)
    task.write_text(f"type: {role if role != 'main' else 'coding'}\n", encoding="utf-8")
    entry = {"cli": "pi", "provider": "timi", "task_path": str(task)}
    # main is a PM-only role; the worker inherits the recorded window model.
    if role == "main":
        mw_common.window_model_path(tmp_path).write_text(value + "\n", encoding="utf-8")
    selected, source = launcher._resolve_entry_model(entry, tmp_path)
    assert selected == value
    assert source == ("window" if role == "main" else f"config:{role}")
    effective = launcher._effective_entry(entry, selected)
    assert (effective["provider"], effective["model"]) == ("openai", "gpt-6.1-sol")
    assert launcher._build_command(effective)[1:5] == ["--provider", "openai", "--model", "gpt-6.1-sol"]


def test_native_worker_credentials_and_fallback(monkeypatch, tmp_path):
    shipped = mw_common.load_providers(pathlib.Path(__file__).with_name("providers.json"))
    assert shipped == mw_common.default_config()
    home = tmp_path / "home"
    auth = home / ".pi/agent/auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(json.dumps({"openai": {"type": "api_key", "key": "fake-file-key"}}), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("OPENAI_API_KEY", "fake-env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://unrelated-proxy.invalid")
    monkeypatch.setenv("TIMI_API_KEY", "fake-other-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-other-key")
    entry = {"cli": "pi", "provider": "openai", "task_path": str(tmp_path / "task.md")}
    env = launcher._build_env(entry, shipped)
    assert env["OPENAI_API_KEY"] == "fake-env-key"
    assert all(name not in env for name in ("TIMI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_BASE_URL"))
    assert env["PI_WORKER_TASK"] == entry["task_path"]
    assert mw_common.validate_fallback_models({"review": ["openai/gpt-6.1-sol"]}) == (
        {"review": ["openai/gpt-6.1-sol"]}, None,
    )
    assert launcher._fallback_candidate_available("openai/gpt-6.1-sol", shipped) == (True, "")
    monkeypatch.delenv("OPENAI_API_KEY")
    assert launcher._build_env(entry, shipped)["OPENAI_API_KEY"] == "fake-file-key"
    auth.unlink()
    with pytest.raises(RuntimeError, match="openai credential is not available"):
        launcher._build_env(entry, shipped)
    available, reason = launcher._fallback_candidate_available("openai/gpt-6.1-sol", shipped)
    assert not available and "credential unavailable" in reason

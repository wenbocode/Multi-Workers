"""
test_dispatch_models.py — dispatch model defaults (mw-dispatch-models).

Covers the config layer (.mw/dispatch.yml + .mw/window-model), the resolution
chain (task.md model: > role config > window model > per-cli default), prefix
route compatibility, the launcher's direct-provider spawn/env branches, and the
`mw model` CLI. Fully hermetic: everything under tmp_path, env-isolated
credentials from the test_launcher providers fixture config.
"""
import argparse
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher
import mw
import mw_common


# ── fixtures ──────────────────────────────────────────────────────────────────


def _task_file(root: pathlib.Path, body: str) -> pathlib.Path:
    t = root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md"
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text(body, encoding="utf-8")
    return t


def _project(tmp_path: pathlib.Path, *, task_body: str = "type: coding\ndo it\n",
             dispatch_yml: str | None = None, window_model: str | None = None) -> pathlib.Path:
    _task_file(tmp_path, task_body)
    if dispatch_yml is not None:
        (tmp_path / ".mw").mkdir(exist_ok=True)
        (tmp_path / ".mw" / "dispatch.yml").write_text(dispatch_yml, encoding="utf-8")
    if window_model is not None:
        (tmp_path / ".mw").mkdir(exist_ok=True)
        (tmp_path / ".mw" / "window-model").write_text(window_model + "\n", encoding="utf-8")
    return tmp_path


def _entry(task: pathlib.Path, **overrides) -> dict[str, str]:
    entry = {
        "cli": "pi", "provider": "timi", "task_path": str(task),
        "task_key": "t1", "status": "pending",
        "dispatched_at": "2026-09-18T00:00:00+00:00",
        "updated_at": "2026-09-18T00:00:00+00:00",
        "model": "",
    }
    entry.update(overrides)
    return entry


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
def creds(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Hermetic credential environment for the direct-provider env branches."""
    monkeypatch.setenv("TIMI_API_KEY", "timi-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test")
    for gone in ("ANTHROPIC_BASE_URL", "DEEPSEEK_BASE_URL", "TIMI_BASE_URL",
                 "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(gone, raising=False)
    return _HERMETIC_CONFIG


# ── config layer ──────────────────────────────────────────────────────────────


class TestLoadDispatchConfig:
    def test_missing_file_is_nothing_configured(self, tmp_path: pathlib.Path) -> None:
        config, err = mw_common.load_dispatch_config(tmp_path)
        assert config == {} and err is None

    def test_valid_roles(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".mw").mkdir()
        (tmp_path / ".mw" / "dispatch.yml").write_text(
            "models:\n  coding: timi/glm-5.3\n  review: timi/glm-5.3-air\n", encoding="utf-8",
        )
        config, err = mw_common.load_dispatch_config(tmp_path)
        assert err is None
        assert config == {"models": {"coding": "timi/glm-5.3", "review": "timi/glm-5.3-air"}}

    def test_broken_yaml_is_fail_soft(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".mw").mkdir()
        (tmp_path / ".mw" / "dispatch.yml").write_text("models: [broken\n", encoding="utf-8")
        config, err = mw_common.load_dispatch_config(tmp_path)
        assert config == {} and err and "unreadable" in err

    def test_unknown_role_rejected(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".mw").mkdir()
        (tmp_path / ".mw" / "dispatch.yml").write_text(
            "models:\n  villain: timi/x\n", encoding="utf-8",
        )
        config, err = mw_common.load_dispatch_config(tmp_path)
        assert config == {} and err and "villain" in err


class TestParseAndCompat:
    # Mirror of the TS-side PY_PREFIX_MAP (agent-team-loop.test.ts "dispatch
    # model config"): both maps must stay equal when a provider joins the
    # namespace — this is the Python half of the parity lock.
    _TS_MIRROR = {
        "timi": "timi",
        "anthropic": "claude",
        "openai-codex": "codex",
        "deepseek": "deepseek",
        "zai-coding-cn": "zai",
    }

    def test_prefix_map_matches_ts_mirror(self) -> None:
        assert mw_common.MODEL_PREFIX_TO_PI_PROVIDER == {
            prefix: provider for provider, prefix in self._TS_MIRROR.items()
        }
        assert mw_common.PROVIDER_ID_TO_PREFIX == self._TS_MIRROR
        assert mw_common.CLI_PREFIX_TO_CLI == {"codex_cli": "codex", "claude_cli": "claude"}

    def test_parse(self) -> None:
        assert mw_common.parse_model_value("timi/glm-5.3") == ("timi", "glm-5.3")
        assert mw_common.parse_model_value("glm-5.3") == ("", "glm-5.3")
        assert mw_common.parse_model_value(" codex_cli/gpt-5.6-sol ") == ("codex_cli", "gpt-5.6-sol")

    def test_bare_matches_any_cli(self) -> None:
        assert mw_common.model_value_compatible("pi", "glm-5.3")
        assert mw_common.model_value_compatible("codex", "gpt-5.6-sol")

    def test_provider_prefixes_are_pi_only(self) -> None:
        assert mw_common.model_value_compatible("pi", "claude/claude-sonnet-5")
        assert mw_common.model_value_compatible("pi", "codex/gpt-5.6-sol")
        assert not mw_common.model_value_compatible("codex", "claude/x")
        assert not mw_common.model_value_compatible("claude", "deepseek/x")

    def test_cli_prefixes_match_their_cli(self) -> None:
        assert mw_common.model_value_compatible("codex", "codex_cli/gpt-5.6-sol")
        assert mw_common.model_value_compatible("claude", "claude_cli/claude-sonnet-5")
        assert not mw_common.model_value_compatible("pi", "codex_cli/x")
        assert not mw_common.model_value_compatible("codex", "claude_cli/x")

    def test_unknown_prefix_incompatible(self) -> None:
        assert not mw_common.model_value_compatible("pi", "openrouter/x")


# ── resolution chain ──────────────────────────────────────────────────────────


class TestResolveDispatchModel:
    def _resolve(self, *, cli="pi", task_type="coding", entry_model="", models=None, window=""):
        return mw_common.resolve_dispatch_model(
            cli=cli, task_type=task_type, entry_model=entry_model,
            config_models=models or {}, window_model=window,
        )

    def test_explicit_task_model_wins(self) -> None:
        value, source = self._resolve(
            entry_model="codex/gpt-5.6-sol",
            models={"coding": "timi/glm-5.3"}, window="claude/x",
        )
        assert (value, source) == ("codex/gpt-5.6-sol", "task")

    def test_role_config(self) -> None:
        value, source = self._resolve(task_type="review", models={"review": "timi/glm-5.3-air"})
        assert (value, source) == ("timi/glm-5.3-air", "config:review")

    def test_type_to_role_bucketing(self) -> None:
        for task_type in ("verifier", "reviewer", "review"):
            value, source = self._resolve(task_type=task_type, models={"review": "timi/r"})
            assert source == "config:review", task_type
        for task_type in ("phase-writer", "repair", "roadmap-writer", "", "unknown"):
            value, source = self._resolve(task_type=task_type, models={"coding": "timi/c"})
            assert source == "config:coding", task_type
        value, source = self._resolve(task_type="research", models={"research": "timi/rz"})
        assert source == "config:research"

    def test_window_model_when_role_unset(self) -> None:
        value, source = self._resolve(window="claude/claude-sonnet-5")
        assert (value, source) == ("claude/claude-sonnet-5", "window")

    def test_incompatible_config_falls_to_window(self) -> None:
        # codex_cli/ cannot serve a pi entry → window model applies instead
        value, source = self._resolve(models={"coding": "codex_cli/gpt-x"},
                                      window="claude/claude-sonnet-5")
        assert (value, source) == ("claude/claude-sonnet-5", "window")

    def test_default_when_nothing_compatible(self) -> None:
        value, source = self._resolve(cli="codex", window="claude/x")
        assert (value, source) == ("", "default")


# ── launcher integration ──────────────────────────────────────────────────────


class TestLauncherResolution:
    def test_task_md_model_is_source_of_truth(self, tmp_path: pathlib.Path) -> None:
        # Even with a stale queue-row model (orphan reinsert writes ""),
        # the task.md model: line is explicit.
        root = _project(tmp_path, task_body="type: coding\nmodel: codex/gpt-5.6-sol\ndo\n")
        entry = _entry(root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md", model="")
        value, source = launcher._resolve_entry_model(entry, root)
        assert (value, source) == ("codex/gpt-5.6-sol", "task")
        eff = launcher._effective_entry(entry, value)
        assert (eff["provider"], eff["model"]) == ("openai-codex", "gpt-5.6-sol")

    def test_chain_config_then_window(self, tmp_path: pathlib.Path) -> None:
        task = root = None
        root = _project(
            tmp_path,
            task_body="type: review\ncheck\n",
            dispatch_yml="models:\n  review: timi/glm-5.3-air\n",
            window_model="claude/claude-sonnet-5",
        )
        entry = _entry(root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md")
        value, source = launcher._resolve_entry_model(entry, root)
        assert (value, source) == ("timi/glm-5.3-air", "config:review")

        (root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md").write_text(
            "type: coding\ndo\n", encoding="utf-8")
        value, source = launcher._resolve_entry_model(entry, root)
        assert (value, source) == ("claude/claude-sonnet-5", "window")

    def test_broken_dispatch_yml_falls_through(self, tmp_path: pathlib.Path) -> None:
        root = _project(tmp_path, dispatch_yml="models: [broken\n",
                        window_model="claude/claude-sonnet-5")
        entry = _entry(root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md")
        value, source = launcher._resolve_entry_model(entry, root)
        assert (value, source) == ("claude/claude-sonnet-5", "window")

    def test_effective_entry_rejects_wrong_cli(self, tmp_path: pathlib.Path) -> None:
        task = tmp_path / ".agenticdoc" / "k" / "workers" / "t1" / "task.md"
        entry = _entry(task, cli="pi")
        with pytest.raises(RuntimeError, match="codex entry"):
            launcher._effective_entry(entry, "codex_cli/gpt-x")
        entry_codex = _entry(task, cli="codex", provider="")
        with pytest.raises(RuntimeError, match="pi entry"):
            launcher._effective_entry(entry_codex, "codex/gpt-x")

    def test_bare_model_keeps_route(self, tmp_path: pathlib.Path) -> None:
        task = tmp_path / ".agenticdoc" / "k" / "workers" / "t1" / "task.md"
        entry = _entry(task, provider="timi")
        eff = launcher._effective_entry(entry, "glm-5.3")
        assert (eff["provider"], eff["model"]) == ("timi", "glm-5.3")


class TestDirectProviderSpawn:
    """Prefix-driven spawns: command flags + env wiring for the direct routes."""

    def _eff(self, tmp_path, value, cli="pi"):
        task = _task_file(tmp_path, "type: coding\ndo\n")
        return launcher._effective_entry(_entry(task, cli=cli, provider="timi"), value)

    def test_anthropic_direct(self, tmp_path: pathlib.Path, creds: dict) -> None:
        eff = self._eff(tmp_path, "claude/claude-sonnet-5")
        assert launcher._build_command(eff) == [
            "pi", "--provider", "anthropic", "--model", "claude-sonnet-5",
            "-p", launcher._starter_prompt(eff["task_path"]),
        ]
        env = launcher._build_env(eff, creds)
        assert env["ANTHROPIC_API_KEY"] == "anthropic-test"
        assert "ANTHROPIC_BASE_URL" not in env  # direct: no mw proxy
        assert env["PI_WORKER_TASK"] == eff["task_path"]

    def test_anthropic_base_url_passthrough(self, tmp_path: pathlib.Path,
                                            creds: dict, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gw.example.com")
        eff = self._eff(tmp_path, "claude/claude-sonnet-5")
        env = launcher._build_env(eff, creds)
        assert env["ANTHROPIC_BASE_URL"] == "https://gw.example.com"

    def test_openai_codex_direct(self, tmp_path: pathlib.Path, creds: dict) -> None:
        eff = self._eff(tmp_path, "codex/gpt-5.6-sol")
        assert launcher._build_command(eff)[1:5] == ["--provider", "openai-codex", "--model", "gpt-5.6-sol"]
        env = launcher._build_env(eff, creds)
        # codex' own config carries auth: no proxy credentials in env
        assert "ANTHROPIC_API_KEY" not in env and "TIMI_API_KEY" not in env
        assert env["PI_WORKER_TASK"] == eff["task_path"]

    def test_deepseek_direct(self, tmp_path: pathlib.Path, creds: dict) -> None:
        eff = self._eff(tmp_path, "deepseek/deepseek-chat")
        assert launcher._build_command(eff)[1:5] == ["--provider", "deepseek", "--model", "deepseek-chat"]
        env = launcher._build_env(eff, creds)
        assert env["DEEPSEEK_API_KEY"] == "deepseek-test"
        assert "DEEPSEEK_BASE_URL" not in env  # direct: no mw proxy

    def test_missing_direct_credential_fails_loud(self, tmp_path: pathlib.Path,
                                                  creds: dict, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        eff = self._eff(tmp_path, "claude/claude-sonnet-5")
        with pytest.raises(RuntimeError, match="anthropic credential"):
            launcher._build_env(eff, creds)

    def test_codex_cli_prefix_strips_and_matches(self, tmp_path: pathlib.Path, creds: dict) -> None:
        eff = self._eff(tmp_path, "codex_cli/gpt-5.6-sol", cli="codex")
        assert launcher._build_command(eff)[:4] == ["codex", "exec", "-m", "gpt-5.6-sol"]

    def test_direct_provider_requires_model(self, tmp_path: pathlib.Path) -> None:
        task = _task_file(tmp_path, "type: coding\ndo\n")
        with pytest.raises(RuntimeError, match="explicit model"):
            launcher._build_command({"cli": "pi", "provider": "anthropic",
                                     "task_path": str(task), "model": ""})


# ── mw model CLI ──────────────────────────────────────────────────────────────


def _model_args(project: pathlib.Path, action: str, role: str = "", value: str = "") -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), model_action=action, role=role, value=value,
    )


class TestModelCli:
    def test_set_show_clear_roundtrip(self, tmp_path: pathlib.Path) -> None:
        assert mw.cmd_model(_model_args(tmp_path, "set", "review", "timi/glm-5.3-air")) == 0
        assert mw.cmd_model(_model_args(tmp_path, "set", "coding", "codex/gpt-5.6-sol")) == 0
        config, err = mw_common.load_dispatch_config(tmp_path)
        assert err is None
        assert config["models"] == {"review": "timi/glm-5.3-air", "coding": "codex/gpt-5.6-sol"}

        assert mw.cmd_model(_model_args(tmp_path, "clear", "review")) == 0
        config, _ = mw_common.load_dispatch_config(tmp_path)
        assert config["models"] == {"coding": "codex/gpt-5.6-sol"}
        assert mw.cmd_model(_model_args(tmp_path, "clear", "all")) == 0
        config, _ = mw_common.load_dispatch_config(tmp_path)
        assert config["models"] == {}

    def test_set_rejects_bad_values(self, tmp_path: pathlib.Path) -> None:
        assert mw.cmd_model(_model_args(tmp_path, "set", "coding", "noslash")) == 1
        assert mw.cmd_model(_model_args(tmp_path, "set", "coding", "bogus/x")) == 1
        assert not mw_common.dispatch_config_path(tmp_path).exists()

    def test_set_refuses_broken_existing(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".mw").mkdir()
        (tmp_path / ".mw" / "dispatch.yml").write_text("models: [broken\n", encoding="utf-8")
        assert mw.cmd_model(_model_args(tmp_path, "set", "coding", "timi/x")) == 1
        assert "broken" in (tmp_path / ".mw" / "dispatch.yml").read_text(encoding="utf-8")

    def test_show_prints_effective_chain(self, tmp_path: pathlib.Path,
                                         capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / ".mw").mkdir()
        (tmp_path / ".mw" / "dispatch.yml").write_text(
            "models:\n  review: timi/glm-5.3-air\n", encoding="utf-8")
        (tmp_path / ".mw" / "window-model").write_text("claude/claude-sonnet-5\n", encoding="utf-8")
        assert mw.cmd_model(_model_args(tmp_path, "show")) == 0
        out = capsys.readouterr().out
        assert "review: timi/glm-5.3-air" in out
        assert "window model: claude/claude-sonnet-5" in out
        assert "coding: (unset)" in out and "[window]" in out


# ── doctor section ────────────────────────────────────────────────────────────


class TestDoctorDispatch:
    def test_missing_file_is_silent(self, tmp_path: pathlib.Path) -> None:
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        assert report["dispatch"] == {"exists": False}
        text = mw_common.format_doctor_text(report)
        assert "dispatch:" not in text

    def test_configured_shows_roles(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".mw").mkdir()
        (tmp_path / ".mw" / "dispatch.yml").write_text(
            "models:\n  coding: timi/glm-5.3\n", encoding="utf-8")
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        assert report["dispatch"]["models"] == {"coding": "timi/glm-5.3"}
        text = mw_common.format_doctor_text(report)
        assert "dispatch: coding=timi/glm-5.3" in text

    def test_broken_file_is_suggestion(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / ".mw").mkdir()
        (tmp_path / ".mw" / "dispatch.yml").write_text("models: [broken\n", encoding="utf-8")
        report = mw_common.doctor_report(tmp_path, fix=False, config=_HERMETIC_CONFIG)
        assert report["dispatch"]["error"]
        summary = report["summary"]
        # Fail-soft: a broken dispatch.yml must never be an issue (only a
        # suggestion) — model defaults must not flag the chain unhealthy.
        assert not any("dispatch.yml" in i for i in summary["issues"])
        assert any("dispatch.yml unusable" in s for s in summary["suggestions"])

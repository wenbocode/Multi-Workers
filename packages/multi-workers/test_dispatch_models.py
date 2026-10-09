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

    def test_bom_prefixed_file_reads_like_the_ts_reader(self, tmp_path: pathlib.Path) -> None:
        # A BOM (Windows PowerShell `Set-Content -Encoding utf8`, some editors)
        # must not hide the roles: PyYAML strips it, and the TS reader does too.
        (tmp_path / ".mw").mkdir()
        (tmp_path / ".mw" / "dispatch.yml").write_text(
            "models:\n  review: timi/gpt-5.6-sol\n", encoding="utf-8-sig")
        config, err = mw_common.load_dispatch_config(tmp_path)
        assert err is None
        assert config["models"] == {"review": "timi/gpt-5.6-sol"}


class TestParseAndCompat:
    # Mirror of the TS-side DISPATCH_ROLE_BY_TYPE (agent-team-loop
    # shared/dispatch-models.ts). Both sides hardcode the literal; a drift in
    # either map fails here.
    _TS_ROLE_BY_TYPE = {
        "coding": "coding",
        "phase-writer": "coding",
        "repair": "coding",
        "roadmap-writer": "coding",
        "review": "review",
        "verifier": "review",
        "reviewer": "review",
        "research": "research",
        "rag-research": "research",
        # mw-vision-role T-01: parity sync with mw_common.TASK_TYPE_TO_ROLE
        # and dispatch-models.ts DISPATCH_ROLE_BY_TYPE.
        "vision": "vision",
    }

    def test_role_map_matches_ts_mirror(self) -> None:
        assert mw_common.TASK_TYPE_TO_ROLE == self._TS_ROLE_BY_TYPE
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


class TestModelOverrideEvidence:
    """mw-dispatch-role-escape AC-009/VC-009: a task.md `model:` that beats a
    configured role default leaves a greppable launcher.log line, and the
    spawn still uses the explicit value."""

    class _FakeProc:
        pid = 4242
        returncode = None

    def test_note_only_for_a_deviating_task_model(self, tmp_path: pathlib.Path) -> None:
        root = _project(
            tmp_path,
            task_body="type: coding\nmodel: timi/gpt-5.6-sol\ndo\n",
            dispatch_yml="models:\n  coding: timi/deepseek-v4.1-flash\n",
        )
        task = root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md"
        entry = _entry(task)
        note = launcher._model_override_note(entry, root, "timi/gpt-5.6-sol", "task")
        assert "model-override task=timi/gpt-5.6-sol config:coding=timi/deepseek-v4.1-flash" in note

        # Equal to the role default, non-task source, or no config: silent.
        assert launcher._model_override_note(entry, root, "timi/deepseek-v4.1-flash", "task") == ""
        assert launcher._model_override_note(entry, root, "timi/gpt-5.6-sol", "config:coding") == ""
        bare = _project(tmp_path / "bare", task_body="type: coding\nmodel: timi/gpt-5.6-sol\ndo\n")
        bare_entry = _entry(bare / ".agenticdoc" / "k" / "workers" / "t1" / "task.md")
        assert launcher._model_override_note(bare_entry, bare, "timi/gpt-5.6-sol", "task") == ""

        # A review task compares against the review role, not coding.
        review = _project(
            tmp_path / "rev",
            task_body="type: review\nmodel: timi/gpt-5.6-sol\ndo\n",
            dispatch_yml="models:\n  coding: timi/deepseek-v4.1-flash\n  review: timi/gpt-5.6-luna\n",
        )
        review_entry = _entry(review / ".agenticdoc" / "k" / "workers" / "t1" / "task.md")
        review_note = launcher._model_override_note(review_entry, review, "timi/gpt-5.6-sol", "task")
        assert "config:review=timi/gpt-5.6-luna" in review_note

    def test_spawn_prints_the_override_and_keeps_the_explicit_model(
        self, tmp_path: pathlib.Path, creds: dict, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = _project(
            tmp_path,
            task_body="type: coding\nmodel: timi/gpt-5.6-sol\ndo\n",
            dispatch_yml="models:\n  coding: timi/deepseek-v4.1-flash\n",
        )
        monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / "pi.CMD"))
        captured: dict = {}

        def fake_popen(cmd, **kwargs):  # noqa: ANN001, ANN202
            captured["cmd"] = cmd
            return TestModelOverrideEvidence._FakeProc()

        monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
        entry = _entry(root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md")
        launcher._spawn(entry, root, creds, {})
        out = capsys.readouterr().out
        assert "source=task" in out
        assert "model-override task=timi/gpt-5.6-sol config:coding=timi/deepseek-v4.1-flash" in out
        assert "gpt-5.6-sol" in captured["cmd"]  # explicit value still wins


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


def _model_args(project: pathlib.Path, action: str, role: str = "", value: str = "",
                *, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), model_action=action, role=role, value=value, force=force,
    )


def _emit_verify(capsys: pytest.CaptureFixture[str], line: str) -> None:
    """Print a [VERIFY] line for quality-gate extraction, bypassing pytest capture."""
    with capsys.disabled():
        print(line, flush=True)


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


class TestModelSetVisionCapability:
    """T-11: the `vision` role refuses images=no models at config time, stays
    fail-open on "unknown", and exposes a --force escape hatch. The probe is
    injected through mw_common.model_images (seam style: test_serve_doctor)."""

    _VISION_YES = "timi/deepseek-v4-flash-vision-exp"
    _VISION_NO = "timi/glm-5.3"

    @staticmethod
    def _stub(monkeypatch: pytest.MonkeyPatch, verdict: str) -> None:
        monkeypatch.setattr(mw_common, "model_images", lambda value, **_kw: verdict)

    @staticmethod
    def _probe_must_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(value, **_kw):  # noqa: ANN001, ANN202
            raise AssertionError(f"probe must not run for {value!r}")

        monkeypatch.setattr(mw_common, "model_images", boom)

    def test_no_refusal_leaves_dispatch_yml_byte_identical(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = _project(tmp_path, dispatch_yml="models:\n  coding: timi/glm-5.3\n")
        yml = root / ".mw" / "dispatch.yml"
        before = yml.read_bytes()
        self._stub(monkeypatch, "no")

        rc = mw.cmd_model(_model_args(root, "set", "vision", self._VISION_NO))

        assert rc != 0
        assert yml.read_bytes() == before
        err = capsys.readouterr().err
        assert "images" in err
        assert "mw model set vision" in err and "--force" in err

    def test_yes_writes_vision_role(self, tmp_path: pathlib.Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
        root = _project(tmp_path)
        self._stub(monkeypatch, "yes")
        assert mw.cmd_model(_model_args(root, "set", "vision", self._VISION_YES)) == 0
        config, err = mw_common.load_dispatch_config(root)
        assert err is None
        assert config["models"]["vision"] == self._VISION_YES

    def test_unknown_writes_with_skip_hint(self, tmp_path: pathlib.Path,
                                           monkeypatch: pytest.MonkeyPatch,
                                           capsys: pytest.CaptureFixture[str]) -> None:
        root = _project(tmp_path)
        self._stub(monkeypatch, "unknown")
        assert mw.cmd_model(_model_args(root, "set", "vision", self._VISION_NO)) == 0
        config, _ = mw_common.load_dispatch_config(root)
        assert config["models"]["vision"] == self._VISION_NO
        out = capsys.readouterr().out
        assert "skip" in out and "unknown" in out

    def test_force_skips_the_probe(self, tmp_path: pathlib.Path,
                                   monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
        root = _project(tmp_path)
        self._probe_must_not_run(monkeypatch)
        assert mw.cmd_model(_model_args(root, "set", "vision", self._VISION_NO, force=True)) == 0
        config, _ = mw_common.load_dispatch_config(root)
        assert config["models"]["vision"] == self._VISION_NO
        assert "--force" in capsys.readouterr().out

    def test_force_on_non_vision_role_is_rejected(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _project(tmp_path, dispatch_yml="models:\n  review: timi/glm-5.3-air\n")
        yml = root / ".mw" / "dispatch.yml"
        before = yml.read_bytes()
        self._probe_must_not_run(monkeypatch)
        assert mw.cmd_model(_model_args(root, "set", "coding", "timi/glm-5.3", force=True)) != 0
        assert yml.read_bytes() == before

    def test_other_roles_never_probe(self, tmp_path: pathlib.Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
        root = _project(tmp_path)
        self._probe_must_not_run(monkeypatch)
        for role in ("main", "coding", "review", "research"):
            assert mw.cmd_model(_model_args(root, "set", role, "timi/glm-5.3")) == 0, role
        config, _ = mw_common.load_dispatch_config(root)
        assert set(config["models"]) == {"main", "coding", "review", "research"}

    def test_verify_vc001(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
                          capsys: pytest.CaptureFixture[str]) -> None:
        self._stub(monkeypatch, "yes")
        rc = mw.cmd_model(_model_args(tmp_path, "set", "vision", self._VISION_YES))
        config, _ = mw_common.load_dispatch_config(tmp_path)
        assert rc == 0 and config["models"]["vision"] == self._VISION_YES
        _emit_verify(capsys, f"[VERIFY] VC-001: vision={self._VISION_YES} rc={rc}")

    def test_verify_vc002(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
                          capsys: pytest.CaptureFixture[str]) -> None:
        roles = len(mw_common.DISPATCH_ROLES)
        assert roles == 5 and "vision" in mw_common.DISPATCH_ROLES
        monkeypatch.setattr(sys, "argv", [
            "mw", "model", "set", "--project", str(tmp_path), "villain", "timi/x",
        ])
        with pytest.raises(SystemExit) as exc:
            mw._parse_args()
        assert exc.value.code != 0
        _emit_verify(capsys, f"[VERIFY] VC-002: rc=nonzero roles={roles}")

    def test_verify_vc013(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
                          capsys: pytest.CaptureFixture[str]) -> None:
        root = _project(tmp_path, dispatch_yml="models:\n  coding: timi/glm-5.3\n")
        yml = root / ".mw" / "dispatch.yml"
        before = yml.read_bytes()
        self._stub(monkeypatch, "no")
        no_rc = mw.cmd_model(_model_args(root, "set", "vision", self._VISION_NO))
        unchanged = yml.read_bytes() == before
        self._probe_must_not_run(monkeypatch)
        force_rc = mw.cmd_model(_model_args(root, "set", "vision", self._VISION_NO, force=True))
        assert no_rc != 0 and unchanged and force_rc == 0
        _emit_verify(
            capsys,
            f"[VERIFY] VC-013: no_rc={no_rc} yml_unchanged={str(unchanged).lower()} "
            f"force_rc={force_rc}",
        )


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


class TestDoctorImagesCapability:
    """T-12 (AC-010 / AC-015): the dispatch capability column is probed only
    when roles are configured, `no` lands in suggestions (never issues, which
    would flip summary.healthy and doctor exit 1), and all three verdicts keep
    doctor exit code 0. The probe is injected through mw_common.model_images
    (in-process seam, same style as the T-11 cases above); a real subprocess
    cannot be monkeypatched, so test_serve_doctor covers only the skip branch."""

    _DISPATCH = "models:\n  coding: timi/glm-5.3\n  vision: timi/deepseek-v4-flash-vision-exp\n"

    @staticmethod
    def _stub(monkeypatch: pytest.MonkeyPatch, verdict: str) -> None:
        monkeypatch.setattr(mw_common, "model_images", lambda value, **_kw: verdict)

    @staticmethod
    def _doctor_rc(root: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> int:
        # Keep the unrelated RAG/network section out of this hermetic test and
        # scope pi_shell to a per-test agent dir; a live service (this pytest
        # process) leaves the dispatch verdict as the only healthy/exit lever.
        monkeypatch.setattr(mw, "_doctor_rag", lambda project_dir: {"exists": False})
        monkeypatch.setenv(mw_common.AGENT_DIR_ENV, str(root / "pi-agent"))
        providers = root / "providers.json"
        providers.write_text(json.dumps(_HERMETIC_CONFIG), encoding="utf-8")
        (root / ".mw").mkdir(exist_ok=True)
        mw_common.pid_file(root).write_text(str(os.getpid()), encoding="utf-8")
        return mw.cmd_doctor(
            argparse.Namespace(
                project=str(root), providers=str(providers), json=True,
                fix=False, stale_after=90,
            )
        )

    def test_no_is_a_suggestion_not_an_issue(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = _project(tmp_path, dispatch_yml=self._DISPATCH)
        self._stub(monkeypatch, "no")
        rc = self._doctor_rc(root, monkeypatch)
        report = json.loads(capsys.readouterr().out)
        assert report["dispatch"]["images"] == {"coding": "no", "vision": "no"}
        summary = report["summary"]
        assert not summary["issues"]
        # T-15 (AC-010): the verdict is scoped to the `vision` role, so the
        # text role `coding` (images=no) must stay silent - exactly one image
        # suggestion, and it is the vision one.
        image_suggestions = [s for s in summary["suggestions"] if "images=no" in s]
        assert len(image_suggestions) == 1, summary["suggestions"]
        assert image_suggestions[0].startswith("dispatch role vision")
        assert not any(s.startswith("dispatch role coding") for s in summary["suggestions"])
        assert "images=no" in mw_common.format_doctor_text(report)
        assert rc == 0

    def test_other_roles_silent_when_vision_unconfigured(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """T-15 regression: with no `vision` role configured, text roles whose
        models report images=no must not produce an image suggestion (they do
        not need image input), while the AC-015 column keeps them visible."""
        root = _project(
            tmp_path,
            dispatch_yml="models:\n  coding: timi/glm-5.3\n  review: timi/glm-5.3\n",
        )
        self._stub(monkeypatch, "no")
        rc = self._doctor_rc(root, monkeypatch)
        report = json.loads(capsys.readouterr().out)
        assert report["dispatch"]["images"] == {"coding": "no", "review": "no"}
        summary = report["summary"]
        assert not any("mw model set vision" in s for s in summary["suggestions"])
        assert not summary["issues"]
        assert rc == 0, summary

    def test_three_states_keep_doctor_rc_zero(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        states: list[str] = []
        for verdict, state in (("no", "suggestion"), ("yes", "ok"), ("unknown", "skip")):
            root = tmp_path / verdict
            root.mkdir()
            _project(root, dispatch_yml=self._DISPATCH)
            self._stub(monkeypatch, verdict)
            rc = self._doctor_rc(root, monkeypatch)
            report = json.loads(capsys.readouterr().out)
            summary = report["summary"]
            assert report["dispatch"]["images"] == {"coding": verdict, "vision": verdict}
            assert not summary["issues"]
            if verdict == "no":
                assert any("mw model set vision" in s for s in summary["suggestions"])
            else:
                assert not any("images" in s for s in summary["suggestions"])
            assert f"images={verdict}" in mw_common.format_doctor_text(report)
            assert rc == 0, (verdict, report["summary"])
            states.append(state)
        _emit_verify(capsys, f"[VERIFY] VC-010: doctor_rc=0 states={','.join(states)}")

    def test_model_show_every_role_line_has_images(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        root = _project(
            tmp_path,
            dispatch_yml="models:\n  coding: timi/glm-5.3\n",
            window_model="claude/claude-sonnet-5",
        )
        seen: list[str] = []
        for verdict in ("yes", "no", "unknown"):
            self._stub(monkeypatch, verdict)
            assert mw.cmd_model(_model_args(root, "show")) == 0
            out = capsys.readouterr().out
            role_lines = [
                line for line in out.splitlines()
                if line.split(":", 1)[0] in mw_common.DISPATCH_ROLES
            ]
            assert len(role_lines) == len(mw_common.DISPATCH_ROLES)
            for line in role_lines:
                assert f"images={verdict}" in line, line
            seen.append(verdict)
        _emit_verify(capsys, f"[VERIFY] VC-015: show_images={'/'.join(seen)} rc=0")


# ── vision role resolution ────────────────────────────────────────────────────


class TestVisionRoleResolution:
    """mw-vision-role T-18 (AC-003 / VC-003): a `type: vision` task.md resolves
    to the configured `vision` role default (`source=config:vision`), and a
    task.md `model:` line still wins (`source=task`). The task type/model are
    read through the launcher's real parser so the assertion tracks what the
    dispatch chain actually sees, not a hand-passed stand-in."""

    _VISION = "timi/deepseek-v4-flash-vision-exp"
    _OVERRIDE = "timi/glm-5.3"
    _DISPATCH = f"models:\n  vision: {_VISION}\n  coding: timi/placeholder\n"

    @staticmethod
    def _resolve_task(root: pathlib.Path) -> tuple[str, str, str, str]:
        task = root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md"
        task_type, task_model = launcher._read_task_md_fields(str(task))
        config, err = mw_common.load_dispatch_config(root)
        assert err is None
        value, source = mw_common.resolve_dispatch_model(
            cli="pi",
            task_type=task_type,
            entry_model=task_model,
            config_models=config.get("models", {}),
            window_model=mw_common.read_window_model(root),
        )
        return task_type, task_model, value, source

    def test_verify_vc003(self, tmp_path: pathlib.Path,
                          capsys: pytest.CaptureFixture[str]) -> None:
        root = _project(
            tmp_path,
            task_body="type: vision\ninspect the screenshot\n",
            dispatch_yml=self._DISPATCH,
        )
        task_type, task_model, value, source = self._resolve_task(root)
        assert task_type == "vision" and task_model == ""
        assert (value, source) == (self._VISION, "config:vision")

        (root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md").write_text(
            f"type: vision\nmodel: {self._OVERRIDE}\ninspect\n", encoding="utf-8")
        task_type, task_model, value, source = self._resolve_task(root)
        assert task_model == self._OVERRIDE
        assert (value, source) == (self._OVERRIDE, "task")

        _emit_verify(capsys, "[VERIFY] VC-003: source=config:vision task_override=task")

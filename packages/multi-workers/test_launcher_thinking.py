"""test_launcher_thinking.py — mw-worker-thinking W2 launcher wiring tests.

Fully offline (VC-001..004, AC-001..004): every ``_spawn`` / ``_dry_run`` test
installs a fake ``subprocess.Popen`` and mocks CLI addressing (``shutil.which``),
so no real pi/claude/codex process is ever started and no paid API call can
happen. The policy helper (W1 ``worker_thinking.resolve_worker_thinking``) is
the REAL one reading real ``<control root>/.mw/dispatch.yml`` fixtures; only the
process boundary is faked. Nothing is written outside pytest's ``tmp_path``.

Coverage notes demanded by the card:
  * fake Popen: ``fake_popen`` fixture captures every argv; asserts no real
    process is launched (also for _dry_run).
  * control root: ``test_control_root_not_worker_cwd`` forces ``_worker_cwd``
    to a DIFFERENT game root with a conflicting dispatch.yml and spies the
    resolver's ``project_dir`` — proving the policy is read from the control
    project, never the worker cwd.
  * fallback: ``test_fallback_model_override_still_applies_thinking`` proves
    the ``model_override`` re-dispatch path goes through the same policy read.
"""
from __future__ import annotations

import copy
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher
import worker_thinking
from launcher import _build_command, _dry_run, _spawn, _starter_prompt

LEVELS = worker_thinking.THINKING_LEVELS

# Hermetic credential config (env-only sources), mirroring test_launcher.py.
# `toa` is added so the direct toa/hy4 pi route can be spawned end-to-end.
_HERMETIC_CONFIG = {
    "credentials": {
        "anthropic": {"sources": [{"env": "ANTHROPIC_API_KEY"}]},
        "anthropic-auth": {"sources": [{"env": "ANTHROPIC_AUTH_TOKEN"}]},
        "deepseek": {"sources": [{"env": "DEEPSEEK_API_KEY"}]},
        "timi": {"sources": [{"env": "TIMI_API_KEY"}]},
        "toa": {"sources": [{"env": "TOA_API_KEY"}]},
        "zai-coding-cn": {"sources": [{"env": "ZAI_CODING_CN_API_KEY"}]},
    },
    "providers": {
        "claude": {"port": 7001, "base_url_env": "ANTHROPIC_BASE_URL",
                   "api_key_env": "ANTHROPIC_API_KEY", "credential": "anthropic"},
        "claude-cli": {"port": 7003, "base_url_env": "ANTHROPIC_BASE_URL",
                       "api_key_env": "ANTHROPIC_AUTH_TOKEN", "credential": "anthropic-auth"},
        "deepseek": {"port": 7004, "base_url_env": "DEEPSEEK_BASE_URL",
                     "api_key_env": "DEEPSEEK_API_KEY", "credential": "deepseek"},
        "timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"},
        "toa": {"api_key_env": "TOA_API_KEY", "credential": "toa"},
        "zai-coding-cn": {"api_key_env": "ZAI_CODING_CN_API_KEY", "credential": "zai-coding-cn"},
    },
}


def _entry(task: pathlib.Path, **overrides) -> dict[str, str]:
    entry = {
        "cli": "pi", "provider": "timi", "task_path": str(task),
        "task_key": "t1", "status": "pending",
        "dispatched_at": "2026-11-10T00:00:00+00:00",
        "updated_at": "2026-11-10T00:00:00+00:00",
        "model": "",
    }
    entry.update(overrides)
    return entry


def _project(
    root: pathlib.Path,
    *,
    task_body: str = "type: coding\n\nDo it.\n",
    dispatch_yml: str | None = None,
    entry_kwargs: dict | None = None,
) -> tuple[pathlib.Path, dict[str, str]]:
    task = root / ".agenticdoc" / "k" / "workers" / "t1" / "task.md"
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(task_body, encoding="utf-8")
    if dispatch_yml is not None:
        (root / ".mw").mkdir(exist_ok=True)
        (root / ".mw" / "dispatch.yml").write_text(dispatch_yml, encoding="utf-8")
    entry = _entry(task, **(entry_kwargs or {}))
    queue = root / ".agenticdoc" / "_workers.parallel"
    queue.write_text(launcher._serialize_entry(entry) + "\n", encoding="utf-8")
    return task, entry


class _FakeProc:
    pid = 4242
    returncode = None

    def poll(self) -> None:
        return None


@pytest.fixture()
def task_file(tmp_path: pathlib.Path) -> pathlib.Path:
    t = tmp_path / "task.md"
    t.write_text("type: coding\n\nDo it.\n", encoding="utf-8")
    return t


@pytest.fixture()
def creds(monkeypatch: pytest.MonkeyPatch) -> dict:
    for name, value in {
        "TIMI_API_KEY": "timi-test", "TOA_API_KEY": "toa-test",
        "ANTHROPIC_API_KEY": "anthropic-test", "ANTHROPIC_AUTH_TOKEN": "auth-test",
        "DEEPSEEK_API_KEY": "deepseek-test", "ZAI_CODING_CN_API_KEY": "zai-test",
    }.items():
        monkeypatch.setenv(name, value)
    for gone in ("ANTHROPIC_BASE_URL", "DEEPSEEK_BASE_URL", "TIMI_BASE_URL",
                 "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(gone, raising=False)
    return copy.deepcopy(_HERMETIC_CONFIG)


@pytest.fixture()
def fake_popen(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> dict:
    """Mock CLI addressing + Popen; record every argv. No real pi process/cost."""
    captured: dict = {"cmds": []}
    monkeypatch.setattr(launcher.shutil, "which", lambda name: str(tmp_path / f"{name}.CMD"))

    def _popen(cmd, **kwargs):  # noqa: ANN001, ANN202
        captured["cmd"] = list(cmd)
        captured["cmds"].append(list(cmd))
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(launcher.subprocess, "Popen", _popen)
    # Usage ledger is machine-level / global state; keep the test hermetic.
    monkeypatch.setattr(launcher, "_usage_start", lambda *a, **k: None)
    return captured


def _thinking_values(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, tok in enumerate(cmd)
            if tok == "--thinking" and i + 1 < len(cmd)]


# ── _build_command: three pi routes, exact argv ──────────────────────────────

class TestBuildCommandPiRoutes:
    """VC-001/VC-002: exactly one --thinking LEVEL before -p on every pi route."""

    def test_timi_route(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        starter = _starter_prompt(str(task_file))
        assert _build_command(entry, thinking="high") == [
            "pi", "--provider", "timi", "--model", "glm-5.3",
            "--thinking", "high", "-p", starter,
        ]
        assert _thinking_values(_build_command(entry, thinking="high")) == ["high"]

    def test_direct_route_toa_hy4(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "pi", "provider": "toa", "model": "hy4",
                 "task_path": str(task_file)}
        starter = _starter_prompt(str(task_file))
        assert _build_command(entry, thinking="high") == [
            "pi", "--provider", "toa", "--model", "hy4",
            "--thinking", "high", "-p", starter,
        ]
        assert _thinking_values(_build_command(entry, thinking="off")) == ["off"]

    @pytest.mark.parametrize("model", ["", "glm-5.3"])
    def test_no_provider_route(self, task_file: pathlib.Path, model: str) -> None:
        entry = {"cli": "pi", "provider": "", "model": model,
                 "task_path": str(task_file)}
        starter = _starter_prompt(str(task_file))
        head = ["pi"] + (["--model", model] if model else [])
        assert _build_command(entry, thinking="high") == [
            *head, "--thinking", "high", "-p", starter,
        ]

    def test_all_valid_levels_pass_through_exactly_once(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        for level in LEVELS:  # includes off — never dropped by a truthiness shortcut
            cmd = _build_command(entry, thinking=level)
            assert _thinking_values(cmd) == [level]
            idx = cmd.index("--thinking")
            assert cmd[idx - 1] == "glm-5.3" or cmd[idx - 1] == "--model"
            assert cmd.index("-p") > idx  # --thinking before -p

    def test_off_not_dropped(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        assert _thinking_values(_build_command(entry, thinking="off")) == ["off"]

    def test_session_id_position_and_once(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        starter = _starter_prompt(str(task_file))
        assert _build_command(entry, session_id="sid-1", thinking="high") == [
            "pi", "--provider", "timi", "--model", "glm-5.3",
            "--thinking", "high", "--session-id", "sid-1", "-p", starter,
        ]
        assert _thinking_values(_build_command(entry, session_id="sid-1", thinking="high")) == ["high"]

    @pytest.mark.parametrize("route", [
        {"cli": "pi", "provider": "timi"},
        {"cli": "pi", "provider": "toa", "model": "hy4"},
        {"cli": "pi", "provider": "", "model": "glm-5.3"},
        {"cli": "pi", "provider": ""},
    ])
    @pytest.mark.parametrize("sid", [None, "sid-xyz"])
    def test_none_keeps_historical_argv_byte_for_byte(
        self, task_file: pathlib.Path, route: dict, sid: str | None
    ) -> None:
        entry = {**route, "task_path": str(task_file)}
        if route["provider"] == "timi":
            historical = ["pi", "--provider", "timi", "--model", "glm-5.3"]
        elif route["provider"] == "toa":
            historical = ["pi", "--provider", "toa", "--model", "hy4"]
        else:
            historical = ["pi"]
            if route.get("model"):
                historical += ["--model", route["model"]]
        if sid is not None:
            historical += ["--session-id", sid]
        historical += ["-p", _starter_prompt(str(task_file))]
        assert _build_command(entry, session_id=sid) == historical
        assert _build_command(entry, session_id=sid, thinking=None) == historical
        assert "--thinking" not in historical


# ── _build_command: non-pi never gets the flag ───────────────────────────────

class TestBuildCommandNonPi:
    @pytest.mark.parametrize(("cli", "provider", "model"), [
        ("codex", "", "gpt-5.6-sol"),
        ("claude", "", "claude-sonnet"),
        ("customcli", "", "x"),
    ])
    def test_nonpi_ignores_thinking(self, task_file: pathlib.Path, cli: str,
                                    provider: str, model: str) -> None:
        entry = {"cli": cli, "provider": provider, "model": model,
                 "task_path": str(task_file)}
        assert _build_command(entry, thinking="high") == _build_command(entry)
        assert "--thinking" not in _build_command(entry, thinking="high")

    def test_nonpi_even_ignores_an_invalid_level(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "codex", "provider": "", "task_path": str(task_file)}
        assert "--thinking" not in _build_command(entry, thinking="not-a-level")


# ── _build_command: reject invalid thinking, no duplication/injection ─────────

class TestBuildCommandRejectsInvalidThinking:
    @pytest.mark.parametrize("bad", [
        "HIGH", "bogus", "", "high ", " high", "high --model evil",
        "--provider", "off extra", 0, 1, False, True, ["high"], {"x": 1},
    ])
    def test_invalid_value_is_rejected_not_injected(
        self, task_file: pathlib.Path, bad: object
    ) -> None:
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        with pytest.raises(ValueError):
            _build_command(entry, thinking=bad)  # type: ignore[arg-type]

    def test_duplicate_flag_refused(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            launcher._pi_argv_with_thinking(["pi", "--thinking", "high", "-p", "x"], "low")

    def test_no_flag_injection_via_value(self, task_file: pathlib.Path) -> None:
        entry = {"cli": "pi", "provider": "timi", "task_path": str(task_file)}
        with pytest.raises(ValueError):
            _build_command(entry, thinking="high; rm -rf")
        # A valid level never smuggles extra tokens: argv grows by exactly 2.
        base = _build_command(entry)
        wired = _build_command(entry, thinking="high")
        assert len(wired) == len(base) + 2
        assert wired == [*base[:base.index("-p")], "--thinking", "high", *base[base.index("-p"):]]


# ── _spawn: real call consumes the real policy (fake process boundary) ────────

class TestSpawnWiring:
    def test_default_high_consumed_and_model_source_intact(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _task, entry = _project(tmp_path, dispatch_yml="thinking:\n  default: high\n")
        _spawn(entry, tmp_path, creds, {})
        cmd = fake_popen["cmd"]
        assert _thinking_values(cmd) == ["high"]
        assert cmd.index("--thinking") < cmd.index("-p")
        out = capsys.readouterr().out
        assert "thinking=high thinking-source=config:default" in out
        # Original model line is a separate line and keeps its `source=`.
        model_lines = [ln for ln in out.splitlines() if "model=" in ln and "thinking" not in ln]
        assert model_lines and "source=" in model_lines[0]

    def test_role_override_wins_and_off_consumed(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = "thinking:\n  default: high\n  roles:\n    research: \"off\"\n"
        _task, entry = _project(tmp_path, task_body="type: research\n\nDo it.\n",
                                dispatch_yml=cfg)
        _spawn(entry, tmp_path, creds, {})
        assert _thinking_values(fake_popen["cmd"]) == ["off"]
        assert "thinking=off thinking-source=config:research" in capsys.readouterr().out

    @pytest.mark.parametrize("dispatch_yml", [None, "models:\n  coding: timi/glm-5.3\n"])
    def test_unset_config_keeps_native_default(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        capsys: pytest.CaptureFixture[str], dispatch_yml: str | None,
    ) -> None:
        _task, entry = _project(tmp_path, dispatch_yml=dispatch_yml)
        _spawn(entry, tmp_path, creds, {})
        assert "--thinking" not in fake_popen["cmd"]
        assert "thinking=native default thinking-source=unset" in capsys.readouterr().out

    @pytest.mark.parametrize("bad_cfg", [
        "thinking:\n  default: bogus\n",                    # unknown level
        "thinking:\n  default: off\n",                       # YAML off -> False
        "thinking:\n  roles:\n    main: high\n",             # unknown/disallowed role
        "thinking:\n  unknown_key: high\n",                  # unknown key
        "- not-a-mapping\n",                                 # non-mapping top level
    ])
    def test_invalid_config_warns_and_does_not_inject(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        capsys: pytest.CaptureFixture[str], bad_cfg: str,
    ) -> None:
        _task, entry = _project(tmp_path, dispatch_yml=bad_cfg)
        _spawn(entry, tmp_path, creds, {})
        captured = capsys.readouterr()
        assert "--thinking" not in fake_popen["cmd"]  # spawn still succeeded
        assert "thinking config invalid" in captured.err
        assert "thinking=native default thinking-source=invalid" in captured.out

    def test_header_alias_and_body_type_do_not_flip(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
    ) -> None:
        # header alias rag-research -> research bucket; a body `type: coding`
        # must NOT override the header; a BOM prefix must not hide it.
        body = "\ufefftype: rag-research\n\n## body\n\ntype: coding\n"
        cfg = "thinking:\n  default: high\n  roles:\n    research: \"off\"\n"
        _task, entry = _project(tmp_path, task_body=body, dispatch_yml=cfg)
        _spawn(entry, tmp_path, creds, {})
        assert _thinking_values(fake_popen["cmd"]) == ["off"]  # research, not coding

    def test_body_type_only_does_not_flip_to_role(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
    ) -> None:
        # No header `type:`; the only `type:` line is in the body -> unknown
        # task type falls back to the coding bucket (default high), NOT research.
        body = "context line\n\ntype: research\n"
        cfg = "thinking:\n  default: high\n  roles:\n    research: \"off\"\n"
        _task, entry = _project(tmp_path, task_body=body, dispatch_yml=cfg)
        _spawn(entry, tmp_path, creds, {})
        assert _thinking_values(fake_popen["cmd"]) == ["high"]

    def test_bom_header_still_resolves_default(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
    ) -> None:
        body = "\ufefftype: coding\n\nDo it.\n"
        _task, entry = _project(tmp_path, task_body=body,
                                dispatch_yml="thinking:\n  default: high\n")
        _spawn(entry, tmp_path, creds, {})
        assert _thinking_values(fake_popen["cmd"]) == ["high"]

    def test_consecutive_spawns_reread_config(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
    ) -> None:
        _task, entry = _project(tmp_path, dispatch_yml="thinking:\n  default: high\n")
        cfg_path = tmp_path / ".mw" / "dispatch.yml"
        _spawn(entry, tmp_path, creds, {})                       # high
        cfg_path.write_text("thinking:\n  default: \"off\"\n", encoding="utf-8")
        _spawn(entry, tmp_path, creds, {})                       # off (re-read)
        cfg_path.write_text("models:\n  coding: timi/glm-5.3\n", encoding="utf-8")
        _spawn(entry, tmp_path, creds, {})                       # unset (re-read)
        assert [_thinking_values(c) for c in fake_popen["cmds"]] == [["high"], ["off"], []]

    def test_direct_toa_hy4_spawn_wires_thinking(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
    ) -> None:
        # Model resolution maps toa/hy4 -> direct provider 'toa'; thinking must
        # still be injected on that route (with the model unchanged).
        cfg = "models:\n  coding: toa/hy4\nthinking:\n  default: high\n"
        _task, entry = _project(tmp_path, dispatch_yml=cfg)
        _spawn(entry, tmp_path, creds, {})
        cmd = fake_popen["cmd"]
        assert cmd[1:5] == ["--provider", "toa", "--model", "hy4"]
        assert _thinking_values(cmd) == ["high"]

    def test_fallback_model_override_still_applies_thinking(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _task, entry = _project(tmp_path, dispatch_yml="thinking:\n  default: high\n")
        _spawn(entry, tmp_path, creds, {}, model_override="glm-5.3")
        cmd = fake_popen["cmd"]
        assert _thinking_values(cmd) == ["high"]
        assert cmd[cmd.index("--model") + 1] == "glm-5.3"
        assert "source=fallback" in capsys.readouterr().out

    def test_control_root_not_worker_cwd(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = tmp_path / "control"
        _task, entry = _project(root, dispatch_yml="thinking:\n  default: high\n")
        game = tmp_path / "game"
        (game / ".mw").mkdir(parents=True)
        (game / ".mw" / "dispatch.yml").write_text(
            "thinking:\n  default: \"off\"\n", encoding="utf-8")
        monkeypatch.setattr(launcher, "_worker_cwd", lambda *a, **k: game)

        seen: dict = {}
        real = worker_thinking.resolve_worker_thinking

        def spy(project_dir, task_type):  # noqa: ANN001, ANN202
            seen["project_dir"] = pathlib.Path(project_dir)
            seen["task_type"] = task_type
            return real(project_dir, task_type)

        monkeypatch.setattr(launcher, "resolve_worker_thinking", spy)
        _spawn(entry, root, creds, {})
        assert seen["project_dir"] == root          # control project, not game root
        assert seen["task_type"] == "coding"
        assert _thinking_values(fake_popen["cmd"]) == ["high"]  # control value wins

    def test_nonpi_spawn_does_not_inject_even_with_config(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
    ) -> None:
        _task, entry = _project(tmp_path, dispatch_yml="thinking:\n  default: high\n",
                                entry_kwargs={"cli": "codex", "provider": ""})
        _spawn(entry, tmp_path, creds, {})
        assert "--thinking" not in fake_popen["cmd"]
        assert fake_popen["cmd"][:2] == [str(tmp_path / "codex.CMD"), "exec"]


# ── _resolve_spawn_thinking: fail-soft against a broken resolver ─────────────

class TestResolveSpawnThinkingFailSoft:
    def test_invalid_level_from_resolver_is_sanitized(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            launcher, "resolve_worker_thinking",
            lambda project_dir, task_type: ("bogus-level", "config:default", None),
        )
        _task, entry = _project(tmp_path)
        level, source = launcher._resolve_spawn_thinking(tmp_path, entry)
        assert level is None and source == "invalid"
        assert "unsupported thinking level" in capsys.readouterr().err
        # The sanitized None never reaches _build_command as an invalid value.
        assert "--thinking" not in _build_command(entry, thinking=level)

    def test_resolver_exception_is_fail_soft(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def boom(project_dir, task_type):  # noqa: ANN001, ANN202
            raise RuntimeError("policy exploded")

        monkeypatch.setattr(launcher, "resolve_worker_thinking", boom)
        _task, entry = _project(tmp_path)
        assert launcher._resolve_spawn_thinking(tmp_path, entry) == (None, "error")
        assert "thinking policy unavailable" in capsys.readouterr().err


# ── _dry_run: syncs the real config into the displayed argv ──────────────────

class TestDryRunWiring:
    def test_dry_run_wires_configured_level_and_spawns_nothing(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _project(tmp_path, dispatch_yml="thinking:\n  default: high\n")
        _dry_run(tmp_path, creds)
        out = capsys.readouterr().out
        dr_lines = [ln for ln in out.splitlines() if ln.startswith("[DRY-RUN]")]
        assert dr_lines and "--thinking high" in dr_lines[0]
        assert "thinking=high thinking-source=config:default" in out
        assert not fake_popen["cmds"]  # dry-run never launches a process

    def test_dry_run_role_off(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        cfg = "thinking:\n  default: high\n  roles:\n    research: \"off\"\n"
        _project(tmp_path, task_body="type: research\n\nDo it.\n", dispatch_yml=cfg)
        _dry_run(tmp_path, creds)
        out = capsys.readouterr().out
        assert "--thinking off" in out
        assert "thinking=off thinking-source=config:research" in out

    def test_dry_run_invalid_warns_no_injection(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _project(tmp_path, dispatch_yml="thinking:\n  default: bogus\n")
        _dry_run(tmp_path, creds)
        captured = capsys.readouterr()
        assert "--thinking" not in captured.out
        assert "thinking config invalid" in captured.err
        assert "native default" in captured.out

    def test_dry_run_nonpi_has_no_thinking(
        self, tmp_path: pathlib.Path, creds: dict, fake_popen: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _project(tmp_path, dispatch_yml="thinking:\n  default: high\n",
                 entry_kwargs={"cli": "codex", "provider": ""})
        _dry_run(tmp_path, creds)
        out = capsys.readouterr().out
        assert "--thinking" not in out
        assert "thinking=" not in out
        assert not fake_popen["cmds"]

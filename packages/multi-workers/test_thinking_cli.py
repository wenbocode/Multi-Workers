"""test_thinking_cli.py - `mw thinking` CLI (mw-worker-thinking-command W1).

Offline L1/L2 regression. The primary path is the REAL `python mw.py thinking`
subprocess (argparse + dispatch + `_atomic_write_yml` + cmd_thinking); every
written config is then fed to the EXISTING `worker_thinking.resolve_worker_thinking`
and `launcher._resolve_spawn_thinking`. No real worker, provider, service,
network, or the project's own `.mw/dispatch.yml` is touched (all fixtures live
in pytest `tmp_path`).

Failure injection uses a per-test `sitecustomize.py` on PYTHONPATH, so
read / write / os.replace failures are repeatable in a real subprocess without
adding test hooks to product code. All errors are checked for: nonzero exit,
unchanged original bytes, no temp-file leftovers, no traceback, and no leakage
of config content (SENTINEL).
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

import pytest
import yaml

PACKAGE_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(PACKAGE_DIR))

import launcher
import mw
import mw_common
import thinking_config
import worker_thinking
from worker_thinking import THINKING_LEVELS, THINKING_ROLES, resolve_worker_thinking

MW_PY = PACKAGE_DIR / "mw.py"
SENTINEL = "TOPSECRET-CONFIG-SENTINEL-9b1f"
ROLES = THINKING_ROLES
LEVELS = THINKING_LEVELS

# Nested, non-thinking configuration that must survive every write semantically.
BASELINE = (
    "models:\n"
    "  coding: toa/deepseek-v4.1-flash\n"
    "  main: timi/glm-5.3\n"
    "fallback_models:\n"
    "  coding:\n"
    "    - toa/hy4\n"
    "    - zai/glm-5.3\n"
    "rag:\n"
    "  enabled:\n"
    "    - docs/worker-thinking.md\n"
    "  nested:\n"
    "    retries: 3\n"
    "    labels: [alpha, beta]\n"
    "    unicode: 思考配置\n"
    f"note: {SENTINEL}\n"
)

# Every case embeds SENTINEL in the config: PyYAML parse errors and the existing
# validator diagnostics contain raw source lines / values, so a CLI that echoes
# them would be caught by the global no-leak assertion in `_cli_raw`.
BAD_CONFIGS = [
    f"models: [broken\n{SENTINEL}\n",                              # YAML parse error
    f"- a\n- b\n# {SENTINEL}\n",                                  # top-level list
    f"just a scalar\n# {SENTINEL}\n",                              # top-level scalar
    f"thinking: high\n# {SENTINEL}\n",                             # scalar block
    f"thinking: [high]\n# {SENTINEL}\n",                           # list block
    f"thinking: true\n# {SENTINEL}\n",                             # bool block
    f"thinking:\n# {SENTINEL}\n",                                  # null block
    f"thinking:\n  default: high\n  extra: 1\n# {SENTINEL}\n",     # unknown key
    f"thinking:\n  foo: high\n# {SENTINEL}\n",                     # only unknown key
    f"thinking:\n  roles: oops\n# {SENTINEL}\n",                   # roles not mapping
    f"thinking:\n  roles:\n    main: high\n# {SENTINEL}\n",        # main excluded
    f"thinking:\n  roles:\n    villain: high\n# {SENTINEL}\n",     # unknown role
    f"thinking:\n  default: off\n# {SENTINEL}\n",                  # bool value
    f"thinking:\n  default: null\n# {SENTINEL}\n",                 # None value
    f"thinking:\n  default: {SENTINEL}\n",                         # raw value in diagnostic
    f"thinking:\n  roles:\n    research: [high]\n# {SENTINEL}\n",  # nested value
    f"credentials:\n  api_key: {SENTINEL}\n"
    "thinking:\n  default: high\n  extra: 1\n",                    # credential + bad block
]

FAULT_HOOK = '''\
import builtins
import os
import pathlib

_mode = os.environ.get("MW_THINKING_TEST_FAULT")
_marker = os.environ.get("MW_THINKING_TEST_MARKER", "")

if _mode == "read":
    _orig = pathlib.Path.read_text
    def _read_text(self, *args, **kwargs):
        if _marker in str(self):
            raise OSError("injected read failure")
        return _orig(self, *args, **kwargs)
    pathlib.Path.read_text = _read_text
elif _mode == "write":
    _orig_open = builtins.open
    def _open(file, mode="r", *args, **kwargs):
        if "w" in str(mode) and _marker in str(file):
            raise OSError("injected write failure")
        return _orig_open(file, mode, *args, **kwargs)
    builtins.open = _open
elif _mode == "replace":
    _orig_replace = os.replace
    def _replace(src, dst, *args, **kwargs):
        if _marker in str(dst):
            raise OSError("injected replace failure")
        return _orig_replace(src, dst, *args, **kwargs)
    os.replace = _replace
'''


# ── helpers ───────────────────────────────────────────────────────────────────


def _path(project: pathlib.Path) -> pathlib.Path:
    return mw_common.dispatch_config_path(pathlib.Path(project))


def _config(project: pathlib.Path, text: str, *, encoding: str = "utf-8") -> pathlib.Path:
    path = _path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


def _load(project: pathlib.Path):
    path = _path(project)
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _others(data) -> dict:
    return {key: value for key, value in (data or {}).items() if key != "thinking"}


def _temp_files(project: pathlib.Path) -> list[str]:
    folder = _path(project).parent
    if not folder.exists():
        return []
    return sorted(p.name for p in folder.iterdir() if ".tmp" in p.name)


def _cli_raw(tokens: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, str(MW_PY), "thinking", *tokens],
        capture_output=True, text=True, timeout=60, cwd=PACKAGE_DIR, env=env,
    )
    # Global invariants: no traceback and no config content ever reaches stdout
    # or stderr (even for argparse errors and injected filesystem failures).
    assert "Traceback" not in proc.stderr, proc.stderr
    assert SENTINEL not in proc.stdout + proc.stderr, proc.stdout + proc.stderr
    return proc


def _cli(project: pathlib.Path, *tokens: str, env: dict[str, str] | None = None):
    return _cli_raw([*tokens, f"--project={project}"], env=env)


def _ns(project: pathlib.Path, action: str, target: str | None = None,
        level: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project), thinking_action=action, target=target, level=level
    )


def _writer(path: pathlib.Path, text: str) -> None:
    """Local atomic writer for direct module-level tests (no mw import needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmptest")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _assert_safe_failure(proc, path: pathlib.Path, before: bytes) -> None:
    assert proc.returncode != 0
    assert "Error:" in proc.stderr
    assert path.read_bytes() == before
    assert not _temp_files(path.parent.parent)


def _fault_env(project: pathlib.Path, mode: str) -> dict[str, str]:
    hooks = project / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "sitecustomize.py").write_text(FAULT_HOOK, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(hooks) + os.pathsep + env.get("PYTHONPATH", "")
    env["MW_THINKING_TEST_FAULT"] = mode
    env["MW_THINKING_TEST_MARKER"] = str(_path(project))
    return env


# ── contract / single validator ──────────────────────────────────────────────


def test_thinking_constants_are_shared() -> None:
    assert ROLES == ("coding", "review", "research", "vision", "decide_prepare")
    assert "main" not in ROLES
    assert LEVELS == ("off", "minimal", "low", "medium", "high", "xhigh", "max")
    assert thinking_config.SET_TARGETS == ("default", *ROLES)
    assert thinking_config.CLEAR_TARGETS == ("default", *ROLES, "all")


def test_public_validator_delegates_to_existing_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    marker = "single-validator-marker"
    monkeypatch.setattr(worker_thinking, "_validate_thinking", lambda *a: marker)
    assert worker_thinking.validate_thinking({}, pathlib.Path("x")) == marker


def test_cmd_thinking_calls_existing_validator(monkeypatch: pytest.MonkeyPatch,
                                              tmp_path: pathlib.Path) -> None:
    original = worker_thinking.validate_thinking
    calls: list[object] = []

    def spy(thinking, path):
        calls.append(thinking)
        return original(thinking, path)

    monkeypatch.setattr(worker_thinking, "validate_thinking", spy)
    _config(tmp_path, "thinking:\n  default: high\n")
    assert thinking_config.cmd_thinking(_ns(tmp_path, "set", "review", "low"), _writer) == 0
    assert calls and calls[0] == {"default": "high"}


def test_pm_wrapper_passes_real_atomic_writer(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_thinking(_ns(tmp_path, "set", "vision", "xhigh")) == 0
    assert resolve_worker_thinking(tmp_path, "vision") == ("xhigh", "config:vision", None)
    assert _temp_files(tmp_path) == []


def test_module_writer_receives_complete_serialized_mapping(tmp_path: pathlib.Path) -> None:
    _config(tmp_path, BASELINE)
    seen: list[tuple[pathlib.Path, str]] = []

    def spy(path, text):
        seen.append((path, text))

    assert thinking_config.cmd_thinking(_ns(tmp_path, "set", "default", "off"), spy) == 0
    assert len(seen) == 1
    path, text = seen[0]
    assert path == _path(tmp_path)
    assert "'off'" in text or '"off"' in text
    assert yaml.safe_load(text)["models"] == yaml.safe_load(BASELINE)["models"]
    assert isinstance(yaml.safe_load(text)["thinking"]["default"], str)


def test_invalid_arguments_rejected_before_any_read(tmp_path: pathlib.Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(_project_dir):
        raise AssertionError("load_config must not run for an invalid argument")

    monkeypatch.setattr(thinking_config, "load_config", forbidden)
    for ns in (
        _ns(tmp_path, "set", "main", "high"),
        _ns(tmp_path, "set", "bogus", "high"),
        _ns(tmp_path, "set", "default", "ultra"),
        _ns(tmp_path, "clear", "main"),
        _ns(tmp_path, "clear", "bogus"),
        _ns(tmp_path, "unknown", None, None),
    ):
        assert thinking_config.cmd_thinking(ns, _writer) == 1
    assert not _path(tmp_path).exists()


# ── show (AC-001 / VC-001) ───────────────────────────────────────────────────


def _assert_show_unset(proc) -> None:
    assert proc.returncode == 0
    for role in ROLES:
        assert f"{role}: pi native [unset]" in proc.stdout


def test_show_missing_config_is_read_only(tmp_path: pathlib.Path) -> None:
    proc = _cli(tmp_path, "show")
    _assert_show_unset(proc)
    assert "default: pi native [unset]" in proc.stdout
    assert "config:" in proc.stdout and "dispatch.yml" in proc.stdout
    assert "missing" in proc.stdout
    assert str(pathlib.Path(tmp_path).resolve()).lower() in proc.stdout.lower()
    assert not (tmp_path / ".mw").exists()


def test_bare_thinking_defaults_to_show(tmp_path: pathlib.Path) -> None:
    proc = _cli(tmp_path)
    _assert_show_unset(proc)
    assert "default: pi native [unset]" in proc.stdout
    assert not (tmp_path / ".mw").exists()


def test_show_default_only_sources(tmp_path: pathlib.Path) -> None:
    path = _config(tmp_path, BASELINE + "thinking:\n  default: high\n")
    before = path.read_bytes()
    proc = _cli(tmp_path, "show")
    assert proc.returncode == 0
    assert "default: high [config:default]" in proc.stdout
    for role in ROLES:
        assert f"{role}: high [config:default]" in proc.stdout
    assert path.read_bytes() == before
    assert _temp_files(tmp_path) == []


def test_show_role_override_sources(tmp_path: pathlib.Path) -> None:
    path = _config(
        tmp_path,
        BASELINE + 'thinking:\n  default: high\n  roles:\n    review: "off"\n'
        "    research: minimal\n",
    )
    before = path.read_bytes()
    proc = _cli(tmp_path, "show")
    assert proc.returncode == 0
    assert "default: high [config:default]" in proc.stdout
    assert "review: off [config:review]" in proc.stdout
    assert "research: minimal [config:research]" in proc.stdout
    for role in ("coding", "vision", "decide_prepare"):
        assert f"{role}: high [config:default]" in proc.stdout
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "text,encoding",
    [
        ("", "utf-8"),
        ("# only a comment\n", "utf-8"),
        ("\ufeff# only a comment\n", "utf-8"),
        ("models:\n  coding: toa/x\n", "utf-8-sig"),
    ],
)
def test_show_empty_comment_bom_configs(tmp_path: pathlib.Path, text: str,
                                        encoding: str) -> None:
    path = _config(tmp_path, text, encoding=encoding)
    before = path.read_bytes()
    proc = _cli(tmp_path, "show")
    _assert_show_unset(proc)
    assert path.read_bytes() == before


def test_show_project_before_and_after_subcommand(tmp_path: pathlib.Path) -> None:
    configured = tmp_path / "configured"
    empty = tmp_path / "empty"
    _config(configured, "thinking:\n  default: high\n")
    tail = _cli_raw(["show", f"--project={configured}"])
    head = _cli_raw([f"--project={configured}", "show"])
    other = _cli_raw([f"--project={empty}", "show"])
    assert tail.returncode == head.returncode == 0
    assert "default: high [config:default]" in tail.stdout
    assert "default: high [config:default]" in head.stdout
    assert "default: pi native [unset]" in other.stdout
    assert not (empty / ".mw").exists()


# ── set (AC-002 / AC-006 / VC-002) ───────────────────────────────────────────


@pytest.mark.parametrize("target", ["default", *ROLES])
@pytest.mark.parametrize("level", list(LEVELS))
def test_set_every_target_and_level_roundtrips_through_resolver(
    tmp_path: pathlib.Path, target: str, level: str
) -> None:
    _config(tmp_path, BASELINE)
    baseline_others = _others(_load(tmp_path))
    proc = _cli(tmp_path, "set", target, level)
    assert proc.returncode == 0, proc.stderr
    assert "next worker spawn" in proc.stdout

    data = _load(tmp_path)
    assert _others(data) == baseline_others  # models/fallback/rag/note untouched
    if target == "default":
        assert data["thinking"] == {"default": level}
        for role in ROLES:
            assert resolve_worker_thinking(tmp_path, role) == (level, "config:default", None)
    else:
        assert data["thinking"] == {"roles": {target: level}}
        for role in ROLES:
            expected = (level, f"config:{target}", None) if role == target else (None, "unset", None)
            assert resolve_worker_thinking(tmp_path, role) == expected
    value = data["thinking"]["default"] if target == "default" else data["thinking"]["roles"][target]
    assert isinstance(value, str)
    assert _temp_files(tmp_path) == []


def test_set_off_is_quoted_string_in_file_and_resolver(tmp_path: pathlib.Path) -> None:
    _config(tmp_path, BASELINE)
    assert _cli(tmp_path, "set", "default", "off").returncode == 0
    text = _path(tmp_path).read_text(encoding="utf-8")
    assert "'off'" in text or '"off"' in text
    assert yaml.safe_load(text)["thinking"]["default"] == "off"
    assert resolve_worker_thinking(tmp_path, "coding") == ("off", "config:default", None)


def test_set_default_then_override_precedence(tmp_path: pathlib.Path) -> None:
    _config(tmp_path, BASELINE)
    assert _cli(tmp_path, "set", "default", "high").returncode == 0
    assert _cli(tmp_path, "set", "review", "minimal").returncode == 0
    assert _cli(tmp_path, "set", "decide_prepare", "max").returncode == 0
    data = _load(tmp_path)
    assert data["thinking"] == {
        "default": "high", "roles": {"review": "minimal", "decide_prepare": "max"}
    }
    assert _others(data) == _others(yaml.safe_load(BASELINE))
    assert resolve_worker_thinking(tmp_path, "review") == ("minimal", "config:review", None)
    assert resolve_worker_thinking(tmp_path, "decide_prepare") == ("max", "config:decide_prepare", None)
    assert resolve_worker_thinking(tmp_path, "coding") == ("high", "config:default", None)
    proc = _cli(tmp_path, "show")
    assert "review: minimal [config:review]" in proc.stdout
    assert "coding: high [config:default]" in proc.stdout


def test_set_missing_config_creates_only_dispatch_yml(tmp_path: pathlib.Path) -> None:
    proc = _cli(tmp_path, "set", "coding", "high")
    assert proc.returncode == 0
    assert sorted(p.name for p in (tmp_path / ".mw").iterdir()) == ["dispatch.yml"]
    assert resolve_worker_thinking(tmp_path, "coding") == ("high", "config:coding", None)


@pytest.mark.parametrize(
    "text,encoding",
    [
        ("", "utf-8"),
        ("# comment only\n", "utf-8"),
        ("\ufeff# comment only\n", "utf-8"),
        ("models:\n  coding: toa/x\n", "utf-8-sig"),
        ("models:\n  coding: toa/x\n", "utf-8"),
    ],
)
def test_set_empty_comment_bom_and_existing_config(tmp_path: pathlib.Path, text: str,
                                                   encoding: str) -> None:
    _config(tmp_path, text, encoding=encoding)
    proc = _cli(tmp_path, "set", "research", "low")
    assert proc.returncode == 0
    assert resolve_worker_thinking(tmp_path, "research") == ("low", "config:research", None)
    if "models:" in text:
        assert _load(tmp_path)["models"] == {"coding": "toa/x"}


def test_set_preserves_nested_data_and_aliases(tmp_path: pathlib.Path) -> None:
    text = (
        "shared: &shared\n  depth:\n    - 1\n    - two\n"
        "rag:\n  copy: *shared\n  enabled: true\n"
        "fallback_models:\n  review: [timi/a, zai/b]\n"
        f"note: {SENTINEL}\n"
    )
    _config(tmp_path, text)
    assert _cli(tmp_path, "set", "vision", "xhigh").returncode == 0
    assert _others(_load(tmp_path)) == _others(yaml.safe_load(text))


def test_set_same_value_is_a_no_write(tmp_path: pathlib.Path) -> None:
    path = _config(tmp_path, BASELINE + "thinking:\n  default: high\n")
    assert _cli(tmp_path, "set", "default", "high").returncode == 0
    before = path.read_bytes()
    proc = _cli(tmp_path, "set", "default", "high")
    assert proc.returncode == 0
    assert "no write" in proc.stdout
    assert path.read_bytes() == before
    assert _temp_files(tmp_path) == []


def test_set_project_before_subcommand_writes_only_that_project(tmp_path: pathlib.Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _config(left, "thinking:\n  default: high\n")
    _config(right, "models:\n  coding: toa/x\n")
    before_right = _path(right).read_bytes()
    proc = _cli_raw([f"--project={right}", "set", "default", "minimal"])
    assert proc.returncode == 0
    assert resolve_worker_thinking(right, "coding") == ("minimal", "config:default", None)
    assert resolve_worker_thinking(left, "coding") == ("high", "config:default", None)
    assert _load(right)["models"] == {"coding": "toa/x"}
    assert before_right != _path(right).read_bytes()


# ── clear (AC-003 / VC-003) ──────────────────────────────────────────────────


def test_clear_role_restores_default(tmp_path: pathlib.Path) -> None:
    _config(
        tmp_path,
        BASELINE + 'thinking:\n  default: high\n  roles:\n    review: "off"\n'
        "    research: minimal\n",
    )
    assert _cli(tmp_path, "clear", "review").returncode == 0
    data = _load(tmp_path)
    assert data["thinking"] == {"default": "high", "roles": {"research": "minimal"}}
    assert _others(data) == _others(yaml.safe_load(BASELINE))
    assert resolve_worker_thinking(tmp_path, "review") == ("high", "config:default", None)
    assert resolve_worker_thinking(tmp_path, "research") == ("minimal", "config:research", None)


def test_clear_default_retains_overrides(tmp_path: pathlib.Path) -> None:
    _config(
        tmp_path,
        BASELINE + 'thinking:\n  default: high\n  roles:\n    review: "off"\n',
    )
    assert _cli(tmp_path, "clear", "default").returncode == 0
    assert _load(tmp_path)["thinking"] == {"roles": {"review": "off"}}
    assert _others(_load(tmp_path)) == _others(yaml.safe_load(BASELINE))
    assert resolve_worker_thinking(tmp_path, "review") == ("off", "config:review", None)
    assert resolve_worker_thinking(tmp_path, "coding") == (None, "unset", None)


def test_clear_all_restores_pi_native(tmp_path: pathlib.Path) -> None:
    _config(tmp_path, BASELINE + "thinking:\n  default: high\n  roles:\n    review: low\n")
    assert _cli(tmp_path, "clear", "all").returncode == 0
    data = _load(tmp_path)
    assert "thinking" not in data
    assert _others(data) == _others(yaml.safe_load(BASELINE))
    for role in ROLES:
        assert resolve_worker_thinking(tmp_path, role) == (None, "unset", None)
    show = _cli(tmp_path, "show")
    _assert_show_unset(show)


def test_clear_all_removes_existing_empty_block(tmp_path: pathlib.Path) -> None:
    path = _config(tmp_path, BASELINE + "thinking: {}\n")
    before = path.read_bytes()
    assert _cli(tmp_path, "clear", "all").returncode == 0
    assert "thinking" not in (_load(tmp_path) or {})
    assert path.read_bytes() != before
    assert _others(_load(tmp_path)) == _others(yaml.safe_load(BASELINE))


@pytest.mark.parametrize(
    "text,target",
    [
        (None, "all"),
        (None, "default"),
        (None, "review"),
        (BASELINE, "all"),
        (BASELINE, "default"),
        (BASELINE, "review"),
        (BASELINE + "thinking: {}\n", "default"),
        (BASELINE + "thinking: {}\n", "review"),
        (BASELINE + "thinking:\n  roles: {}\n", "review"),
        (BASELINE + "thinking:\n  default: high\n", "review"),
        (BASELINE + "thinking:\n  roles:\n    coding: low\n", "default"),
    ],
)
def test_clear_missing_target_never_writes(tmp_path: pathlib.Path, text: str | None,
                                           target: str) -> None:
    path = _path(tmp_path)
    if text is not None:
        _config(tmp_path, text)
        before = path.read_bytes()
    proc = _cli(tmp_path, "clear", target)
    assert proc.returncode == 0
    assert "no write" in proc.stdout
    if text is None:
        assert not (tmp_path / ".mw").exists()
    else:
        assert path.read_bytes() == before
    assert _temp_files(tmp_path) == []


def test_repeated_clear_role_is_idempotent(tmp_path: pathlib.Path) -> None:
    _config(tmp_path, BASELINE + "thinking:\n  roles:\n    review: low\n")
    assert _cli(tmp_path, "clear", "review").returncode == 0
    before = _path(tmp_path).read_bytes()
    proc = _cli(tmp_path, "clear", "review")
    assert proc.returncode == 0
    assert "no write" in proc.stdout
    assert _path(tmp_path).read_bytes() == before


# ── invalid arguments / arity (AC-004 / VC-004) ──────────────────────────────


@pytest.mark.parametrize(
    "tokens",
    [
        ("set",),
        ("set", "default"),
        ("set", "default", "high", "extra"),
        ("clear",),
        ("clear", "all", "extra"),
        ("show", "extra"),
        ("bogus",),
        ("--wat",),
        ("set", "main", "high"),
        ("clear", "main"),
        ("set", "bogus", "high"),
        ("clear", "bogus"),
        ("set", "default", "HIGH"),
        ("set", "default", "ultra"),
        ("set", "default", "on"),
        ("set", "default", " high "),
        ("clear", "all", "set"),
    ],
)
def test_invalid_arguments_zero_writes(tmp_path: pathlib.Path, tokens: tuple[str, ...]) -> None:
    path = _config(tmp_path, BASELINE + "thinking:\n  default: high\n")
    before = path.read_bytes()
    proc = _cli(tmp_path, *tokens)
    assert proc.returncode != 0
    assert path.read_bytes() == before
    assert _temp_files(tmp_path) == []
    if "main" in tokens:
        assert "main" in proc.stderr


def test_invalid_arguments_do_not_create_missing_config(tmp_path: pathlib.Path) -> None:
    for tokens in (("set",), ("set", "main", "high"), ("set", "default", "ultra"),
                   ("clear", "bogus"), ("bogus",)):
        assert _cli(tmp_path, *tokens).returncode != 0
    assert not (tmp_path / ".mw").exists()


# ── bad config / read failures (AC-004 / VC-004) ─────────────────────────────


@pytest.mark.parametrize("bad", BAD_CONFIGS)
@pytest.mark.parametrize(
    "tokens",
    [("show",), ("set", "default", "high"), ("set", "review", "off"),
     ("clear", "all"), ("clear", "default"), ("clear", "review")],
)
def test_bad_config_never_overwrites(tmp_path: pathlib.Path, bad: str,
                                     tokens: tuple[str, ...]) -> None:
    path = _config(tmp_path, bad)
    before = path.read_bytes()
    proc = _cli(tmp_path, *tokens)
    _assert_safe_failure(proc, path, before)
    assert "invalid" in proc.stderr.lower() or "unreadable" in proc.stderr.lower() or "mapping" in proc.stderr.lower()


def test_invalid_utf8_is_safe_failure(tmp_path: pathlib.Path) -> None:
    path = _config(tmp_path, "")
    path.write_bytes(f"thinking:\n  default: high\n{SENTINEL}\n".encode("utf-8") + b"\xff")
    before = path.read_bytes()
    for tokens in (("show",), ("set", "default", "low"), ("clear", "all")):
        _assert_safe_failure(_cli(tmp_path, *tokens), path, before)


def test_config_path_is_directory_is_safe_failure(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".mw" / "dispatch.yml").mkdir(parents=True)
    for tokens in (("show",), ("set", "default", "high"), ("clear", "all")):
        proc = _cli(tmp_path, *tokens)
        assert proc.returncode != 0
        assert "Traceback" not in proc.stderr


# ── injected read / write / replace failures (repeatable subprocess) ──────────


@pytest.mark.parametrize(
    "mode,tokens",
    [
        ("read", ("show",)),
        ("read", ("set", "default", "high")),
        ("read", ("clear", "all")),
        ("write", ("set", "default", "minimal")),
        ("write", ("clear", "all")),
        ("replace", ("set", "default", "minimal")),
        ("replace", ("clear", "all")),
    ],
)
def test_injected_filesystem_failures_are_safe(tmp_path: pathlib.Path, mode: str,
                                              tokens: tuple[str, ...]) -> None:
    path = _config(tmp_path, BASELINE + "thinking:\n  default: high\n")
    before = path.read_bytes()
    env = _fault_env(tmp_path, mode)
    proc = _cli(tmp_path, *tokens, env=env)
    _assert_safe_failure(proc, path, before)
    assert _temp_files(tmp_path) == []  # failed atomic replace cleans its temp


def test_injected_replace_failure_repeatable(tmp_path: pathlib.Path) -> None:
    """The same injection twice: no stale temp file, no partial write."""
    path = _config(tmp_path, BASELINE + "thinking:\n  default: high\n")
    before = path.read_bytes()
    env = _fault_env(tmp_path, "replace")
    for _ in range(2):
        _assert_safe_failure(_cli(tmp_path, "set", "review", "minimal", env=env), path, before)
        assert _temp_files(tmp_path) == []
    # Removing the fault writes successfully with the very same command.
    assert _cli(tmp_path, "set", "review", "minimal").returncode == 0
    assert resolve_worker_thinking(tmp_path, "review") == ("minimal", "config:review", None)


def test_direct_writer_failure_has_fixed_diagnostic(tmp_path: pathlib.Path,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    def boom(_path, _text):
        raise OSError(SENTINEL)

    assert thinking_config.cmd_thinking(_ns(tmp_path, "set", "default", "high"), boom) == 1
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err
    assert "Traceback" not in captured.err
    assert "Error:" in captured.err
    assert not _path(tmp_path).exists()


def test_direct_read_failure_has_fixed_diagnostic(tmp_path: pathlib.Path,
                                                 capsys: pytest.CaptureFixture[str],
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_project_dir):
        raise OSError(SENTINEL)

    monkeypatch.setattr(thinking_config, "load_config", boom)
    assert thinking_config.cmd_thinking(_ns(tmp_path, "set", "default", "high"), _writer) == 1
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err
    assert "Traceback" not in captured.err
    assert "Error:" in captured.err


def test_direct_replace_failure_cleans_temp_and_keeps_bytes(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _config(tmp_path, BASELINE + "thinking:\n  default: high\n")
    before = path.read_bytes()

    def boom(_src, _dst):
        raise OSError(SENTINEL)

    monkeypatch.setattr(os, "replace", boom)
    assert thinking_config.cmd_thinking(_ns(tmp_path, "set", "review", "low"), _writer) == 1
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out + captured.err
    assert "Traceback" not in captured.err
    assert path.read_bytes() == before
    assert _temp_files(tmp_path) == []


# ── existing resolver / launcher consumes the real CLI product ───────────────


def test_cli_output_is_consumed_by_launcher_spawn_resolver(tmp_path: pathlib.Path) -> None:
    _config(tmp_path, BASELINE)
    assert _cli(tmp_path, "set", "review", "off").returncode == 0
    task = tmp_path / "task.md"
    task.write_text("type: review\n\nBody.\n", encoding="utf-8")
    entry = {"task_path": str(task), "task_key": "t1"}
    assert launcher._resolve_spawn_thinking(tmp_path, entry) == ("off", "config:review")
    assert _cli(tmp_path, "clear", "all").returncode == 0
    assert launcher._resolve_spawn_thinking(tmp_path, entry) == (None, "unset")


def test_cli_does_not_change_model_or_fallback_resolution(tmp_path: pathlib.Path) -> None:
    _config(tmp_path, BASELINE)
    before, err = mw_common.load_dispatch_config(tmp_path)
    assert err is None
    before_fallback, fb_err = mw_common.load_fallback_models(tmp_path)
    assert fb_err is None
    assert _cli(tmp_path, "set", "coding", "max").returncode == 0
    assert mw_common.load_dispatch_config(tmp_path) == (before, None)
    assert mw_common.load_fallback_models(tmp_path) == (before_fallback, None)
    assert _cli(tmp_path, "clear", "all").returncode == 0
    assert mw_common.load_dispatch_config(tmp_path) == (before, None)

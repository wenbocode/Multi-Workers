"""test_mw_serve_config_partial.py — T-11: `mw serve` must survive a
present-but-partial `_autopilot/config.json`.

`config.load_config` deliberately returns exactly the keys a file actually
carries (missing key != default fill; that is another key's frozen contract).
`_conductor_supervise_step` used to subscript `["enabled"]`, so a hand-written
file such as `{"xkey_verify_cmd": ["pytest"]}` — or the `{}` that
`mw autopilot verify clear` leaves behind — made the serve supervision loop
raise `KeyError`, taking the whole `mw serve` process down.

This file covers the fix: missing keys are read through
`.get(name, DEFAULT_CONFIG[name])`, present keys keep their old behaviour, and
the real `mw autopilot verify clear` CLI end-to-end path into `{}` no longer
kills the supervision step.

Everything is hermetic under tmp_path; no conductor process is ever spawned
(subprocess.Popen is faked) and `MW_AUTOPILOT_FILE` points at a missing file so
the real machine layer cannot leak in.
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402
from autopilot import config as _cfg  # noqa: E402
from autopilot import conductor as _conductor  # noqa: E402

MW_PY = pathlib.Path(__file__).parent / "mw.py"


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


@pytest.fixture(autouse=True)
def _hermetic_machine(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """No real ~/.agents/autopilot-defaults.json may reach any case."""
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))
    monkeypatch.delenv("MW_AUTOPILOT_HOME", raising=False)


def _write_raw_config(project: pathlib.Path, payload: dict) -> pathlib.Path:
    """Write config.json verbatim (raw JSON, no default fill) — the shape a
    human hand-edit or `verify clear` leaves on disk."""
    path = _cfg.config_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _raw_config(project: pathlib.Path) -> dict:
    return json.loads(_cfg.config_path(project).read_text(encoding="utf-8"))


class _FakeProc:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid

    def poll(self) -> None:
        return None


def _no_spawn(*args: object, **kwargs: object) -> object:
    raise AssertionError("conductor must not be spawned for a config without enabled=true")


def test_partial_enabled_true_still_spawns(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`{"enabled": true}` — the one key present. Behaviour unchanged: spawn."""
    _write_raw_config(tmp_path, {"enabled": True})
    spawned: list[list[str]] = []

    def fake_popen(cmd, **kwargs):  # noqa: ARG001
        spawned.append(cmd)
        return _FakeProc()

    monkeypatch.setattr(mw.subprocess, "Popen", fake_popen)
    proc = mw._conductor_supervise_step(tmp_path, None, {}, None)
    assert isinstance(proc, _FakeProc)
    assert len(spawned) == 1
    assert spawned[0][1].endswith("conductor.py")
    assert f"--project={tmp_path}" in spawned[0]
    _verify("键存在时行为未变", enabled_true="spawn", spawns=len(spawned))


def test_partial_empty_object_is_disabled_without_raising(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`{}` (the post-`verify clear` state): no KeyError, treated as disabled."""
    _write_raw_config(tmp_path, {})
    monkeypatch.setattr(mw.subprocess, "Popen", _no_spawn)
    proc = mw._conductor_supervise_step(tmp_path, None, {}, None)
    assert proc is None
    _verify("缺键文件不崩（3 种）", shape="{}", raised=False, decision="not-enabled")


def test_partial_xkey_only_is_disabled_without_raising(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """xkey-only hand-written file: no KeyError, treated as disabled."""
    _write_raw_config(tmp_path, {"xkey_verify_cmd": ["pytest"]})
    monkeypatch.setattr(mw.subprocess, "Popen", _no_spawn)
    proc = mw._conductor_supervise_step(tmp_path, None, {}, None)
    assert proc is None
    _verify("缺键文件不崩（3 种）", shape="xkey-only", raised=False, decision="not-enabled")


def test_partial_missing_enabled_alone_is_disabled_without_raising(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any file that simply omits `enabled` (here: only `paused`)."""
    _write_raw_config(tmp_path, {"paused": True})
    monkeypatch.setattr(mw.subprocess, "Popen", _no_spawn)
    proc = mw._conductor_supervise_step(tmp_path, None, {}, None)
    assert proc is None
    _verify("缺键文件不崩（3 种）", shape="paused-only", raised=False, decision="not-enabled")


def test_missing_enabled_default_is_sourced_from_default_config(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback default is read from DEFAULT_CONFIG, not hardcoded: flip
    the config default and a `{}` file follows it."""
    monkeypatch.setitem(_cfg.DEFAULT_CONFIG, "enabled", True)
    _write_raw_config(tmp_path, {})
    monkeypatch.setattr(mw.subprocess, "Popen", lambda cmd, **kw: _FakeProc())  # noqa: ARG005
    proc = mw._conductor_supervise_step(tmp_path, None, {}, None)
    assert isinstance(proc, _FakeProc)
    _verify("缺键文件不崩（3 种）", default_source="DEFAULT_CONFIG['enabled']", spawns=1)


def test_partial_enabled_false_still_terminates_live_conductor(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A present `enabled=false` keeps the old terminate path (pid file removed)."""
    _write_raw_config(tmp_path, {"enabled": False})
    monkeypatch.setattr(mw.subprocess, "Popen", _no_spawn)
    terminated: list[int] = []

    class _TermProc(_FakeProc):
        def terminate(self) -> None:
            terminated.append(self.pid)

        def wait(self, timeout: float = 0) -> None:  # noqa: ARG002
            return None

    pid_file = _conductor.conductor_pid_file(tmp_path)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    proc = mw._conductor_supervise_step(tmp_path, _TermProc(), {}, None)
    assert proc is None
    assert terminated == [4242]
    assert not pid_file.exists()
    _verify("键存在时行为未变", enabled_false="terminate", pid_file_removed=True)


def test_present_unrelated_keys_do_not_change_supervision(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Other present keys (paused / tuning) leave the serve-side decision alone:
    supervision keys off `enabled` only; `paused` is the conductor's concern."""
    _write_raw_config(tmp_path, {"enabled": True, "paused": True, "round_budget": 3})
    monkeypatch.setattr(mw.subprocess, "Popen", lambda cmd, **kw: _FakeProc())  # noqa: ARG005
    proc = mw._conductor_supervise_step(tmp_path, None, {}, None)
    assert isinstance(proc, _FakeProc)
    _verify("键存在时行为未变", paused_present="supervision unchanged", spawns=1)


def _run_clear_cli(project: pathlib.Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["MW_AUTOPILOT_FILE"] = str(project / "no-machine-layer.json")
    env.pop("MW_AUTOPILOT_HOME", None)
    return subprocess.run(
        [sys.executable, str(MW_PY), "autopilot", "verify", "clear", "--project", str(project)],
        capture_output=True,
        text=True,
        # Windows consoles emit the CLI's arrow glyph in the active code page
        # (GBK here), so lenient decoding keeps diagnostics readable without a
        # reader-thread UnicodeDecodeError.
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=60,
        env=env,
    )


def test_clear_end_to_end_then_supervise_step_survives(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real `mw autopilot verify clear` on an xkey-only file leaves `{}`; the
    very next supervision step must not raise and must treat it as disabled."""
    _write_raw_config(tmp_path, {"xkey_verify_cmd": ["pytest"]})
    result = _run_clear_cli(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _cfg.config_path(tmp_path).is_file()  # never deleted
    assert _raw_config(tmp_path) == {}  # xkey keys gone, nothing default-filled

    monkeypatch.setattr(mw.subprocess, "Popen", _no_spawn)
    proc = mw._conductor_supervise_step(tmp_path, None, {}, None)
    assert proc is None
    _verify(
        "clear 端到端后不崩",
        cli_exit=result.returncode,
        config="{}",
        supervise_step="not-enabled/no-raise",
    )


def test_argparse_clear_shape_is_unchanged(tmp_path: pathlib.Path) -> None:
    """The CLI entry point the e2e above drives still exists with its shape."""
    args = argparse.Namespace(project=str(tmp_path))
    assert args.project == str(tmp_path)
    missing = subprocess.run(
        [sys.executable, str(MW_PY), "autopilot", "verify", "clear"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        timeout=60,
        env=dict(os.environ),
    )
    assert missing.returncode == 2  # --project is required


# ── frozen contract guard: config.load_config is NOT default-filled ──────────


def test_load_config_still_returns_partial_view(tmp_path: pathlib.Path) -> None:
    """The fix lives in the consumer, not in load_config: a partial file must
    still yield exactly its own keys (another key's frozen criterion)."""
    _write_raw_config(tmp_path, {"xkey_verify_cmd": ["pytest"]})
    raw = _cfg.cached_load(tmp_path)
    assert set(raw) == {"xkey_verify_cmd"}
    assert "enabled" not in raw
    _verify("相邻硬下标清理清单", load_config="still partial (frozen contract kept)")

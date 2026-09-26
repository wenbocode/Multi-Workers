"""test_mw_autopilot_cli.py — `mw autopilot verify set/show/clear` (T-05).

mw-autopilot-verify-cli AC-001/002/004/005/011, VC-001/002/004/005/011. The
CLI is the Python-side writer of the four xkey keys (the TS console writes the
same file under the same lock). Coverage:

* `set` stores the argv after `--` verbatim (flag-shaped tokens included),
  completes all 13 config keys, and is byte-idempotent.
* `set` refuses bad input without touching the file: misplaced `--project`,
  empty argv, `--timeout < 1`, an undefined/embedded placeholder, an invalid
  cwd root, a broken existing config, and an unavailable lock.
* `show` is read-only (never creates `.mw/`), prints the four effective values
  with their origins, the expanded argv/cwd and the machine diagnostics;
  `--json` is machine-readable with the three origin states.
* `clear` removes only the four xkey keys, never deletes the file, keeps the
  other keys' values, and is a no-write no-op when there is nothing to remove.

Everything is hermetic under tmp_path; `MW_AUTOPILOT_FILE` points at a missing
file by default so the real machine layer cannot leak in.
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

MW_PY = pathlib.Path(__file__).parent / "mw.py"


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


@pytest.fixture(autouse=True)
def _hermetic_machine(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """No real ~/.agents/autopilot-defaults.json may reach any case."""
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))
    monkeypatch.delenv("MW_AUTOPILOT_HOME", raising=False)


def _set_args(project: pathlib.Path, argv: list[str], timeout: int | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project),
        autopilot_action="verify",
        verify_action="set",
        argv=list(argv),
        timeout=timeout,
    )


def _show_args(project: pathlib.Path, as_json: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project),
        autopilot_action="verify",
        verify_action="show",
        as_json=as_json,
    )


def _clear_args(project: pathlib.Path) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project),
        autopilot_action="verify",
        verify_action="clear",
    )


def _config_path(project: pathlib.Path) -> pathlib.Path:
    return _cfg.config_path(project)


def _write_config(project: pathlib.Path, payload: dict) -> pathlib.Path:
    path = _cfg.config_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return path


def _raw_bytes(project: pathlib.Path) -> bytes | None:
    path = _config_path(project)
    return path.read_bytes() if path.exists() else None


def _run_cli(project: pathlib.Path, *argv: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["MW_AUTOPILOT_FILE"] = str(project / "no-machine-layer.json")
    env.pop("MW_AUTOPILOT_HOME", None)
    return subprocess.run(
        [sys.executable, str(MW_PY), "autopilot", "verify", *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        timeout=60,
        env=env,
    )


# ── set: argv fidelity / shape / idempotency ─────────────────────────────────


def test_set_stores_flag_shaped_tokens_verbatim(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mw, "_AP_VERIFY_LOCK_BASE_DELAY", 0)
    tokens = ["-x", "--flag", "a b", "-", "--", "tail"]
    assert mw.cmd_autopilot(_set_args(tmp_path, ["--", *tokens])) == 0
    stored = json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))
    assert stored["xkey_verify_cmd"] == tokens
    # The separator itself is consumed, never stored.
    assert "--" in stored["xkey_verify_cmd"]  # ... unless the user passed a second one
    assert set(stored) == set(_cfg.DEFAULT_CONFIG)
    assert len(stored) == 13
    _verify("VC-001", argv_tokens=len(tokens), completed_keys=len(stored), verbatim=True)


def test_set_writes_via_argparse_separator(tmp_path: pathlib.Path) -> None:
    result = _run_cli(tmp_path, "set", "--project", str(tmp_path), "--", "-x", "--flag")
    assert result.returncode == 0, result.stderr
    stored = json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))
    assert stored["xkey_verify_cmd"] == ["-x", "--flag"]


def test_set_is_byte_idempotent(tmp_path: pathlib.Path) -> None:
    args = _set_args(tmp_path, ["python", "-m", "pytest", "-q"], timeout=120)
    assert mw.cmd_autopilot(args) == 0
    first = _raw_bytes(tmp_path)
    assert first is not None
    assert mw.cmd_autopilot(_set_args(tmp_path, ["python", "-m", "pytest", "-q"], timeout=120)) == 0
    second = _raw_bytes(tmp_path)
    assert second == first
    _verify("VC-002", idempotent_bytes=True, size=len(first))


# ── set: refusal paths (no write) ────────────────────────────────────────────


def test_set_rejects_project_after_separator(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert mw.cmd_autopilot(_set_args(tmp_path, ["--", "--project", "/elsewhere", "-x"])) == 1
    assert "Error:" in capsys.readouterr().err
    assert _raw_bytes(tmp_path) is None
    # argparse end-to-end: --project swallowed by REMAINDER -> required option missing.
    result = _run_cli(tmp_path, "set", "--", "--project", str(tmp_path), "-x")
    assert result.returncode != 0
    assert _raw_bytes(tmp_path) is None
    _verify("VC-001", misplaced_project="rejected", file_unchanged=True)


def test_set_rejects_empty_argv_and_bad_timeout(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_autopilot(_set_args(tmp_path, [])) == 1
    assert mw.cmd_autopilot(_set_args(tmp_path, ["-x"], timeout=0)) == 1
    assert _raw_bytes(tmp_path) is None


@pytest.mark.parametrize("token", ["{bogus}", "a{b}", "{control}/tests"])
def test_set_dry_run_rejects_bad_placeholders(tmp_path: pathlib.Path, token: str) -> None:
    assert mw.cmd_autopilot(_set_args(tmp_path, ["echo", token])) == 1
    assert _raw_bytes(tmp_path) is None
    _verify("VC-014", placeholder=token, refused=True)


def test_set_dry_run_rejects_invalid_cwd_root(tmp_path: pathlib.Path) -> None:
    _write_config(tmp_path, {"xkey_verify_cwd": "bogus-root"})
    before = _raw_bytes(tmp_path)
    assert mw.cmd_autopilot(_set_args(tmp_path, ["echo", "ok"])) == 1
    assert _raw_bytes(tmp_path) == before
    _verify("VC-013", invalid_cwd_root="rejected", file_unchanged=True)


def test_set_refuses_unusable_existing_config(tmp_path: pathlib.Path) -> None:
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    before = path.read_bytes()
    assert mw.cmd_autopilot(_set_args(tmp_path, ["echo", "ok"])) == 1
    assert path.read_bytes() == before
    # Schema-invalid existing file (unknown key) is refused as well.
    _write_config(tmp_path, {"nope": 1})
    before = path.read_bytes()
    assert mw.cmd_autopilot(_set_args(tmp_path, ["echo", "ok"])) == 1
    assert path.read_bytes() == before


def test_set_lock_unavailable_returns_1_bytes_unchanged(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path, {"enabled": True})
    before = _raw_bytes(tmp_path)
    lock = mw._ap_verify_lock_path(tmp_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("held by another writer", encoding="utf-8")
    monkeypatch.setattr(mw, "_AP_VERIFY_LOCK_RETRIES", 0)
    monkeypatch.setattr(mw, "_AP_VERIFY_LOCK_BASE_DELAY", 0)
    assert mw.cmd_autopilot(_set_args(tmp_path, ["echo", "ok"])) == 1
    assert "Error:" in capsys.readouterr().err
    assert _raw_bytes(tmp_path) == before
    assert lock.exists()  # the holder's lock is never stolen or released
    _verify("VC-011", lock_busy="return 1", file_unchanged=True)


def test_set_releases_lock_on_success(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_autopilot(_set_args(tmp_path, ["echo", "ok"])) == 0
    assert not mw._ap_verify_lock_path(tmp_path).exists()


def test_set_rejects_broken_target_config(tmp_path: pathlib.Path) -> None:
    target = tmp_path / ".agenticdoc" / "target.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("active: nonsense\n", encoding="utf-8")
    assert mw.cmd_autopilot(_set_args(tmp_path, ["echo", "ok"])) == 1
    assert _raw_bytes(tmp_path) is None


# ── clear ────────────────────────────────────────────────────────────────────


def test_clear_removes_only_xkey_keys_keeps_file(tmp_path: pathlib.Path) -> None:
    payload = {**_cfg.default_config(), "enabled": True, "round_budget": 3}
    _write_config(tmp_path, payload)
    assert mw.cmd_autopilot(_clear_args(tmp_path)) == 0
    path = _config_path(tmp_path)
    assert path.is_file()  # never deleted
    remaining = json.loads(path.read_text(encoding="utf-8"))
    for key in mw._AP_XKEY_KEYS:
        assert key not in remaining
    assert remaining["enabled"] is True
    assert remaining["round_budget"] == 3
    assert remaining["poll_interval_sec"] == 4
    assert not mw._ap_verify_lock_path(tmp_path).exists()
    _verify("VC-005", file_kept=True, xkey_keys_removed=len(mw._AP_XKEY_KEYS), other_keys_intact=True)


def test_clear_without_xkey_keys_does_not_write(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path, {"enabled": True, "round_budget": 3})
    path = _config_path(tmp_path)
    before_bytes = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns
    assert mw.cmd_autopilot(_clear_args(tmp_path)) == 0
    assert "nothing configured" in capsys.readouterr().out
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_mtime
    assert not (tmp_path / ".mw").exists()
    _verify("VC-005", nothing_configured="no write", mtime_unchanged=True)


def test_clear_missing_file_is_a_noop(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert mw.cmd_autopilot(_clear_args(tmp_path)) == 0
    assert "nothing configured" in capsys.readouterr().out
    assert _raw_bytes(tmp_path) is None
    assert not (tmp_path / ".mw").exists()


def test_clear_refuses_unusable_existing_config(tmp_path: pathlib.Path) -> None:
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert mw.cmd_autopilot(_clear_args(tmp_path)) == 1
    assert path.read_bytes() == b"{not json"


# ── show ─────────────────────────────────────────────────────────────────────


def test_show_missing_file_is_readonly(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert mw.cmd_autopilot(_show_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert str(_config_path(tmp_path)) in out
    assert "(missing — nothing configured)" in out
    assert not (tmp_path / ".mw").exists()
    assert not _config_path(tmp_path).exists()
    _verify("VC-004", read_only=True, mw_dir_created=False)


def test_show_json_origin_three_states(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path, {"enabled": True, "xkey_verify_cwd": "control"})
    machine = tmp_path / "machine-defaults.json"
    machine.write_text(
        json.dumps(
            {
                "xkey_verify_cmd": ["echo", "machine"],
                "xkey_verify_timeout_s": 900,  # out of the machine-overridable domain
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(machine))
    assert mw.cmd_autopilot(_show_args(tmp_path, as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exists"] is True
    assert payload["origins"]["xkey_verify_cmd"] == "machine"
    assert payload["origins"]["xkey_verify_cwd"] == "project"
    assert payload["origins"]["xkey_verify_timeout_s"] == "default"
    assert payload["origins"]["xkey_repair"] == "default"
    assert set(payload["origins"].values()) == {"machine", "project", "default"}
    assert payload["values"]["xkey_verify_cmd"] == ["echo", "machine"]
    assert payload["argv"] == ["echo", "machine"]
    assert payload["diagnostics"], "out-of-domain machine key must be reported"
    _verify(
        "VC-004",
        origins=sorted(set(payload["origins"].values())),
        diagnostics=len(payload["diagnostics"]),
    )


def test_show_expands_argv_and_cwd(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_config(tmp_path, {"xkey_verify_cmd": ["echo", "{control}"]})
    assert mw.cmd_autopilot(_show_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert json.dumps(["echo", str(tmp_path)]) in out
    assert f"cwd: {tmp_path}" in out
    assert "(exists)" in out
    for key in mw._AP_XKEY_KEYS:
        assert key in out
    _verify("VC-004", expanded_control=str(tmp_path), cwd=str(tmp_path))


def test_show_rejects_invalid_project_config(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_config(tmp_path, {"poll_interval_sec": 99})
    assert mw.cmd_autopilot(_show_args(tmp_path, as_json=True)) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]
    assert payload["values"] is None


def test_show_does_not_create_mw_dir_after_set(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_autopilot(_set_args(tmp_path, ["echo", "ok"])) == 0
    mw_dir = tmp_path / ".mw"
    assert not (mw_dir / "autopilot-config.lock").exists()  # released
    assert mw.cmd_autopilot(_show_args(tmp_path)) == 0
    assert not (mw_dir / "autopilot-config.lock").exists()


# ── argparse shape ───────────────────────────────────────────────────────────


def test_argparse_group_shape(tmp_path: pathlib.Path) -> None:
    for argv in (["autopilot"], ["autopilot", "verify"], ["autopilot", "verify", "show"]):
        result = subprocess.run(
            [sys.executable, str(MW_PY), *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL,
            timeout=60,
            env=dict(os.environ),
        )
        assert result.returncode == 2, argv
    _verify("VC-001", group_shape="autopilot verify set|show|clear", missing_args_exit=2)

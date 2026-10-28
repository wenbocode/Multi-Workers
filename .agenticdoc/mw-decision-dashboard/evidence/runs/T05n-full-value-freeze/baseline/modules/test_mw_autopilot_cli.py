"""test_mw_autopilot_cli.py — `mw autopilot verify set/show/clear` (T-05).

mw-autopilot-verify-cli AC-001/002/004/005/011, VC-001/002/004/005/011. The
CLI is the Python-side writer of the four xkey keys (the TS console writes the
same file under the same lock). Coverage:

* `set` stores the argv after `--` verbatim (flag-shaped tokens included),
  completes all 14 config keys, and is byte-idempotent.
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
from autopilot import contract_guard  # noqa: E402

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
    # Count changed 13 -> 14 (slot-capacity T-03), 14 -> 17 (mw-gate-verdict-hardening T-18),
    # 17 -> 20 (mw-gate-verdict-hardening T-02 G1/G2 keys).
    assert len(stored) == 21
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


def test_set_lock_held_by_another_process_returns_1(tmp_path: pathlib.Path) -> None:
    """A live foreign process holding the lock wins: rc=1, target untouched.

    The lock is file-based (``O_CREAT|O_EXCL``), so a lock file owned by a
    running second process is indistinguishable from a stale file to ``set``;
    both must fail loud and leave the target bytes alone. The child acquires
    through the real ``mw_common.acquire_lock`` protocol and stays alive."""
    _write_config(tmp_path, {"enabled": True})
    before = _raw_bytes(tmp_path)
    lock = tmp_path / ".mw" / "autopilot-config.lock"
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import pathlib, sys, time\n"
                f"sys.path.insert(0, {str(MW_PY.parent)!r})\n"
                "import mw_common\n"
                f"mw_common.acquire_lock(pathlib.Path({str(lock)!r}))\n"
                "print('locked', flush=True)\n"
                "time.sleep(30)\n"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"
        assert lock.is_file()
        result = _run_cli(tmp_path, "set", "--project", str(tmp_path), "--", "echo", "ok")
        assert result.returncode == 1, result.stderr
        assert "[mw autopilot verify set] Error:" in result.stderr
        assert _raw_bytes(tmp_path) == before
        assert lock.is_file()  # the holder's lock is never stolen or released
    finally:
        holder.terminate()
        holder.wait(timeout=10)
    _verify("VC-011", lock_holder="live process", returncode=1, file_unchanged=True)


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
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["error"]
    assert payload["values"] is None
    # Errors follow the frozen `[mw autopilot verify <action>] Error:` stderr
    # contract; the JSON payload stays on stdout for machines.
    assert "[mw autopilot verify show] Error:" in captured.err
    assert "Error:" not in captured.out


def test_show_text_error_goes_to_stderr(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_config(tmp_path, {"poll_interval_sec": 99})
    assert mw.cmd_autopilot(_show_args(tmp_path)) == 1
    captured = capsys.readouterr()
    assert "[mw autopilot verify show] Error:" in captured.err
    assert "Error:" not in captured.out
    # The config-path line stays on stdout so the failed read is still locatable.
    assert str(_config_path(tmp_path)) in captured.out


def test_show_does_not_create_mw_dir_after_set(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_autopilot(_set_args(tmp_path, ["echo", "ok"])) == 0
    mw_dir = tmp_path / ".mw"
    assert not (mw_dir / "autopilot-config.lock").exists()  # released
    assert mw.cmd_autopilot(_show_args(tmp_path)) == 0
    assert not (mw_dir / "autopilot-config.lock").exists()


# ── contract-guard (T-11 / AC-013, VC-016) ───────────────────────────────────

CONTRACT_SPEC = """# Spec

## 3. Acceptance Criteria

| AC ID | 判据 |
|---|---|
| AC-001 | first frozen contract text |
"""

CONTRACT_DESIGN = """# Design

VC-001: first assertion text
       Layer: L0   Output: [VERIFY] VC-001: one=true   Source: AC-001
"""


def _guard_args(
    project: pathlib.Path, key: str | None = None, as_json: bool = False
) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project),
        autopilot_action="contract-guard",
        key=key,
        as_json=as_json,
    )


def _run_guard_cli(project: pathlib.Path, *argv: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["MW_AUTOPILOT_FILE"] = str(project / "no-machine-layer.json")
    env.pop("MW_AUTOPILOT_HOME", None)
    return subprocess.run(
        [sys.executable, str(MW_PY), "autopilot", "contract-guard", *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        timeout=60,
        env=env,
    )


def _frozen_key(
    project: pathlib.Path, key: str = "k1"
) -> pathlib.Path:
    key_dir = project / ".agenticdoc" / key
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "spec.md").write_text(CONTRACT_SPEC, encoding="utf-8", newline="\n")
    (key_dir / "design.md").write_text(CONTRACT_DESIGN, encoding="utf-8", newline="\n")
    contract_guard.freeze_contract(key_dir, key, CONTRACT_SPEC, CONTRACT_DESIGN)
    return key_dir


def _rewrite_ac(key_dir: pathlib.Path) -> None:
    (key_dir / "spec.md").write_text(
        CONTRACT_SPEC.replace(
            "first frozen contract text", "first frozen contract text REWRITTEN"
        ),
        encoding="utf-8",
        newline="\n",
    )


def _authorizing_gate(project: pathlib.Path, gate_id: str, key: str) -> None:
    gdir = project / ".agenticdoc" / "_autopilot" / "gates"
    gdir.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        [
            "---",
            f"id: {gate_id}",
            "kind: stalled",
            "stage:",
            f"key: {key}",
            "created_at: 2026-10-10T08:00:00+00:00",
            "created_by: conductor",
            "question: approve the contract text change?",
            "context_refs: []",
            "status: approved",
            "answered_at: 2026-10-10T09:00:00+00:00",
            "answered_by: human",
            "note:",
            'authorizes: \'["contract-change"]\'',
            "---",
            "",
        ]
    )
    (gdir / f"{gate_id}.md").write_text(text, encoding="utf-8", newline="\n")


def test_contract_guard_cli_no_freeze_is_readonly(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert mw.cmd_autopilot(_guard_args(tmp_path, key="k1")) == 0
    assert "freeze=no" in capsys.readouterr().out
    assert mw.cmd_autopilot(_guard_args(tmp_path, key="k1", as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["refused"] is False and payload["ok"] is True
    assert payload["keys"][0]["freeze"] is False
    assert "no_anchor" not in payload["keys"][0]  # not part of the wire shape
    # Without --key there is no anchored key at all: nothing to check.
    assert mw.cmd_autopilot(_guard_args(tmp_path)) == 0
    assert "no freeze sidecar" in capsys.readouterr().out
    assert not (tmp_path / ".agenticdoc").exists()
    _verify("VC-016", no_freeze="exit 0", read_only=True)


def test_contract_guard_cli_refuses_unauthorized_change(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _rewrite_ac(_frozen_key(tmp_path))
    assert mw.cmd_autopilot(_guard_args(tmp_path, key="k1", as_json=True)) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["refused"] is True and payload["ok"] is False
    assert payload["unauthorized"] == 1
    entry = payload["keys"][0]
    assert entry["key"] == "k1"
    assert entry["changed_ids"] == ["AC-001"]
    assert entry["carrier"] is None
    assert entry["authorized"] is False
    assert str(tmp_path) not in json.dumps(payload)
    assert mw.cmd_autopilot(_guard_args(tmp_path, key="k1")) == 1
    assert "ok=no refused" in capsys.readouterr().out
    _verify("VC-016", refused=True, changed_ids=entry["changed_ids"], carrier=None)


def test_contract_guard_cli_authorizing_gate_clears_it(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _rewrite_ac(_frozen_key(tmp_path))
    _authorizing_gate(tmp_path, "gate-0001", "k1")
    assert mw.cmd_autopilot(_guard_args(tmp_path, key="k1", as_json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["refused"] is False
    assert payload["keys"][0]["carrier"] == "gate-0001"
    assert payload["keys"][0]["authorized"] is True
    _verify("VC-016", carrier=payload["keys"][0]["carrier"], refused=False)


def test_contract_guard_cli_all_keys_and_reproducible(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _rewrite_ac(_frozen_key(tmp_path, "k1"))
    _rewrite_ac(_frozen_key(tmp_path, "k0"))
    assert mw.cmd_autopilot(_guard_args(tmp_path, as_json=True)) == 1
    first = capsys.readouterr().out
    assert mw.cmd_autopilot(_guard_args(tmp_path, as_json=True)) == 1
    second = capsys.readouterr().out
    assert first == second
    payload = json.loads(first)
    assert [entry["key"] for entry in payload["keys"]] == ["k0", "k1"]
    assert payload["unauthorized"] == 2
    _verify("VC-016", reproducible=True, keys="k0,k1", unauthorized=2)


def test_contract_guard_cli_argparse_shape(tmp_path: pathlib.Path) -> None:
    result = _run_guard_cli(tmp_path)  # --project required
    assert result.returncode == 2
    result = _run_guard_cli(tmp_path, "--project", str(tmp_path), "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["keys"] == []


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

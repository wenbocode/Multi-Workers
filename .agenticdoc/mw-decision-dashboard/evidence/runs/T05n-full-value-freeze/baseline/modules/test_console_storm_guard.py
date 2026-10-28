"""Runner tests for packages/multi-workers (W-04b, mw-console-storm-hardening).

ac_refs:
  - goal.md: mw 后台服务常驻运行（L0 cmd_start 除雷 + L1 后台命令 runner 证据链）
  - spec.md AC-001 (cmd_start flags + serve-console.log 重定向), AC-002 (spawn 站点
    审计表 + DETACHED_PROCESS 防回潮), AC-003 (run-detached marker/argv/日志契约),
    AC-004 (heartbeat 推进 + timeout rc=124/timed_out), AC-007 (posix start_new_session)
  - design.md D-001 (cmd_start: CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW, 去
    DETACHED_PROCESS), D-002 (console_run.py 两层结构, 4 行 handoff, marker/heartbeat),
    D-004 (守卫测试: 非测试 .py grep DETACHED=0 + 审计表存在), D-006 (审计表)
  - evidence/research/design-win32-console-semantics-20261015.md M1/M2/M3 (flags 语义)
  - evidence/research/design-spawn-site-audit-20261015.md (VC-002 存在性断言对象)
  - mw.py:506 (cmd_start L0 改点), console_run.py:1 (runner 模块),
    test_common.py:740 先例 (spy 捕获 Popen kwargs)

Assertion groups and AC/VC mapping:
  | group | assert set                                              | AC   | VC  |
  |-------|---------------------------------------------------------|------|-----|
  | 1     | cmd_start win32 creationflags = NO_WINDOW|NEW_GROUP,     | AC-001 | VC-001 |
  |       | 按位不含 DETACHED_PROCESS, stdout/stderr 重定向到        |       |     |
  |       | .mw/serve-console.log (monkeypatch Popen 捕获 kwargs)  |       |     |
  | 2     | 非测试 .py 剥注释+docstring 后 DETACHED_PROCESS 命中=0  | AC-002 | VC-002 |
  |       | + 审计表文件存在                                        |       |     |
  | 3     | run-detached 真实短命令全链: stdout 恰 4 行, marker     | AC-003 | VC-003 |
  |       | schema=mw-run/1 rc=0, cmd.txt 原样, run.log 存在       |       |     |
  | 4     | heartbeat 0.5s 推进 ≥2 不同 ts_ms; timeout 0.05min ->   | AC-004 | VC-004 |
  |       | marker rc=124 timed_out=true                            |       |     |
  | 5     | posix seam: start_new_session=True, kwargs 无           | AC-007 | VC-007 |
  |       | creationflags                                          |       |     |
  | 6     | 集成用例全用 tmp_path (cwd/run_dir), marker 出现即回收  | all  | all  |

VC-002 scope note: the scan covers non-test .py files under
packages/multi-workers but EXCLUDES the mw_console_guard/ subpackage: that
package's contract (spec AC-005, D-003) is to PRESERVE explicit
DETACHED_PROCESS flags, so it intentionally references the constant in code
(`EXPLICIT = subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS`,
mw_console_guard.py:30). The DETACHED_PROCESS=0 guard applies to the hardened
spawn sites (mw.py / console_run.py / launcher.py / ...), where design D-001
removed the flag; docstrings and `#` comments (e.g. mw.py:508 M2/M3 notes,
console_run.py:19 module docstring) are prose and allowed.
"""
from __future__ import annotations

import io
import json
import pathlib
import subprocess
import sys
import time
import tokenize

import pytest

PKG_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]
SKIP_NO_WINDOW = not hasattr(subprocess, "CREATE_NO_WINDOW")
SKIP_NON_WIN32 = sys.platform != "win32"

AUDIT_FILE = (
    REPO_ROOT
    / ".agenticdoc"
    / "mw-console-storm-hardening"
    / "evidence"
    / "research"
    / "design-spawn-site-audit-20261015.md"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _poll_until(predicate, *, timeout_s: float = 15.0, interval: float = 0.2):
    """Poll `predicate()` every `interval` s until truthy or `timeout_s`."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        val = predicate()
        if val:
            return val
        time.sleep(interval)
    return None


def _strip_prose(src: str) -> str:
    """Remove `#` comments and triple-quoted docstring prose; keep all other
    string literals so `getattr(subprocess, "DETACHED_PROCESS")`-style usages
    stay visible to the grep. Docstrings in this codebase are triple-quoted
    prose, so a STRING token starting with three quotes is allowed prose while
    single/double-quoted strings are preserved."""
    out: list[str] = []
    prev_row, prev_col = 1, 0
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        start_row, start_col = tok.start
        while prev_row < start_row:  # re-emit blank rows to keep line mapping
            out.append("\n")
            prev_row += 1
            prev_col = 0
        out.append(" " * (start_col - prev_col))
        prev_col = start_col + len(tok.string)
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and tok.string.startswith(('"""', "'''")):
            continue  # docstring prose
        out.append(tok.string)
    return "".join(out)


def _run_detached(
    capsys,
    *,
    run_dir: pathlib.Path,
    argv: list[str],
    heartbeat_s: float | None = None,
    timeout_min: float | None = None,
    platform: str | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> str:
    """Call console_run.cmd_run_detached (importing the package modules in
    this process) and return its 4-line stdout contract. `platform` injects the
    posix seam via monkeypatch (VC-007)."""
    import console_run

    if platform is not None:
        assert monkeypatch is not None
        monkeypatch.setattr(sys, "platform", platform)
    args = argparse_namespace(cwd=str(run_dir.parent), run_dir=str(run_dir), argv=argv)
    if heartbeat_s is not None:
        args.heartbeat_s = heartbeat_s
    if timeout_min is not None:
        args.timeout_min = timeout_min
    rc = console_run.cmd_run_detached(args)
    assert rc == 0
    return capsys.readouterr().out


def argparse_namespace(**kw):
    """Build the argparse.Namespace shape cmd_run_detached/cmd_start read."""
    import argparse

    ns = argparse.Namespace()
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


# ---------------------------------------------------------------------------
# Group 1 (VC-001 / AC-001): cmd_start flags + serve-console.log redirect
# ---------------------------------------------------------------------------

@pytest.mark.skipif(SKIP_NO_WINDOW, reason="Windows-only: CREATE_NO_WINDOW absent")
def test_vc001_cmd_start_flags_and_redirect(tmp_path, monkeypatch):
    """monkeypatch subprocess.Popen captures kwargs (test_common.py:740 pattern):
    win32 branch must pass CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW (no
    DETACHED_PROCESS bit) and redirect stdout/stderr to .mw/serve-console.log."""
    seen: dict = {}

    class FakeProc:
        pid = 424242

    def spy_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        seen.update(kwargs)
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", spy_popen)
    import mw

    ns = argparse_namespace(
        project=str(tmp_path),
        pi_port=7001,
        claude_port=7003,
        deepseek_port=None,
        poll_interval=5,
        max_workers=None,
        providers=None,
    )
    assert mw.cmd_start(ns) == 0

    flags = seen.get("creationflags")
    expected = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    assert flags == expected, (
        "cmd_start win32 creationflags=0x%x, expected 0x%x "
        "(CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW)" % (flags or 0, expected)
    )
    assert flags & subprocess.DETACHED_PROCESS == 0, (
        "cmd_start still carries DETACHED_PROCESS bit: flags=0x%x (0x%x)"
        % (flags, subprocess.DETACHED_PROCESS)
    )
    serve_log = (tmp_path / ".mw" / "serve-console.log").resolve()
    out_name = pathlib.Path(seen["stdout"].name).resolve() if seen.get("stdout") else None
    err_name = pathlib.Path(seen["stderr"].name).resolve() if seen.get("stderr") else None
    assert out_name == serve_log, (
        "stdout redirect target %r, expected %r" % (out_name, serve_log)
    )
    assert err_name == serve_log, (
        "stderr redirect target %r, expected %r" % (err_name, serve_log)
    )
    assert serve_log.exists(), "serve-console.log not created at %s" % serve_log
    assert seen["cmd"][2] == "serve", (
        "cmd_start spawn argv not mw serve: %r" % (seen.get("cmd"),)
    )
    print(
        "[VERIFY] VC-001: flags=0x%x detached_bit=%d serve_log=%s"
        % (flags, flags & subprocess.DETACHED_PROCESS, serve_log),
        flush=True,
    )


# ---------------------------------------------------------------------------
# Group 2 (VC-002 / AC-002): DETACHED_PROCESS regression guard + audit table
# ---------------------------------------------------------------------------

def test_vc002_detached_guard_grep_and_audit_table():
    """Scan every non-test .py file under packages/multi-workers (excluding the
    mw_console_guard/ subpackage - see header scope note) after stripping `#`
    comments and triple-quoted docstrings: DETACHED_PROCESS must have 0 hits.
    Also asserts the spawn-site audit table exists (D-006)."""
    assert AUDIT_FILE.is_file(), (
        "spawn-site audit table missing: %s" % AUDIT_FILE
    )

    raw_hits: dict[str, list[int]] = {}
    stripped_hits: dict[str, list[int]] = {}
    scanned = 0
    for p in sorted(PKG_DIR.rglob("*.py")):
        rel = p.relative_to(PKG_DIR)
        if any(part in rel.parts for part in ("__pycache__", ".pytest_cache", ".tmp")):
            continue
        if p.name.startswith("test_") or "test" in rel.parts:
            continue  # test code excluded (incl. this file + test_mw_console_guard.py)
        if "mw_console_guard" in rel.parts:
            continue  # guard package: contract requires the reference (see header)
        scanned += 1
        src = p.read_text(encoding="utf-8", errors="replace")
        stripped = _strip_prose(src)
        for i, line in enumerate(src.splitlines(), 1):
            if "DETACHED_PROCESS" in line:
                raw_hits.setdefault(str(rel), []).append(i)
        for i, line in enumerate(stripped.splitlines(), 1):
            if "DETACHED_PROCESS" in line:
                stripped_hits.setdefault(str(rel), []).append(i)

    assert scanned > 0, "guard scan found no scanned files under %s" % PKG_DIR
    total = sum(len(v) for v in stripped_hits.values())
    assert total == 0, (
        "DETACHED_PROCESS used in non-test code after stripping comments/"
        "docstrings: %r" % stripped_hits
    )
    print(
        "[VERIFY] VC-002: files=%d raw_hits=%d stripped_hits=%d audit=%s"
        % (scanned, sum(len(v) for v in raw_hits.values()), total, AUDIT_FILE),
        flush=True,
    )


# ---------------------------------------------------------------------------
# Group 3 (VC-003 / AC-003): run-detached real short-command full chain
# ---------------------------------------------------------------------------

@pytest.mark.skipif(SKIP_NON_WIN32, reason="win32-only: cmd /c exit; posix seam covered by VC-007")
def test_vc003_run_detached_full_chain(tmp_path, capsys):
    run_dir = tmp_path / "run"
    argv = ["cmd", "/c", "exit"]
    out = _run_detached(capsys, run_dir=run_dir, argv=argv)

    lines = out.splitlines()
    assert len(lines) == 4, (
        "cmd_run_detached stdout must be exactly 4 lines, got %d: %r"
        % (len(lines), out)
    )
    assert lines[0].startswith("[mw run-detached] pid="), lines[0]
    assert lines[1].startswith("marker="), lines[1]
    assert lines[2].startswith("heartbeat="), lines[2]
    assert lines[3].startswith("log="), lines[3]

    # cmd.txt verbatim argv, one element per line
    assert (run_dir / "cmd.txt").read_text(encoding="utf-8") == "\n".join(argv) + "\n", (
        "cmd.txt mismatch in %s" % run_dir
    )

    marker = _poll_until(lambda: _read_json(run_dir / "marker.json"))
    assert marker is not None, "marker.json never appeared in %s (15s)" % run_dir
    assert marker.get("schema") == "mw-run/1", "marker schema=%r" % marker.get("schema")
    assert marker.get("rc") == 0, "marker rc=%r expected 0: %r" % (marker.get("rc"), marker)
    assert marker.get("timed_out") is False, "timed_out=%r" % marker.get("timed_out")
    assert marker.get("argv") == argv, "marker argv=%r expected %r" % (marker.get("argv"), argv)
    assert marker.get("wall_sec", 0) >= 0
    assert (run_dir / "run.log").is_file(), "run.log missing in %s" % run_dir
    print(
        "[VERIFY] VC-003: lines=%d rc=%d schema=%s run_dir=%s"
        % (len(lines), marker.get("rc"), marker.get("schema"), run_dir),
        flush=True,
    )


# ---------------------------------------------------------------------------
# Group 4 (VC-004 / AC-004): heartbeat progression + timeout seam
# ---------------------------------------------------------------------------

def _read_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@pytest.mark.skipif(SKIP_NON_WIN32, reason="win32-only: ping -n semantics")
def test_vc004a_heartbeat_progression(tmp_path, capsys):
    """--heartbeat-s 0.5 + ping -n 3 (~2s) -> heartbeat.json ts_ms advances:
    collect distinct ts_ms while polling; require >= 2."""
    run_dir = tmp_path / "run"
    argv = ["ping", "-n", "3", "127.0.0.1"]
    _run_detached(capsys, run_dir=run_dir, argv=argv, heartbeat_s=0.5)

    seen_ts: set[int] = set()
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        hb = _read_json(run_dir / "heartbeat.json")
        if hb is not None:
            assert hb.get("schema") == "mw-heartbeat/1", "heartbeat schema=%r" % hb.get("schema")
            seen_ts.add(int(hb["ts_ms"]))
        if len(seen_ts) >= 2:
            break
        time.sleep(0.15)
    assert len(seen_ts) >= 2, (
        "heartbeat ts_ms did not advance (saw %d distinct in %s): %r"
        % (len(seen_ts), run_dir, sorted(seen_ts))
    )
    print(
        "[VERIFY] VC-004a: distinct_heartbeats=%d ts=%r" % (len(seen_ts), sorted(seen_ts)),
        flush=True,
    )


@pytest.mark.skipif(SKIP_NON_WIN32, reason="win32-only: ping -n semantics")
def test_vc004b_timeout_seam(tmp_path, capsys):
    """--timeout-min 0.05 (3s) + ping -n 10 (~9s) -> timeout kills the tree:
    marker rc=124, timed_out=true (W-01 实测参数)."""
    run_dir = tmp_path / "run"
    argv = ["ping", "-n", "10", "127.0.0.1"]
    _run_detached(capsys, run_dir=run_dir, argv=argv, timeout_min=0.05)

    marker = _poll_until(lambda: _read_json(run_dir / "marker.json"))
    assert marker is not None, "marker.json never appeared in %s (15s)" % run_dir
    assert marker.get("rc") == 124, (
        "timeout marker rc=%r expected 124 (0x7c): %r" % (marker.get("rc"), marker)
    )
    assert marker.get("timed_out") is True, (
        "timed_out=%r expected True: %r" % (marker.get("timed_out"), marker)
    )
    assert marker.get("schema") == "mw-run/1", "marker schema=%r" % marker.get("schema")
    print(
        "[VERIFY] VC-004b: rc=%d timed_out=%s wall_sec=%s run_dir=%s"
        % (marker.get("rc"), marker.get("timed_out"), marker.get("wall_sec"), run_dir),
        flush=True,
    )


# ---------------------------------------------------------------------------
# Group 5 (VC-007 / AC-007): posix platform seam
# ---------------------------------------------------------------------------

def test_vc007_posix_seam(tmp_path, capsys, monkeypatch):
    """posix branch: start_new_session=True, no creationflags in kwargs."""
    run_dir = tmp_path / "run"
    argv = ["sh", "-c", "true"]
    seen: dict = {}

    class FakeProc:
        pid = 777

    def spy_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        seen.update(kwargs)
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", spy_popen)
    out = _run_detached(
        capsys,
        run_dir=run_dir,
        argv=argv,
        platform="posix",
        monkeypatch=monkeypatch,
    )
    assert seen.get("start_new_session") is True, (
        "posix branch start_new_session=%r expected True" % seen.get("start_new_session")
    )
    assert "creationflags" not in seen, (
        "posix branch passed creationflags=%r" % seen.get("creationflags")
    )
    assert len(out.splitlines()) == 4, out
    assert (run_dir / "cmd.txt").read_text(encoding="utf-8") == "\n".join(argv) + "\n"
    print(
        "[VERIFY] VC-007: start_new_session=%s creationflags_present=%s"
        % (seen.get("start_new_session"), "creationflags" in seen),
        flush=True,
    )

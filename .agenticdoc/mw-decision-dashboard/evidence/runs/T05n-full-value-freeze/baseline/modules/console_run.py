"""console_run.py — detached background command runner (mw-console-storm-hardening L1).

Two-stage structure (design.md D-002):

    mw run-detached [--cwd D] [--run-dir D] [--timeout-min N] [--heartbeat-s S] -- <cmd...>
      |   foreground CLI: validate -> build run_dir -> spawn the supervisor in a
      |   hidden console -> print the 4-line handoff contract -> return immediately
      `-> _run_supervisor             (internal mw.py subcommand, hidden from --help)
             |   creates run.log, injects the console-guard env, spawns <cmd...>
             |   (flags=0, list-args, no shell) with stdout+stderr -> run.log,
             |   writes heartbeat.json every interval, kills the tree on timeout
             `-> marker.json          (written before the supervisor exits)

win32: the supervisor is spawned with CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP.
Design M1 (evidence/research/design-win32-console-semantics-20261015.md): a
console-less parent + this flag combo gives the child a *hidden* console
(GetConsoleProcessList > 0, GetConsoleWindow == 0) that all descendants inherit,
so 0 visible windows even for future spawn sites that forget a flag.
DETACHED_PROCESS is never used (M2/M3: it leaves the tree console-less and
NO_WINDOW is ignored in the DETACHED combo, so grandchildren pop windows).
posix: start_new_session=True, no creationflags, no guard injection.

Evidence contract (spec §3 AC-003/AC-004):
  run_dir/     cmd.txt        argv verbatim, one element per line
               run.log        child stdout+stderr combined (wb)
               heartbeat.json {"schema":"mw-heartbeat/1","pid":...,"ts_ms":...}
               marker.json    {"schema":"mw-run/1","rc":...,"timed_out":...,
                               "started_at_ms":...,"ended_at_ms":...,
                               "wall_sec":...,"pid":...,"argv":[...]}
  timeout kill   -> marker rc=124 / timed_out=true
  spawn failure  -> marker rc=127 / spawn_failed=true
  P-003: heartbeat/marker are written temp-file + os.replace (never in-place).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

_HEARTBEAT_DEFAULT_S = 5.0

#: mw.py lives in this package dir; used both for the supervisor argv
#: ([sys.executable, mw.py, _run_supervisor, ...]) and for the guard directory
#: (Path(mw.py).parent / "mw_console_guard").
_MW_PY = pathlib.Path(__file__).resolve().parent / "mw.py"


# ── CLI: mw run-detached ───────────────────────────────────────────────────

def _strip_one_separator(argv: list[str]) -> list[str]:
    # argparse REMAINDER passes the first `--` through (self-note mw.py:3657),
    # so drop exactly one leading separator before storing/writing the argv.
    if argv and argv[0] == "--":
        return argv[1:]
    return argv


def _resolve_run_dir(cwd: pathlib.Path, explicit: str | None) -> pathlib.Path:
    """Fresh run dir: default <cwd>/.mw/runs/run-<YYYYMMDD-HHMMSS>, or the
    --run-dir target. An existing dir gets a -2/-3 suffix instead of failing
    (toolchain precedent mw.py:_toolchain_run_dir)."""
    if explicit:
        base = pathlib.Path(explicit).resolve()
    else:
        base = cwd / ".mw" / "runs" / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = base
    n = 2
    while True:
        try:
            # F1: create-and-fail is the atomic form. The old exists()->mkdir()
            # pair had a TOCTOU window where a concurrent creator wins in
            # between; FileExistsError now drives the -N suffix retry instead.
            run_dir.mkdir(parents=True, exist_ok=False)
            return run_dir
        except FileExistsError:
            run_dir = pathlib.Path(f"{base}-{n}")
            n += 1


def cmd_run_detached(args: argparse.Namespace) -> int:
    """Foreground CLI half: validate argv, write cmd.txt, spawn the
    hidden-console supervisor, print the 4-line handoff and return immediately."""
    argv = _strip_one_separator([str(t) for t in (getattr(args, "argv", None) or [])])
    if not argv:
        print("[mw run-detached] Error: no command after '--'", file=sys.stderr)
        return 1

    # F2a: validate before any side effect (run dir / cmd.txt). Values must be
    # strictly positive and decimals are legal (VC-004a 0.5s, VC-004b 0.05min);
    # `is None` (not `or`) keeps an explicit 0 from being silently replaced by
    # the default. mw.py's argparse owns flag parsing, so this is the post-check.
    heartbeat_s_raw = getattr(args, "heartbeat_s", None)
    timeout_min_raw = getattr(args, "timeout_min", None)
    try:
        heartbeat_s = _HEARTBEAT_DEFAULT_S if heartbeat_s_raw is None else float(heartbeat_s_raw)
        if not heartbeat_s > 0:  # NaN-safe: NaN > 0 is False
            raise ValueError(f"--heartbeat-s must be > 0, got {heartbeat_s}")
        timeout_min = None if timeout_min_raw is None else float(timeout_min_raw)
        if timeout_min is not None and not timeout_min > 0:
            raise ValueError(f"--timeout-min must be > 0, got {timeout_min}")
    except (TypeError, ValueError) as exc:
        print(f"[mw run-detached] Error: {exc}", file=sys.stderr)
        return 1

    cwd = pathlib.Path(args.cwd).resolve() if getattr(args, "cwd", None) else pathlib.Path.cwd()
    run_dir = _resolve_run_dir(cwd, getattr(args, "run_dir", None))
    (run_dir / "cmd.txt").write_text("\n".join(argv) + "\n", encoding="utf-8", newline="\n")

    sup_argv: list[str] = [
        sys.executable,
        str(_MW_PY),
        "_run_supervisor",
        "--run-dir",
        str(run_dir),
        "--cwd",
        str(cwd),
        "--heartbeat-s",
        str(heartbeat_s),
    ]
    if timeout_min is not None:
        sup_argv += ["--timeout-min", str(timeout_min)]
    sup_argv += ["--", *argv]

    if sys.platform == "win32":
        proc = subprocess.Popen(  # noqa: S603
            sup_argv,
            creationflags=(
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            ),
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(sup_argv, start_new_session=True, close_fds=True)  # noqa: S603

    print(f"[mw run-detached] pid={proc.pid}")
    print(f"marker={run_dir / 'marker.json'}")
    print(f"heartbeat={run_dir / 'heartbeat.json'}")
    print(f"log={run_dir / 'run.log'}")
    return 0


# ── Supervisor: _run_supervisor ────────────────────────────────────────────

def _positive_float(name: str, text: str) -> float:
    """F2a lower bound shared by --heartbeat-s/--timeout-min: strictly positive,
    decimals allowed (0.5s / 0.05min must stay valid). argparse turns the
    ArgumentTypeError into a usage error on stderr and a non-zero exit."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{name} must be a number, got {text!r}") from None
    if not value > 0:  # NaN-safe
        raise argparse.ArgumentTypeError(f"{name} must be > 0, got {value}")
    return value


def _positive_timeout_min(text: str) -> float:
    return _positive_float("--timeout-min", text)


def _positive_heartbeat_s(text: str) -> float:
    return _positive_float("--heartbeat-s", text)


def parse_supervisor_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mw _run_supervisor", add_help=False)
    p.add_argument("--cwd", default=None)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--timeout-min", type=_positive_timeout_min, default=None)
    p.add_argument("--heartbeat-s", type=_positive_heartbeat_s, default=_HEARTBEAT_DEFAULT_S)
    p.add_argument("argv", nargs=argparse.REMAINDER)
    return p.parse_args(argv)


def run_supervisor_entry(argv: list[str]) -> int:
    """Internal mw.py subcommand entry (never registered in argparse, so it
    stays out of --help): parse the supervisor argv and run the loop."""
    try:
        args = parse_supervisor_args(argv)
    except SystemExit:
        return 2
    return run_supervisor(args)


def _atomic_write_json(path: pathlib.Path, data: dict) -> None:
    """P-003: temp file + os.replace, never an in-place truncating write."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _marker_data(
    *,
    rc: int,
    timed_out: bool,
    started_at_ms: int,
    ended_at_ms: int,
    pid: int,
    argv: list[str],
    spawn_failed: bool = False,
) -> dict:
    data = {
        "schema": "mw-run/1",
        "rc": rc,
        "timed_out": bool(timed_out),
        "started_at_ms": started_at_ms,
        "ended_at_ms": ended_at_ms,
        "wall_sec": round((ended_at_ms - started_at_ms) / 1000.0, 3),
        "pid": pid,
        "argv": list(argv),
    }
    if spawn_failed:
        data["spawn_failed"] = True
    return data


def _child_env() -> dict:
    """Env for the user command: the caller's env plus, on win32 only, the
    console guard (MW_CONSOLE_GUARD=1 + PYTHONPATH prefix). Skipped when
    MW_CONSOLE_GUARD=0 is already set, and skipped on posix (design D-002:
    explicit skip avoids PYTHONPATH pollution; the guard is win32-only)."""
    env = dict(os.environ)
    if sys.platform != "win32":
        return env
    if os.environ.get("MW_CONSOLE_GUARD", "").strip() == "0":
        return env
    env["MW_CONSOLE_GUARD"] = "1"
    guard_dir = _MW_PY.parent / "mw_console_guard"
    if guard_dir.is_dir():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(guard_dir) + (os.pathsep + existing if existing else "")
    else:
        # fail-open: a missing guard dir must never block the command (D-003)
        print(f"[mw run-detached] warning: guard dir missing: {guard_dir}", file=sys.stderr)
    return env


def _kill_tree(child: subprocess.Popen) -> None:
    """Timeout kill of the whole tree, then reap. win32 taskkill /T /F; posix
    kill(-pgid) — the child is its own process-group leader (spawned with
    start_new_session on posix), so the supervisor's own group survives to
    write the marker (mw-worker-tree-kill precedent)."""
    try:
        if sys.platform == "win32":
            subprocess.run(  # noqa: S603
                ["taskkill", "/T", "/F", "/PID", str(child.pid)],
                capture_output=True,
                timeout=15,
            )
        else:
            os.killpg(child.pid, signal.SIGKILL)
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    except Exception:
        pass


def run_supervisor(args: argparse.Namespace) -> int:
    """Supervision loop: spawn the user command with stdout+stderr -> run.log,
    write heartbeat.json every interval, kill the tree on timeout, then write
    marker.json (before this process exits) and return 0."""
    run_dir = pathlib.Path(args.run_dir).resolve()
    cwd = pathlib.Path(args.cwd).resolve() if getattr(args, "cwd", None) else None
    timeout_min = float(getattr(args, "timeout_min", None) or 0)
    heartbeat_s = float(getattr(args, "heartbeat_s", _HEARTBEAT_DEFAULT_S) or _HEARTBEAT_DEFAULT_S)
    # F2a defense-in-depth: a negative heartbeat would make time.sleep() raise
    # and abort the loop without a marker. parse_supervisor_args already
    # rejects it; guard direct run_supervisor(Namespace) callers too.
    if not heartbeat_s > 0:  # NaN-safe
        print(
            f"[mw run-detached] supervisor error: --heartbeat-s must be > 0, got {heartbeat_s}",
            file=sys.stderr,
        )
        return 2
    argv = _strip_one_separator([str(t) for t in (getattr(args, "argv", None) or [])])

    started_at_ms = int(time.time() * 1000)
    try:
        log_fh = open(run_dir / "run.log", "wb")
    except OSError as exc:
        print(f"[mw run-detached] supervisor error: cannot open run.log: {exc}", file=sys.stderr)
        return 1

    try:
        try:
            child = subprocess.Popen(  # noqa: S603
                argv,
                cwd=str(cwd) if cwd else None,
                stdout=log_fh,
                stderr=log_fh,
                env=_child_env(),
                start_new_session=sys.platform != "win32",
            )
        except OSError as exc:
            _atomic_write_json(
                run_dir / "marker.json",
                _marker_data(
                    rc=127,
                    timed_out=False,
                    started_at_ms=started_at_ms,
                    ended_at_ms=int(time.time() * 1000),
                    pid=0,
                    argv=argv,
                    spawn_failed=True,
                ),
            )
            print(f"[mw run-detached] supervisor error: spawn failed: {exc}", file=sys.stderr)
            return 0

        deadline = time.monotonic() + timeout_min * 60.0 if timeout_min > 0 else None
        timed_out = False
        while True:
            _atomic_write_json(
                run_dir / "heartbeat.json",
                {"schema": "mw-heartbeat/1", "pid": child.pid, "ts_ms": int(time.time() * 1000)},
            )
            rc = child.poll()
            if rc is not None:
                break
            if deadline is not None and time.monotonic() >= deadline:
                _kill_tree(child)
                rc = 124
                timed_out = True
                break
            time.sleep(heartbeat_s)

        _atomic_write_json(
            run_dir / "marker.json",
            _marker_data(
                rc=rc,
                timed_out=timed_out,
                started_at_ms=started_at_ms,
                ended_at_ms=int(time.time() * 1000),
                pid=child.pid,
                argv=argv,
            ),
        )
        return 0
    finally:
        # N2: close explicitly even when flush() raises, so an exception on the
        # supervision path can never leak the run.log handle.
        try:
            log_fh.flush()
        finally:
            log_fh.close()

"""
mw.py — Multi-Workers service manager.

Subcommands:
  serve  — foreground: start launcher + conductor (proxy only when proxy-routed credentials exist), block until Ctrl-C/SIGTERM
  start  — background: detach and run serve
  stop   — send SIGTERM to running mw serve
  status — check if mw serve is running
  init   — install Extension bundle + AgenticTask framework into project
  pull-agentictask — clone/update the AgenticTask framework repo into .tmp/
  push-agentictask — commit+push local framework changes back to the remote repo
  setup  — one-time machine bootstrap: clone framework + install extension globally
  bootstrap — fresh-machine one-shot: prereqs → npm ci → build → link pi → setup → init → start → doctor
  update-env — incremental self-check over the update anchors (UPDATE.md); --apply runs the safe fixes
  ue-toolchain — dual-mode UE toolchain discipline (UE game dev: game repo + engine source repo, MSVC/UBT): run a configured command with evidence, discover UE targets, EOL-normalized hashing
  run-detached — detached background command runner: hidden-console supervisor + heartbeat/marker evidence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import console_run
import mw_common
import rag_templates
import usage
import worktree_cmd
from mw_common import (
    check_pid as _check_pid,
    port_is_bound as _port_is_bound,
)
from autopilot import config as _ap_config
from autopilot import conductor as _ap_conductor
from autopilot import contract_guard
from autopilot import roadmap as _ap_roadmap
from autopilot import timeline as _ap_timeline

_SCRIPT_DIR = pathlib.Path(__file__).parent
_LAUNCHER_PY = _SCRIPT_DIR / "launcher.py"
_PROXY_MULTI_PY = _SCRIPT_DIR / "proxy_multi.py"
_CONDUCTOR_PY = _SCRIPT_DIR / "autopilot" / "conductor.py"

# Local, gitignored clone of the AgenticTask framework repo — the bootstrap
# fallback for `init` on machines without a live framework checkout.
# `pull-agentictask` clones it from the remote once (then fast-forward-updates
# it). Because it is a real git clone, `push-agentictask` can commit+push
# framework changes straight back to the remote — Multi-Workers only records
# the remote URL, not any local path. `.tmp/` stays gitignored here; the
# nested `.git` is an independent repo. `init` source priority (see
# _resolve_framework_source): --sync-agentictask > the mw checkout's own
# .agents/skills/agentic-task (dev machine: the live working repo) > this cache.
_TMP_AGENTICTASK = _SCRIPT_DIR / ".tmp" / "agentic-task"
_DEFAULT_AGENTICTASK_REMOTE = "https://github.com/wenbocode/AgenticTask.git"
_DEFAULT_AGENTICTASK_BRANCH = "master"
_AGENTICTASK_IGNORE = {".git", "__pycache__"}


def _is_git_url(s: str) -> bool:
    """Heuristic: does `s` name a git remote (vs. a local source directory)?"""
    return s.startswith(("http://", "https://", "git@", "ssh://")) or s.endswith(".git")


# ── Port helpers ─────────────────────────────────────────────────────────────
# _port_is_bound / _check_pid live in mw_common (shared with doctor).


def _source_desc(source: dict) -> str:
    return mw_common._source_desc(source)  # noqa: SLF001 - re-export for serve logging


# ── PID helpers ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _pid_path(project_dir: pathlib.Path) -> pathlib.Path:
    return mw_common.pid_file(project_dir)


def _write_pid(pid_path: pathlib.Path) -> None:
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid(pid_path: pathlib.Path) -> None:
    try:
        pid_path.unlink()
    except FileNotFoundError:
        pass


def _stop_request_path(project_dir: pathlib.Path) -> pathlib.Path:
    return project_dir / ".mw" / "mw.stop"


def _write_stop_request(project_dir: pathlib.Path) -> None:
    p = _stop_request_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("stop", encoding="utf-8")


def _clear_stop_request(project_dir: pathlib.Path) -> None:
    try:
        _stop_request_path(project_dir).unlink()
    except FileNotFoundError:
        pass


# ── serve code identity (T-13 / AC-005: "is the serve running current code?") ─
# Identity schema version. Bump whenever the field set or its semantics change:
# a serve whose meta lacks (or predates) the current schema cannot be carrying
# the current drift self-check, so `mw status` / `mw doctor` report "must
# restart". A legacy meta (no `schema` key) reads as 0.
SERVE_META_SCHEMA = 1
# FS-timestamp slack for the legacy (pre-`code_digest`) mtime fallback — kept
# from the original stale-serve fix (FS mtime granularity vs the wall stamp).
_SERVE_META_MTIME_SLACK_MS = 2000
# Serve-loop drift re-check interval. A module constant, not a config key
# (AC-011); the comparison is a pure stat + one sha256 (~8 ms on this repo).
_SERVE_DRIFT_CHECK_SEC = 60.0
_RUNTIME_CODE_SUFFIXES = (".py", ".json")
_GIT_TIMEOUT_SEC = 3


def _serve_meta_path(project_dir: pathlib.Path) -> pathlib.Path:
    """Serve stamp for extension-side staleness detection (stale-serve fix):
    the agent-team-loop extension compares `started_at_ms` (and, since T-13,
    the recorded `commit`/`code_digest`) against the mw source tree. Removed on
    serve exit alongside the PID file."""
    return project_dir / ".mw" / "serve.meta"


def _serve_meta_identity(code_dir: pathlib.Path | None = None) -> dict:
    """Collect the running code's identity for `serve.meta` (fail-open).

    Every field degrades to None/"" — a missing git binary, a hung subprocess
    (3 s timeout), an unreadable tree, or no runtime files at all are never a
    reason to alert. Collection is pure file reads plus at most one git call
    (`dirty`); the digest walk is ~8 ms on this repo.
    """
    tree = pathlib.Path(code_dir) if code_dir is not None else _SCRIPT_DIR
    dirty = _git_dirty_counts(tree)
    newest = _mw_code_newest_mtime(tree)
    return {
        "schema": SERVE_META_SCHEMA,
        "commit": _git_head_oid(tree),
        "dirty_tracked": None if dirty is None else dirty[0],
        "dirty_untracked": None if dirty is None else dirty[1],
        "code_mtime_ms": None if newest is None else int(newest * 1000),
        "code_digest": _runtime_digest(tree),
        "version": _framework_version(),
    }


def _write_serve_meta(project_dir: pathlib.Path, identity: dict | None = None) -> None:
    """Atomically write the serve stamp (temp + os.replace, same volume).

    `identity` is collected by the caller BEFORE `_write_pid`, so a slow or
    hung git can never leave "PID file present, service not really up"; when
    omitted (unit tests) it is collected here.
    """
    meta = {
        "pid": os.getpid(),
        "started_at_ms": int(time.time() * 1000),
        "code_dir": str(_SCRIPT_DIR),
    }
    meta.update(identity if identity is not None else _serve_meta_identity())
    meta["written_at_ms"] = int(time.time() * 1000)
    p = _serve_meta_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(meta), encoding="utf-8")
    os.replace(tmp, p)


def _remove_serve_meta(project_dir: pathlib.Path) -> None:
    for p in (
        _serve_meta_path(project_dir),
        _serve_meta_path(project_dir).with_name("serve.meta.tmp"),
    ):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


# ── Conductor supervision (D-101: conductor = mw serve third child) ─────────

def _conductor_decision(enabled: bool, pid_alive: bool) -> str:
    """Pure supervision decision: spawn | terminate | none.

    serve's 1s loop applies this each iteration: enabled + no live conductor
    → spawn; disabled + live conductor → terminate; conductor death is
    detected via the pid file within 1s and healed by respawn (存活自愈)."""
    if enabled and not pid_alive:
        return "spawn"
    if (not enabled) and pid_alive:
        return "terminate"
    return "none"


def _conductor_supervise_step(
    project_dir: pathlib.Path,
    proc: subprocess.Popen[bytes] | None,
    spawn_kwargs: dict,
    log_handle: object,
) -> subprocess.Popen[bytes] | None:
    """One serve-loop supervision step for the conductor (config mtime-cached
    via cached_load). Returns the (possibly new) conductor proc.

    A present-but-partial config.json only carries the keys a human actually
    wrote (see config.load_config), so every key read here goes through
    ``.get(name, DEFAULT_CONFIG[name])``: a missing ``enabled`` means "not
    enabled", never a KeyError that would take the whole serve loop down."""
    enabled = _ap_config.cached_load(project_dir).get(
        "enabled", _ap_config.DEFAULT_CONFIG["enabled"]
    )
    pid_alive = (
        _check_pid(_ap_conductor.conductor_pid_file(project_dir)) is not None
        or (proc is not None and proc.poll() is None)
    )
    decision = _conductor_decision(enabled, pid_alive)
    if decision == "spawn":
        proc = subprocess.Popen(  # noqa: S603
            [sys.executable, str(_CONDUCTOR_PY), f"--project={project_dir}"],
            stdout=log_handle,
            stderr=log_handle,
            **spawn_kwargs,
        )
        print(f"[mw serve] conductor spawned (PID {proc.pid})", flush=True)
    elif decision == "terminate":
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception:
                pass
        try:
            _ap_conductor.conductor_pid_file(project_dir).unlink()
        except FileNotFoundError:
            pass
        proc = None
        print("[mw serve] conductor terminated (autopilot disabled)", flush=True)
    return proc


# ── Subcommand: serve ────────────────────────────────────────────────────────

def cmd_serve(args: argparse.Namespace) -> int:
    import threading

    project_dir = pathlib.Path(args.project).resolve()
    pid_path = _pid_path(project_dir)
    mw_dir = project_dir / ".mw"
    mw_dir.mkdir(parents=True, exist_ok=True)

    existing = _check_pid(pid_path)
    if existing is not None:
        print(
            f"[mw serve] already running (PID {existing}). Use 'mw stop' first.",
            file=sys.stderr,
        )
        return 1

    _clear_stop_request(project_dir)

    # ── Logging: redirect own stdout/stderr to mw.log ──
    mw_log = open(mw_dir / "mw.log", "a", encoding="utf-8")
    proxy_log = open(mw_dir / "proxy.log", "a", encoding="utf-8")
    # launcher.log is truncated per serve session: it belongs to the launcher
    # child of THIS serve instance, and stale FATAL lines from previous
    # (pre-fix) sessions would otherwise keep doctor reporting a false issue.
    launcher_log = open(mw_dir / "launcher.log", "w", encoding="utf-8")
    # Same per-session truncate pattern as launcher.log; respawns within one
    # serve session share the handle, so their output appends (D-101).
    conductor_log = open(mw_dir / "conductor.log", "w", encoding="utf-8")
    real_stdout, real_stderr = sys.stdout, sys.stderr
    sys.stdout = mw_log
    sys.stderr = mw_log

    intentional_stop = threading.Event()
    exit_code = 1  # default: unexpected/error exit
    proxy_proc: subprocess.Popen[bytes] | None = None
    launcher_proc: subprocess.Popen[bytes] | None = None
    conductor_proc: subprocess.Popen[bytes] | None = None
    wrote_pid = False

    try:
        # ── Route precheck (design D-002 / AC-002, AC-003) ──
        # Runs BEFORE the PID file is written, so "PID file exists" implies
        # "service actually started" (the PM stable-window relies on it).
        # Default: the providers.json shipped next to mw.py (the package copy),
        # NOT the in-memory defaults — the file is the source of truth.
        providers_path = (
            pathlib.Path(args.providers)
            if args.providers
            else pathlib.Path(__file__).parent / "providers.json"
        )
        config = mw_common.load_providers(providers_path)
        precheck = mw_common.route_precheck(config, os.environ)
        for st in precheck["routes"]:
            if st["available"]:
                print(
                    f"[mw serve] route {st['route']}: available ({_source_desc(st['source'])})",
                    flush=True,
                )
            else:
                print(f"[mw serve] route {st['route']}: missing ({st['missing']})", flush=True)
        if precheck["all_missing"]:
            msg = "[mw serve] FATAL: no route has credentials; refusing to start. Set at least one credential (env or configured file source) before mw serve."
            print(msg, flush=True)
            print(msg, file=real_stderr, flush=True)
            exit_code = 1
            return 1

        # Identity collection is deliberately BEFORE the PID file (T-13): a git
        # call that hangs here would otherwise leave "mw.pid exists" true while
        # launcher/conductor never spawn — the stale-serve failure shape.
        identity = _serve_meta_identity()
        _write_pid(pid_path)
        wrote_pid = True
        _write_serve_meta(project_dir, identity)
        print(f"[mw serve] code identity: {_format_serve_identity(identity)}", flush=True)
        # Build spawn kwargs: hide console window on Windows
        spawn_kwargs: dict = {}
        if sys.platform == "win32":
            spawn_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        proxy_cmd = [
            sys.executable,
            str(_PROXY_MULTI_PY),
            f"--pi-port={args.pi_port}",
            f"--claude-port={args.claude_port}",
        ]
        if args.deepseek_port:
            proxy_cmd.append(f"--deepseek-port={args.deepseek_port}")
        # The LLM proxy only serves port-routed providers (claude / claude-cli /
        # deepseek) and needs the private timi-proxy-cli package; direct routes
        # (timi, zai-coding-cn, codex-native) never touch it. With no
        # proxy-routed credential available, skip it entirely instead of dying
        # on the optional dependency — fresh machines without that package hit
        # ModuleNotFoundError at import and used to take the whole service down.
        proxy_routes = [
            st["route"]
            for st in precheck["routes"]
            if st["available"]
            and (config.get("providers", {}).get(st["route"]) or {}).get("port")
        ]
        # If another mw instance already has the proxy running on these ports,
        # share it instead of starting a second one (supports multiple pi windows).
        proxy_already_running = _port_is_bound(args.pi_port) and _port_is_bound(args.claude_port)
        if not proxy_routes:
            proxy_proc = None
            print(
                "[mw serve] no proxy-routed credentials (claude/claude-cli/deepseek)"
                " - proxy disabled; direct routes only (timi / zai-coding-cn / codex-native)",
                flush=True,
            )
        elif proxy_already_running:
            proxy_proc = None
            print(
                f"[mw serve] ports {args.pi_port}/{args.claude_port} already bound"
                " — sharing existing proxy",
                flush=True,
            )
        else:
            proxy_proc = subprocess.Popen(proxy_cmd, stdout=proxy_log, stderr=proxy_log, **spawn_kwargs)  # noqa: S603

        launcher_cmd = [
            sys.executable,
            str(_LAUNCHER_PY),
            f"--project={project_dir}",
            f"--poll-interval={args.poll_interval}",
            f"--pi-port={args.pi_port}",
            f"--claude-port={args.claude_port}",
        ]
        if args.deepseek_port:
            launcher_cmd.append(f"--deepseek-port={args.deepseek_port}")
        if args.max_workers:
            launcher_cmd.append(f"--max-workers={args.max_workers}")
        if args.providers:
            launcher_cmd.append(f"--providers={args.providers}")

        launcher_proc = subprocess.Popen(launcher_cmd, stdout=launcher_log, stderr=launcher_log, **spawn_kwargs)  # noqa: S603

        if proxy_proc is not None:
            proxy_info = f"proxy={proxy_proc.pid}"
        elif proxy_routes:
            proxy_info = "proxy=shared"
        else:
            proxy_info = "proxy=disabled"
        print(
            f"[mw serve] started (PID {os.getpid()}) — {proxy_info} launcher={launcher_proc.pid}",
            flush=True,
        )

        if sys.platform != "win32":
            def _on_sigterm(signum: int, frame: object) -> None:  # noqa: ARG001
                intentional_stop.set()
            signal.signal(signal.SIGTERM, _on_sigterm)

        drift_seen: set[tuple] = set()
        drift_last = 0.0  # first iteration = the startup comparison
        try:
            while True:
                if intentional_stop.is_set():
                    break
                if _stop_request_path(project_dir).exists():
                    _clear_stop_request(project_dir)
                    intentional_stop.set()
                    break
                if launcher_proc.poll() is not None:
                    break
                if proxy_proc is not None and proxy_proc.poll() is not None:
                    print(
                        f"[mw serve] FATAL: proxy exited (code {proxy_proc.returncode});"
                        " .mw/proxy.log tail:",
                        flush=True,
                    )
                    for tail_line in mw_common.read_log_tail(mw_dir / "proxy.log", 15):
                        print(f"  {tail_line}", flush=True)
                    break
                # Conductor supervision (D-101): config-driven spawn/terminate,
                # respawn within 1s on death. A dead conductor does NOT stop serve.
                conductor_proc = _conductor_supervise_step(
                    project_dir, conductor_proc, spawn_kwargs, conductor_log
                )
                # Code drift self-check (T-13/AC-005), throttled to 60 s. Only
                # warns (stderr -> mw.log + timeline `config`); it never restarts
                # (AC-006: TS owns interactive restart).
                now_mono = time.monotonic()
                if now_mono - drift_last >= _SERVE_DRIFT_CHECK_SEC:
                    drift_last = now_mono
                    _report_serve_code_drift(project_dir, drift_seen)
                time.sleep(1)
        except KeyboardInterrupt:
            intentional_stop.set()

        exit_code = 0 if intentional_stop.is_set() else 1

    finally:
        for proc in (conductor_proc, launcher_proc, proxy_proc):
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                except Exception:
                    pass
        if wrote_pid:
            _remove_pid(pid_path)
            _remove_serve_meta(project_dir)
        _clear_stop_request(project_dir)
        print("[mw serve] stopped", flush=True)
        # Restore the real streams (in-process callers like tests keep working)
        sys.stdout = real_stdout
        sys.stderr = real_stderr
        # Close log files
        mw_log.close()
        proxy_log.close()
        launcher_log.close()
        conductor_log.close()

    return exit_code


# ── Subcommand: start ────────────────────────────────────────────────────────

def cmd_start(args: argparse.Namespace) -> int:
    """Detach and run mw serve in the background."""
    cmd = [sys.executable, str(pathlib.Path(__file__).resolve()), "serve"]
    # Forward serve-relevant args
    cmd += [
        f"--project={args.project}",
        f"--pi-port={args.pi_port}",
        f"--claude-port={args.claude_port}",
        f"--poll-interval={args.poll_interval}",
    ]
    if args.max_workers:
        cmd.append(f"--max-workers={args.max_workers}")
    if args.providers:
        cmd.append(f"--providers={args.providers}")
    if args.deepseek_port:
        cmd.append(f"--deepseek-port={args.deepseek_port}")

    if sys.platform == "win32":
        # Design M1 (evidence/research/design-win32-console-semantics-20261015.md):
        # with a console-less parent, CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        # gives the child a *hidden* console (GetConsoleProcessList > 0) that
        # every descendant inherits — the whole serve tree is covered
        # structurally, even for future spawn sites that forget a flag.
        # No DETACHED_PROCESS: it leaves the tree console-less (M3: NO_WINDOW is
        # ignored in the DETACHED combo) and grandchildren pop windows (M2).

        # Redirect serve's own stdio to .mw/serve-console.log (append): under
        # the old DETACHED mode this output vanished without a trace.
        serve_log_dir = pathlib.Path(args.project) / ".mw"
        serve_log_dir.mkdir(parents=True, exist_ok=True)
        serve_log_fh = open(serve_log_dir / "serve-console.log", "ab")
        try:
            proc = subprocess.Popen(  # noqa: S603
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                close_fds=True,
                stdout=serve_log_fh,
                stderr=serve_log_fh,
            )
        finally:
            # The child owns its duplicated handles; close ours even on spawn
            # failure so a repeated `mw start` cannot leak file handles.
            serve_log_fh.close()
    else:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            start_new_session=True,
            close_fds=True,
        )

    print(f"[mw start] background PID: {proc.pid}")
    return 0


# ── Subcommand: stop ─────────────────────────────────────────────────────────

def _stop_serve(project_dir: pathlib.Path) -> bool:
    """Graceful stop: stop-request, then wait up to 30s for serve to exit.
    True when stopped (or not running in the first place). Shared by cmd_stop
    and update-env --apply."""
    pid_path = _pid_path(project_dir)
    pid = _check_pid(pid_path)
    if pid is None:
        return True
    _write_stop_request(project_dir)
    # Wait up to 30s for serve to exit (no force-kill)
    for _ in range(60):
        time.sleep(0.5)
        if _check_pid(pid_path) is None:
            return True
    return False


def cmd_stop(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project).resolve()
    pid = _check_pid(_pid_path(project_dir))
    if pid is None:
        print("[mw stop] not running (no PID or process not found)")
        return 0
    if _stop_serve(project_dir):
        print(f"[mw stop] stopped PID {pid}")
        return 0
    print(f"[mw stop] warning: process {pid} did not exit in 30s")
    return 1


# ── Subcommand: status ───────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project).resolve()
    pid_path = _pid_path(project_dir)
    pid = _check_pid(pid_path)
    if pid is not None:
        print(f"[mw status] running (PID {pid})")
    else:
        print("[mw status] not running")
    # Conductor row (D-101): PID, alive, last tick watermark (timeline tail).
    cstat = _ap_conductor.conductor_status(project_dir)
    if cstat["running"]:
        print(
            f"[mw status] conductor: running (PID {cstat['pid']}, "
            f"last tick seq={cstat['last_seq']} ts={cstat['last_ts']})"
        )
    else:
        print("[mw status] conductor: not running")
    # Serve code identity (T-13/AC-005): the smallest fresh-process-side entry —
    # a new `mw status` process reads serve.meta + the code tree, so it sees a
    # stale serve that could never see itself. Exit code is unchanged (a stale
    # serve is still a valid status read; `mw doctor` is the gating entry).
    if pid is None:
        print("[mw status] serve code: n/a (not running)")
    else:
        print(f"[mw status] serve code: {serve_code_verdict(project_dir)['detail']}")
        mismatch = _serve_identity_mismatch(project_dir, pid)
        if mismatch:
            print(f"[mw status] {mismatch}")
    return 0 if pid is not None else 1


# ── Subcommand: doctor ───────────────────────────────────────────────────────

def cmd_doctor(args: argparse.Namespace) -> int:
    """One-shot full-chain diagnostic (service/proxy/orphan/log/queue/credentials/bundle).

    Exit 0 = healthy, 1 = issues found. --fix auto-fixes stale entries + stale
    PID; --json emits the machine-readable report (consumed by /mw doctor)."""
    project_dir = pathlib.Path(args.project).resolve()
    providers_path = (
        pathlib.Path(args.providers)
        if args.providers
        else pathlib.Path(__file__).parent / "providers.json"
    )
    config = mw_common.load_providers(providers_path)
    raw_scan_roots = getattr(args, "worktree_scan_roots", None)
    worktree_scan_roots = (
        [part for part in str(raw_scan_roots).split(";") if part.strip()]
        if raw_scan_roots
        else None
    )
    report = mw_common.doctor_report(
        project_dir,
        fix=args.fix,
        config=config,
        stale_after_sec=args.stale_after,
        worktree_scan_roots=worktree_scan_roots,
    )
    # Conductor section (D-101): informational like worker_liveness — a not
    # running conductor (autopilot disabled) is not an issue.
    report["conductor"] = _ap_conductor.conductor_status(project_dir)
    # RAG section (mw-rag-integration D-010): informational — a broken config
    # or an unreachable server never flips the healthy verdict.
    report["rag"] = _doctor_rag(project_dir)
    # Write-face refusal surface (mw-write-face-guard W-15, AC-006): purely
    # informational — a refusal is normal gate behaviour, so neither 0 nor N
    # refusals may flip the healthy verdict (it never enters `issues`).
    report["write_face"] = _doctor_write_face(project_dir)
    # Serve code identity (T-13/AC-005): drift is an ISSUE (exit 1); the TS
    # `doctorMw` caller tolerates exit 1 and still parses the JSON. Missing
    # baseline fields are only a suggestion (never alert on absence).
    serve_code = _serve_code_doctor_section(project_dir)
    report["serve_code"] = serve_code
    if serve_code["verdict"] == "drift":
        report["summary"]["issues"].append(serve_code["detail"])
        report["summary"]["healthy"] = False
    elif serve_code["verdict"] == "undecidable":
        report["summary"]["suggestions"].append(serve_code["detail"])
    if serve_code.get("identity_mismatch"):
        report["summary"]["suggestions"].append(serve_code["identity_mismatch"])
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(mw_common.format_doctor_text(report))
        rag = report.get("rag") or {}
        if rag.get("exists") or rag.get("enabled"):
            print(_format_rag_doctor_line(rag))
        print(_format_write_face_doctor_line(report["write_face"]))
        print(f"serve code: {serve_code['detail']}")
    return 0 if report["summary"]["healthy"] else 1


# ── Subcommand: target (dual-workspace config, mw-dual-workspace D-011) ──────

def _yml_scalar(value: str) -> str:
    """Single-quoted YAML scalar (no escape sequences; Windows paths safe)."""
    return "'" + value.replace("'", "''") + "'"


def _apply_bootstrap_line(text: str, key: str, value: str | None) -> str:
    """Line-level top-level `key: value` update — comments, section bodies and
    line endings elsewhere are preserved byte-for-byte (design D-010: the three
    profile sections are hand-maintained; `target set` never rewrites them via
    YAML round-trip). value=None drops the key."""
    lines = text.splitlines(keepends=True)
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    out: list[str] = []
    replaced = False
    for line in lines:
        if pattern.match(line):
            if value is not None:
                ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
                out.append(f"{key}: {value}{ending}")
            replaced = True
        else:
            out.append(line)
    if value is not None and not replaced:
        idx = 0
        while idx < len(out) and (out[idx].lstrip().startswith("#") or out[idx].strip() == ""):
            idx += 1
        out.insert(idx, f"{key}: {value}\n")
    return "".join(out)


def _target_template(game: str, engine: str | None, vcs: str | None, uproject: str | None) -> str:
    lines = [
        "# Dual-workspace target config (mw target set). File absent = single mode.",
        "# Bootstrap fields are managed by `mw target set/clear`; the three sections",
        "# below are hand-maintained profiles (mw-dual-workspace design D-010).",
        "mode: dual",
        f"game: {game}",
    ]
    if engine is not None:
        lines.append(f"engine: {engine}")
    if vcs is not None:
        lines.append(f"vcs: {vcs}")
    if uproject is not None:
        lines.append(f"uproject: {uproject}")
    lines += [
        "",
        "toolchain:",
        "  # Dual-mode UE project: command templates with {game}/{engine}/{uproject}",
        "  # placeholders (UE game repo + engine source repo, MSVC/UBT). PM-side execution",
        "  # goes through `mw ue-toolchain run <name> [--args \"...\"]`: runs from the control",
        "  # root, archives cmd.txt / run.log / exit.txt / errors.txt / meta.json (exit",
        "  # code + error-signature scan + --watch EOL-normalized before/after hashes).",
        "  # mw exit code = clean exit AND zero signature lines AND zero --watch drift;",
        "  # error signatures are the MSVC/UE set — the run evidence discipline itself is",
        "  # toolchain-agnostic. Practice guide (per-project parts: UBT args, modal",
        "  # windows, fixtures): docs/dual-toolchain-practice-guide.md",
        "  # build_editor: '\"{engine}/Engine/Build/BatchFiles/Build.bat\" ProjEditor Win64 Development -project=\"{uproject}\" -WaitMutex'",
        "  # build_local: same template + -NoUBA -MaxParallelActions=16   # no-Horde fallback",
        "",
        "ignore:",
        "  # L1 deny globs for read/ls/find/grep (absolute or game-root-relative",
        "  # minimatch basis). Uncomment and extend:",
        "  # deny_globs:",
        "  #   - \"**/*.uasset\"",
        "  #   - \"**/DerivedDataCache/**\"",
        "",
        "contract:",
        "  # forbidden_paths: []",
        "  # conventions: |",
        "  #   project conventions injected into every dispatched task.md",
        "  # docs: []",
        "",
    ]
    return "\n".join(lines)


def _print_target_summary(config: dict) -> None:
    print(f"[mw target] mode: {config['mode']} (source: {config['source']})")
    print(f"[mw target] control root: {config['control_root']}")
    print(f"[mw target] game root:    {config['game_root']}")
    print(f"[mw target] engine root:  {config['engine_root'] or '-'}")
    print(f"[mw target] vcs: {config['vcs'] or '-'}  uproject: {config['uproject'] or '-'}")
    if config["toolchain"]:
        print(f"[mw target] toolchain commands: {', '.join(sorted(config['toolchain']))}")


def _target_set(project_dir: pathlib.Path, args: argparse.Namespace) -> int:
    game = pathlib.Path(args.game).resolve()
    if not game.is_dir():
        print(f"[mw target set] Error: game root not found: {game}", file=sys.stderr)
        return 1
    engine: str | None = None
    if args.engine is not None:
        engine_path = pathlib.Path(args.engine).resolve()
        if not engine_path.is_dir():
            print(f"[mw target set] Error: engine root not found: {engine_path}", file=sys.stderr)
            return 1
        engine = _yml_scalar(str(engine_path))
    vcs = args.vcs
    uproject: str | None = None
    if args.uproject is not None:
        candidate = pathlib.Path(args.uproject)
        if not candidate.is_absolute():
            candidate = game / candidate
        if not candidate.is_file():
            print(f"[mw target set] Error: uproject not found: {candidate}", file=sys.stderr)
            return 1
        uproject = _yml_scalar(args.uproject)

    yml = mw_common.target_yml_path(project_dir)
    yml.parent.mkdir(parents=True, exist_ok=True)
    if yml.exists():
        text = yml.read_text(encoding="utf-8")
        try:
            raw = _try_parse_yml(text)
        except mw_common.TargetConfigError as e:
            # FIX-7: a parseable but non-mapping file is never an empty v1 —
            # refuse instead of migrating/rewriting on top of it.
            print(f"[mw target set] Error ({e.kind}): {e}", file=sys.stderr)
            return 1
        if raw is not None and _yml_shape(raw) == "v2":
            # v2 file: the dual block is the target of the bootstrap write and
            # `active` flips to dual (new branch, design D-008; the v1 flat
            # write below is byte-identical to the historical one — AC-013).
            exact = _read_yml_exact(yml)
            if raw.get("dual") is not None and not _block_layout_ok(exact, "dual"):
                print(
                    f"[mw target set] Error: {_FLOW_LAYOUT_MSG.format(block='dual')}",
                    file=sys.stderr,
                )
                return 1
            exact = _apply_bootstrap_line(exact, "active", "dual")
            exact = _apply_mode_block(
                exact,
                "dual",
                [
                    ("game", _yml_scalar(str(game))),
                    ("engine", engine),
                    ("vcs", f"{vcs}" if vcs is not None else None),
                    ("uproject", uproject),
                ],
                None,
            )
            try:
                _atomic_write_yml(yml, exact)
            except OSError as e:
                print(f"[mw target set] Error: writing {yml} failed: {e}", file=sys.stderr)
                return 1
        elif raw is not None and _yml_shape(raw) == "mixed":
            print(f"[mw target set] Error: {_MIXED_FORMAT_MSG}", file=sys.stderr)
            return 1
        else:
            # v1 (or unparseable) file: the historical flat line write, unchanged
            text = _apply_bootstrap_line(text, "mode", "dual")
            text = _apply_bootstrap_line(text, "game", _yml_scalar(str(game)))
            text = _apply_bootstrap_line(text, "engine", engine)
            text = _apply_bootstrap_line(text, "vcs", f"{vcs}" if vcs is not None else None)
            text = _apply_bootstrap_line(text, "uproject", uproject)
            yml.write_text(text, encoding="utf-8")
    else:
        yml.write_text(
            _target_template(_yml_scalar(str(game)), engine, vcs, uproject),
            encoding="utf-8",
        )
    try:
        config = mw_common.load_target_config(project_dir)
    except mw_common.TargetConfigError as e:
        # Bootstrap fields are written; a hand-maintained section is broken.
        print(f"[mw target set] Warning: config resolves with an error ({e.kind}): {e}", file=sys.stderr)
        return 1
    _print_target_summary(config)
    return 0


def _target_clear(project_dir: pathlib.Path) -> int:
    """`mw target clear` (mw-target-partition FIX-6): a v1 file keeps the
    historical whole-file unlink (zero change); a v2 file clears only the
    dual block — active: dual → single, a parked partition block survives,
    and the file is deleted only when no mode block remains (symmetric to
    `mw partition clear`, AC-011)."""
    yml = mw_common.target_yml_path(project_dir)
    if not yml.exists():
        print("[mw target clear] no target.yml — already single mode")
        return 0
    exact = _read_yml_exact(yml)
    try:
        raw = _try_parse_yml(exact)
    except mw_common.TargetConfigError as e:
        print(f"[mw target clear] Error ({e.kind}): {e}", file=sys.stderr)
        return 1
    if raw is None:
        print(
            "[mw target clear] Error: target.yml is not valid YAML — fix or remove it first",
            file=sys.stderr,
        )
        return 1
    shape = _yml_shape(raw)
    if shape == "mixed":
        print(f"[mw target clear] Error: {_MIXED_FORMAT_MSG}", file=sys.stderr)
        return 1
    if shape != "v2":
        # v1 flat file: the historical behavior — remove the whole file
        try:
            yml.unlink()
        except OSError as e:
            print(f"[mw target clear] Error: removing {yml} failed: {e}", file=sys.stderr)
            return 1
        print(f"[mw target clear] removed {yml} — mode resolves to single")
        return 0
    if not isinstance(raw.get("dual"), dict):
        print("[mw target clear] no dual block — nothing to clear")
        return 0
    lines = exact.splitlines(keepends=True)
    header_idx = _find_block_header(lines, "dual")
    if header_idx is None:
        print(f"[mw target clear] Error: {_FLOW_LAYOUT_MSG.format(block='dual')}", file=sys.stderr)
        return 1
    end = _block_end(lines, header_idx)
    start = header_idx
    if start > 0 and lines[start - 1].strip() == "":
        start -= 1  # the separator blank line appended with the block
    del lines[start:end]
    text = "".join(lines)
    was_active = raw.get("active") == "dual"
    if was_active:
        text = _apply_bootstrap_line(text, "active", "single")
    if not isinstance(raw.get("partition"), dict):
        # no mode block remains — the file carries no mode config anymore
        try:
            yml.unlink()
        except OSError as e:
            print(f"[mw target clear] Error: removing {yml} failed: {e}", file=sys.stderr)
            return 1
        print(f"[mw target clear] removed dual block; no mode blocks remain — deleted {yml}")
        return 0
    try:
        _atomic_write_yml(yml, text)
    except OSError as e:
        print(f"[mw target clear] Error: writing {yml} failed: {e}", file=sys.stderr)
        return 1
    if was_active:
        print("[mw target clear] removed dual block, active: single (partition block kept)")
    else:
        print(f"[mw target clear] removed parked dual block (active stays {raw.get('active')})")
    return 0


def _target_show(project_dir: pathlib.Path) -> int:
    try:
        config = mw_common.load_target_config(project_dir)
    except mw_common.TargetConfigError as e:
        print(f"[mw target show] Error ({e.kind}): {e}", file=sys.stderr)
        return 1
    if config["mode"] == "partition":
        # AC-018a: the partition family owns the view while partition is active
        print(
            "[mw target show] Error: active mode is partition — use `mw partition show` "
            "(partition fields are not part of the target/dual view)",
            file=sys.stderr,
        )
        return 1
    _print_target_summary(config)
    render_failed = False
    for name, command in sorted(config["toolchain"].items()):
        try:
            rendered = mw_common.render_toolchain_command(command, config)
            print(f"[mw target]   {name}: {rendered}")
        except mw_common.TargetConfigError as e:
            render_failed = True
            print(f"[mw target]   {name}: ERROR ({e.kind}): {e}", file=sys.stderr)
    if config["ignore"]["deny_globs"]:
        print(f"[mw target] deny_globs: {len(config['ignore']['deny_globs'])} rule(s)")
    return 1 if render_failed else 0


def _target_on(project_dir: pathlib.Path) -> int:
    """`mw target on` (AC-023, symmetric to `mw partition on`): v2 file with a
    usable dual block → active: dual. v1 files are rejected with the
    migration hint (on/off require v2; `mw partition set` is the migration
    path — `mw target set` keeps writing v1 on v1 files, AC-013)."""
    yml = mw_common.target_yml_path(project_dir)
    if not yml.exists():
        print(
            "[mw target on] Error: no target.yml — run `mw target set --game <dir> ...` first",
            file=sys.stderr,
        )
        return 1
    exact = _read_yml_exact(yml)
    try:
        raw = _try_parse_yml(exact)
    except mw_common.TargetConfigError as e:
        print(f"[mw target on] Error ({e.kind}): {e}", file=sys.stderr)
        return 1
    if raw is None:
        print(
            "[mw target on] Error: target.yml is not valid YAML — fix or remove it first",
            file=sys.stderr,
        )
        return 1
    shape = _yml_shape(raw)
    if shape == "mixed":
        print(f"[mw target on] Error: {_MIXED_FORMAT_MSG}", file=sys.stderr)
        return 1
    if shape == "v1":
        print(
            "[mw target on] Error: target.yml is v1 format — on/off require v2; run "
            "`mw partition set ...` (it migrates v1 to v2 with a .bak backup)",
            file=sys.stderr,
        )
        return 1
    block = raw.get("dual")
    if not isinstance(block, dict) or block.get("game") is None:
        print(
            "[mw target on] Error: no usable dual block (game root missing) — run "
            "`mw target set --game <dir> ...` first",
            file=sys.stderr,
        )
        return 1
    if not _block_layout_ok(exact, "dual"):
        print(f"[mw target on] Error: {_FLOW_LAYOUT_MSG.format(block='dual')}", file=sys.stderr)
        return 1
    text = _apply_bootstrap_line(exact, "active", "dual")
    try:
        _atomic_write_yml(yml, text)
    except OSError as e:
        print(f"[mw target on] Error: writing {yml} failed: {e}", file=sys.stderr)
        return 1
    try:
        mw_common.load_target_config(project_dir)
    except mw_common.TargetConfigError as e:
        print(
            f"[mw target on] Warning: active is now dual but the config resolves with "
            f"an error ({e.kind}): {e}",
            file=sys.stderr,
        )
        return 1
    print("[mw target on] active: dual (takes effect on the next worker spawn; no serve restart needed)")
    return 0


def _target_off(project_dir: pathlib.Path) -> int:
    """`mw target off` (AC-023, symmetric to `mw partition off`): active dual →
    active single, dual block kept. Everything else is an idempotent no-op
    (exit 0) except v1 files, which carry the migration hint (AC-023)."""
    yml = mw_common.target_yml_path(project_dir)
    if not yml.exists():
        print("[mw target off] dual mode is not active (no target.yml) — nothing to do")
        return 0
    exact = _read_yml_exact(yml)
    try:
        raw = _try_parse_yml(exact)
    except mw_common.TargetConfigError as e:
        print(f"[mw target off] Error ({e.kind}): {e}", file=sys.stderr)
        return 1
    if raw is None:
        print(
            "[mw target off] Error: target.yml is not valid YAML — fix or remove it first",
            file=sys.stderr,
        )
        return 1
    shape = _yml_shape(raw)
    if shape == "mixed":
        print(f"[mw target off] Error: {_MIXED_FORMAT_MSG}", file=sys.stderr)
        return 1
    if shape == "v1":
        print(
            "[mw target off] Error: target.yml is v1 format — on/off require v2; run "
            "`mw partition set ...` (it migrates v1 to v2 with a .bak backup)",
            file=sys.stderr,
        )
        return 1
    if raw.get("active") != "dual":
        print(f"[mw target off] dual mode is not active (active: {raw.get('active')}) — nothing to do")
        return 0
    text = _apply_bootstrap_line(exact, "active", "single")
    try:
        _atomic_write_yml(yml, text)
    except OSError as e:
        print(f"[mw target off] Error: writing {yml} failed: {e}", file=sys.stderr)
        return 1
    print("[mw target off] active: single (dual block kept; takes effect on the next worker spawn)")
    return 0


def cmd_target(args: argparse.Namespace) -> int:
    """Dual-workspace target config: set bootstrap fields / clear / show the
    resolved view (mw-dual-workspace AC-005, D-011) + on/off mode switching
    (mw-target-partition AC-023)."""
    project_dir = pathlib.Path(args.project).resolve()
    if args.target_action == "set":
        return _target_set(project_dir, args)
    if args.target_action == "clear":
        return _target_clear(project_dir)
    if args.target_action == "on":
        return _target_on(project_dir)
    if args.target_action == "off":
        return _target_off(project_dir)
    return _target_show(project_dir)


# ── Subcommand: toolchain (dual-mode discipline, practice guide) ───────────

def _toolchain_run_dir(control_root: pathlib.Path, out_parent: pathlib.Path | None, name: str) -> pathlib.Path:
    """Fresh run directory <stamp>-<name> under --out (default the
    machine-local .mw/toolchain-runs). Same-second collisions get a -2/-3
    suffix instead of failing."""
    parent = out_parent if out_parent is not None else control_root / ".mw" / "toolchain-runs"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = parent / f"{stamp}-{name}"
    n = 2
    while run_dir.exists():
        run_dir = parent / f"{stamp}-{name}-{n}"
        n += 1
    run_dir.mkdir(parents=True)
    return run_dir


def _toolchain_load_config(project_dir: pathlib.Path) -> dict | None:
    """Fail-closed config load for the toolchain subcommands: prints the
    TargetConfigError and returns None (caller returns exit 1)."""
    try:
        return mw_common.load_target_config(project_dir)
    except mw_common.TargetConfigError as e:
        print(f"[mw ue-toolchain] Error: target config {e.kind}: {e}", file=sys.stderr)
        return None


def _toolchain_run(args: argparse.Namespace) -> int:
    """Execute toolchain.<name> from the control root with the practice
    guide's evidence discipline (§2.2/§2.3/§4.2): verbatim cmd.txt, UTF-8
    combined run.log (.log extension — quality gates only scan *.log),
    exit.txt, errors.txt + meta.json (error-signature scan; --watch proves
    watched sources were not edited while the command ran, EOL-normalized
    so autocr lf flips are not false drift). Verdict = exit 0 AND zero
    error lines AND zero drift; anything else exits 1 so scripts can gate
    on it (differential acceptance compares two runs' errors.txt sets)."""
    project_dir = pathlib.Path(args.project).resolve()
    config = _toolchain_load_config(project_dir)
    if config is None:
        return 1
    toolchain = config.get("toolchain") or {}
    template = toolchain.get(args.name)
    if template is None:
        print(
            f"[mw ue-toolchain] Error: no toolchain command named '{args.name}' "
            f"(configured: {', '.join(toolchain) or 'none'})",
            file=sys.stderr,
        )
        return 1
    try:
        command = mw_common.render_toolchain_command(template, config)
    except mw_common.TargetConfigError as e:
        print(f"[mw ue-toolchain] Error: {e.kind}: {e}", file=sys.stderr)
        return 1
    # forwarded extra args (--args "...") are appended verbatim; a single
    # string sidesteps argparse's REMAINDER quirk (everything after the name
    # positional would be swallowed, including --project)
    if args.args and args.args.strip():
        command = command + " " + args.args.strip()

    control_root = pathlib.Path(config["control_root"])
    out_parent = pathlib.Path(args.out).resolve() if args.out else None
    run_dir = _toolchain_run_dir(control_root, out_parent, args.name)

    watched: list[dict] = []
    for w in args.watch or []:
        p = pathlib.Path(w)
        if not p.is_absolute():
            p = control_root / p
        watched.append({
            "path": str(p),
            "before": mw_common.sha256_eol_normalized(p) if p.is_file() else None,
            "after": None,
        })

    (run_dir / "cmd.txt").write_text(command + "\n", encoding="utf-8", newline="\n")
    print(f"[mw ue-toolchain] run: {command}")
    print(f"[mw ue-toolchain] dir: {run_dir}")
    started = time.time()
    proc = subprocess.run(command, shell=True, cwd=str(control_root), capture_output=True)
    seconds = time.time() - started
    log_text = (proc.stdout or b"").decode("utf-8", errors="replace") + "\n" + \
        (proc.stderr or b"").decode("utf-8", errors="replace")
    (run_dir / "run.log").write_text(log_text, encoding="utf-8", newline="\n")
    (run_dir / "exit.txt").write_text(f"{proc.returncode}\n", encoding="utf-8", newline="\n")
    error_lines = mw_common.scan_build_error_lines(log_text)
    (run_dir / "errors.txt").write_text(
        "".join(line + "\n" for line in error_lines), encoding="utf-8", newline="\n"
    )
    for entry in watched:
        p = pathlib.Path(entry["path"])
        entry["after"] = mw_common.sha256_eol_normalized(p) if p.is_file() else None
        entry["drift"] = entry["after"] != entry["before"]
    drift = [e for e in watched if e["drift"]]

    ok = proc.returncode == 0 and not error_lines and not drift
    meta = {
        "name": args.name,
        "template": template,
        "command": command,
        "cwd": str(control_root),
        "exit_code": proc.returncode,
        "seconds": round(seconds, 2),
        "error_line_count": len(error_lines),
        "watched_drift_count": len(drift),
        "watched": watched,
        "ok": ok,
        "run_dir": str(run_dir),
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    print(
        f"[mw ue-toolchain] exit={proc.returncode} seconds={seconds:.1f} "
        f"error_lines={len(error_lines)} watched_drift={len(drift)}/{len(watched)} "
        f"— {'OK' if ok else 'ATTENTION'}"
    )
    if args.json:
        print(json.dumps(meta, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def _toolchain_targets(args: argparse.Namespace) -> int:
    """List UE build target names discovered from <game>/Source/*.Target.cs
    (practice §2.1: names are read, never guessed)."""
    project_dir = pathlib.Path(args.project).resolve()
    config = _toolchain_load_config(project_dir)
    if config is None:
        return 1
    targets = mw_common.discover_build_targets(config["game_root"])
    if not targets:
        print(f"[mw ue-toolchain] no *.Target.cs under {config['game_root']}\\Source (non-UE game root?)")
        return 0
    for t in targets:
        print(f"- {t['name']} ({t['kind']}) — {t['file']}")
    print("[mw ue-toolchain] editor targets end in 'Editor'; use them for incremental editor builds")
    return 0


def _toolchain_hash(args: argparse.Namespace) -> int:
    """EOL-normalized sha256 (practice §5.5) for freeze/drift checks."""
    for raw in args.files:
        p = pathlib.Path(raw)
        if not p.is_file():
            print(f"[mw ue-toolchain] Error: not a file: {p}", file=sys.stderr)
            return 1
        print(f"{mw_common.sha256_eol_normalized(p)}  {p}")
    return 0


def cmd_toolchain(args: argparse.Namespace) -> int:
    if args.toolchain_action == "run":
        return _toolchain_run(args)
    if args.toolchain_action == "targets":
        return _toolchain_targets(args)
    return _toolchain_hash(args)


# ── Subcommand: rag (RAG server config + skill sync, mw-rag-integration) ────
#
# Verbs (D-010): list / probe / sync (`audit` is added by T-10). `sync` is the
# ONLY writer of <project>/.pi/skills/mw-rag.md (D-012/AC-017) — the pi session
# itself never installs or removes it (D-014, zero write surface). `probe` is
# diagnostic: an unreachable server is reported, never raised and never an
# exit code (design §4.2, 5s per enabled server, enabled set only).

_RAG_SKILL_SOURCE_RELATIVE = ("skills", "mw-rag", "SKILL.md")
_RAG_SKILL_INSTALL_RELATIVE = (".pi", "skills", "mw-rag.md")
_RAG_PROBE_TIMEOUT_S = 5.0
_RAG_MCP_PROTOCOL_VERSION = "2025-03-26"
_RAG_CAPABILITY_KEYS = ("graph", "chat", "rewrite")


def _rag_skill_source() -> pathlib.Path:
    """Framework-repo skill source (never resolved through cwd)."""
    return _SCRIPT_DIR.joinpath(*_RAG_SKILL_SOURCE_RELATIVE)


def _rag_skill_target(project_dir: pathlib.Path) -> pathlib.Path:
    """pi project-level skill slot: <project>/.pi/skills/mw-rag.md."""
    return pathlib.Path(project_dir).joinpath(*_RAG_SKILL_INSTALL_RELATIVE)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: pathlib.Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _rag_enabled(config: dict) -> list[str]:
    return [
        name for name in (config.get("enabled") or [])
        if isinstance(name, str) and name.strip()
    ]


def _rag_skill_state(project_dir: pathlib.Path) -> dict:
    """Installation status of .pi/skills/mw-rag.md vs the framework source."""
    source = _rag_skill_source()
    target = _rag_skill_target(project_dir)
    source_sha = _sha256_file(source) if source.is_file() else None
    target_sha = _sha256_file(target) if target.is_file() else None
    if target_sha is None:
        status = "absent"
    elif source_sha is None:
        status = "source-missing"
    elif target_sha == source_sha:
        status = "installed"
    else:
        status = "drift"
    return {
        "path": str(target),
        "status": status,
        "source_sha256": source_sha,
        "installed_sha256": target_sha,
    }


def _rag_install_skill(project_dir: pathlib.Path) -> int:
    """Byte-copy the skill source into <project>/.pi/skills/mw-rag.md.

    Temp file + os.replace in the target directory: atomic and byte-identical
    (AC-017). `.pi/skills` is created only here (an enabled project), and no
    other file under it is ever touched.
    """
    source = _rag_skill_source()
    if not source.is_file():
        print(f"[mw rag sync] Error: framework skill source not found: {source}", file=sys.stderr)
        return 1
    data = source.read_bytes()
    digest = _sha256_bytes(data)
    target = _rag_skill_target(project_dir)
    if target.is_file() and _sha256_file(target) == digest:
        print(f"[mw rag sync] unchanged (already installed) {target} sha256={digest}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + f".tmp{os.getpid()}")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    print(f"[mw rag sync] installed {target} sha256={digest}")
    return 0


def _rag_remove_skill(project_dir: pathlib.Path) -> int:
    """Remove .pi/skills/mw-rag.md when RAG is not enabled. Only that file."""
    target = _rag_skill_target(project_dir)
    if not target.exists():
        print(f"[mw rag sync] unchanged (not enabled, {target} absent)")
        return 0
    digest = _sha256_file(target)
    target.unlink()
    print(f"[mw rag sync] removed {target} sha256={digest}")
    return 0


def _cmd_rag_sync(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project).resolve()
    config, error = mw_common.load_rag_config(project_dir)
    if error:
        print(f"[mw rag sync] Error: {error}", file=sys.stderr)
        return 1
    if _rag_enabled(config):
        return _rag_install_skill(project_dir)
    return _rag_remove_skill(project_dir)


def _rag_format_origins(entry: dict) -> list[tuple[str, object, str]]:
    """Flatten one merged server entry into (field, value, origin) rows."""
    origin = entry.get("origin") or {}
    rows: list[tuple[str, object, str]] = []
    for path, value in (
        ("transport", entry.get("transport")),
        ("adapter", entry.get("adapter")),
        ("sources", ",".join(entry.get("sources") or [])),
        ("path_roots_file", entry.get("path_roots_file")),
    ):
        rows.append((path, value, str(origin.get(path, "-"))))
    for block in ("mcp", "skill", "capabilities"):
        data = entry.get(block)
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            path = f"{block}.{key}"
            rows.append((path, value, str(origin.get(path, "-"))))
    return rows


def _cmd_rag_list(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project).resolve()
    config, error = mw_common.load_rag_config(project_dir)
    if error:
        print(f"[mw rag list] Error: {error}", file=sys.stderr)
        return 1
    enabled = _rag_enabled(config)
    if args.json:
        print(json.dumps(config, indent=2, ensure_ascii=False, default=str))
        return 0
    print(f"[mw rag] enabled: {', '.join(enabled) if enabled else '(none)'}")
    print(f"[mw rag] default server: {config.get('default_server') or '-'}")
    print(f"[mw rag] fingerprint: {config.get('fingerprint')}")
    servers = config.get("servers") or {}
    for name in sorted(servers):
        mark = "enabled" if name in enabled else "disabled"
        print(f"[mw rag] server {name} [{mark}]")
        for field, value, field_origin in _rag_format_origins(servers[name]):
            print(f"  {field} = {value if value is not None else '-'} [{field_origin}]")
    return 0


def _mcp_post(
    url: str,
    payload: dict,
    *,
    token: str | None = None,
    session_id: str | None = None,
    timeout: float,
) -> tuple[dict, str | None]:
    """One JSON-RPC 2.0 POST (design §4.2: stdlib only, no SSE)."""
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["X-MCP-Token"] = token
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace")
        returned_session = response.headers.get("Mcp-Session-Id")
    if not body.strip():
        return {}, returned_session
    parsed = json.loads(body)
    return parsed if isinstance(parsed, dict) else {}, returned_session


def _mcp_sources(payload: dict) -> list[str] | None:
    if not isinstance(payload, dict):
        return None
    result = payload.get("result", payload)
    if isinstance(result, list):
        return [str(item) for item in result]
    if isinstance(result, dict):
        for key in ("sources", "source"):
            value = result.get(key)
            if isinstance(value, list):
                return [str(item) for item in value]
    return None


def _mcp_capabilities(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    result = payload.get("result", payload)
    if not isinstance(result, dict):
        return {}
    caps = result.get("capabilities")
    if not isinstance(caps, dict):
        return {}
    return {key: caps[key] for key in _RAG_CAPABILITY_KEYS if isinstance(caps.get(key), bool)}


def _probe_mcp_server(entry: dict, timeout: float) -> dict:
    """initialize -> Mcp-Session-Id -> list_sources. Raises on connect failure."""
    mcp = entry.get("mcp") or {}
    url = mcp.get("url")
    out: dict = {"reachable": False, "error": None, "session": False, "sources": None}
    if not url:
        out["error"] = "mcp.url is missing"
        return out
    token = None
    token_env = mcp.get("token_env")
    if token_env:
        token = os.environ.get(str(token_env))
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": _RAG_MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mw-rag-probe", "version": "1"},
        },
    }
    _response, session_id = _mcp_post(url, init, token=token, timeout=timeout)
    out["reachable"] = True
    out["session"] = bool(session_id)
    if session_id:
        try:
            _mcp_post(
                url,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                token=token,
                session_id=session_id,
                timeout=timeout,
            )
        except Exception:  # noqa: BLE001 - notification is best-effort
            pass
    try:
        listed, _ = _mcp_post(
            url,
            {"jsonrpc": "2.0", "id": 2, "method": "list_sources", "params": {}},
            token=token,
            session_id=session_id,
            timeout=timeout,
        )
        out["sources"] = _mcp_sources(listed)
        server_caps = _mcp_capabilities(listed)
        if server_caps:
            out["server_capabilities"] = server_caps
    except Exception as exc:  # noqa: BLE001 - reachable, but the source list is not
        out["error"] = f"list_sources: {type(exc).__name__}: {exc}"
    return out


def _probe_skill_server(entry: dict, project_dir: pathlib.Path) -> dict:
    """skill transport: reachable iff the configured skill dir exists."""
    out: dict = {"reachable": False, "error": None, "session": False, "sources": None}
    skill = entry.get("skill") or {}
    raw_dir = skill.get("dir")
    if not raw_dir:
        out["error"] = "skill.dir is missing"
        return out
    path = pathlib.Path(str(raw_dir))
    if not path.is_absolute():
        path = pathlib.Path(project_dir) / path
    if path.is_dir():
        out["reachable"] = True
    else:
        out["error"] = f"skill.dir not found: {path}"
    return out


def _rag_probe_server(
    name: str,
    entry: dict,
    project_dir: pathlib.Path,
    timeout: float | None = None,
) -> dict:
    """Probe one enabled server; never raises. Capability correction per D-004."""
    timeout = _RAG_PROBE_TIMEOUT_S if timeout is None else timeout
    started = time.monotonic()
    transport = str(entry.get("transport") or "mcp")
    result: dict = {
        "server": name,
        "transport": transport,
        "reachable": False,
        "error": None,
        "session": False,
        "sources": None,
    }
    try:
        if transport in ("mcp", "both") and isinstance(entry.get("mcp"), dict):
            result.update(_probe_mcp_server(entry, timeout))
        elif transport == "skill" and isinstance(entry.get("skill"), dict):
            result.update(_probe_skill_server(entry, project_dir))
        else:
            result["error"] = (
                f"server '{name}' has no probeable mcp/skill block (transport={transport})"
            )
    except Exception as exc:  # noqa: BLE001 - probe failures are diagnostics, not errors
        result["reachable"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
    declared = {
        key: bool((entry.get("capabilities") or {}).get(key))
        for key in _RAG_CAPABILITY_KEYS
    }
    server_caps = result.pop("server_capabilities", None) or {}
    corrected: list[str] = []
    for key in _RAG_CAPABILITY_KEYS:
        if key in server_caps and server_caps[key] != declared[key]:
            declared[key] = server_caps[key]
            corrected.append(key)
    result["capabilities"] = declared
    result["corrected"] = corrected
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result


def _cmd_rag_probe(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project).resolve()
    config, error = mw_common.load_rag_config(project_dir)
    if error:
        print(f"[mw rag probe] Error: {error}", file=sys.stderr)
        return 1
    enabled = _rag_enabled(config)
    servers = config.get("servers") or {}
    results = {
        name: _rag_probe_server(name, servers.get(name) or {}, project_dir)
        for name in enabled
    }
    if args.json:
        print(json.dumps(
            {
                "enabled": enabled,
                "fingerprint": config.get("fingerprint"),
                "servers": results,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ))
        return 0
    if not enabled:
        print("[mw rag probe] no enabled servers")
        return 0
    for name, result in results.items():
        state = "reachable" if result["reachable"] else "unreachable"
        detail = f" ({result['error']})" if result.get("error") else ""
        corrected = f" corrected={','.join(result['corrected'])}" if result["corrected"] else ""
        print(f"[mw rag probe] {name}: {state}{detail}{corrected}")
    return 0


# ── `mw rag audit`: read-only citation + require cross-check (T-10) ─────────
#
# D-008: stdout is the default surface and `--out` is the only file this
# command is allowed to write; nothing under the project is created, removed
# or modified (VC-019 writes=0, D-014). `rag_call` rows are read key=value by
# key (never by position or a whole-line anchor), so extra/new fields can
# never crash the parser; citations use the D-004 grammar
# (`server:source:file_path:line`) whose TS implementation is the contract.

_RAG_EVIDENCE_KINDS = (
    "rag_call",
    "rag_fallback",
    "rag-unavailable",
    "rag-rewrite-degraded",
    "rag-budget-exceeded",
    "rag-required-missing",
)
# key=value tokens; the audit reads the fields it needs by name.
_RAG_KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\S+)")
# D-004 citation extraction. `parse_citation` accepts any file_path (spaces,
# `::`, Unicode); this *extractor* is stricter because it runs over prose and
# trace logs: server/source are identifier-shaped and file_path is a single
# whitespace-free token, so `13:00:53` / `node:internal/...:1517` in a log line
# cannot masquerade as a citation. Callers additionally require the server to
# be a configured name.
_RAG_CITATION_RE = re.compile(
    r"(?<![\w:./-])([A-Za-z0-9_][A-Za-z0-9_.-]*):([A-Za-z0-9_][A-Za-z0-9_.-]*):"
    r"(\S*?):([0-9]+)(?=$|[\s)\]\"',;`!?.])"
)
_RAG_PATH_DEFAULT_ROLE = "engine"


def parse_citation(text: str) -> dict | None:
    """Parse `server:source:file_path:line` (D-004) -> four fields or None.

    Left: two `:`-free segments (server, source). Right: the final segment is
    the line (ASCII digits only). Everything in between is file_path verbatim,
    so `::`, Windows backslashes, spaces and Unicode survive. Mirrors the TS
    `adapter.ts::parseCitation`.
    """
    if not isinstance(text, str):
        return None
    first = text.find(":")
    if first <= 0:
        return None
    server = text[:first]
    rest = text[first + 1:]
    second = rest.find(":")
    if second <= 0:
        return None
    source = rest[:second]
    tail = rest[second + 1:]
    last = tail.rfind(":")
    if last < 0:
        return None
    file_path = tail[:last]
    line_text = tail[last + 1:]
    if not file_path or re.fullmatch(r"[0-9]+", line_text) is None:
        return None
    return {
        "server": server,
        "source": source,
        "file_path": file_path,
        "line": int(line_text),
    }


def parse_rag_evidence_line(line: str) -> dict | None:
    """Parse one trace line -> {"kind", "fields"} by key=value, else None.

    Field lookup is by key, never positional: `rag_call`'s canonical prefix is
    the six fields `server/tool/via/ms/results/mcp_tool`, but any extra field a
    later revision adds is simply carried in `fields` (the audit keeps working).
    """
    if not isinstance(line, str):
        return None
    for kind in _RAG_EVIDENCE_KINDS:
        if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(kind)}(?![A-Za-z0-9_-])", line):
            fields: dict[str, str] = {}
            for key, value in _RAG_KV_RE.findall(line):
                fields.setdefault(key, value)
            return {"kind": kind, "fields": fields}
    return None


def _rag_int(value: object) -> int:
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
        return int(value)
    return 0


def _rag_read_lines(path: pathlib.Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _rag_safe_print(text: str) -> None:
    """Print without dying on a legacy code page (GBK console, mojibake trace)."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        text = text.encode(encoding, "replace").decode(encoding, "replace")
    print(text)


def _rag_relpath(path: pathlib.Path, project_dir: pathlib.Path) -> str:
    try:
        return pathlib.Path(path).resolve().relative_to(
            pathlib.Path(project_dir).resolve()
        ).as_posix()
    except (OSError, ValueError):
        return pathlib.Path(path).as_posix()


def _rag_load_path_roots(
    path_roots_file: object, project_dir: pathlib.Path
) -> tuple[dict | None, str | None]:
    """Path-roots mapping for one server -> (roots, reason).

    `roots is None` means "cannot cross-check" (unconfigured / missing /
    malformed), which the audit reports as `unverified` rather than crashing.
    Mirrors the TS `adapter.ts::loadPathRoots`.
    """
    if not isinstance(path_roots_file, str) or not path_roots_file.strip():
        return None, "path_roots not configured"
    path = pathlib.Path(path_roots_file)
    if not path.is_absolute():
        path = pathlib.Path(project_dir) / path
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None, f"path_roots file missing: {path}"
    try:
        data = json.loads(text)
    except ValueError:
        return None, f"path_roots file is not valid JSON: {path}"
    if not isinstance(data, dict):
        return None, f"path_roots file must be a JSON object: {path}"
    roots: dict[str, str] = {}
    for key, value in data.items():
        if str(key).startswith("_"):
            continue
        if not isinstance(value, str) or not value.strip():
            return None, f"path_roots entry '{key}' must be a non-empty path string"
        roots[str(key)] = value
    return roots, None


def _rag_resolve_local_path(
    file_path: str, roots: dict, project_dir: pathlib.Path
) -> tuple[str | None, bool, str | None]:
    """Map one `role::rel` (bare rel -> `engine`) onto the local tree.

    Returns (local_path, exists, reason). Unknown role and path traversal are
    `missing` findings (the reference cannot be resolved), matching T-10.
    """
    role = _RAG_PATH_DEFAULT_ROLE
    relative = file_path
    separator = file_path.find("::")
    if separator >= 0:
        role = file_path[:separator].strip()
        relative = file_path[separator + 2:]
    if role not in roots:
        available = ", ".join(sorted(roots)) or "none"
        return None, False, f"unknown role '{role}' (available roles: {available})"
    root = pathlib.Path(roots[role])
    if not root.is_absolute():
        root = pathlib.Path(project_dir) / root
    try:
        root = root.resolve()
        normalized = relative.strip().replace("\\", "/").lstrip("/")
        resolved = (root / normalized).resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None, False, f"path traversal escapes role '{role}' root: {file_path}"
    if resolved.is_file():
        return str(resolved), True, None
    return str(resolved), False, "file missing"


def _rag_check_citation(
    citation: str, config: dict, project_dir: pathlib.Path
) -> dict | None:
    """Cross-check one citation against the merged config + local tree."""
    parsed = parse_citation(citation)
    if parsed is None:
        return None
    record: dict = dict(parsed)
    record["citation"] = citation
    entry = (config.get("servers") or {}).get(parsed["server"])
    if not isinstance(entry, dict):
        record.update(
            status="unverified", local_path=None, exists=False,
            reason=f"unknown server '{parsed['server']}'",
        )
        return record
    roots, reason = _rag_load_path_roots(entry.get("path_roots_file"), project_dir)
    if roots is None:
        record.update(status="unverified", local_path=None, exists=False, reason=reason)
        return record
    local_path, exists, why = _rag_resolve_local_path(
        parsed["file_path"], roots, project_dir
    )
    if exists:
        record.update(status="ok", local_path=local_path, exists=True, reason=None)
    else:
        record.update(status="missing", local_path=local_path, exists=False, reason=why)
    return record


def _rag_extract_citations(line: str, known: set[str]) -> list[str]:
    """Candidate citations in one text line (configured servers only).

    Backtick spans are parsed as a whole first, which is how the skill writes
    citations and is the only way a `file_path` containing spaces stays
    unambiguous. The token regex then picks up bare (unquoted) citations; a
    server name that is not configured is treated as ordinary prose because
    `a:b:c:1` is indistinguishable from a timestamp or a module path.
    """
    found: list[str] = []
    seen: set[str] = set()
    for span in re.findall(r"`([^`\n]+)`", line):
        text = span.strip()
        parsed = parse_citation(text)
        if parsed is None or parsed["server"] not in known or text in seen:
            continue
        seen.add(text)
        found.append(text)
    for match in _RAG_CITATION_RE.finditer(line):
        text = match.group(0)
        if text in seen or match.group(1) not in known or "\ufffd" in text:
            continue
        seen.add(text)
        found.append(text)
    return found


def _rag_audit_collect_citations(
    path: pathlib.Path, config: dict, project_dir: pathlib.Path, attrib: dict
) -> list[dict]:
    records: list[dict] = []
    rel = _rag_relpath(path, project_dir)
    known = {
        str(name) for name in (config.get("servers") or {})
        if isinstance(name, str) and name
    }
    if not known:
        return records
    for lineno, line in enumerate(_rag_read_lines(path), start=1):
        for text in _rag_extract_citations(line, known):
            checked = _rag_check_citation(text, config, project_dir)
            if checked is None:
                continue
            record = dict(attrib)
            record.update(checked)
            record["file"] = rel
            record["line_number"] = lineno
            records.append(record)
    return records


def _rag_audit_doc_citations(
    rag_dir: pathlib.Path, config: dict, project_dir: pathlib.Path, key_name: str
) -> list[dict]:
    """Citations from `<key>/rag/**/*.md` (research docs, D-008)."""
    if not rag_dir.is_dir():
        return []
    records: list[dict] = []
    for md in sorted(rag_dir.rglob("*.md")):
        attrib = {
            "source_kind": "rag-doc",
            "key": key_name,
            "task_key": md.stem,
            "worker": None,
            "role": "rag-research",
            "phase": "",
        }
        records.extend(_rag_audit_collect_citations(md, config, project_dir, attrib))
    return records


def _rag_audit_collect_calls(
    trace_path: pathlib.Path, project_dir: pathlib.Path, attrib: dict
) -> list[dict]:
    """`rag_call` rows (+ degraded association) from one worker trace.log."""
    calls: list[dict] = []
    degraded: set[tuple[str, str]] = set()
    rel = _rag_relpath(trace_path, project_dir)
    for lineno, line in enumerate(_rag_read_lines(trace_path), start=1):
        parsed = parse_rag_evidence_line(line)
        if parsed is None:
            continue
        fields = parsed["fields"]
        if parsed["kind"] == "rag-rewrite-degraded":
            degraded.add((fields.get("server", ""), fields.get("tool", "")))
            continue
        if parsed["kind"] != "rag_call":
            continue
        record = dict(attrib)
        record.update({
            "file": rel,
            "line_number": lineno,
            "server": fields.get("server", ""),
            "tool": fields.get("tool", ""),
            "via": fields.get("via", ""),
            "ms": _rag_int(fields.get("ms")),
            "results": _rag_int(fields.get("results")),
            "mcp_tool": fields.get("mcp_tool"),
            "degraded": False,
        })
        calls.append(record)
    for record in calls:
        if (record["server"], record["tool"]) in degraded:
            record["degraded"] = True
    return calls


def _rag_task_meta(task_path: pathlib.Path) -> dict:
    """task.md `type:` / `phase:` header declarations (missing -> "").

    Both keys come from the AC-005 single source `mw_common.read_task_type` /
    `read_task_header_scalar` (T-14): first value of the header region, BOM
    stripped, body lines never win. Same judgement the worker uses, so role
    attribution here cannot drift from the spawn-time role."""
    try:
        content = task_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"type": "", "phase": ""}
    task_type = mw_common.read_task_type(content).type or ""
    phase = mw_common.read_task_header_scalar(content, "phase") or ""
    return {"type": task_type, "phase": phase}


def _rag_terminal_workers(
    project_dir: pathlib.Path, agenticdoc: pathlib.Path
) -> dict[str, list[tuple[str, pathlib.Path, dict]]]:
    """Terminal `_workers.parallel` rows grouped by key: {key: [(worker, dir, row)]}.

    Non-terminal entries are skipped on purpose: a half-written output.md must
    never participate in the judgement (D-008).
    """
    grouped: dict[str, list[tuple[str, pathlib.Path, dict]]] = {}
    workers_path = mw_common.workers_path(project_dir)
    if not workers_path.exists():
        return grouped
    for entry in mw_common.parse_workers_file(workers_path):
        if entry["status"] not in mw_common._TERMINAL_STATUSES:
            continue
        task_path = pathlib.Path(entry["task_path"])
        worker_dir = task_path.parent
        if not worker_dir.is_dir():
            continue
        try:
            rel = task_path.resolve().relative_to(agenticdoc.resolve())
        except (OSError, ValueError):
            continue
        if len(rel.parts) < 3 or rel.parts[1] != "workers":
            continue
        grouped.setdefault(rel.parts[0], []).append((rel.parts[2], worker_dir, entry))
    return grouped


def _rag_audit_project(project_dir: pathlib.Path, key: str | None = None) -> dict:
    """Read-only audit of one project -> `{calls, citations, missing, unverified,
    required_missing, ...}` (T-10 / AC-015). Never writes, never goes online.

    Required judgement = `role.require OR phase.require` (union, no exception);
    "used RAG" = at least one verifiable (locally existing) citation attributable
    to the task; a bare `rag_call` row is not enough (VC-020).
    """
    project = pathlib.Path(project_dir)
    config, error = mw_common.load_rag_config(project)
    report: dict = {
        "project": str(project),
        "key": key,
        "enabled": _rag_enabled(config) if not error else [],
        "calls": [],
        "citations": [],
        "missing": [],
        "unverified": [],
        "required_missing": [],
        "error": error,
    }
    if error:
        return report
    agenticdoc = project / ".agenticdoc"
    workers = _rag_terminal_workers(project, agenticdoc)
    if key is not None:
        key_dirs = [agenticdoc / key] if (agenticdoc / key).is_dir() else []
    elif agenticdoc.is_dir():
        key_dirs = sorted(
            (p for p in agenticdoc.iterdir() if p.is_dir()), key=lambda p: p.name
        )
    else:
        key_dirs = []

    citations: list[dict] = []
    calls: list[dict] = []
    required_missing: list[dict] = []
    for key_dir in key_dirs:
        key_name = key_dir.name
        doc_citations = _rag_audit_doc_citations(
            key_dir / "rag", config, project, key_name
        )
        citations.extend(doc_citations)
        for worker, worker_dir, entry in workers.get(key_name, []):
            meta = _rag_task_meta(worker_dir / "task.md")
            task_type = meta["type"]
            # Unknown/absent `type:` falls back to coding, mirroring
            # `roleForTaskType` (shared/dispatch-models.ts:78) and
            # `mw_common.py:303` (T-16 / D-105).
            role = mw_common.TASK_TYPE_TO_ROLE.get(task_type, "coding")
            phase = meta["phase"]
            attrib = {
                "source_kind": "worker",
                "key": key_name,
                "task_key": str(entry.get("task_key") or worker),
                "worker": worker,
                "role": role,
                "phase": phase,
            }
            worker_citations: list[dict] = []
            for name in ("output.md", "trace.log"):
                path = worker_dir / name
                if not path.is_file():
                    continue
                found = _rag_audit_collect_citations(path, config, project, attrib)
                worker_citations.extend(found)
                citations.extend(found)
            calls.extend(
                _rag_audit_collect_calls(worker_dir / "trace.log", project, attrib)
            )
            if not mw_common._rag_required_for(config, role, phase):
                continue
            used = any(record["status"] == "ok" for record in worker_citations)
            if not used and role == "research":
                # A rag-research task's citations land in <key>/rag/*.md, not in
                # its own worker dir (T-09), so the key's docs count for it.
                used = any(record["status"] == "ok" for record in doc_citations)
            if used:
                continue
            server, _source, _rewrite = mw_common._rag_resolve_defaults(config, role, phase)
            required_missing.append({
                "key": key_name,
                "task_key": str(entry.get("task_key") or worker),
                "worker": worker,
                "role": role,
                "phase": phase,
                "server": server,
                "reason": "required role/phase without a verifiable citation",
            })

    citations.sort(key=lambda c: (
        c["key"], str(c.get("worker") or ""), c["file"], c["line_number"], c["citation"]
    ))
    calls.sort(key=lambda c: (
        c["key"], str(c.get("worker") or ""), c["line_number"], c["tool"]
    ))
    required_missing.sort(key=lambda r: (r["key"], r["worker"], r["role"], r["phase"]))
    report["citations"] = citations
    report["calls"] = calls
    report["missing"] = [c for c in citations if c["status"] == "missing"]
    report["unverified"] = [c for c in citations if c["status"] == "unverified"]
    report["required_missing"] = required_missing
    return report


def _rag_audit_where(record: dict) -> str:
    worker = record.get("worker") or record.get("task_key") or "-"
    phase = record.get("phase") or "-"
    return f"{record.get('key')}/{worker}[{record.get('role')}/{phase}]"


def _rag_audit_text_lines(report: dict) -> list[str]:
    enabled = report.get("enabled") or []
    lines = [
        f"[mw rag audit] enabled={', '.join(enabled) if enabled else '(none)'} "
        f"key={report.get('key') or '*'}",
        f"[mw rag audit] calls={len(report['calls'])} "
        f"citations={len(report['citations'])} missing={len(report['missing'])} "
        f"unverified={len(report['unverified'])} "
        f"required_missing={len(report['required_missing'])}",
    ]
    for record in report["missing"]:
        lines.append(
            f"[mw rag audit] missing {_rag_audit_where(record)} "
            f"{record['citation']} -> {record['reason']}"
        )
    for record in report["unverified"]:
        lines.append(
            f"[mw rag audit] unverified {_rag_audit_where(record)} "
            f"{record['citation']} -> {record['reason']}"
        )
    for record in report["required_missing"]:
        lines.append(
            f"[mw rag audit] required-missing {record['key']}/{record['worker']} "
            f"role={record['role']} phase={record['phase'] or '-'} "
            f"server={record['server'] or '-'}"
        )
    return lines


def _cmd_rag_audit(args: argparse.Namespace) -> int:
    """`mw rag audit`: 0 clean / 1 warning / 2 usage or config error (D-008)."""
    project = pathlib.Path(args.project)
    if not project.is_dir():
        print(f"[mw rag audit] Error: project directory not found: {args.project}", file=sys.stderr)
        return 2
    project = project.resolve()
    key = args.key
    if key is not None and not (project / ".agenticdoc" / key).is_dir():
        print(
            f"[mw rag audit] Error: no such key directory: {project / '.agenticdoc' / key}",
            file=sys.stderr,
        )
        return 2
    report = _rag_audit_project(project, key=key)
    if report.get("error"):
        print(f"[mw rag audit] Error: {report['error']}", file=sys.stderr)
        return 2
    payload = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_name(out_path.name + f".tmp{os.getpid()}")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, out_path)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
    if args.json:
        _rag_safe_print(payload)
    else:
        for line in _rag_audit_text_lines(report):
            _rag_safe_print(line)
    if report["missing"] or report["unverified"] or report["required_missing"]:
        return 1
    return 0


# ── Subcommand: rag init (zero-interaction template generator) ──────────────
#
# `mw rag init` renders the canonical templates from rag_templates.py and
# writes them. Discipline (design D-202~D-206): zero interaction (no prompt),
# project files by default (machine layer only on --machine/--only-machine),
# never YAML-round-trip target.yml (text-level append/replace so comments and
# other sections survive), refuse existing targets unless --force, and make
# --dry-run/--print pure reads (exit 0, zero writes).

_RAG_INIT_SERVER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _rag_machine_write_path() -> pathlib.Path | None:
    """Machine-layer path for `mw rag init --machine`, including the create case.

    `mw_common.machine_rag_servers_path()` returns None when the file does not
    exist yet, so the same env order is mirrored here for the write target.
    MW_RAG_SERVERS_HOME wins over HOME so a test hook can never make init touch
    the user's real HOME.
    """
    home = (os.environ.get(mw_common.RAG_ENV_HOME) or "").strip()
    if home:
        return pathlib.Path(home) / ".agents" / "rag-servers.yml"
    existing = mw_common.machine_rag_servers_path()
    if existing is not None:
        return existing
    override = (os.environ.get(mw_common.RAG_ENV_FILE) or "").strip()
    if override:
        return pathlib.Path(override)
    for var in ("HOME", "USERPROFILE"):
        home = (os.environ.get(var) or "").strip()
        if home:
            return pathlib.Path(home) / ".agents" / "rag-servers.yml"
    return None


def _rag_init_target_state(path: pathlib.Path) -> tuple[str, str]:
    """(state, detail): missing | no-rag | has-rag | unreadable."""
    if not path.exists():
        return "missing", "does not exist (will be created)"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return "unreadable", str(exc)
    if re.search(r"^rag\s*:", text, flags=re.MULTILINE):
        return "has-rag", "already has a top-level 'rag:' key"
    return "no-rag", "exists without a top-level 'rag:' key (will be appended)"


def _replace_top_level_block(text: str, key: str, new_block: str) -> str:
    """Replace the top-level `key:` block (from its line to the next top-level
    key or EOF) with `new_block`, leaving every other byte untouched. Used by
    `--force` so target.yml's comments and other sections survive (D-204)."""
    lines = text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}\s*:", line):
            start = i
            break
    if start is None:
        return text
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] not in (" ", "\t"):
            end = j
            break
    return "".join(lines[:start]) + new_block + "".join(lines[end:])


def _cmd_rag_init_print(project_dir: pathlib.Path, servers_text: str, target_text: str) -> None:
    """Emit the 3-section --print contract (manual parity, T-22)."""
    for path, text in (
        (mw_common.rag_servers_path(project_dir), servers_text),
        (mw_common.target_yml_path(project_dir), target_text),
        (project_dir / ".mw" / "rag-roots.json", rag_templates.ROOTS_TEMPLATE),
    ):
        print(f"# ===== file: {path} =====")
        sys.stdout.write(text)


def _cmd_rag_init(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project)
    if not project_dir.is_dir():
        print(f"[mw rag init] Error: project directory not found: {args.project}", file=sys.stderr)
        return 1
    project_dir = project_dir.resolve()
    if args.machine and args.only_machine:
        print("[mw rag init] Error: --machine and --only-machine are mutually exclusive", file=sys.stderr)
        return 1

    server = (args.server or rag_templates.DEFAULT_SERVER).strip()
    if not _RAG_INIT_SERVER_RE.match(server):
        print(
            f"[mw rag init] Error: invalid --server {server!r} "
            "(use letters/digits/'.'/'_'/'-', starting alphanumeric)",
            file=sys.stderr,
        )
        return 1
    url = (args.url or rag_templates.DEFAULT_MCP_URL).strip()
    token_env = (args.token_env if args.token_env is not None else rag_templates.DEFAULT_TOKEN_ENV).strip()
    transport = args.transport or "mcp"

    # Step 1: a broken existing config must never abort init (init repairs it);
    # only an unreadable/absent project dir (checked above) is fatal.
    config, _error = mw_common.load_rag_config(project_dir)
    known_servers = set((config.get("servers") or {}).keys())

    servers_text = rag_templates.render_servers_template(
        server,
        url,
        token_env,
        transport,
        rag_templates.DEFAULT_SKILL_DIR,
        rag_templates.DEFAULT_SKILL_CLI_ENTRY,
        not args.no_roots,
    )
    target_text = rag_templates.render_target_rag_template(server, args.enable, args.enable)

    project_servers = mw_common.rag_servers_path(project_dir)
    target_yml = mw_common.target_yml_path(project_dir)
    roots_path = project_dir / ".mw" / "rag-roots.json"

    # --print is a pure read (D-205): emit the templates and exit 0 before any
    # refusal/plan logic can turn it into an error.
    if args.print_templates:
        _cmd_rag_init_print(project_dir, servers_text, target_text)
        return 0

    machine_path = _rag_machine_write_path() if (args.machine or args.only_machine) else None

    plans: list[dict] = []
    refusals: list[tuple[pathlib.Path, str]] = []
    report: list[tuple[str, pathlib.Path, str]] = []

    def _plan_servers(path: pathlib.Path, label: str) -> None:
        if path.exists() and not args.force:
            refusals.append((path, "already exists (use --force to overwrite)"))
            report.append(("refuse", path, "already exists (use --force to overwrite)"))
        else:
            state = "overwrite" if path.exists() else "write"
            plans.append({"kind": label, "path": path, "text": servers_text, "state": state})
            report.append((state, path, "servers template"))

    if not args.only_machine:
        _plan_servers(project_servers, "servers")
        target_state, target_detail = _rag_init_target_state(target_yml)
        if target_state == "unreadable":
            refusals.append((target_yml, target_detail))
            report.append(("refuse", target_yml, target_detail))
        elif target_state == "has-rag" and not args.force:
            reason = "already has a top-level 'rag:' key (use --force to replace it)"
            refusals.append((target_yml, reason))
            report.append(("refuse", target_yml, reason))
        else:
            plans.append({"kind": "target", "path": target_yml, "text": target_text, "state": target_state})
            report.append((target_state, target_yml, target_detail))
    else:
        report.append(("skip", project_servers, "--only-machine: project files are not written"))
        report.append(("skip", target_yml, "--only-machine: project files are not written"))
        report.append(("skip", roots_path, "--only-machine: project files are not written"))

    if machine_path is not None:
        _plan_servers(machine_path, "machine-servers")

    if not args.no_roots and not args.only_machine:
        if roots_path.exists() and not args.force:
            reason = "already exists (use --force to overwrite)"
            refusals.append((roots_path, reason))
            report.append(("refuse", roots_path, reason))
        else:
            state = "overwrite" if roots_path.exists() else "write"
            plans.append({"kind": "roots", "path": roots_path,
                          "text": rag_templates.ROOTS_TEMPLATE, "state": state})
            report.append((state, roots_path, "rag-roots.json template"))

    # --enable references the server from target.yml, so it must actually be
    # declared (freshly written or already present) or the config would break.
    declared = set(known_servers)
    for plan in plans:
        if plan["kind"] in ("servers", "machine-servers"):
            declared.add(server)
    if args.enable and server not in declared:
        reason = f"cannot --enable server {server!r}: not declared in any rag-servers.yml"
        refusals.append((target_yml, reason))
        report.append(("refuse", target_yml, reason))

    if args.dry_run:
        print("[mw rag init] dry-run — no files written")
        for action, path, detail in report:
            print(f"[mw rag init] {action:9s} {path}  ({detail})")
        return 0

    if refusals:
        for path, reason in refusals:
            print(f"[mw rag init] Error: refusing to write {path}: {reason}", file=sys.stderr)
        print("[mw rag init] nothing written. Edit by hand or re-run with --force.", file=sys.stderr)
        return 1

    try:
        for plan in plans:
            kind, path = plan["kind"], plan["path"]
            if kind != "target":
                _atomic_write_yml(path, plan["text"])
                continue
            if plan["state"] == "missing":
                _atomic_write_yml(path, plan["text"])
                continue
            current = path.read_text(encoding="utf-8")
            if plan["state"] == "no-rag":
                base = current if current.endswith("\n") else current + "\n"
                _atomic_write_yml(path, base + "\n" + plan["text"])
            else:  # has-rag + --force: replace only that top-level block
                _atomic_write_yml(path, _replace_top_level_block(current, "rag", plan["text"]))
    except OSError as exc:
        print(f"[mw rag init] Error: writing files failed: {exc}", file=sys.stderr)
        return 1

    for plan in plans:
        print(f"[mw rag init] wrote {plan['path']}")
    print("[mw rag init] next steps:")
    print(f"  1. Edit {project_servers}: set mcp.url and mcp.token_env (env var NAME only).")
    print(f"  2. Add {server!r} to rag.enabled in {target_yml} (or re-run with --enable).")
    print("  3. Run `mw rag list --project <dir>`, `mw rag probe`, `mw rag sync`; "
          "restart `mw serve` so workers pick up the change.")
    return 0


def cmd_rag(args: argparse.Namespace) -> int:
    return _RAG_ACTIONS[args.rag_action](args)


_RAG_ACTIONS = {
    "init": _cmd_rag_init,
    "list": _cmd_rag_list,
    "probe": _cmd_rag_probe,
    "audit": _cmd_rag_audit,
    "sync": _cmd_rag_sync,
}


def _doctor_rag(project_dir: pathlib.Path) -> dict:
    """RAG section for `mw doctor` (shape of mw_common._doctor_dispatch).

    Informational: a broken config or an unreachable server is surfaced, never
    flagged as a chain issue. Probe runs for the enabled set only, so a project
    without RAG does no network I/O (D-014).
    """
    project_dir = pathlib.Path(project_dir)
    machine_path = mw_common.machine_rag_servers_path()
    project_path = mw_common.rag_servers_path(project_dir)
    section: dict = {
        "exists": bool(project_path.exists() or machine_path is not None),
        "machine_file": str(machine_path) if machine_path is not None else None,
        "project_file": str(project_path) if project_path.exists() else None,
        "skill": _rag_skill_state(project_dir),
    }
    config, error = mw_common.load_rag_config(project_dir)
    if error:
        section["error"] = error
        section["enabled"] = []
        section["default_server"] = None
        section["fingerprint"] = None
        section["probe"] = {}
        section["required_missing"] = 0
        return section
    enabled = _rag_enabled(config)
    servers = config.get("servers") or {}
    section["enabled"] = enabled
    section["default_server"] = config.get("default_server")
    section["fingerprint"] = config.get("fingerprint")
    section["probe"] = {
        name: {
            "reachable": result["reachable"],
            "transport": result["transport"],
            "error": result.get("error"),
            "corrected": result["corrected"],
        }
        for name, result in (
            (name, _rag_probe_server(name, servers.get(name) or {}, project_dir))
            for name in enabled
        )
    }
    # Required-but-unused count from the same read-only audit (T-10 item 3).
    section["required_missing"] = len(
        (_rag_audit_project(project_dir).get("required_missing") or [])
    )
    return section


def _format_rag_doctor_line(section: dict) -> str:
    enabled = section.get("enabled") or []
    if section.get("error"):
        return f"rag: ERROR - {section['error']}"
    if not enabled:
        skill = section.get("skill") or {}
        return f"rag: not enabled (skill {skill.get('status', 'unknown')})"
    probe = section.get("probe") or {}
    state = ", ".join(
        f"{name}={'reachable' if item.get('reachable') else 'unreachable'}"
        for name, item in sorted(probe.items())
    )
    fingerprint = (section.get("fingerprint") or "")[:12]
    skill_status = (section.get("skill") or {}).get("status", "unknown")
    required_missing = int(section.get("required_missing") or 0)
    required = f"; required_missing={required_missing}" if required_missing else ""
    return (
        f"rag: enabled={', '.join(enabled)}; probe={state}; "
        f"fingerprint={fingerprint}; skill={skill_status}{required}"
    )


# ── Write-face refusal surface (mw-write-face-guard W-15 / AC-006) ──────────

#: Conductor audit event family (`autopilot/dispatch.py` WRITE_FACE_AUDIT_*).
#: `write-face-overlap` / `write-face-undeclared` are themselves the stable
#: code; `write-face-rejected` is a container that carries the parse-time code
#: in its detail (card requirement 4).
_WRITE_FACE_EVENT_PREFIX = "write-face-"
_WRITE_FACE_RECENT_LIMIT = 5
#: by_code bucket for a row whose code could not be read from its name/detail
#: (the row is still counted — requirement 4 forbids dropping it).
_WRITE_FACE_UNKNOWN_CODE = "unknown"


def _write_face_detail_parts(detail: str) -> tuple[str | None, str]:
    """Split an audit detail into ``(task_key, rest)`` on the FIRST ``": "``.

    Both audit channels prefix the refused task key and their tail carries
    further colons (PM `"<key>: write-face-overlap: overlap-with:<key>"`),
    so ``split(":")`` would truncate the reason (card requirement 4).
    """
    head, sep, rest = detail.partition(": ")
    if not sep:
        return None, detail
    return (head or None), rest


def _parse_write_face_event(event: dict) -> dict:
    """One conductor timeline `write-face-*` event -> a `recent` entry.

    Only the event name is guaranteed.  The shipped overlap/undeclared shapes
    are read for their side fields; a `write-face-rejected` container is read
    for its code.  An unexpected detail still yields a counted row whose
    unread fields stay ``None`` (never dropped).
    """
    ev = str(event.get("ev") or "")
    detail = str(event.get("detail") or "")
    task_key, rest = _write_face_detail_parts(detail)
    code: str | None = None
    overlap_with: str | None = None
    sample: str | None = None
    if ev == "write-face-overlap":
        code = ev
        marker = "overlap with "
        index = rest.find(marker)
        if index >= 0:
            tail = rest[index + len(marker):]
            other, at_sep, after = tail.partition(" at ")
            overlap_with = other.split(" (", 1)[0].strip() or None
            if at_sep:
                sample = after.split(" (", 1)[0].strip() or None
    elif ev == "write-face-undeclared":
        code = ev
    else:
        # `write-face-rejected` (or a future write-face-* container): the
        # detail is `"<code> <operator detail>"`.
        code = rest.split(" ", 1)[0].strip() or None
    return {
        "source": "conductor",
        "ts": None,
        "task_key": task_key,
        "code": code,
        "overlap_with": overlap_with,
        "sample": sample,
    }


def _parse_write_face_ledger_row(row: dict) -> dict | None:
    """One `auto-decisions.jsonl` row -> a `recent` entry, or ``None`` when
    the row is not a write-face refusal.

    `recordDispatchAlarm` (pm-orchestrator.ts) writes
    ``{seq, phase: "dispatch-alarm", kind, count, detail}`` with no key
    column: the refused task key prefixes `detail` and the tail is the
    byte-identical conductor refusal reason.  `write-scope-risk` shares the
    channel but is not a refusal, so it must not enter the refusal counts
    (card requirement 4).
    """
    if str(row.get("phase") or "") != "dispatch-alarm":
        return None
    if str(row.get("kind") or "") != "write-face-refusal":
        return None
    detail = str(row.get("detail") or "")
    task_key, reason = _write_face_detail_parts(detail)
    overlap = re.search(r"overlap-with:(\S+)", reason)
    sample = re.search(r"sample=(\S+)", reason)
    return {
        "source": "pm",
        "ts": None,
        "task_key": task_key,
        "code": reason.partition(":")[0].strip() or None,
        "overlap_with": overlap.group(1) if overlap else None,
        "sample": sample.group(1) if sample else None,
    }


def _doctor_write_face(project_dir: pathlib.Path) -> dict:
    """Read-only write-face refusal surface for `mw doctor` (AC-006).

    Two independent audit channels, each already scoped to write-face:

    * conductor — timeline events named ``write-face-*``; `query_events`
      walks the rotated generations too, so history is not lost;
    * PM — `auto-decisions.jsonl` rows with ``phase == "dispatch-alarm"``
      and ``kind == "write-face-refusal"`` (`conductor.auto_decision_rows`
      is the tolerant single reader: torn lines skipped, absent file empty).

    Zero writes, zero locks, no influence on `summary`/`issues`: a refusal is
    normal gate behaviour, so 0 and N are both healthy.  Every read is
    fail-soft — a broken source contributes nothing (never raises).
    """
    project_dir = pathlib.Path(project_dir)
    by_code: dict[str, int] = {}
    by_source = {"conductor": 0, "pm": 0}
    # (recency sort key, entry).  Conductor events carry a timestamp; the PM
    # ledger has none, so those rows sort as the oldest and only fill the
    # window when fewer than `_WRITE_FACE_RECENT_LIMIT` timestamped events
    # exist.  The key's tail keeps equal-second events in seq order.
    ranked: list[tuple[tuple[bool, str, str, int], dict]] = []

    try:
        events = _ap_timeline.query_events(
            _ap_timeline.timeline_path(project_dir)
        ).events
    except Exception:  # noqa: BLE001 — the surface must never break doctor
        events = []
    for event in events:
        if not isinstance(event, dict):
            continue
        ev = str(event.get("ev") or "")
        if not ev.startswith(_WRITE_FACE_EVENT_PREFIX):
            continue
        entry = _parse_write_face_event(event)
        ts = event.get("ts")
        entry["ts"] = str(ts) if ts else None
        by_source["conductor"] += 1
        code = entry.get("code") or _WRITE_FACE_UNKNOWN_CODE
        by_code[code] = by_code.get(code, 0) + 1
        ranked.append(
            (
                (entry["ts"] is not None, entry["ts"] or "", "conductor",
                 int(event.get("seq") or 0)),
                entry,
            )
        )

    try:
        rows = _ap_conductor.auto_decision_rows(project_dir)
    except Exception:  # noqa: BLE001 — ditto
        rows = []
    for row in rows:
        entry = _parse_write_face_ledger_row(row) if isinstance(row, dict) else None
        if entry is None:
            continue
        by_source["pm"] += 1
        code = entry.get("code") or _WRITE_FACE_UNKNOWN_CODE
        by_code[code] = by_code.get(code, 0) + 1
        ranked.append(((False, "", "pm", int(row.get("seq") or 0)), entry))

    ranked.sort(key=lambda item: item[0])
    recent = [entry for _, entry in ranked[-_WRITE_FACE_RECENT_LIMIT:]]
    recent.reverse()  # newest first
    return {
        "total": by_source["conductor"] + by_source["pm"],
        "by_code": dict(sorted(by_code.items())),
        "by_source": by_source,
        "recent": recent,
    }


def _format_write_face_doctor_line(section: dict) -> str:
    total = int(section.get("total") or 0)
    by_source = section.get("by_source") or {}
    if not total:
        return "write-face: no gate refusals (conductor=0, pm=0)"
    codes = ", ".join(
        f"{code}={count}"
        for code, count in sorted((section.get("by_code") or {}).items())
    )
    return (
        f"write-face: {total} gate refusal(s) "
        f"(conductor={int(by_source.get('conductor') or 0)}, "
        f"pm={int(by_source.get('pm') or 0)}); by_code={codes}"
    )


# ── Subcommand: partition (large-project split, mw-target-partition) ────────

_PARTITION_RESERVED_ROOT_NAMES = frozenset(("parent", "partition", "game", "engine", "uproject"))
_PARTITION_ROOT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PARTITION_ENV_FAMILY = (
    mw_common.ENV_PARTITION_PARENT,
    mw_common.ENV_PARTITION_ROOT,
    mw_common.ENV_TARGET_GAME,
    mw_common.ENV_TARGET_ENGINE,
)
_V1_FLAT_KEYS = ("mode", "game", "engine", "uproject")
_MIXED_FORMAT_MSG = (
    "target.yml is mixed format (v2 'active:' key together with v1 flat fields) "
    "— resolve the file to one format first"
)
_FLOW_LAYOUT_MSG = (
    "the {block} block uses an unsupported layout (flow style?) — "
    "rewrite it in block style first"
)


def _read_yml_exact(path: pathlib.Path) -> str:
    """Read target.yml without newline translation — the block-level editor
    (D-008) preserves hand-maintained lines byte-for-byte, so the file's real
    endings must survive the read/write round trip."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _try_parse_yml(text: str) -> dict | None:
    """yaml.safe_load without the resolver's validation. None when the file
    is not parseable (callers fail closed); a parseable but non-mapping
    document (list / scalar top level) raises TargetConfigError(invalid-
    config) with the resolver's message instead of counting as an empty
    mapping — mw-target-partition FIX-7: the CLI writers must refuse a
    malformed file (no silent v1 migration / rewrite on top of it)."""
    import yaml

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(raw, dict):
        raise mw_common.TargetConfigError(
            "invalid-config", "target.yml: top level must be a mapping"
        )
    return raw


def _yml_shape(raw: dict) -> str:
    """File shape for the writers: 'v2' (top-level `active:`), 'v1' (flat
    fields), or 'mixed' (active + v1 flat fields — rejected, never written)."""
    if "active" in raw:
        if any(k in raw for k in _V1_FLAT_KEYS):
            return "mixed"
        return "v2"
    return "v1"


def _atomic_write_yml(yml: pathlib.Path, text: str) -> None:
    """Atomic target.yml write: temp file + os.replace (spec §2.3 — a crash
    mid-write never truncates the config; concurrent sets serialize on the
    final rename). Endings are written verbatim (no translation)."""
    yml.parent.mkdir(parents=True, exist_ok=True)
    tmp = yml.with_name(yml.name + f".tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, yml)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _dominant_ending(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _find_block_header(lines: list[str], block_key: str) -> int | None:
    """Index of the top-level `block_key:` mapping header line, or None."""
    pattern = re.compile(rf"^{re.escape(block_key)}\s*:\s*(#.*)?(\r?\n)?$")
    for i, line in enumerate(lines):
        if pattern.match(line):
            return i
    return None


def _block_end(lines: list[str], start: int) -> int:
    """First index after the block whose header sits at `start`: content is
    every indented line plus blank runs followed by more indented lines."""
    j = start + 1
    while j < len(lines):
        line = lines[j]
        if line.strip() == "":
            k = j + 1
            while k < len(lines) and lines[k].strip() == "":
                k += 1
            if k < len(lines) and lines[k][:1] in (" ", "\t"):
                j = k
                continue
            return j
        if line[:1] not in (" ", "\t"):
            return j
        j += 1
    return j


def _block_layout_ok(text: str, block_key: str) -> bool:
    """The line-level block editor needs a `block_key:` mapping header at
    column 0; a flow-style block (or a scalar value) is an unsupported layout
    — reject instead of appending a duplicate key."""
    return _find_block_header(text.splitlines(keepends=True), block_key) is not None


def _edit_block_scalar(
    body: list[str],
    key: str,
    value: str | None,
    scalar_keys: tuple[str, ...],
    ending: str,
) -> list[str]:
    """Line-level edit of one 2-space-indented bootstrap scalar inside a mode
    block: replace in place (comments and every other line untouched), drop
    the line when value is None (omitted fields are not persisted), insert
    after the last bootstrap scalar (else at the top of the block body).
    Mirrors _apply_bootstrap_line's contract at depth 1 (design D-008)."""
    pattern = re.compile(rf"^  {re.escape(key)}\s*:")
    out: list[str] = []
    replaced = False
    for line in body:
        if pattern.match(line):
            if value is not None:
                out.append(f"  {key}: {value}{_line_ending(line) or ending}")
            replaced = True
        else:
            out.append(line)
    if value is not None and not replaced:
        scalar_re = re.compile(rf"^  ({'|'.join(re.escape(k) for k in scalar_keys)})\s*:")
        idx = 0
        for i, line in enumerate(out):
            if scalar_re.match(line):
                idx = i + 1
        out.insert(idx, f"  {key}: {value}{ending}")
    return out


def _edit_block_roots(
    body: list[str],
    roots: list[tuple[str, str]],
    scalar_keys: tuple[str, ...],
    ending: str,
) -> list[str]:
    """Whole-section rewrite of the 2-space `roots:` mapping inside a mode
    block (design D-008): the located section (header + its indented body) is
    replaced as a unit; an empty list drops the section (--root not given).
    Blank lines trailing the section stay outside the replaced range."""
    idx: int | None = None
    for i, line in enumerate(body):
        if re.match(r"^  roots\s*:", line):
            idx = i
            break
    section: list[str] = []
    if roots:
        section.append(f"  roots:{ending}")
        for name, value in roots:
            section.append(f"    {name}: {value}{ending}")
    if idx is None:
        if not section:
            return body
        scalar_re = re.compile(rf"^  ({'|'.join(re.escape(k) for k in scalar_keys)})\s*:")
        insert_at = 0
        for i, line in enumerate(body):
            if scalar_re.match(line):
                insert_at = i + 1
        return body[:insert_at] + section + body[insert_at:]
    # Section extent: the `  roots:` line plus following blank or 4+-indented
    # lines (entries are written at 4-space indent; 2-space content belongs
    # to the surrounding block).
    j = idx + 1
    while j < len(body):
        line = body[j]
        if line.strip() == "":
            k = j
            while k < len(body) and body[k].strip() == "":
                k += 1
            if k < len(body) and body[k][:1] == " " and len(body[k]) - len(body[k].lstrip()) >= 4:
                j = k
                continue
            break
        if line[:1] == " " and len(line) - len(line.lstrip()) >= 4:
            j += 1
            continue
        break
    while j > idx + 1 and body[j - 1].strip() == "":
        j -= 1
    return body[:idx] + section + body[j:]


def _apply_mode_block(
    text: str,
    block_key: str,
    scalars: list[tuple[str, str | None]],
    roots: list[tuple[str, str]] | None,
) -> str:
    """Block-level edit of one v2 mode block (design D-008): bootstrap
    scalars are line-edited (comments preserved), the roots mapping is
    rewritten as a whole section, and every other line of the block — the
    hand-maintained toolchain/ignore/contract profiles and their comments —
    is preserved byte-for-byte. The block is appended (after a blank
    separator) when missing; roots=None skips roots handling entirely."""
    ending = _dominant_ending(text)
    scalar_keys = tuple(key for key, _ in scalars)
    lines = text.splitlines(keepends=True)
    header_idx = _find_block_header(lines, block_key)
    if header_idx is None:
        block: list[str] = [f"{block_key}:{ending}"]
        for key, value in scalars:
            if value is not None:
                block.append(f"  {key}: {value}{ending}")
        if roots:
            block.append(f"  roots:{ending}")
            for name, value in roots:
                block.append(f"    {name}: {value}{ending}")
        out = list(lines)
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + ending
        if any(line.strip() for line in out):
            out.append(ending)
        out.extend(block)
        return "".join(out)
    end = _block_end(lines, header_idx)
    body = lines[header_idx + 1 : end]
    for key, value in scalars:
        body = _edit_block_scalar(body, key, value, scalar_keys, ending)
    if roots is not None:
        body = _edit_block_roots(body, roots, scalar_keys, ending)
    lines[header_idx + 1 : end] = body
    return "".join(lines)


def _migrate_v1_text(text: str) -> str:
    """One-shot v1 → v2 migration (design D-008): every v1 field — bootstrap
    scalars and the hand-maintained toolchain/ignore/contract profiles —
    moves into a v2 dual block; `active` mirrors the v1 resolution (dual when
    a game root existed, else single). Layout may change (yaml generator);
    field content is preserved (AC-022 asserts the content level).

    mw-target-partition FIX-7: a non-mapping document raises instead of
    migrating as an empty config (the caller's _try_parse_yml gate makes
    this unreachable in practice — kept fail-closed for direct callers)."""
    import yaml

    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise mw_common.TargetConfigError(
            "invalid-config", "target.yml: top level must be a mapping"
        )
    active = "dual" if raw.get("game") is not None else "single"
    dual: dict = {}
    for key in ("game", "engine", "vcs", "uproject", "toolchain", "ignore", "contract"):
        value = raw.get(key)
        if value is not None:
            dual[key] = value
    data: dict = {"active": active}
    if dual:
        data["dual"] = dual
    header = (
        "# Workspace target config (v2 — migrated from the v1 flat format by `mw partition set`).\n"
        "# 'active' selects the mode (single | dual | partition); mode blocks carry bootstrap\n"
        "# fields plus hand-maintained profiles. Backup of the v1 file: target.yml.bak.\n"
    )
    return header + yaml.safe_dump(
        data, allow_unicode=True, default_flow_style=False, sort_keys=False
    )


def _partition_template(
    parent: str,
    partition: str,
    vcs: str | None,
    roots: list[tuple[str, str]],
) -> str:
    """Fresh v2 target.yml for a control root with no file yet: active
    partition + the partition block (bootstrap + roots as given — omitted
    fields are not persisted) + comment scaffolding for the hand-maintained
    profiles (mirrors _target_template)."""
    lines = [
        "# Workspace target config (mw partition set). 'active' selects the mode",
        "# (single | dual | partition); mode blocks carry bootstrap fields plus",
        "# hand-maintained profiles (mw-target-partition design D-008).",
        "active: partition",
        "partition:",
        f"  parent: {parent}",
        f"  partition: {partition}",
    ]
    if vcs is not None:
        lines.append(f"  vcs: {vcs}")
    if roots:
        lines.append("  roots:")
        for name, value in roots:
            lines.append(f"    {name}: {value}")
    lines += [
        "  toolchain:",
        "  # command templates with {parent}/{partition}/{root name} placeholders, e.g.",
        "  # build: 'build.bat {partition} {sdk}'",
        "",
        "  ignore:",
        "  # L1 deny globs for read/ls/find/grep (absolute or partition-root-relative",
        "  # minimatch basis). Uncomment and extend:",
        "  # deny_globs:",
        "  #   - \"**/DerivedDataCache/**\"",
        "",
        "  contract:",
        "  # forbidden_paths: []",
        "  # conventions: |",
        "  #   project conventions injected into every dispatched task.md",
        "  # docs: []",
        "",
    ]
    return "\n".join(lines)


def _print_partition_summary(config: dict) -> None:
    print(f"[mw partition] mode: {config['mode']} (source: {config['source']})")
    print(f"[mw partition] control root: {config['control_root']}")
    print(f"[mw partition] parent root: {config['parent_root'] or '-'}")
    print(f"[mw partition] partition root: {config['partition_root'] or '-'}")
    roots = config.get("roots") or {}
    for name in sorted(roots):
        print(f"[mw partition] root {name}: {roots[name]}")
    print(f"[mw partition] vcs: {config['vcs'] or '-'}")
    if config["toolchain"]:
        print(f"[mw partition] toolchain commands: {', '.join(sorted(config['toolchain']))}")


def _partition_env_conflict() -> list[str]:
    """Set vars across the two families (MW_PARTITION_* / MW_TARGET_*); a
    blank value counts as unset (same normalization as the resolver)."""
    conflicts: list[str] = []
    for name in _PARTITION_ENV_FAMILY:
        value = os.environ.get(name)
        if value is not None and value.strip() != "":
            conflicts.append(name)
    return conflicts


def _parse_root_args(root_args: list[str] | None) -> list[tuple[str, str]]:
    """--root NAME=DIR values: split on the first '=', validate the name
    (^[A-Za-z0-9_-]+$, not a reserved name), reject duplicates. Raises
    ValueError with the reason (the caller prints stderr + exit 1)."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in root_args or []:
        name, sep, value = item.partition("=")
        if not sep or not name or value.strip() == "":
            raise ValueError(f"--root expects NAME=DIR, got {item!r}")
        if _PARTITION_ROOT_NAME_RE.match(name) is None or name in _PARTITION_RESERVED_ROOT_NAMES:
            raise ValueError(
                f"--root name '{name}' is invalid (must match [A-Za-z0-9_-]+ and must not "
                "be a reserved name: parent, partition, game, engine, uproject)"
            )
        if name in seen:
            raise ValueError(f"--root name '{name}' given more than once")
        seen.add(name)
        out.append((name, value))
    return out


def _resolve_cli_path(project_dir: pathlib.Path, value: str) -> pathlib.Path:
    """CLI path: relative values anchor to the control root (spec §2.1)."""
    p = pathlib.Path(value)
    if not p.is_absolute():
        p = project_dir / p
    return p.resolve()


def _partition_set(project_dir: pathlib.Path, args: argparse.Namespace) -> int:
    # (1) cross-family env guard: a live env override could silently disagree
    # with the written file — reject before touching anything (file,
    # migration, .bak all untouched).
    conflicts = _partition_env_conflict()
    if conflicts:
        print(
            "[mw partition set] Error: cross env: "
            f"{', '.join(conflicts)} is set — unset MW_PARTITION_* / MW_TARGET_* before "
            "writing target.yml (env overrides are read-only activations, never persisted)",
            file=sys.stderr,
        )
        return 1

    # (2) argument validation
    if not args.parent:
        print(
            "[mw partition set] Error: --parent is required "
            "(the parent project root — extended writable workspace for the partition)",
            file=sys.stderr,
        )
        return 1
    parent = _resolve_cli_path(project_dir, args.parent)
    partition = (
        _resolve_cli_path(project_dir, args.partition)
        if args.partition is not None
        else project_dir.resolve()
    )
    try:
        roots = _parse_root_args(args.root)
    except ValueError as e:
        print(f"[mw partition set] Error: {e}", file=sys.stderr)
        return 1
    vcs = args.vcs

    # (3) path existence (parent / explicit partition / named roots)
    if not parent.is_dir():
        print(f"[mw partition set] Error: parent root not found: {parent}", file=sys.stderr)
        return 1
    if args.partition is not None and not partition.is_dir():
        print(f"[mw partition set] Error: partition root not found: {partition}", file=sys.stderr)
        return 1
    root_values: list[tuple[str, str]] = []
    for name, raw_path in roots:
        root_path = _resolve_cli_path(project_dir, raw_path)
        if not root_path.is_dir():
            print(f"[mw partition set] Error: root '{name}' not found: {root_path}", file=sys.stderr)
            return 1
        root_values.append((name, _yml_scalar(str(root_path))))

    # (4) root relation: parent and partition distinct, non-nested (realpath)
    a = os.path.normcase(os.path.normpath(str(parent)))
    b = os.path.normcase(os.path.normpath(str(partition)))
    if a == b or a.startswith(b + os.sep) or b.startswith(a + os.sep):
        print(
            "[mw partition set] Error: root relation is invalid — parent "
            f"({parent}) and partition ({partition}) must not be equal or nested",
            file=sys.stderr,
        )
        return 1

    yml = mw_common.target_yml_path(project_dir)
    migrated = False
    if yml.exists():
        exact = _read_yml_exact(yml)
        try:
            raw = _try_parse_yml(exact)
        except mw_common.TargetConfigError as e:
            # FIX-7: a parseable but non-mapping file is never an empty v1 —
            # refuse before any .bak / migration touches the disk.
            print(f"[mw partition set] Error ({e.kind}): {e}", file=sys.stderr)
            return 1
        if raw is None:
            print(
                "[mw partition set] Error: target.yml is not valid YAML — fix or remove it first",
                file=sys.stderr,
            )
            return 1
        shape = _yml_shape(raw)
        if shape == "mixed":
            print(f"[mw partition set] Error: {_MIXED_FORMAT_MSG}", file=sys.stderr)
            return 1
        if shape == "v2" and raw.get("partition") is not None and not _block_layout_ok(exact, "partition"):
            print(
                f"[mw partition set] Error: {_FLOW_LAYOUT_MSG.format(block='partition')}",
                file=sys.stderr,
            )
            return 1
        if shape == "v1":
            # (5a) one-shot v1 → v2 migration: the .bak is written from the
            # original bytes BEFORE the new content lands — a failure between
            # the two leaves the original file and the backup intact. FIX-8:
            # the backup itself is a unique temp file + os.replace (same
            # atomicity as the main write — a crash never truncates .bak).
            bak = yml.with_name(yml.name + ".bak")
            tmp = bak.with_name(bak.name + f".tmp{os.getpid()}")
            try:
                shutil.copyfile(str(yml), str(tmp))
                os.replace(tmp, bak)
            except OSError as e:
                print(f"[mw partition set] Error: writing backup {bak} failed: {e}", file=sys.stderr)
                return 1
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
            migrated = True
            try:
                exact = _migrate_v1_text(exact)
            except mw_common.TargetConfigError as e:
                print(f"[mw partition set] Error ({e.kind}): {e}", file=sys.stderr)
                return 1
    else:
        exact = _partition_template(
            _yml_scalar(str(parent)), _yml_scalar(str(partition)), vcs, root_values
        )

    # (5b) block-level write: active → partition; partition block bootstrap
    # scalars line-edited (comments kept), roots rewritten as a whole section;
    # omitted fields are not persisted (vcs/roots dropped when not given).
    exact = _apply_bootstrap_line(exact, "active", "partition")
    exact = _apply_mode_block(
        exact,
        "partition",
        [
            ("parent", _yml_scalar(str(parent))),
            ("partition", _yml_scalar(str(partition))),
            ("vcs", vcs),
        ],
        root_values,
    )
    try:
        _atomic_write_yml(yml, exact)
    except OSError as e:
        print(f"[mw partition set] Error: writing {yml} failed: {e}", file=sys.stderr)
        return 1
    if migrated:
        print(
            "[mw partition set] migrated v1 target.yml to v2 (all v1 fields moved into the "
            f"dual block); backup: {yml.with_name(yml.name + '.bak')}"
        )
    try:
        config = mw_common.load_target_config(project_dir)
    except mw_common.TargetConfigError as e:
        # Bootstrap fields are written; a hand-maintained section is broken.
        print(
            f"[mw partition set] Warning: config resolves with an error ({e.kind}): {e}",
            file=sys.stderr,
        )
        return 1
    _print_partition_summary(config)
    return 0


def _partition_show(project_dir: pathlib.Path) -> int:
    try:
        config = mw_common.load_target_config(project_dir)
    except mw_common.TargetConfigError as e:
        print(f"[mw partition show] Error ({e.kind}): {e}", file=sys.stderr)
        return 1
    yml = mw_common.target_yml_path(project_dir)
    if config["mode"] != "partition":
        # mw-target-partition FIX-4 (AC-018a): no special case for a missing
        # file — active is not partition, so the command exits 1 naming the
        # current mode and the switch commands (on/set), exactly like every
        # other non-partition shape.
        if yml.exists():
            try:
                raw = _try_parse_yml(_read_yml_exact(yml))
            except mw_common.TargetConfigError as e:
                print(f"[mw partition show] Error ({e.kind}): {e}", file=sys.stderr)
                return 1
            raw = raw or {}
            if _yml_shape(raw) == "v1":
                where = "target.yml is v1 format (no partition mode)"
                hint = (
                    "run `mw partition set --parent <dir> --partition <dir>` — it migrates "
                    "v1 to v2 (with a target.yml.bak backup)"
                )
            else:
                where = f"active mode is '{raw.get('active')}'"
                hint = (
                    "run `mw partition on` (after `mw partition set`), or "
                    "`mw partition set --parent <dir> --partition <dir>` to reconfigure"
                )
        elif config["source"] == "env":
            where = f"{config['mode']} mode via env"
            hint = "run `mw partition set --parent <dir> --partition <dir>` first"
        else:
            where = f"active mode is '{config['mode']}' (no target.yml)"
            hint = "run `mw partition set --parent <dir> --partition <dir>` first"
        print(
            f"[mw partition show] Error: partition mode is not active ({where}) — {hint}",
            file=sys.stderr,
        )
        return 1
    _print_partition_summary(config)
    render_failed = False
    for name, command in sorted(config["toolchain"].items()):
        try:
            rendered = mw_common.render_toolchain_command(command, config)
            print(f"[mw partition]   {name}: {rendered}")
        except mw_common.TargetConfigError as e:
            render_failed = True
            print(f"[mw partition]   {name}: ERROR ({e.kind}): {e}", file=sys.stderr)
    if config["ignore"]["deny_globs"]:
        print(f"[mw partition] deny_globs: {len(config['ignore']['deny_globs'])} rule(s)")
    return 1 if render_failed else 0


def _partition_clear(project_dir: pathlib.Path) -> int:
    conflicts = _partition_env_conflict()
    if conflicts:
        print(
            "[mw partition clear] Error: cross env: "
            f"{', '.join(conflicts)} is set — unset MW_PARTITION_* / MW_TARGET_* before "
            "changing target.yml",
            file=sys.stderr,
        )
        return 1
    yml = mw_common.target_yml_path(project_dir)
    if not yml.exists():
        print("[mw partition clear] no partition block — nothing to clear")
        return 0
    exact = _read_yml_exact(yml)
    try:
        raw = _try_parse_yml(exact)
    except mw_common.TargetConfigError as e:
        print(f"[mw partition clear] Error ({e.kind}): {e}", file=sys.stderr)
        return 1
    if raw is None:
        print(
            "[mw partition clear] Error: target.yml is not valid YAML — fix or remove it first",
            file=sys.stderr,
        )
        return 1
    shape = _yml_shape(raw)
    if shape == "mixed":
        print(f"[mw partition clear] Error: {_MIXED_FORMAT_MSG}", file=sys.stderr)
        return 1
    if shape != "v2" or not isinstance(raw.get("partition"), dict):
        # v1 flat file or a v2 without the block: nothing to remove
        print("[mw partition clear] no partition block — nothing to clear")
        return 0
    lines = exact.splitlines(keepends=True)
    header_idx = _find_block_header(lines, "partition")
    if header_idx is None:
        print(
            f"[mw partition clear] Error: {_FLOW_LAYOUT_MSG.format(block='partition')}",
            file=sys.stderr,
        )
        return 1
    end = _block_end(lines, header_idx)
    start = header_idx
    if start > 0 and lines[start - 1].strip() == "":
        start -= 1  # the separator blank line appended with the block
    del lines[start:end]
    text = "".join(lines)
    was_active = raw.get("active") == "partition"
    if was_active:
        text = _apply_bootstrap_line(text, "active", "single")
    if not isinstance(raw.get("dual"), dict):
        # no mode block remains — the file carries no mode config anymore
        try:
            yml.unlink()
        except OSError as e:
            print(f"[mw partition clear] Error: removing {yml} failed: {e}", file=sys.stderr)
            return 1
        print(f"[mw partition clear] removed partition block; no mode blocks remain — deleted {yml}")
        return 0
    try:
        _atomic_write_yml(yml, text)
    except OSError as e:
        print(f"[mw partition clear] Error: writing {yml} failed: {e}", file=sys.stderr)
        return 1
    if was_active:
        print("[mw partition clear] removed partition block, active: single (dual block kept)")
    else:
        print(f"[mw partition clear] removed parked partition block (active stays {raw.get('active')})")
    return 0


def _partition_on(project_dir: pathlib.Path) -> int:
    yml = mw_common.target_yml_path(project_dir)
    if not yml.exists():
        print(
            "[mw partition on] Error: no target.yml — run "
            "`mw partition set --parent <dir> --partition <dir>` first",
            file=sys.stderr,
        )
        return 1
    exact = _read_yml_exact(yml)
    try:
        raw = _try_parse_yml(exact)
    except mw_common.TargetConfigError as e:
        print(f"[mw partition on] Error ({e.kind}): {e}", file=sys.stderr)
        return 1
    if raw is None:
        print(
            "[mw partition on] Error: target.yml is not valid YAML — fix or remove it first",
            file=sys.stderr,
        )
        return 1
    shape = _yml_shape(raw)
    if shape == "mixed":
        print(f"[mw partition on] Error: {_MIXED_FORMAT_MSG}", file=sys.stderr)
        return 1
    if shape == "v1":
        print(
            "[mw partition on] Error: target.yml is v1 format — on/off require v2; run "
            "`mw partition set ...` (it migrates v1 to v2 with a .bak backup)",
            file=sys.stderr,
        )
        return 1
    block = raw.get("partition")
    if not isinstance(block, dict):
        print(
            "[mw partition on] Error: no partition block — run "
            "`mw partition set --parent <dir> --partition <dir>` first",
            file=sys.stderr,
        )
        return 1
    missing = [k for k in ("parent", "partition") if block.get(k) is None]
    if missing:
        print(
            f"[mw partition on] Error: the partition block is missing field(s) {', '.join(missing)} "
            "— run `mw partition set ...` first",
            file=sys.stderr,
        )
        return 1
    if not _block_layout_ok(exact, "partition"):
        print(f"[mw partition on] Error: {_FLOW_LAYOUT_MSG.format(block='partition')}", file=sys.stderr)
        return 1
    text = _apply_bootstrap_line(exact, "active", "partition")
    try:
        _atomic_write_yml(yml, text)
    except OSError as e:
        print(f"[mw partition on] Error: writing {yml} failed: {e}", file=sys.stderr)
        return 1
    try:
        mw_common.load_target_config(project_dir)
    except mw_common.TargetConfigError as e:
        print(
            "[mw partition on] Warning: active is now partition but the config resolves with "
            f"an error ({e.kind}): {e}",
            file=sys.stderr,
        )
        return 1
    print("[mw partition on] active: partition (takes effect on the next worker spawn; no serve restart needed)")
    return 0


def _partition_off(project_dir: pathlib.Path) -> int:
    yml = mw_common.target_yml_path(project_dir)
    if not yml.exists():
        print("[mw partition off] partition mode is not active (no target.yml) — nothing to do")
        return 0
    exact = _read_yml_exact(yml)
    try:
        raw = _try_parse_yml(exact)
    except mw_common.TargetConfigError as e:
        print(f"[mw partition off] Error ({e.kind}): {e}", file=sys.stderr)
        return 1
    if raw is None:
        print(
            "[mw partition off] Error: target.yml is not valid YAML — fix or remove it first",
            file=sys.stderr,
        )
        return 1
    shape = _yml_shape(raw)
    if shape == "mixed":
        print(f"[mw partition off] Error: {_MIXED_FORMAT_MSG}", file=sys.stderr)
        return 1
    if shape == "v1":
        print(
            "[mw partition off] Error: target.yml is v1 format — on/off require v2; run "
            "`mw partition set ...` (it migrates v1 to v2 with a .bak backup)",
            file=sys.stderr,
        )
        return 1
    if raw.get("active") != "partition":
        print(f"[mw partition off] partition mode is not active (active: {raw.get('active')}) — nothing to do")
        return 0
    text = _apply_bootstrap_line(exact, "active", "single")
    try:
        _atomic_write_yml(yml, text)
    except OSError as e:
        print(f"[mw partition off] Error: writing {yml} failed: {e}", file=sys.stderr)
        return 1
    print("[mw partition off] active: single (partition block kept; takes effect on the next worker spawn)")
    return 0


def cmd_partition(args: argparse.Namespace) -> int:
    """Partition-workspace target config (mw-target-partition): set (v1 → v2
    migration + partition block write) / show / clear / on / off."""
    project_dir = pathlib.Path(args.project).resolve()
    if args.partition_action == "set":
        return _partition_set(project_dir, args)
    if args.partition_action == "clear":
        return _partition_clear(project_dir)
    if args.partition_action == "on":
        return _partition_on(project_dir)
    if args.partition_action == "off":
        return _partition_off(project_dir)
    return _partition_show(project_dir)


# ── Subcommand: model (dispatch model defaults) ──────────────────────────────

def _dispatch_extra_keys(path: pathlib.Path) -> dict:
    """Top-level dispatch.yml keys other than ``models`` (fallback_models, ...).

    ``_model_write`` rewrites the whole file from a role->value mapping. Before
    that rewrite we lift every other top-level key off the existing file so the
    write cannot silently drop configuration it does not own (mw-model-error-
    perception D5: the launcher reads the top-level `fallback_models` key). A
    missing/unreadable/unparsable/non-mapping file contributes nothing — the
    caller has already refused a write on an unusable file.
    """
    import yaml

    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key != "models"}


def _model_write(
    project_dir: pathlib.Path,
    models: dict[str, str],
    fallback_models: dict[str, list[str]] | None = None,
) -> None:
    """Write .mw/dispatch.yml from a complete role→value mapping.

    Read-modify-write: untouched top-level keys (notably `fallback_models`) are
    preserved verbatim, never replaced by a models-only dict."""

# mw-model-fallback-cli: `fallback_models` is a task-type -> ordered-chain mapping.
# None keeps the file's existing block verbatim; a mapping replaces it, and an
# empty mapping drops the top-level key entirely (no leftovers after the last clear).
    import yaml

    path = mw_common.dispatch_config_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _dispatch_extra_keys(path)
    if models:
        data["models"] = models
    if fallback_models is not None:
        if fallback_models:
            data["fallback_models"] = fallback_models
        else:
            data.pop("fallback_models", None)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=True),
        encoding="utf-8",
    )


def cmd_model(args: argparse.Namespace) -> int:
    """Dispatch model defaults: per-role models used when a task carries no
    explicit `model:` (mw-dispatch-models). Resolution order per spawn:
    task.md model: > dispatch.yml role > current window model > per-cli default."""
    project_dir = pathlib.Path(args.project).resolve()
    action = args.model_action

    if action == "set":
        role, value = args.role, args.value.strip()
        if role not in mw_common.DISPATCH_ROLES:
            print(
                f"[mw model set] Error: unknown role {role!r} "
                f"(valid: {', '.join(mw_common.DISPATCH_ROLES)})",
                file=sys.stderr,
            )
            return 1
        prefix, model_id = mw_common.parse_model_value(value)
        if not prefix or not model_id:
            print(
                f"[mw model set] Error: value must be 'prefix/model' "
                f"(e.g. timi/glm-5.3), got {value!r}",
                file=sys.stderr,
            )
            return 1
        if prefix not in mw_common.KNOWN_MODEL_PREFIXES:
            print(
                f"[mw model set] Error: unknown prefix {prefix!r} "
                f"(valid: {', '.join(sorted(mw_common.KNOWN_MODEL_PREFIXES))})",
                file=sys.stderr,
            )
            return 1
        # T-11: a vision role must be able to read images. The probe is
        # fail-open: only a hard "no" refuses (missing/unavailable stays
        # "unknown" and writes), and --force overrides entirely.
        if args.force and role != "vision":
            print(
                f"[mw model set] Error: --force is only valid for the 'vision' role "
                f"(got {role!r}); it only skips the image-capability probe",
                file=sys.stderr,
            )
            return 1
        if role == "vision":
            if args.force:
                print(f"[mw model set] --force: image-capability probe skipped for {value}")
            else:
                verdict = mw_common.model_images(value)
                if verdict == "no":
                    print(
                        f"[mw model set] Error: {value} reports images=no — a 'vision' "
                        "role model must accept image input",
                        file=sys.stderr,
                    )
                    print(
                        "[mw model set] Suggest: pick a vision-capable model, e.g. "
                        "`mw model set vision timi/deepseek-v4-flash-vision-exp`, or "
                        f"override with `mw model set vision {value} --force`",
                        file=sys.stderr,
                    )
                    return 1
                if verdict == "unknown":
                    print(
                        f"[mw model set] skip: image capability of {value} is unknown "
                        "(probe unavailable or model not listed); writing anyway"
                    )
        existing, err = mw_common.load_dispatch_config(project_dir)
        if err:
            print(
                f"[mw model set] Error: existing dispatch.yml is unusable ({err}) — "
                "fix or remove it before writing",
                file=sys.stderr,
            )
            return 1
        models = dict(existing.get("models", {}))
        models[role] = value
        _model_write(project_dir, models)
        print(f"[mw model set] {role} = {value} → {mw_common.dispatch_config_path(project_dir)}")
        return 0

    if action == "clear":
        role = args.role
        existing, err = mw_common.load_dispatch_config(project_dir)
        if err:
            print(f"[mw model clear] Error: {err}", file=sys.stderr)
            return 1
        models = dict(existing.get("models", {}))
        if role == "all":
            if not models:
                print("[mw model clear] nothing configured")
                return 0
            _model_write(project_dir, {})
            print(f"[mw model clear] removed all roles → {mw_common.dispatch_config_path(project_dir)}")
            return 0
        if role not in mw_common.DISPATCH_ROLES:
            print(
                f"[mw model clear] Error: unknown role {role!r} "
                f"(valid: {', '.join(mw_common.DISPATCH_ROLES)} or 'all')",
                file=sys.stderr,
            )
            return 1
        if role not in models:
            print(f"[mw model clear] {role} is not configured")
            return 0
        del models[role]
        _model_write(project_dir, models)
        print(f"[mw model clear] removed {role} → {mw_common.dispatch_config_path(project_dir)}")
        return 0

    if action == "set-fallback":
        # mw-model-fallback-cli: an ordered per-task-type fallback chain. The
        # comma-separated value goes through the same validator the launcher
        # and doctor read with, so CLI writes and file reads cannot diverge.
        task_type = args.role
        if task_type not in mw_common.FALLBACK_TASK_TYPES:
            print(
                f"[mw model set-fallback] Error: unknown task type {task_type!r} "
                f"(valid: {', '.join(sorted(mw_common.FALLBACK_TASK_TYPES))})",
                file=sys.stderr,
            )
            return 1
        # R-01 F1: the validator input is the raw CSV split - no pre-stripping and
        # no empty-item filtering, so `mw_common.validate_fallback_models` stays the
        # single authority for the empty-entry and single-line rules (filtering here
        # let `a,,b` and embedded CR/LF through). Whitespace around entries is still
        # tolerated: `parse_model_value` strips each item itself.
        if not args.value.strip():
            print(
                "[mw model set-fallback] Error: value must be a comma-separated list of "
                f"1..{mw_common.FALLBACK_MAX_MODELS} 'prefix/model' entries "
                "(e.g. timi/deepseek-v4.1-flash,zai/glm-5.3)",
                file=sys.stderr,
            )
            return 1
        cleaned, err = mw_common.validate_fallback_models({task_type: args.value.split(",")})
        if err:
            print(f"[mw model set-fallback] Error: {err}", file=sys.stderr)
            return 1
        existing, err = mw_common.load_dispatch_config(project_dir)
        if err:
            print(
                f"[mw model set-fallback] Error: existing dispatch.yml is unusable ({err}) "
                "— fix or remove it before writing",
                file=sys.stderr,
            )
            return 1
        fallbacks, fb_err = mw_common.load_fallback_models(project_dir)
        if fb_err:
            print(
                "[mw model set-fallback] Error: existing fallback_models is unusable "
                f"({fb_err}) — fix or remove it before writing",
                file=sys.stderr,
            )
            return 1
        chain = cleaned[task_type]
        fallbacks[task_type] = chain
        _model_write(project_dir, dict(existing.get("models", {})), fallback_models=fallbacks)
        print(
            f"[mw model set-fallback] {task_type} = {', '.join(chain)} "
            f"({len(chain)} in order) → {mw_common.dispatch_config_path(project_dir)}"
        )
        return 0

    if action == "clear-fallback":
        task_type = args.role
        if task_type not in mw_common.FALLBACK_TASK_TYPES:
            print(
                f"[mw model clear-fallback] Error: unknown task type {task_type!r} "
                f"(valid: {', '.join(sorted(mw_common.FALLBACK_TASK_TYPES))})",
                file=sys.stderr,
            )
            return 1
        existing, err = mw_common.load_dispatch_config(project_dir)
        if err:
            print(f"[mw model clear-fallback] Error: {err}", file=sys.stderr)
            return 1
        fallbacks, fb_err = mw_common.load_fallback_models(project_dir)
        if fb_err:
            print(f"[mw model clear-fallback] Error: {fb_err}", file=sys.stderr)
            return 1
        if task_type not in fallbacks:
            print(f"[mw model clear-fallback] {task_type} is not configured")
            return 0
        del fallbacks[task_type]
        _model_write(project_dir, dict(existing.get("models", {})), fallback_models=fallbacks)
        print(
            f"[mw model clear-fallback] removed {task_type} → "
            f"{mw_common.dispatch_config_path(project_dir)}"
        )
        return 0

    # show
    existing, err = mw_common.load_dispatch_config(project_dir)
    path = mw_common.dispatch_config_path(project_dir)
    print(f"config: {path}{' (missing — nothing configured)' if not path.exists() else ''}")
    if err:
        print(f"Error: {err}")
        return 1
    window = mw_common.read_window_model(project_dir)
    print(f"window model: {window or '(none recorded)'}")
    for role in mw_common.DISPATCH_ROLES:
        configured = existing.get("models", {}).get(role, "")
        if configured:
            print(f"{role}: {configured} images={mw_common.model_images(configured)}")
            continue
        # Effective preview on the default worker route (pi+timi): the first
        # compatible layer of the chain after the role config.
        value, source = mw_common.resolve_dispatch_model(
            cli="pi",
            task_type=role if role != "main" else "coding",
            entry_model="",
            config_models={},  # this role is unset — show what lies beneath
            window_model=window,
        )
        effective = value or "(route default: glm-5.3 for pi+timi, gpt-5.6-sol for codex)"
        # AC-015: every role line carries a capability verdict. An unset role
        # previews the route default (no concrete model id here) - fall back to
        # "unknown" without probing an empty string.
        capability = mw_common.model_images(value) if value else "unknown"
        print(f"{role}: (unset) → {effective} [{source}] images={capability}")
    fallbacks, fb_err = mw_common.load_fallback_models(project_dir)
    if fb_err:
        # Same contract as a broken `models` block above: a config the reader
        # rejects is a nonzero exit, never a silent success (R-01 可观测性).
        print(f"fallback: Error: {fb_err}")
        return 1
    if fallbacks:
        for task_type in sorted(fallbacks):
            print(f"fallback {task_type}: {', '.join(fallbacks[task_type])}")
    else:
        print("fallback: (none configured)")
    return 0


# ── Subcommand: autopilot (xkey verification CLI) ────────────────────────────
# mw-autopilot-verify-cli D-005/D-006/D-014. `mw autopilot verify set` is the
# only Python-side writer of the four xkey keys; the TS console writes the same
# file and takes the same lock. The lock budget is frozen (retries=6,
# base_delay=0.02 -> worst case ~1.26 s): an unavailable lock must fail loudly
# instead of hanging for the 14 h the mw_common defaults would allow. The retry
# constants are module-level so tests can monkeypatch them.

_AP_VERIFY_LOCK_FILENAME = "autopilot-config.lock"
_AP_VERIFY_LOCK_RETRIES = 6
_AP_VERIFY_LOCK_BASE_DELAY = 0.02
_AP_XKEY_KEYS = (
    "xkey_repair",
    "xkey_verify_cmd",
    "xkey_verify_timeout_s",
    "xkey_verify_cwd",
)


def _ap_verify_lock_path(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".mw" / _AP_VERIFY_LOCK_FILENAME


def _ap_verify_error(action: str, message: str) -> int:
    print(f"[mw autopilot verify {action}] Error: {message}", file=sys.stderr)
    return 1


def _ap_read_raw_config(path: pathlib.Path) -> tuple[dict | None, str | None]:
    """Read + schema-validate the raw project config (fail-closed).

    Returns ``(raw, None)`` or ``(None, message)``. A missing file yields
    ``({}, None)`` — it means 'autopilot never enabled', not an error."""
    if not path.exists():
        return {}, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"cannot read {path}: {exc}"
    try:
        _ap_config.validate_config(raw)
    except _ap_config.ConfigError as exc:
        return None, str(exc)
    return raw, None


def _ap_resolve_verify_cwd(cwd_key: str, target: dict) -> tuple[str | None, str | None]:
    """Resolve ``xkey_verify_cwd`` against a resolved target config (D-008).

    ``""`` = auto (``workspace_root``: partition->partition, dual->game,
    single/legacy->control). ``control``/``partition``/``parent`` and
    ``<root name>`` are explicit selectors. Returns ``(path, None)`` or
    ``(None, message)``; a typo fails closed (kind ``invalid-config``)."""
    mode = target.get("mode")
    roots = target.get("roots") or {}
    if cwd_key == "":
        return mw_common.workspace_root(target), None
    if cwd_key == "control":
        return target["control_root"], None
    if cwd_key == "partition" and target.get("partition_root") is not None:
        return target["partition_root"], None
    if cwd_key == "parent" and target.get("parent_root") is not None:
        return target["parent_root"], None
    if cwd_key in roots:
        return roots[cwd_key], None
    valid = ["'' (auto)", "control"]
    if target.get("partition_root") is not None:
        valid += ["partition", "parent"]
    valid += sorted(roots)
    return None, (
        f"invalid-config: xkey_verify_cwd {cwd_key!r} is not a valid root for "
        f"{mode} mode (valid: {', '.join(valid)})"
    )


def _ap_verify_set(args: argparse.Namespace, project_dir: pathlib.Path) -> int:
    """Locked read-modify-write of the four xkey keys (D-006/D-014).

    The 13 keys are completed with defaults, then the new argv (and optional
    timeout) is dry-run through the same renderer/cwd resolver the conductor
    uses; any failure refuses to write. The write itself only goes through
    ``autopilot.config.save_config``."""
    action = "set"
    # REMAINDER keeps the separator itself in the list (argparse passes the
    # first `--` through for a REMAINDER positional), so drop exactly one
    # leading separator before storing the argv.
    raw_argv = [str(token) for token in (args.argv or [])]
    if raw_argv and raw_argv[0] == "--":
        raw_argv = raw_argv[1:]
    argv = raw_argv
    # REMAINDER swallows everything after `--`, so a misplaced --project would
    # be stored as a literal token (mw.py:983-985 self-noted pitfall).
    if "--project" in argv:
        return _ap_verify_error(
            action, "--project must appear before '--' (tokens after '--' are stored verbatim)"
        )
    if not argv:
        return _ap_verify_error(
            action, "no argv given after '--' (use `clear` to remove the command)"
        )
    changes: dict = {"xkey_verify_cmd": argv}
    if args.timeout is not None:
        if args.timeout < 1:
            return _ap_verify_error(action, f"--timeout must be >= 1, got {args.timeout}")
        changes["xkey_verify_timeout_s"] = args.timeout

    path = _ap_config.config_path(project_dir)
    lock = _ap_verify_lock_path(project_dir)
    try:
        mw_common.acquire_lock(
            lock, retries=_AP_VERIFY_LOCK_RETRIES, base_delay=_AP_VERIFY_LOCK_BASE_DELAY
        )
    except RuntimeError as exc:
        return _ap_verify_error(
            action, f"{exc} (remove the stale lock if no writer is active)"
        )
    try:
        raw, err = _ap_read_raw_config(path)
        if err is not None:
            return _ap_verify_error(
                action,
                f"existing _autopilot/config.json is unusable ({err}) — "
                "fix or remove it before writing",
            )
        merged = {**_ap_config.default_config(), **(raw or {}), **changes}
        try:
            _ap_config.validate_config(merged)
        except _ap_config.ConfigError as exc:
            return _ap_verify_error(action, str(exc))
        # Dry-run: the writer must resolve argv and cwd exactly like the
        # conductor does (effective view: project layer + machine layer), so a
        # bad placeholder/root never lands on disk. `set` never changes the cwd
        # key, so the effective cwd read here is what the next tick will use.
        try:
            target = mw_common.load_target_config(project_dir)
            rendered = mw_common.render_argv(merged["xkey_verify_cmd"], target)
        except mw_common.TargetConfigError as exc:
            return _ap_verify_error(action, f"{exc.kind}: {exc}")
        try:
            effective_values, _, _ = mw_common._autopilot_effective_values(project_dir)
        except _ap_config.ConfigError as exc:  # fail-closed: never write over an unusable layer
            return _ap_verify_error(action, f"effective config is unusable ({exc})")
        cwd_key = str(effective_values.get("xkey_verify_cwd") or "")
        cwd, cwd_err = _ap_resolve_verify_cwd(cwd_key, target)
        if cwd_err is not None:
            return _ap_verify_error(action, cwd_err)
        written = _ap_config.save_config(project_dir, merged)
    finally:
        mw_common.release_lock(lock)

    print(f"[mw autopilot verify set] {written}")
    print(
        "  xkey_verify_cmd: "
        + json.dumps(merged["xkey_verify_cmd"], ensure_ascii=False)
    )
    print(f"  xkey_verify_timeout_s: {merged['xkey_verify_timeout_s']}")
    print(f"  xkey_verify_cwd: {cwd_key or '(auto)'}")
    print(f"  argv: {json.dumps(rendered, ensure_ascii=False)}")
    print(f"  cwd: {cwd}")
    return 0


def _ap_verify_show(args: argparse.Namespace, project_dir: pathlib.Path) -> int:
    """Read-only effective view (D-014): values + origins + expanded argv/cwd.

    Never creates a directory or a file (no ``.mw/``, no lock)."""
    path = _ap_config.config_path(project_dir)
    values: dict = {}
    origins: dict = {}
    diagnostics: list[str] = []
    argv: list[str] | None = None
    cwd: str | None = None
    error: str | None = None
    try:
        values, origins, diagnostics = mw_common._autopilot_effective_values(project_dir)
    except _ap_config.ConfigError as exc:  # project layer is fail-closed
        error = str(exc)
    if error is None:
        cmd = [str(part) for part in (values.get("xkey_verify_cmd") or [])]
        try:
            target = mw_common.load_target_config(project_dir)
            argv = mw_common.render_argv(cmd, target)
        except mw_common.TargetConfigError as exc:
            error = f"{exc.kind}: {exc}"
        else:
            cwd, cwd_err = _ap_resolve_verify_cwd(
                str(values.get("xkey_verify_cwd") or ""), target
            )
            if cwd_err is not None:
                error = cwd_err

    if getattr(args, "as_json", False):
        payload = {
            "path": str(path),
            "exists": path.exists(),
            "values": {key: values.get(key) for key in _AP_XKEY_KEYS} if not error else None,
            "origins": {key: origins.get(key, "default") for key in _AP_XKEY_KEYS} if not error else None,
            "argv": argv,
            "cwd": cwd,
            "diagnostics": diagnostics,
            "error": error,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if error is not None:
            return _ap_verify_error("show", error)
        return 0

    suffix = " (missing — nothing configured)" if not path.exists() else " (exists)"
    print(f"config: {path}{suffix}")
    if error is not None:
        return _ap_verify_error("show", error)
    for key in _AP_XKEY_KEYS:
        value = values.get(key)
        if key == "xkey_verify_cwd" and not value:
            shown = "(auto)"
        else:
            shown = json.dumps(value, ensure_ascii=False)
        print(f"{key}: {shown} [{origins.get(key, 'default')}]")
    print(f"argv: {json.dumps(argv, ensure_ascii=False)}")
    print(f"cwd: {cwd}")
    for diagnostic in diagnostics:
        print(f"diagnostics: {diagnostic}")
    return 0


def _ap_verify_clear(args: argparse.Namespace, project_dir: pathlib.Path) -> int:
    """Remove only the four xkey keys; the file is never deleted (D-005).

    No key present -> ``nothing configured``, no write, exit 0. Other keys
    keep their values (the file stays partial rather than being default-filled,
    so the byte footprint of an unrelated key never changes)."""
    action = "clear"
    path = _ap_config.config_path(project_dir)
    if not path.exists():
        print("[mw autopilot verify clear] nothing configured")
        return 0
    raw, err = _ap_read_raw_config(path)
    if err is not None:
        return _ap_verify_error(
            action,
            f"existing _autopilot/config.json is unusable ({err}) — "
            "fix or remove it before writing",
        )
    if not any(key in (raw or {}) for key in _AP_XKEY_KEYS):
        print("[mw autopilot verify clear] nothing configured")
        return 0

    lock = _ap_verify_lock_path(project_dir)
    try:
        mw_common.acquire_lock(
            lock, retries=_AP_VERIFY_LOCK_RETRIES, base_delay=_AP_VERIFY_LOCK_BASE_DELAY
        )
    except RuntimeError as exc:
        return _ap_verify_error(
            action, f"{exc} (remove the stale lock if no writer is active)"
        )
    try:
        raw, err = _ap_read_raw_config(path)
        if err is not None:
            return _ap_verify_error(
                action,
                f"existing _autopilot/config.json is unusable ({err}) — "
                "fix or remove it before writing",
            )
        removed = [key for key in _AP_XKEY_KEYS if key in (raw or {})]
        if not removed:
            print("[mw autopilot verify clear] nothing configured")
            return 0
        for key in removed:
            del raw[key]
        _ap_config.save_config(project_dir, raw)
    finally:
        mw_common.release_lock(lock)
    print(f"[mw autopilot verify clear] removed {', '.join(removed)} → {path}")
    return 0


def cmd_autopilot(args: argparse.Namespace) -> int:
    """Autopilot CLI: `verify set|show|clear` (xkey channel), `gates` and
    `contract-guard`.

    Errors print ``[mw autopilot <action>] Error: ...`` to stderr and return 1;
    only `verify set`/`clear` write (both under the dedicated lock). `gates`
    (pre-existing) and `contract-guard` (T-11) are read-only machine exits."""
    project_dir = pathlib.Path(args.project).resolve()
    if args.autopilot_action == "gates":
        return _ap_gates(args, project_dir)
    if args.autopilot_action == "answer":
        return _ap_answer(args, project_dir)
    if args.autopilot_action == "contract-guard":
        return _ap_contract_guard(args, project_dir)
    if args.autopilot_action == "contract-freeze":
        return _ap_contract_freeze(args, project_dir)
    if args.autopilot_action != "verify":
        print(
            f"[mw autopilot] Error: unknown action {args.autopilot_action!r}",
            file=sys.stderr,
        )
        return 1
    if args.verify_action == "set":
        return _ap_verify_set(args, project_dir)
    if args.verify_action == "clear":
        return _ap_verify_clear(args, project_dir)
    return _ap_verify_show(args, project_dir)


# ── `mw autopilot gates`: layer-B machine exit (T-13 / AC-006, AC-012) ───────

# Per-kind consequence table for the card's A/R line. Code constants only - no
# prose derivation and no model call (design D3.2 L3; TS mirror console.ts
# GATE_ACTIONS).
_GATE_CARD_ACTIONS: dict[str, tuple[str, str, str]] = {
    "stage-confirm": (
        "stage opens, its keys become eligible",
        "stage stays halted until a new proposal",
        "no",
    ),
    "stage-close": (
        "stage -> closed, next stage-confirm opens",
        "stage -> halted, roadmap edit required",
        "no",
    ),
    "stalled": ("one resume round granted for the key", "key stays stalled (terminal)", "yes"),
    "budget-exhausted": (
        "one resume round granted for the loop",
        "loop stays exhausted (terminal)",
        "yes",
    ),
    "goal-change": ("new goal adopted, keys re-validate", "goal change refused, halt and report", "no"),
    "xkey-authorize": ("cross-key write ticket authorized", "ticket refused, blocker recorded", "no"),
}

# Each gate renders EXACTLY 13 lines, each <= 110 columns (design D-015).
_GATE_CARD_LINE_MAX = 110


def _gate_card_clamp(value: object, limit: int) -> str:
    text = value if isinstance(value, str) else str(value)
    limit = max(0, limit)
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "\u2026"


def _gate_card_line(value: object) -> str:
    return _gate_card_clamp(value, _GATE_CARD_LINE_MAX)


def _gate_downstream_keys(stage: object, entry: dict) -> list[str] | None:
    """Keys depending (transitively) on the gate's key, or every key of a
    stage-level gate's stage. None when the roadmap/stage is unavailable.
    Same derivation as console.ts downstreamKeys."""
    if stage is None:
        return None
    key = entry.get("key")
    if not key:
        return [k.key for k in stage.keys]
    found: set[str] = set()
    grew = True
    while grew:
        grew = False
        for item in stage.keys:
            if item.key in found:
                continue
            if key in item.depends_on or any(dep in found for dep in item.depends_on):
                found.add(item.key)
                grew = True
    return sorted(found)


def _gate_verdict_summary(value: object) -> str:
    """`key:verdict` summary from the verdicts_final snapshot (L5)."""
    if not isinstance(value, list):
        return mw_common.GATE_MISSING_SENTINEL
    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        parts.append(f"{item.get('key', '?')}:{item.get('verdict', '?')}")
    return ",".join(parts) if parts else mw_common.GATE_MISSING_SENTINEL


def _render_gate_cards(section: dict, project_dir: pathlib.Path) -> list[str]:
    """The layer-B card: header + EXACTLY 13 lines per pending gate, fixed
    order, each line <= 110 columns (AC-026 / design D3.2). Missing v2 fields
    render the one sentinel literal - never prose, never a guess. Pure read:
    no model/dispatch reference, no directory creation."""
    sentinel = mw_common.GATE_MISSING_SENTINEL
    pending = section.get("pending") or []
    if not pending:
        total = section.get("total", 0)
        return [f"no pending gates ({total} total, {total - section.get('pending_count', 0)} answered)"]
    stages: dict[int, object] = {}
    try:
        parsed = _ap_roadmap.load_roadmap(_ap_roadmap.roadmap_path(project_dir))
        stages = {stage.number: stage for stage in parsed.stages}
    except Exception:
        stages = {}
    lines: list[str] = [f"{len(pending)} pending gate(s):"]
    for entry in pending:
        gate_id = entry["id"]
        kind = entry["kind"]
        created_at = mw_common._gate_node_value(entry.get("created_at"))
        waited = mw_common._gate_node_value(entry.get("waited_s"))
        waited_text = sentinel if waited is None else mw_common._gate_waited_text(waited)
        action = _GATE_CARD_ACTIONS.get(kind)
        approve, reject, reversible = action if action is not None else (sentinel, sentinel, sentinel)
        stage = stages.get(entry.get("stage")) if entry.get("stage") is not None else None
        goal = stage.goal if stage is not None and stage.goal else sentinel
        refs = entry.get("context_refs") or []
        src = refs[1] if len(refs) > 1 else sentinel
        history = entry.get("history") or []
        history_text = (
            "none"
            if not history
            else "; ".join(
                f"{h['gate_id']} [{h['kind']}] {h['scope']} {h['status']} {h['answered_at'] or '\u2014'}"
                for h in history
            )
        )
        notes = [h for h in history if h.get("note")]
        prior_note = f"[{notes[-1]['gate_id']}] {notes[-1]['note']}" if notes else "none"
        constraints = entry.get("constraints")
        constraints_text = sentinel if not constraints else "; ".join(str(c) for c in constraints)
        downstream = _gate_downstream_keys(stage, entry)
        impact = (
            sentinel
            if downstream is None
            else f"downstream={len(downstream)} keys [{','.join(downstream[:5])}]"
        )
        roadmap_status = stage.status if stage is not None else sentinel
        q_tail = f" (full: {entry['path']})"
        records = entry.get("evidence") or []
        if not records:
            evidence_text = f"evidence: {sentinel}"
        else:
            described = []
            for record in records[:3]:
                rel = record.get("ref") or record.get("path") or "?"
                if record.get("path") is None:
                    described.append(f"{rel} ({sentinel})")
                else:
                    described.append(f"{rel} ({record['bytes']}B, mtime={record['mtime']})")
            evidence_text = "evidence: " + "; ".join(described)
            if len(records) > 3:
                evidence_text += f" +{len(records) - 3} more"
            if entry.get("drift_detail"):
                evidence_text += f" DRIFT({entry['drift_detail']})"
        open_items = entry.get("open_items")
        open_text = sentinel if open_items is None else json.dumps(open_items, ensure_ascii=False)
        lines.append(_gate_card_line(f"{gate_id} [{kind}] {entry['scope']} created={created_at} waited={waited_text}"))
        lines.append(
            _gate_card_line(
                f"Q: {_gate_card_clamp(entry.get('question') or '', max(0, _GATE_CARD_LINE_MAX - 3 - len(q_tail)))}{q_tail}"
            )
        )
        lines.append(
            _gate_card_line(
                f"A: approve = {approve} (reversible: {reversible}) | "
                f"R: reject = {reject} (reversible: {reversible})"
            )
        )
        lines.append(
            _gate_card_line(
                f"goal: {_gate_card_clamp(goal, 60)} | "
                f"goal_sha256={entry.get('goal_sha256') or sentinel} | "
                f"proposal_sha256={entry.get('proposal_sha256') or sentinel} | "
                f"roadmap_validation={sentinel if entry.get('roadmap_validation') is None else json.dumps(entry['roadmap_validation'], ensure_ascii=False)}"
            )
        )
        lines.append(
            _gate_card_line(
                f"reason: {mw_common._gate_node_value(entry.get('reason_code')) or sentinel} "
                f'src="{_gate_card_clamp(src, 60)}" | verdict: l3={_gate_verdict_summary(entry.get("verdicts_final"))}'
            )
        )
        lines.append(_gate_card_line(evidence_text))
        lines.append(
            _gate_card_line(
                f"impact: {impact} | stage-close: {'this gate' if kind == 'stage-close' else 'na'} | "
                f"next-stage: na | roadmap: {roadmap_status}"
            )
        )
        lines.append(_gate_card_line(f"history: {history_text}"))
        lines.append(
            _gate_card_line(
                f"default: {mw_common._gate_node_value(entry.get('default_action')) or sentinel} | "
                f"ttl: {mw_common._gate_node_value(entry.get('expires_at')) or sentinel}"
            )
        )
        lines.append(
            _gate_card_line(
                f"budget: loop={entry.get('loop') or sentinel} "
                f"used={entry.get('used_rounds') if entry.get('used_rounds') is not None else sentinel}/"
                f"{entry.get('round_limit') if entry.get('round_limit') is not None else sentinel} "
                f"credits={entry.get('credits_used') if entry.get('credits_used') is not None else sentinel}"
            )
        )
        lines.append(
            _gate_card_line(
                f"constraints: {_gate_card_clamp(constraints_text, 50)} | "
                f"prior: {_gate_card_clamp(prior_note, 40)}"
            )
        )
        lines.append(_gate_card_line(f"open-items: {open_text}"))
        lines.append(
            _gate_card_line(
                f"answer: {entry['answer_entry']['value']}  "
                f"expected: {entry.get('answer_source') or sentinel}"
            )
        )
    return lines


def _ap_gates(args: argparse.Namespace, project_dir: pathlib.Path) -> int:
    """`mw autopilot gates [--json]`: read-only gate queue view. Text = the
    layer-B 13-line cards; --json = the doctor gate segment (layer C machine
    exit, same shape as `mw doctor --json`'s `gates` key)."""
    section = mw_common._doctor_gates(project_dir)
    if section.get("error"):
        print(f"[mw autopilot gates] Error: {section['error']}", file=sys.stderr)
        return 1
    if getattr(args, "as_json", False):
        print(json.dumps(section, indent=2, default=str))
        return 0
    for line in _render_gate_cards(section, project_dir):
        print(line)
    for err in section.get("parse_errors") or []:
        print(f"warning: {err['path']}: {err['error']}")
    # T-24 / VC-048: an off-gate prose authorization is visible in the gates
    # view too (the JSON section carries the full `crosskey_prose` node).
    for request in (section.get("crosskey_prose") or {}).get("requests") or []:
        if request.get("authorization") != "prose":
            continue
        print(
            "warning: cross-key request "
            f"{request.get('request_id') or request['path']} is authorized by prose "
            f"only ({request['path']}) - treated as unauthorized (VC-048)"
        )
    return 0


def _ap_answer(args: argparse.Namespace, project_dir: pathlib.Path) -> int:
    """`mw autopilot answer --gate-id <id> (--approve|--reject) [--note N]
    [--answered-by WHO] [--confirm-destructive]`: write one human gate answer.

    Thin wrapper over `conductor.answer_gate_confirmed` (AC-009): a `reject` is
    destructive and is refused without `--confirm-destructive`, with the
    accurate consequence printed and NOTHING written. A confirmed answer uses
    the same byte-preserving four-field rewrite as the TS `/autopilot gate`
    writer, so `answered_by`/`answered_at`/the timeline audit is preserved."""
    decision = "approve" if getattr(args, "approve", False) else "reject"
    host = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "host"
    answered_by = getattr(args, "answered_by", None) or f"mw-cli@{host}"
    st = _ap_conductor.ConductorState(
        _ap_timeline.Timeline(_ap_timeline.timeline_path(project_dir)),
        _ap_conductor.goal_mtime_ns(project_dir),
    )
    result = _ap_conductor.answer_gate_confirmed(
        project_dir, st, args.gate_id, decision,
        answered_by=answered_by,
        note=getattr(args, "note", None),
        confirm=bool(getattr(args, "confirm_destructive", False)),
    )
    if not result.ok:
        print(f"[mw autopilot answer] Error: {result.error}", file=sys.stderr)
        return 1
    print(
        f"[mw autopilot answer] {result.gate_id} → {result.status} "
        f"(answered_by={answered_by})"
    )
    return 0


def _ap_contract_guard(args: argparse.Namespace, project_dir: pathlib.Path) -> int:
    """`mw autopilot contract-guard [--key K] [--json]`: read-only G3 verdict.

    The judgement is delegated to `autopilot.contract_guard.evaluate` (T-04) -
    this CLI never re-derives freeze/diff/approval logic, and never writes (the
    freeze sidecar is produced by the conductor / the T-04 library, not here).
    Exit 0 = the done gate would not refuse (no anchor included); 1 = an
    unauthorized frozen-contract change, or an unreadable gate queue. `--json`
    carries no timestamp and no absolute path, so it is reproducible."""
    key = getattr(args, "key", None)
    try:
        if key:
            entries = [mw_common._contract_guard_entry(project_dir, key)]
        else:
            scan = mw_common._contract_guard_scan(project_dir)
            entries = list(scan["keys"]) if scan is not None else []
    except (ValueError, OSError) as exc:  # GateFormatError is a ValueError
        print(f"[mw autopilot contract-guard] Error: {exc}", file=sys.stderr)
        return 1

    def refused(entry: dict) -> bool:
        # `no_anchor` is present on the `--key` path and stripped from the
        # doctor-scan shape (a scan entry is always anchored).
        return (not entry["authorized"]) and not entry.get("no_anchor", False)

    failed = any(refused(entry) for entry in entries)
    if getattr(args, "as_json", False):
        payload = {
            "keys": [
                {
                    "authorized": entry["authorized"],
                    "carrier": entry["carrier"],
                    "changed_ids": entry["changed_ids"],
                    "freeze": not entry.get("no_anchor", False),
                    "key": entry["key"],
                    "reasons": entry["reasons"],
                    "refused": refused(entry),
                }
                for entry in entries
            ],
            "ok": not failed,
            "refused": failed,
            "unauthorized": sum(1 for entry in entries if refused(entry)),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if failed else 0

    if not entries:
        print("contract-guard: no freeze sidecar (nothing to check)")
        return 0
    for entry in entries:
        changed = ",".join(entry["changed_ids"]) or "-"
        carrier = entry["carrier"] or "none"
        if entry.get("no_anchor", False):
            print(f"contract-guard: {entry['key']} freeze=no carrier=none ok=yes (no anchor)")
        elif entry["authorized"]:
            print(
                f"contract-guard: {entry['key']} freeze=yes changed={changed} "
                f"carrier={carrier} ok=yes"
            )
        else:
            print(
                f"contract-guard: {entry['key']} freeze=yes changed={changed} "
                f"carrier={carrier} ok=no refused"
            )
    return 1 if failed else 0


# ── `mw autopilot contract-freeze`: explicit G3 anchor writer (T-23 / AC-025) ──

#: `--block` choice -> the blocks it processes. `all` = both acceptance
#: boundaries; a block left out is reported as `skipped` without being touched.
_CONTRACT_FREEZE_BLOCKS: dict[str, tuple[tuple[str, str], ...]] = {
    "ac": (("ac", "spec"),),
    "vc": (("vc", "design"),),
    "all": (("ac", "spec"), ("vc", "design")),
}


def _read_optional_text(path: pathlib.Path) -> str:
    """UTF-8 text or ``""`` when the artifact is absent.

    A missing ``spec.md``/``design.md`` yields an empty family - the freeze
    then has nothing to fill for that block (never an error)."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _contract_freeze_plan(
    existing: dict | None,
    identity: object,
    selected: tuple[tuple[str, str], ...],
    force: bool,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, object]], dict[str, list[str]]]:
    """Pure per-block decision against one sidecar snapshot.

    Returns ``(blocks, statuses, replaced)``:
      - ``blocks``: final ``{family: {id: sha}}`` to persist (the on-disk
        snapshot for a block that is not touched).
      - ``statuses``: ``{block: {"status": ..., "ids": [...]}}`` with
        ``written`` (filled or ``--force`` re-frozen), ``unchanged``
        (present and equal to the current text -> default skip), ``refused``
        (present and different without ``--force``), or ``skipped`` (not
        selected, or no ids to anchor).
      - ``replaced``: ``{block: [changed/removed ids]}`` for the ``--force``
        print and the refusal diagnostic.
    """
    acs = dict(getattr(identity, "acs", {}) or {})
    vcs = dict(getattr(identity, "vcs", {}) or {})
    current = {"ac": acs, "vc": vcs}
    family_of = {"ac": "spec", "vc": "design"}
    selected_names = {name for name, _ in selected}
    blocks: dict[str, dict[str, str]] = {}
    statuses: dict[str, dict[str, object]] = {}
    replaced: dict[str, list[str]] = {}
    for name in ("ac", "vc"):
        family = family_of[name]
        frozen_raw = existing.get(family) if isinstance(existing, dict) else None
        frozen = dict(frozen_raw) if isinstance(frozen_raw, dict) else {}
        blocks[family] = frozen
        if name not in selected_names:
            statuses[name] = {"status": "skipped", "ids": []}
            continue
        cur = current[name]
        if not frozen:
            if cur:
                blocks[family] = dict(cur)
                statuses[name] = {"status": "written", "ids": sorted(cur)}
            else:
                statuses[name] = {"status": "skipped", "ids": []}
            continue
        if frozen == cur:
            statuses[name] = {"status": "unchanged", "ids": sorted(frozen)}
            continue
        ids = sorted(
            field_id
            for field_id in set(frozen) | set(cur)
            if frozen.get(field_id) != cur.get(field_id)
        )
        replaced[name] = ids
        if force:
            blocks[family] = dict(cur)
            statuses[name] = {"status": "written", "ids": sorted(cur)}
        else:
            statuses[name] = {"status": "refused", "ids": ids}
    return blocks, statuses, replaced


def _write_contract_freeze(
    key_dir: pathlib.Path,
    key: str,
    blocks: dict[str, dict[str, str]],
) -> None:
    """Persist one merged payload through the T-04 atomic writer."""
    payload = contract_guard.build_freeze(key, "", "")
    payload["spec"] = dict(sorted(blocks.get("spec", {}).items()))
    payload["design"] = dict(sorted(blocks.get("design", {}).items()))
    contract_guard.write_freeze(key_dir, payload)


def _ap_contract_freeze(args: argparse.Namespace, project_dir: pathlib.Path) -> int:
    """`mw autopilot contract-freeze --project P --key K [--block ac|vc|all]
    [--force] [--json]`: the explicit G3 anchor writer.

    T-23's human entry for a block the first-sight producer never anchored
    (historical keys are never backfilled automatically). A missing block is
    filled; an existing block whose frozen shas equal the current text is left
    untouched (``unchanged``); an existing block whose text changed is refused
    without ``--force`` (exit 1, the replaced ids are printed) and re-frozen
    with ``--force`` (old/new family sha printed). The write goes through
    ``contract_guard.write_freeze`` (tmp+replace). No lock is added: the
    sidecar is a per-key file, so the same-key concurrent case is handled by
    re-reading immediately before the write - if a writer got there first, the
    decision is re-derived from that snapshot and the write is idempotent.
    """
    key = args.key
    force = bool(getattr(args, "force", False))
    selected = _CONTRACT_FREEZE_BLOCKS[getattr(args, "block", "all") or "all"]
    key_dir = project_dir / ".agenticdoc" / key
    freeze_rel = contract_guard.freeze_path(key_dir).relative_to(project_dir).as_posix()
    try:
        existing = contract_guard.read_freeze(key_dir)
        identity = contract_guard.extract_contract(
            _read_optional_text(key_dir / contract_guard.SPEC_FILE_NAME),
            _read_optional_text(key_dir / contract_guard.DESIGN_FILE_NAME),
        )
        blocks, statuses, replaced = _contract_freeze_plan(existing, identity, selected, force)
        for name, _family in selected:
            if statuses[name]["status"] != "written":
                continue
            # Lock-free idempotence: re-read right before the write. A block
            # that appeared since the snapshot wins, so re-derive once.
            latest = contract_guard.read_freeze(key_dir)
            if latest != existing:
                existing = latest
                blocks, statuses, replaced = _contract_freeze_plan(latest, identity, selected, force)
            if any(statuses[n]["status"] == "written" for n, _f in selected):
                _write_contract_freeze(key_dir, key, blocks)
            break
    except (OSError, ValueError) as exc:  # UnicodeDecodeError / relative_to are ValueError
        print(f"[mw autopilot contract-freeze] Error: {exc}", file=sys.stderr)
        return 1

    refused = any(statuses[name]["status"] == "refused" for name in ("ac", "vc"))
    if getattr(args, "as_json", False):
        print(json.dumps(
            {
                "key": key,
                "freeze_rel": freeze_rel,
                "blocks": {name: statuses[name] for name in ("ac", "vc")},
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ))
        return 1 if refused else 0

    print(f"contract-freeze: {key} freeze={freeze_rel}")
    family_of = {"ac": "spec", "vc": "design"}
    for name in ("ac", "vc"):
        status = statuses[name]["status"]
        ids = ",".join(statuses[name]["ids"]) or "-"
        line = f"contract-freeze: {name} {status} ids={ids}"
        if name in replaced:
            line += f" replaced={','.join(replaced[name])}"
        if status == "written" and name in replaced:
            # --force re-freeze diagnostics: old/new family sha.
            family = family_of[name]
            old_block = existing.get(family) if isinstance(existing, dict) else None
            old_sha = contract_guard.family_sha(old_block if isinstance(old_block, dict) else {})
            line += f" old_sha={old_sha} new_sha={contract_guard.family_sha(blocks[family])}"
        if status == "refused":
            line += " - pass --force to re-freeze"
        print(line)
    return 1 if refused else 0


# ── Subcommand: pull-agentictask ───────────────────────────────────────────────

def _git_short_commit(repo: pathlib.Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip() or "unknown"
    except Exception:
        return "unknown"


def _rmtree_robust(path: pathlib.Path) -> None:
    """rmtree that survives Windows read-only files (git pack/.idx are read-only,
    and plain shutil.rmtree raises PermissionError on them)."""
    def _on_error(func, p, _exc):
        try:
            os.chmod(p, 0o777)
        except OSError:
            pass
        func(p)
    # Python 3.12+ renamed onerror→onexc; pass onexc where available, else onerror.
    try:
        shutil.rmtree(path, onexc=_on_error)  # type: ignore[call-arg]
    except TypeError:
        shutil.rmtree(path, onerror=_on_error)


def _copy_agentictask_source(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Copy the framework source tree into the cache, excluding .git/__pycache__."""
    if dst.exists():
        _rmtree_robust(dst)
    shutil.copytree(
        str(src),
        str(dst),
        ignore=shutil.ignore_patterns(*_AGENTICTASK_IGNORE),
    )


def _git(
    args: list[str], *, cwd: pathlib.Path | None = None, timeout: float | None = None
) -> subprocess.CompletedProcess:
    """Run a git command, capturing output. Never raises: a non-zero exit, a
    missing binary, and a timeout all come back as a failure CompletedProcess
    (every caller only inspects `returncode`). `timeout=None` keeps long
    operations (fetch/pull/push) unbounded; identity collection passes 3 s."""
    cmd = ["git"]
    if cwd is not None:
        cmd += ["-C", str(cwd)]
    cmd += args
    kwargs: dict = {"capture_output": True, "text": True}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if sys.platform == "win32":
        # A windowless serve must not flash a console window for any child.
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    try:
        return subprocess.run(cmd, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def _validate_agentictask_install(dst: pathlib.Path) -> tuple[bool, str]:
    """An AgenticTask checkout must carry install.py (the installer we invoke later)."""
    if not (dst / "install.py").is_file():
        return False, f"{dst} does not look like an AgenticTask repo (missing install.py)."
    return True, ""


def _checkout_framework_dir() -> pathlib.Path:
    """The mw checkout's own AgenticTask install (dev machines only).

    mw.py always lives inside a Multi-Workers checkout; when that checkout has
    itself been mw-inited, this is the live working repo the framework is
    developed and published from — always fresher than any cache. The directory
    is untracked in the Multi-Workers repo, so it only exists where someone ran
    `mw init` on the checkout itself.
    """
    return _repo_root() / ".agents" / "skills" / "agentic-task"


def _resolve_framework_source(sync_source: str | None) -> pathlib.Path:
    """Pick the AgenticTask install source, freshest first:

    1. --sync-agentictask <dir>  (explicit override)
    2. the mw checkout's own .agents/skills/agentic-task — the live working
       repo on a dev machine; bypasses the cache entirely, so installs can
       never go stale behind it. May carry uncommitted state: commit & push
       first when you want published state propagated.
    3. the .tmp/agentic-task cache — bootstrap fallback; auto-cloned once from
       the default remote when missing, refreshed later via pull-agentictask.
    """
    if sync_source:
        return pathlib.Path(sync_source).resolve()
    checkout = _checkout_framework_dir()
    if (checkout / "install.py").is_file():
        return checkout
    if not (_TMP_AGENTICTASK / "install.py").is_file():
        pulled, pull_msg = _pull_agentictask(_DEFAULT_AGENTICTASK_REMOTE, force=False)
        print(f"[mw init] auto-pull: {pull_msg}")
    return _TMP_AGENTICTASK


def _pull_via_git(url: str, *, force: bool, branch: str) -> tuple[bool, str]:
    """Clone the framework repo into the cache, or fast-forward an existing clone.
    The cache becomes a real, independently pushable git repo (see push-agentictask)."""
    dst = _TMP_AGENTICTASK
    git_dir = dst / ".git"

    if git_dir.exists():
        # Existing clone → update in place, preserving local commits/edits.
        fetch = _git(["fetch", "origin"], cwd=dst)
        if fetch.returncode != 0:
            return False, f"git fetch failed: {(fetch.stderr or fetch.stdout).strip()}"
        if force:
            # Explicitly discard local state and align with the remote branch.
            reset = _git(["reset", "--hard", f"origin/{branch}"], cwd=dst)
            if reset.returncode != 0:
                return False, f"git reset --hard failed: {(reset.stderr or reset.stdout).strip()}"
        else:
            pull = _git(["pull", "--ff-only", "origin", branch], cwd=dst)
            if pull.returncode != 0:
                return False, (
                    f"git pull --ff-only failed (local diverged from origin/{branch}?): "
                    f"{(pull.stderr or pull.stdout).strip()} — resolve manually or use --force."
                )
    elif dst.exists():
        # A non-git cache (old copytree layout) sits here. Converting it to a clone
        # is destructive, so require --force before we rmtree it.
        if not force:
            return False, (
                f"non-git cache present at {dst}. Use --force to replace it with a fresh clone."
            )
        _rmtree_robust(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        clone = _git(["clone", "--branch", branch, url, str(dst)])
        if clone.returncode != 0:
            return False, f"git clone failed: {(clone.stderr or clone.stdout).strip()}"
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        clone = _git(["clone", "--branch", branch, url, str(dst)])
        if clone.returncode != 0:
            return False, f"git clone failed: {(clone.stderr or clone.stdout).strip()}"

    ok, err = _validate_agentictask_install(dst)
    if not ok:
        return False, err
    return True, f"cloned/updated from {url}@{branch} (commit {_git_short_commit(dst)}) → {dst}"


def _pull_via_copy(src: pathlib.Path, *, force: bool) -> tuple[bool, str]:
    """Copy a local framework source dir into the cache (no .git → not pushable).
    Fallback for offline/vendored sources; the git path is preferred."""
    src = src.resolve()
    if not src.is_dir():
        return False, f"source not found: {src}"
    ok, err = _validate_agentictask_install(src)
    if not ok:
        return False, err
    if _TMP_AGENTICTASK.exists() and not force:
        return True, f"cache already present: {_TMP_AGENTICTASK} (use --force to refresh)"
    _TMP_AGENTICTASK.parent.mkdir(parents=True, exist_ok=True)
    _copy_agentictask_source(src, _TMP_AGENTICTASK)
    return True, (
        f"copied from {src} (commit {_git_short_commit(src)}) → {_TMP_AGENTICTASK} "
        "(plain copy, no .git — not pushable; use a git URL for push support)"
    )


def _pull_agentictask(source: str, *, force: bool, branch: str = _DEFAULT_AGENTICTASK_BRANCH) -> tuple[bool, str]:
    """Populate the local cache. A git URL (or an absent local dir) clones/updates a
    real git repo; an existing local dir is copied byte-for-byte. Returns (ok, message)."""
    source = str(source)
    if _is_git_url(source):
        return _pull_via_git(source, force=force, branch=branch)
    # Non-URL: an existing local directory → copytree; otherwise treat as a git target
    # only if it looks like a URL (handled above). A missing local path is an error.
    return _pull_via_copy(pathlib.Path(source), force=force)


def cmd_pull_agentictask(args: argparse.Namespace) -> int:
    ok, msg = _pull_agentictask(args.source, force=args.force, branch=args.branch)
    if ok:
        print(f"[mw pull-agentictask] {msg}")
        return 0
    print(f"[mw pull-agentictask] Error: {msg}", file=sys.stderr)
    return 1


def cmd_push_agentictask(args: argparse.Namespace) -> int:
    """Commit (optional) + push local framework changes from the .tmp clone back to
    its remote. Requires the cache to be a real git clone (pull from a git URL first)."""
    dst = _TMP_AGENTICTASK
    if not (dst / ".git").exists():
        print(
            f"[mw push-agentictask] Error: {dst} is not a git clone. "
            "Run 'python mw.py pull-agentictask --force' (from a git URL) first.",
            file=sys.stderr,
        )
        return 1

    # Is the working tree dirty?
    status = _git(["status", "--porcelain"], cwd=dst)
    if status.returncode != 0:
        print(f"[mw push-agentictask] Error: git status failed: {(status.stderr or status.stdout).strip()}",
              file=sys.stderr)
        return 1
    dirty = bool(status.stdout.strip())

    if dirty:
        if not args.message:
            print(
                "[mw push-agentictask] Error: working tree has uncommitted changes. "
                "Pass -m/--message to commit them, or commit manually first.",
                file=sys.stderr,
            )
            return 1
        add = _git(["add", "-A"], cwd=dst)
        if add.returncode != 0:
            print(f"[mw push-agentictask] Error: git add failed: {(add.stderr or add.stdout).strip()}",
                  file=sys.stderr)
            return 1
        commit = _git(["commit", "-m", args.message], cwd=dst)
        if commit.returncode != 0:
            print(f"[mw push-agentictask] Error: git commit failed: {(commit.stderr or commit.stdout).strip()}",
                  file=sys.stderr)
            return 1
        print(f"[mw push-agentictask] committed: {args.message} ({_git_short_commit(dst)})")

    push = _git(["push", "origin", args.branch], cwd=dst)
    if push.returncode != 0:
        print(f"[mw push-agentictask] Error: git push failed: {(push.stderr or push.stdout).strip()}",
              file=sys.stderr)
        return 1
    print(f"[mw push-agentictask] pushed to origin/{args.branch} (commit {_git_short_commit(dst)})")
    return 0


# ── Subcommand: init ─────────────────────────────────────────────────────────

_BUNDLE_REL = pathlib.Path("dist") / "extensions" / "agent-team-loop.js"


def _bundle_path() -> pathlib.Path:
    return _SCRIPT_DIR / _BUNDLE_REL


def _check_bundle() -> bool:
    return _bundle_path().exists()


# ── Bundle build (bash-free, cwd-independent) ──────────────────────────────────

# Source entry point, relative to the repo root (mw.py lives at
# <repo>/packages/multi-workers/mw.py, so the root is two levels up).
_EXT_SRC_REL = (
    pathlib.Path("packages") / "coding-agent" / "src" / "extensions" / "agent-team-loop" / "index.ts"
)

# esbuild + self-check, driven by node. SRC/OUT come from env vars (MW_SRC/MW_OUT)
# so no Windows backslash ever lands inside a JS string literal. Mirrors the
# format/target/external contract of build-extension.sh (ESM so the host's
# jiti.import(path, {default:true}) unwraps the activate() function reliably).
#
# MW_VERSION is the packages/coding-agent/package.json version injected through
# `define` (C-31): a bundled module cannot resolve that package.json at runtime,
# so config.ts's `pkg.version` read fell back to "0.0.0" and the producer
# identity line became incomparable. The define inlines the real version
# literal into the emitted bundle.
_BUILD_NODE_SCRIPT = r"""
const esbuild = require('esbuild');
const { createJiti } = require('jiti');
const url = require('url');
const SRC = process.env.MW_SRC;
const OUT = process.env.MW_OUT;
const VERSION = process.env.MW_VERSION || '';
esbuild.build({
  entryPoints: [SRC],
  bundle: true,
  outfile: OUT,
  platform: 'node',
  format: 'esm',
  target: 'node18',
  external: ['node:*'],
  define: { __PI_CODING_AGENT_VERSION__: JSON.stringify(VERSION) },
  logLevel: 'warning',
}).then(() => {
  const j = createJiti(url.pathToFileURL(process.cwd() + '/').href, { moduleCache: false });
  return j.import(OUT, { default: true });
}).then((f) => {
  if (typeof f !== 'function') {
    console.error('Self-check FAILED: host loader expects a function, got ' + typeof f);
    process.exit(1);
  }
  console.log('built + self-check OK (' + (f.name || 'anon') + ')' + (VERSION ? ' version=' + VERSION : ''));
}).catch((e) => {
  console.error('Build FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
"""

# The version source the injected bundle literal and the service baseline share
# (single source: packages/coding-agent/package.json, lockstep releases).
_FRAMEWORK_PACKAGE_JSON_REL = pathlib.Path("packages") / "coding-agent" / "package.json"


def _repo_root() -> pathlib.Path:
    return _SCRIPT_DIR.parent.parent


def _framework_version() -> str:
    """Version literal injected into the extension bundle, or "" when unreadable.

    Best-effort: a missing/unparseable package.json leaves the define empty, so
    config.ts falls back to its runtime read exactly as before.
    """
    try:
        data = json.loads((_repo_root() / _FRAMEWORK_PACKAGE_JSON_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    version = data.get("version") if isinstance(data, dict) else None
    return version.strip() if isinstance(version, str) else ""


def _build_bundle(out: pathlib.Path | None = None) -> tuple[bool, str]:
    """Compile the agent-team-loop extension bundle with esbuild and self-check
    that it loads as a function (the host loader contract).

    `out` defaults to the tracked bundle path (`<mw>/dist/extensions/
    agent-team-loop.js`); tests pass a temporary path so the real artifact is
    never touched. Pure Python + node: no bash, no msys `pwd -W`, and
    cwd-independent — all paths derive from mw.py's own location, so ANY pi
    window can rebuild mw regardless of its working directory. node runs with
    cwd=repo root so that require('esbuild')/require('jiti') resolve from the
    repo's node_modules.
    """
    repo_root = _repo_root()
    src = repo_root / _EXT_SRC_REL
    if out is None:
        out = _bundle_path()
    if not src.is_file():
        return False, f"extension source not found: {src}"
    node = shutil.which("node")
    if node is None:
        return False, "node not found on PATH — install Node.js to build the extension."

    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["MW_SRC"] = str(src)
    env["MW_OUT"] = str(out)
    env["MW_VERSION"] = _framework_version()
    result = subprocess.run(  # noqa: S603
        [node, "-e", _BUILD_NODE_SCRIPT],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "esbuild build failed").strip()
    return True, (result.stdout or "").strip() or f"built {out}"


def _rebuild_pi_dist() -> tuple[bool, str]:
    """Rebuild packages/coding-agent/dist via `npm run build` (tsgo + copy-assets).

    The npm global `pi` links to packages/coding-agent, so the runtime executes
    the repo's dist. Without this rebuild the built-in agent-team-loop copy
    compiled into dist goes stale behind the freshly installed global bundle
    (mostly benign - the global bundle wins activation - but it drifts
    silently), and any pi-core changes never reach the runtime at all.
    """
    pkg = _repo_root() / "packages" / "coding-agent"
    npm = shutil.which("npm")
    if npm is None:
        return False, "npm not found on PATH - cannot rebuild packages/coding-agent/dist"
    result = subprocess.run(  # noqa: S603
        [npm, "run", "build"],
        cwd=str(pkg),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "npm run build failed").strip().splitlines()
        return False, "npm run build failed: " + " | ".join(tail[-3:])
    return True, "dist rebuilt"


def _mw_py_path_file() -> pathlib.Path:
    """Sidecar next to the global extension recording mw.py's absolute path, so
    the extension's findMwPy() resolves mw.py from any project (the repo-relative
    lookup fails when the bundle is loaded from the global install dir)."""
    return _global_ext_dir() / ".mw-py-path"


def _write_mw_py_path() -> None:
    p = _mw_py_path_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(pathlib.Path(__file__).resolve()), encoding="utf-8")


def _agentictask_update_install() -> tuple[bool, str]:
    """Install the /update-agentictask convenience extension into pi's global
    extensions dir. Machine-independent template (agentictask-update.ts ships
    next to mw.py): mw.py is located at runtime via MW_PY / the .mw-py-path
    sidecar, so nothing is rendered per machine. Idempotent: skips when the
    installed copy is identical, overwrites a drifted one. Returns (ok, msg)."""
    src = pathlib.Path(__file__).parent / "agentictask-update.ts"
    if not src.is_file():
        return False, f"agentictask-update template missing: {src}"
    ext_dir = _global_ext_dir()
    ext_dir.mkdir(parents=True, exist_ok=True)
    dst = ext_dir / "agentictask-update.ts"
    content = src.read_text(encoding="utf-8")
    if dst.is_file() and dst.read_text(encoding="utf-8") == content:
        return True, f"agentictask-update extension up-to-date: {dst}"
    dst.write_text(content, encoding="utf-8")
    return True, f"agentictask-update extension installed: {dst}"


def _goal_gate_install() -> tuple[bool, str]:
    """Install the goal.md loader + write gate into pi's global extensions dir.

    Machine-independent template (goal.ts ships next to mw.py). The gate is
    repo-owned so it is traceable and carries permanent regression tests
    (mw-goal-gate-write-intent): it used to live only as a hand-installed file
    in ~/.pi/agent/extensions with no tests, and its bash heuristic gated
    read-only commands (every mention of goal.md) instead of writes.
    Idempotent: skips when the installed copy is identical, overwrites a
    drifted one. Byte-exact (read/write bytes) so the installed copy hashes
    equal to the template on every platform. Returns (ok, msg)."""
    src = pathlib.Path(__file__).parent / "goal.ts"
    if not src.is_file():
        return False, f"goal.ts template missing: {src}"
    ext_dir = _global_ext_dir()
    ext_dir.mkdir(parents=True, exist_ok=True)
    dst = ext_dir / "goal.ts"
    content = src.read_bytes()
    if dst.is_file() and dst.read_bytes() == content:
        return True, f"goal.md write gate up-to-date: {dst}"
    dst.write_bytes(content)
    return True, f"goal.md write gate installed: {dst}"


def _deploy_bundle(no_dist: bool) -> int:
    """Install the freshly built bundle globally: bundle copy + .mw-py-path
    sidecar + /update-agentictask command + goal.md write gate + pi dist
    rebuild. Shared by `mw build --install` and `mw update-env --apply`.
    Returns exit code.

    The dist rebuild runs BEFORE the global copy: if it fails the old global
    bundle is left untouched (fail-closed) instead of pairing a fresh global
    copy with a stale dist (partial deploy, AC-009(c))."""
    dist_msg = ""
    if not no_dist:
        dok, dmsg = _rebuild_pi_dist()
        if not dok:
            print(f"[mw build] Error: {dmsg}", file=sys.stderr)
            return 1
        dist_msg = dmsg
    ext_dst = _global_ext_dir() / "agent-team-loop.js"
    ext_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(_bundle_path()), str(ext_dst))
    _write_mw_py_path()
    ok_u, msg_u = _agentictask_update_install()
    print(f"[mw build] {msg_u}" if ok_u else f"[mw build] Warning: {msg_u}",
          file=None if ok_u else sys.stderr)
    ok_g, msg_g = _goal_gate_install()
    print(f"[mw build] {msg_g}" if ok_g else f"[mw build] Warning: {msg_g}",
          file=None if ok_g else sys.stderr)
    print(f"[mw build] installed globally: {ext_dst}")
    # The npm global `pi` links to packages/coding-agent, so the runtime
    # executes the repo's dist — the rebuild above made it match the source.
    if no_dist:
        print("[mw build] dist rebuild skipped (--no-dist)")
        return 0
    print(f"[mw build] {dist_msg}: {_repo_root() / 'packages' / 'coding-agent' / 'dist'}")
    return 0


# Pathspecs whose uncommitted changes would be silently compiled into tracked
# build artifacts: `mw build --install` runs tsgo over coding-agent/src, while
# `mw bootstrap` runs the root build over every workspace's src. `git diff
# --quiet` is not enough here: it misses staged and untracked files, and tsgo's
# include: src/**/*.ts compiles new untracked sources too.
_BUILD_DIRTY_PATHS = ["packages/coding-agent/src"]
_BOOTSTRAP_DIRTY_PATHS = ["packages/*/src/**"]


def _git_dirty_paths(repo: pathlib.Path, paths: list[str]) -> list[str] | None:
    """Porcelain lines for uncommitted changes under `paths` (staged, unstaged
    and untracked). None when the check cannot be made (not a git checkout): a
    non-git tree cannot commit compiled artifacts, so the guard is skipped
    rather than blocking."""
    if not (repo / ".git").exists():
        return None
    r = _git(["status", "--porcelain", "--untracked-files=all", "--", *paths], cwd=repo)
    if r.returncode != 0:
        return None
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def _refuse_dirty_build(label: str, dirty: list[str], paths: list[str],
                        allow_cmd: str) -> None:
    """Refusal shown by both `mw build --install` and `mw bootstrap`."""
    shown = "\n".join(f"  {ln}" for ln in dirty[:5])
    if len(dirty) > 5:
        shown += f"\n  ...（另有 {len(dirty) - 5} 处）"
    print(
        f"[{label}] Error: 工作树有未提交改动，构建会把它编进 tracked 产物"
        f"（多会话共享 cwd 时多半属于别的会话）：\n{shown}\n"
        f"(共 {len(dirty)} 处；拦截面 {', '.join(paths)})\n"
        f"确认后重跑：{allow_cmd}",
        file=sys.stderr,
    )


def _bootstrap_dirty_guard(repo_root: pathlib.Path, allow_dirty: bool) -> bool:
    """False (after printing the refusal) when the root `npm run build` in
    `mw bootstrap` would compile uncommitted packages/*/src changes into the
    tracked dist trees. Non-git trees skip the check."""
    dirty = _git_dirty_paths(repo_root, _BOOTSTRAP_DIRTY_PATHS)
    if not dirty:
        return True
    if allow_dirty:
        print("[mw bootstrap] --allow-dirty: 已按脏树构建，产物可能含未提交源码", flush=True)
        return True
    _refuse_dirty_build("mw bootstrap", dirty, _BOOTSTRAP_DIRTY_PATHS,
                        "mw bootstrap --allow-dirty")
    return False


def cmd_build(args: argparse.Namespace) -> int:
    if args.install:
        allow_dirty = bool(getattr(args, "allow_dirty", False))
        dirty = _git_dirty_paths(_repo_root(), _BUILD_DIRTY_PATHS)
        if dirty and not allow_dirty:
            _refuse_dirty_build("mw build", dirty, _BUILD_DIRTY_PATHS,
                                "mw build --install --allow-dirty")
            return 1
        if dirty:
            print("[mw build] --allow-dirty: 已按脏树构建，产物可能含未提交源码")
    ok, msg = _build_bundle()
    if not ok:
        print(f"[mw build] Error: {msg}", file=sys.stderr)
        return 1
    print(f"[mw build] {msg}")
    print(f"[mw build] bundle: {_bundle_path()}")
    if args.install:
        rc = _deploy_bundle(no_dist=args.no_dist)
        if rc == 0:
            print("[mw build] Restart open pi windows to load the new bundle and dist.")
        return rc
    return 0


def _sync_dir(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Copy files from src into dst; only update files that exist in src. Keep dst-only files."""
    import shutil
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(target))


def _install_framework(
    project_dir: pathlib.Path,
    *,
    source: pathlib.Path,
    codex_scope: str = "project",
) -> tuple[bool, str]:
    """Install the AgenticTask framework into project_dir by invoking the
    installer bundled with the framework source (single source of truth). This
    lays down .claude/ + .agents/skills/agentic-task and writes .agentic-framework.
    Returns (ok, message)."""
    installer = source / "install.py"
    if not installer.is_file():
        return (
            False,
            f"AgenticTask framework not found at {source}. "
            "Run 'python mw.py pull-agentictask' to clone it from the remote repo first.",
        )
    cmd = [
        sys.executable,
        str(installer),
        str(project_dir),
        "--codex-scope",
        codex_scope,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "install.py failed").strip()
    return True, f"framework installed from {source}"


def cmd_init(args: argparse.Namespace) -> int:
    # AC-036: bundle must exist before creating any directories
    if not _check_bundle():
        print(
            f"[mw init] Error: Extension bundle not found at {_bundle_path()}\n"
            "Run 'bash packages/multi-workers/build-extension.sh' to build it first.",
            file=sys.stderr,
        )
        return 1

    project_dir = pathlib.Path(args.project).resolve()

    # AC-020: create directory structure
    (project_dir / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (project_dir / ".mw").mkdir(parents=True, exist_ok=True)
    (project_dir / ".pi" / "extensions").mkdir(parents=True, exist_ok=True)

    # Create placeholder files
    index_md = project_dir / ".agenticdoc" / "_index.md"
    if not index_md.exists():
        index_md.write_text("# AgenticTask Index\n\nactive: \n", encoding="utf-8")

    index_parallel = project_dir / ".agenticdoc" / "_index.parallel"
    if not index_parallel.exists():
        index_parallel.write_text("", encoding="utf-8")

    # Project goal is the north-star that every key/spec derives from. Seed a
    # `status: draft` skeleton so the goal brainstorm workflow (/goal) — or the
    # user editing it by hand — has something to fill in. Do NOT write real
    # content here: the goal must be co-created interactively, not fabricated.
    goal_md = project_dir / ".agenticdoc" / "goal.md"
    if not goal_md.exists():
        goal_md.write_text(
            "# Project Goal\n\n"
            "> status: draft\n"
            "> 项目总目标尚未确立。运行 /goal 与 Agent 对话共创，"
            "或直接编辑本文件填好三段内容后把 status 改为 active。\n\n"
            "## Goal\n\n"
            "<!-- 项目要达成的总目标：要构建/解决什么，核心交付是什么 -->\n\n"
            "## Context\n\n"
            "<!-- Agent 应知的上下文：技术栈、已有系统、相关约束 -->\n\n"
            "## Key Constraints\n\n"
            "<!-- 关键约束：性能要求、禁止的做法、测试规则等 -->\n",
            encoding="utf-8",
        )

    # AC-036: install Extension bundle — GLOBAL WINS.
    # The extension is normally installed globally by `mw setup` (~/.pi/agent/
    # extensions/), which loads for every project. A project-local copy would then
    # register the same tools a second time and the host rejects the load with a
    # "tool conflicts" error. So: only install locally when there is NO global copy,
    # and delete any stale local copy when a global one exists.
    global_bundle = _global_ext_dir() / "agent-team-loop.js"
    bundle_dst = project_dir / ".pi" / "extensions" / "agent-team-loop.js"
    if global_bundle.exists():
        if bundle_dst.exists():
            bundle_dst.unlink()
            print(f"[mw init] Removed redundant project-local extension (global install active): {bundle_dst}")
        else:
            print(f"[mw init] Using global extension install: {global_bundle}")
    else:
        shutil.copy2(str(_bundle_path()), str(bundle_dst))
        print(f"[mw init] Extension installed: {bundle_dst}")

    # Install the AgenticTask framework (.claude/ + .agents/skills/agentic-task)
    # by default so pi/codex can run the framework out of the box. Skippable
    # with --no-framework.
    #   - --sync-agentictask SOURCE overrides the install source with a local dir.
    #   - Otherwise _resolve_framework_source picks the freshest source: the mw
    #     checkout's own framework repo (dev machine), then the .tmp cache
    #     (auto-cloned once from the default remote so fresh machines work
    #     unattended).
    # Framework failure is a WARNING, not fatal: the bundle + mw service must still
    # come up so any project (even offline/unrelated) initializes cleanly.
    if not args.no_framework:
        source = _resolve_framework_source(args.sync_agentictask)
        ok, msg = _install_framework(project_dir, source=source, codex_scope=args.codex_scope)
        print(f"[mw init] {msg}" if ok else f"[mw init] Warning: {msg}", file=sys.stderr if not ok else None)

    print(f"[mw init] Project initialized: {project_dir}")
    return 0


# ── Subcommand: setup (one-time per machine) ───────────────────────────────────

def _global_ext_dir() -> pathlib.Path:
    """pi's global extensions dir (single source: mw_common.global_ext_dir)."""
    return mw_common.global_ext_dir()


def cmd_setup(args: argparse.Namespace) -> int:
    """Bootstrap the machine so ANY project auto-installs on pi launch:
    (1) cache the framework source, (2) install the extension bundle GLOBALLY so
    pi loads it in every project → its session_start auto-runs `mw init` per project."""
    # Rebuild first when asked (bash-free) so a single `mw setup --build` from any
    # window refreshes and deploys the bundle in one shot.
    if args.build:
        ok, msg = _build_bundle()
        if not ok:
            print(f"[mw setup] Error: build failed: {msg}", file=sys.stderr)
            return 1
        print(f"[mw setup] {msg}")

    if not _check_bundle():
        print(
            f"[mw setup] Error: Extension bundle not found at {_bundle_path()}\n"
            "Run 'python mw.py build' (or 'mw setup --build') to build it first.",
            file=sys.stderr,
        )
        return 1

    # (1) framework source cache (clone from remote URL, or copy from a local dir)
    ok, msg = _pull_agentictask(args.source, force=args.force, branch=args.branch)
    print(f"[mw setup] {msg}" if ok else f"[mw setup] Warning: pull failed: {msg}",
          file=sys.stderr if not ok else None)

    # (2) global extension install
    import shutil
    ext_dir = _global_ext_dir()
    ext_dir.mkdir(parents=True, exist_ok=True)
    ext_dst = ext_dir / "agent-team-loop.js"
    shutil.copy2(str(_bundle_path()), str(ext_dst))
    _write_mw_py_path()
    print(f"[mw setup] Extension installed globally: {ext_dst}")

    # (2b) /update-agentictask convenience command (reads the sidecar above;
    # failure is a warning — the core loop works without it).
    ok_u, msg_u = _agentictask_update_install()
    print(f"[mw setup] {msg_u}" if ok_u else f"[mw setup] Warning: {msg_u}",
          file=None if ok_u else sys.stderr)

    # (2c) goal.md loader + write gate (the repo template is the source of
    # truth; failure is a warning — the core loop works without it).
    ok_g, msg_g = _goal_gate_install()
    print(f"[mw setup] {msg_g}" if ok_g else f"[mw setup] Warning: {msg_g}",
          file=None if ok_g else sys.stderr)

    # (3) pin pi's shellPath when missing (fresh-machine shell bootstrap):
    # additive merge into ~/.pi/agent/settings.json — PowerShell detected via
    # PATH, mirroring pi's own resolution order. Never overwrites an existing
    # value; never rewrites a malformed file (mw_common.ensure_pi_shell_path).
    shell = mw_common.ensure_pi_shell_path(env=os.environ, fix=True)
    if shell["status"] in ("filled", "replaced"):
        print(f"[mw setup] pi shellPath {shell['status']}: {shell['shell_path']}")
    elif shell["status"] == "ok":
        print(f"[mw setup] pi shellPath already configured: {shell['shell_path']}")
    elif shell["status"] != "not-applicable":
        print(
            f"[mw setup] Warning: pi shellPath {shell['status']} — {shell['detail']}",
            file=sys.stderr,
        )
    print("[mw setup] Done — pi will now auto-init the agent-team loop in every project on launch.")
    return 0


# ── Subcommand: bootstrap (fresh-machine one-shot, steps 1-8) ─────────────────

# Fallback minimum node version when the root package.json engines.node is
# unreadable (kept in sync with package.json ">=22.19.0").
_NODE_MIN_FALLBACK = (22, 19, 0)


def _version_tuple(raw: str) -> tuple[int, int, int] | None:
    """"v22.19.0" / "22.19.0" → (22, 19, 0); unparseable → None."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _node_engine_min(repo_root: pathlib.Path) -> tuple[int, int, int]:
    """Minimum node version from the root package.json `engines.node` so the
    check never drifts from the declared requirement. Falls back to
    _NODE_MIN_FALLBACK when unreadable — bootstrap must not block on metadata."""
    try:
        data = json.loads((repo_root / "package.json").read_text(encoding="utf-8"))
        parsed = _version_tuple(str(data["engines"]["node"]))
        if parsed is not None:
            return parsed
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        pass
    return _NODE_MIN_FALLBACK


def _run_stream(cmd: list[str], *, cwd: pathlib.Path) -> bool:
    """Run a long child (npm/pip) with inherited stdio so progress streams to
    the console. cmd[0] must be a RESOLVED executable (shutil.which), never a
    bare name — Windows Popen does not apply PATHEXT resolution."""
    result = subprocess.run(cmd, cwd=str(cwd))  # noqa: S603 - resolved paths, list args, no shell
    return result.returncode == 0


def _npm_hydrate(target_root: pathlib.Path) -> bool:
    """Repo-standard dependency hydration: `npm ci --ignore-scripts` on a fresh
    tree, `npm install --ignore-scripts` when node_modules already exists.

    Single source of truth for the install vector shared by `mw bootstrap`
    step 2 and `mw worktree add` (design decision D-6) so the two can never
    drift. `--ignore-scripts` is a repo hard rule (lifecycle scripts need an
    explicit review). cmd[0] is a resolved executable because Windows Popen
    does not apply PATHEXT resolution.
    """
    npm = shutil.which("npm")
    if npm is None:
        return False
    target_root = pathlib.Path(target_root)
    install_cmd = [
        npm,
        "install" if (target_root / "node_modules").is_dir() else "ci",
        "--ignore-scripts",
    ]
    return _run_stream(install_cmd, cwd=target_root)


def _run_capture(cmd: list[str], *, timeout: float = 60.0) -> str | None:
    """Short child with captured stdout (version probes). None = failed."""
    try:
        result = subprocess.run(  # noqa: S603 - resolved paths, list args, no shell
            cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


# Fallback scoped name when packages/coding-agent/package.json is unreadable.
_PI_PKG_NAME_FALLBACK = "@earendil-works/pi-coding-agent"


def _pi_package_name(repo_root: pathlib.Path) -> str:
    """The pi package's scoped name, read from its own package.json (no drift)."""
    try:
        data = json.loads(
            (repo_root / "packages" / "coding-agent" / "package.json").read_text(encoding="utf-8")
        )
        name = data.get("name")
        if isinstance(name, str) and name:
            return name
    except (OSError, ValueError):
        pass
    return _PI_PKG_NAME_FALLBACK


def _global_pi_package_dir(npm: str, repo_root: pathlib.Path) -> pathlib.Path | None:
    """Where the global install of the pi package sits (`npm root -g`/<name>).
    None when npm fails or the dir is absent — the caller decides what that
    means (after npm link, the package must exist there)."""
    root_raw = _run_capture([npm, "root", "-g"])
    if not root_raw:
        return None
    pkg_dir = pathlib.Path(root_raw.strip()) / _pi_package_name(repo_root)
    return pkg_dir if pkg_dir.exists() else None


def _pi_link_target_ok(global_pkg: pathlib.Path, repo_pkg: pathlib.Path) -> bool:
    """True when the global package path resolves (realpath — junctions and
    symlinks included) to the repo's packages/coding-agent. This is what makes
    the global `pi` THIS fork rather than a leftover registry install of the
    official package (which lacks the timi provider and only fails later, at
    worker dispatch time)."""
    return os.path.normcase(os.path.realpath(global_pkg)) == os.path.normcase(
        os.path.realpath(repo_pkg)
    )


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Fresh-machine one-shot: everything from prerequisites to a running,
    doctor-verified service. Re-runnable: every step is idempotent or
    self-verifying.

      1. prerequisites: python >= 3.11, node >= engines.node, npm, git, and
         the credential-route status. Missing credentials do NOT abort a
         fresh install (~/.pi/agent/auth.json cannot exist yet): steps 2-6
         are credential-free, so bootstrap warns, skips the service start
         (step 7), and points at the --fast re-run for after credentials
         are configured
      2. node_modules: `npm ci --ignore-scripts` on a fresh clone,
         `npm install --ignore-scripts` when node_modules exists (incremental)
      3. repo build: root `npm run build` (tui→ai→…→coding-agent; the ai build
         fetches the models.dev catalog — network required)
      4. global `pi`: `npm link packages/coding-agent` — workers run
         `pi --provider timi` and the timi provider/models only exist in this
         fork, so the npm-registry pi cannot be used; verified via `pi --version`
      5. mw setup --build: extension bundle + global extension install +
         AgenticTask framework source cache
      6. mw init: per-project init (idempotent; .agenticdoc may already be
         committed) + framework install into .agents/ / .claude/
      7. mw start: background service (proxy + launcher + conductor), waiting
         for the PID file (serve runs its route precheck before writing it)
      8. mw doctor: full-chain verification

    --fast skips steps 2-3 for credential-fix re-runs (requires a previous
    full bootstrap); --no-start leaves the service down (the doctor verdict
    then tolerates the expected 'service not running' issue).
    """
    t0 = time.monotonic()
    repo_root = _repo_root()
    project_dir = (
        pathlib.Path(args.project).resolve() if args.project else repo_root
    )
    node_modules = repo_root / "node_modules"
    dist_cli = repo_root / "packages" / "coding-agent" / "dist" / "cli.js"

    def step(n: int, msg: str) -> None:
        print(f"[mw bootstrap] step {n}/8: {msg}", flush=True)

    def skip(n: int, msg: str) -> None:
        print(f"[mw bootstrap] step {n}/8: skipped ({msg})", flush=True)

    def fail(msg: str) -> int:
        print(f"[mw bootstrap] Error: {msg}", file=sys.stderr, flush=True)
        return 1

    if args.fast and not (node_modules.is_dir() and dist_cli.is_file()):
        return fail(
            "--fast needs a previous full bootstrap (node_modules + dist missing) — "
            "run without --fast first"
        )

    # 1. prerequisites
    step(1, "prerequisites (python, node, npm, git, credential route)")
    if sys.version_info < (3, 11):
        return fail(f"python >= 3.11 required (tomllib / fromisoformat), running {sys.version.split()[0]}")
    node = shutil.which("node")
    npm = shutil.which("npm")
    git = shutil.which("git")
    if node is None or npm is None:
        return fail("node/npm not found on PATH — install Node.js (see package.json engines.node)")
    if git is None:
        return fail("git not found on PATH — needed to clone the AgenticTask framework")
    node_raw = _run_capture([node, "--version"])
    node_ver = _version_tuple(node_raw) if node_raw else None
    if node_ver is None or node_ver < _node_engine_min(repo_root):
        return fail(
            f"node >= {'.'.join(map(str, _node_engine_min(repo_root)))} required "
            f"(package.json engines.node), running {node_raw or 'unknown'}"
        )
    providers_path = pathlib.Path(__file__).parent / "providers.json"
    config = mw_common.load_providers(providers_path)
    precheck = mw_common.route_precheck(config, os.environ)
    creds_missing = bool(precheck["all_missing"])
    if creds_missing:
        # Fresh machine: nothing is configured yet (~/.pi/agent/auth.json
        # does not exist). That must not block the install — steps 2-6 are
        # credential-free, pi windows open without the service, and the
        # service start (step 7) is skipped until credentials exist.
        print(
            "[mw bootstrap] Warning: no route has credentials yet (fresh install?)\n"
            "  Steps 2-6 proceed; the service start (step 7) will be skipped.\n"
            "  Configure later (the default worker route is timi):\n"
            "    set TIMI_API_KEY in your environment, or\n"
            "    write ~/.pi/agent/auth.json: {\"timi\": {\"key\": \"<key>\"}}\n"
            "  Then start the service: python mw.py bootstrap --fast\n"
            "  (pi windows and /mw commands work without the service)",
            flush=True,
        )
    else:
        available = ", ".join(
            r["route"] for r in precheck["routes"] if r["available"]
        )
        print(
            f"[mw bootstrap] python {sys.version.split()[0]}, node {node_raw}, "
            f"git ok; credential routes available: {available}",
            flush=True,
        )
    try:
        import yaml  # noqa: F401 - availability probe for target.yml (dual-workspace)
    except ImportError:
        print("[mw bootstrap] PyYAML missing — attempting pip install (dual-workspace target.yml)", flush=True)
        if not _run_stream([sys.executable, "-m", "pip", "install", "pyyaml"], cwd=repo_root):
            print(
                "[mw bootstrap] Warning: pip install pyyaml failed — dual-workspace "
                "target.yml stays disabled; single-mode works without it",
                flush=True,
            )

    # 2. node_modules
    if args.fast:
        skip(2, "--fast")
    else:
        step(2, "npm ci/install --ignore-scripts")
        if not _npm_hydrate(repo_root):
            return fail("npm install failed — see the output above")

    # 3. repo build (all packages, dependency order)
    if args.fast:
        skip(3, "--fast")
    else:
        step(3, "npm run build (root; the ai build fetches models.dev — network required)")
        if not _bootstrap_dirty_guard(repo_root, bool(getattr(args, "allow_dirty", False))):
            return 1
        if not _run_stream([npm, "run", "build"], cwd=repo_root):
            return fail("repo build failed — see the output above")

    # 4. global pi link (the runtime must be THIS fork: timi provider lives here)
    step(4, "npm link packages/coding-agent (global pi = this repo)")
    if not _run_stream([npm, "link"], cwd=repo_root / "packages" / "coding-agent"):
        return fail("npm link failed — see the output above")
    pi_bin = shutil.which("pi")
    if pi_bin is None:
        return fail("pi not on PATH after npm link")
    # The global pi must BE this fork, not just any pi: a machine that
    # previously installed the official package from the npm registry must
    # not silently keep running it (no timi provider — workers would only
    # fail later, at dispatch time, far away from the real cause).
    repo_pkg = repo_root / "packages" / "coding-agent"
    global_pkg = _global_pi_package_dir(npm, repo_root)
    if global_pkg is None:
        return fail(
            "global pi package not found via 'npm root -g' — npm link did not "
            f"install {_pi_package_name(repo_root)} globally"
        )
    if not _pi_link_target_ok(global_pkg, repo_pkg):
        return fail(
            f"global pi is not linked to this repo: {global_pkg} does not resolve "
            f"to {repo_pkg}. It is likely a registry install of the official "
            "package (no timi provider). Fix: "
            f"npm uninstall -g {_pi_package_name(repo_root)} && re-run bootstrap"
        )
    pi_ver = _run_capture([pi_bin, "--version"])
    if pi_ver is None:
        return fail(f"pi --version failed at {pi_bin} — is packages/coding-agent/dist built?")
    print(f"[mw bootstrap] pi on PATH: {pi_bin} ({pi_ver})", flush=True)

    # 5. machine setup: bundle + global extension + framework source cache
    step(5, "mw setup --build (extension bundle, global install, framework cache)")
    setup_args = argparse.Namespace(
        build=True, source=args.source, branch=args.branch, force=False,
    )
    if cmd_setup(setup_args) != 0:
        return fail("mw setup failed — see the output above")

    # 6. project init (idempotent; global extension wins over a local copy)
    step(6, f"mw init {project_dir}")
    init_args = argparse.Namespace(
        project=str(project_dir), no_framework=False, codex_scope="project",
        sync_agentictask=None,
    )
    if cmd_init(init_args) != 0:
        return fail("mw init failed — see the output above")
    if not (project_dir / ".agents" / "skills" / "agentic-task" / "SKILL.md").is_file():
        print(
            "[mw bootstrap] Warning: AgenticTask framework not installed — the "
            "/agentic PM workflow is unavailable (workers still dispatch). "
            "Check the mw setup / mw init messages above.",
            flush=True,
        )

    # 7. service start (background proxy + launcher + conductor)
    pid_path = _pid_path(project_dir)
    if args.no_start:
        skip(7, "--no-start; start later with: python mw.py start --project <dir>")
    elif _check_pid(pid_path) is not None:
        skip(7, f"already running (PID {_check_pid(pid_path)})")
    elif creds_missing:
        skip(
            7,
            "no credential route configured — set TIMI_API_KEY or write "
            "~/.pi/agent/auth.json, then: python mw.py bootstrap --fast",
        )
    else:
        step(7, "mw start (background service: proxy + launcher + conductor)")
        start_args = argparse.Namespace(
            project=str(project_dir), pi_port=7001, claude_port=7003,
            deepseek_port=None, poll_interval=5, max_workers=None, providers=None,
        )
        if cmd_start(start_args) != 0:
            return fail("mw start failed — see the output above")
        # serve runs its route precheck BEFORE writing the PID file, so "PID
        # file exists" implies "service actually started" (cmd_serve contract)
        for _ in range(60):
            time.sleep(0.5)
            if _check_pid(pid_path) is not None:
                break
        pid = _check_pid(pid_path)
        if pid is None:
            return fail(
                "service did not come up within 30s — inspect "
                f"{project_dir / '.mw' / 'mw.log'}"
            )
        print(f"[mw bootstrap] service running (PID {pid})", flush=True)

    # 8. full-chain verification
    step(8, "mw doctor (full-chain verification)")
    report = mw_common.doctor_report(
        project_dir, fix=False, config=config, stale_after_sec=90,
    )
    report["conductor"] = _ap_conductor.conductor_status(project_dir)
    print(mw_common.format_doctor_text(report))
    issues = list(report["summary"]["issues"])
    if args.no_start or creds_missing:
        # Expected by construction — do not fail the verdict for what was
        # asked (--no-start) or for the documented fresh-install path
        # (credentials configured after bootstrap; service starts on the
        # --fast re-run).
        issues = [i for i in issues if "mw service not running" not in i]
    timi_missing = [
        r for r in precheck["routes"] if r["route"] == "timi" and not r["available"]
    ]
    if timi_missing:
        action = (
            "Configure it, then: python mw.py bootstrap --fast"
            if creds_missing
            else "Set it and restart: python mw.py stop --project <dir> && "
                 "python mw.py bootstrap --fast"
        )
        print(
            "[mw bootstrap] Warning: TIMI_API_KEY is not set — pi workers "
            f"(the default dispatch route) cannot run. {action}",
            flush=True,
        )
    elapsed = int(time.monotonic() - t0)
    if issues:
        print(f"[mw bootstrap] finished with {len(issues)} issue(s) in {elapsed}s", flush=True)
        return 1
    print(f"[mw bootstrap] done in {elapsed}s", flush=True)
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

# ── Subcommand: update-env (UPDATE.md §3/§4 as a tool) ─────────────────────

# Adapter dirs install.py copies from <framework>/claude/ into <project>/.claude/
# (mirror of CLAUDE_DIRS in the framework's install.py / diff-installed.py).
_CLAUDE_ADAPTER_DIRS = ("commands", "agents", "skills", "scripts")
_UPDATE_ENV_SKIP_DIRS = ("__pycache__", "dist", ".tmp", "test")
_UPDATE_ENV_MARKS = {"ok": "  ok ", "stale": "STALE", "warn": "WARN ", "info": "info ", "skip": "skip "}


def _ts(mtime: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))


def _newest_file_mtime(root: pathlib.Path) -> float | None:
    """Newest file mtime under root (seconds), or None when it holds no files."""
    newest: float | None = None
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        m = f.stat().st_mtime
        newest = m if newest is None else max(newest, m)
    return newest


def _runtime_code_files(root: pathlib.Path | None = None) -> list[pathlib.Path]:
    """The serve's runtime code set: *.py|*.json under the tree, skipping
    __pycache__/dist/.tmp and any `test`/`test_*`/`_*` entry. One definition
    shared by the mtime baseline and the content digest, so "what counts as
    code" cannot drift between the two judges."""
    tree = pathlib.Path(root) if root is not None else _SCRIPT_DIR
    out: list[pathlib.Path] = []
    for f in tree.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(tree)
        except ValueError:
            continue
        if any(part in _UPDATE_ENV_SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if f.suffix not in _RUNTIME_CODE_SUFFIXES:
            continue
        if f.name.startswith("test_") or f.name.startswith("_"):
            continue
        out.append(f)
    return out


def _mw_code_newest_mtime(root: pathlib.Path | None = None) -> float | None:
    """Staleness baseline for a running serve — the Python mirror of the TS
    side's mwCodeNewestMtimeMs: only runtime code (*.py|*.json), skipping
    __pycache__/dist/.tmp/test and test_*/_* files. `.tmp` is excluded on both
    sides (the framework cache is not serve runtime code), and `test` is
    excluded because 69% of the input files under this tree are fixtures —
    editing a fixture must not turn a healthy serve stale. `root` defaults to
    the checker's own tree; identity comparison always passes the meta tree."""
    newest: float | None = None
    for f in _runtime_code_files(root):
        try:
            m = f.stat().st_mtime
        except OSError:
            continue
        newest = m if newest is None else max(newest, m)
    return newest


def _runtime_digest(root: pathlib.Path | None = None) -> str | None:
    """sha256 over the runtime file set: sorted relative posix path + NUL +
    raw bytes. Paths are in the digest (so delete/rename is visible where
    mtime is blind); mtimes are NOT (a `touch` must not read as drift).
    Cross-language contract: the TS mirror, if it grows one, must produce the
    identical string. None when the set is empty/unreadable (fail-open)."""
    tree = pathlib.Path(root) if root is not None else _SCRIPT_DIR
    files = _runtime_code_files(tree)
    if not files:
        return None
    h = hashlib.sha256()
    try:
        for f in sorted(files, key=lambda p: p.relative_to(tree).as_posix()):
            h.update(f.relative_to(tree).as_posix().encode("utf-8"))
            h.update(b"\0")
            h.update(f.read_bytes())
    except OSError:
        return None
    return "sha256:" + h.hexdigest()


def _resolve_git_dir(start: pathlib.Path) -> pathlib.Path | None:
    """Ascend from `start` to the containing `.git`, following a `gitdir:`
    file (linked worktree) when present. Pure file reads, no git binary."""
    try:
        cur = pathlib.Path(start).resolve()
    except OSError:
        return None
    for candidate in (cur, *cur.parents):
        dotgit = candidate / ".git"
        if dotgit.is_dir():
            return dotgit
        if dotgit.is_file():
            try:
                text = dotgit.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                return None
            if not text.lower().startswith("gitdir:"):
                return None
            target = text.split(":", 1)[1].strip()
            path = pathlib.Path(target)
            if not path.is_absolute():
                path = (dotgit.parent / path).resolve()
            return path
    return None


def _common_git_dir(git_dir: pathlib.Path) -> pathlib.Path | None:
    """The `commondir` target (linked worktrees keep `packed-refs` there)."""
    try:
        text = (git_dir / "commondir").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    candidate = pathlib.Path(text)
    if not candidate.is_absolute():
        candidate = (git_dir / candidate).resolve()
    return candidate


def _packed_ref_oid(packed: pathlib.Path, ref: str) -> str | None:
    try:
        text = packed.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "^")):
            continue
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref and re.fullmatch(r"[0-9a-fA-F]{40}", parts[0]):
            return parts[0].lower()
    return None


def _head_oid_from_git_dir(git_dir: pathlib.Path) -> str | None:
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if re.fullmatch(r"[0-9a-fA-F]{40}", head):
        return head.lower()  # detached HEAD
    if not head.startswith("ref:"):
        return None
    ref = head.split(":", 1)[1].strip()
    roots = [git_dir]
    common = _common_git_dir(git_dir)
    if common is not None and common != git_dir:
        roots.append(common)
    for root in roots:
        try:
            loose = root.joinpath(*ref.split("/")).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if re.fullmatch(r"[0-9a-fA-F]{40}", loose):
            return loose.lower()
    for root in roots:
        oid = _packed_ref_oid(root / "packed-refs", ref)
        if oid:
            return oid
    return None


def _git_head_oid(code_dir: pathlib.Path) -> str | None:
    """Full 40-hex HEAD OID, comparable across writers.

    Must NOT use `_git_head_short`: `rev-parse --short` returns a length that
    varies with the object database (9 hex here vs 40 for a file read), so a
    short form can never equal a full OID — reusing it would make every
    comparison a permanent false drift. Pure file read first (no spawn), git
    as a timeout-guarded fallback, None when neither works (fail-open)."""
    git_dir = _resolve_git_dir(pathlib.Path(code_dir))
    if git_dir is not None:
        oid = _head_oid_from_git_dir(git_dir)
        if oid:
            return oid
    r = _git(["rev-parse", "HEAD"], cwd=pathlib.Path(code_dir), timeout=_GIT_TIMEOUT_SEC)
    if r is not None and r.returncode == 0:
        oid = r.stdout.strip()
        if re.fullmatch(r"[0-9a-fA-F]{40}", oid):
            return oid.lower()
    return None


def _git_dirty_counts(repo: pathlib.Path) -> tuple[int, int] | None:
    """(tracked_changes, untracked_files) or None when git is unavailable,
    times out, or exits non-zero. Deliberately distinct from `_git_dirty`:
    that one reports (0, 0) on failure, which is fine for its callers but
    wrong for identity — "unknown" must not read as "clean"."""
    r = _git(["status", "--porcelain"], cwd=pathlib.Path(repo), timeout=_GIT_TIMEOUT_SEC)
    if r is None or r.returncode != 0:
        return None
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    tracked = sum(1 for ln in lines if not ln.startswith("??"))
    return (tracked, len(lines) - tracked)


def _read_serve_meta(project_dir: pathlib.Path) -> dict:
    """serve.meta as a dict, tolerating absence, unreadable files, and the
    half-written JSON an older non-atomic writer could leave behind."""
    try:
        data = json.loads(_serve_meta_path(project_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _same_path(a: object, b: object) -> bool:
    try:
        return os.path.normcase(str(pathlib.Path(str(a)).resolve())) == os.path.normcase(
            str(pathlib.Path(str(b)).resolve())
        )
    except OSError:
        return False


def _iso_ms(ms: float | None) -> str:
    if ms is None:
        return "?"
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ms / 1000))


def _fmt_duration(sec: float) -> str:
    total = int(max(0, sec))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d{hours}h{minutes}m"
    if hours:
        return f"{hours}h{minutes}m"
    return f"{minutes}m"


def serve_code_verdict(
    project_dir: pathlib.Path,
    *,
    checker_dir: pathlib.Path | None = None,
    fallback_started_ms: float | None = None,
) -> dict:
    """Classify whether the running serve's code is the disk's code (AC-005).

    Decision order: content (digest — authoritative; mtime only for legacy
    meta) -> commit (legacy meta only, the AC-005 literal) -> capability
    (`meta.schema < SERVE_META_SCHEMA` = "must restart") -> undecidable. The
    baseline tree is always `meta.code_dir`, never the checker's own tree
    (`same_tree=False` makes `capability` unknown instead of guessed). Never
    raises and never alerts on missing fields (fail-open).
    """
    project_dir = pathlib.Path(project_dir)
    checker = pathlib.Path(checker_dir) if checker_dir is not None else _SCRIPT_DIR
    meta = _read_serve_meta(project_dir)
    started_ms = _as_int(meta.get("started_at_ms"))
    if started_ms is None and fallback_started_ms is not None:
        started_ms = int(fallback_started_ms)
    code_dir_raw = meta.get("code_dir")
    tree = pathlib.Path(code_dir_raw) if isinstance(code_dir_raw, str) and code_dir_raw else checker
    same_tree = _same_path(tree, checker)
    expected_digest = meta.get("code_digest") if isinstance(meta.get("code_digest"), str) else None
    expected_commit = meta.get("commit") if isinstance(meta.get("commit"), str) else None
    schema = _as_int(meta.get("schema")) or 0
    result: dict = {
        "verdict": "undecidable",
        "reason": None,
        "restart_required": False,
        "tree": str(tree),
        "checker_tree": str(checker),
        "same_tree": same_tree,
        "serve_pid": _as_int(meta.get("pid")),
        "schema": schema,
        "expected_schema": SERVE_META_SCHEMA,
        "started_at_ms": started_ms,
        "base_ms": None,
        "code_mtime_ms": None,
        "drift_age_s": None,
        "upper_bound": False,
        "expected_commit": expected_commit,
        "actual_commit": None,
        "expected_digest": expected_digest,
        "actual_digest": None,
        "dirty_tracked": _as_int(meta.get("dirty_tracked")),
        "dirty_untracked": _as_int(meta.get("dirty_untracked")),
        "version": meta.get("version") if isinstance(meta.get("version"), str) else "",
        "detail": "",
        "fix": "/mw restart",
    }
    if not meta:
        result["reason"] = "meta-missing"
        result["detail"] = _serve_code_detail(result)
        return result
    if not tree.is_dir():
        result["reason"] = "code-dir-missing"
        result["detail"] = _serve_code_detail(result)
        return result
    base_ms = _as_int(meta.get("code_mtime_ms")) or started_ms
    result["base_ms"] = base_ms
    if base_ms is None:
        result["reason"] = "no-baseline"
        result["detail"] = _serve_code_detail(result)
        return result

    newest = _mw_code_newest_mtime(tree)
    mtime_ms = None if newest is None else int(newest * 1000)
    digest_now = _runtime_digest(tree)
    commit_now = _git_head_oid(tree)
    result["code_mtime_ms"] = mtime_ms
    result["actual_digest"] = digest_now
    result["actual_commit"] = commit_now

    if expected_digest is not None:
        content_changed = digest_now != expected_digest
    else:
        content_changed = mtime_ms is not None and mtime_ms > base_ms + _SERVE_META_MTIME_SLACK_MS
    commit_moved = bool(expected_commit and commit_now and expected_commit != commit_now)
    capability = (schema >= SERVE_META_SCHEMA) if same_tree else None
    now_ms = int(time.time() * 1000)

    if content_changed:
        since = mtime_ms if mtime_ms is not None else base_ms
        result.update(
            verdict="drift",
            reason="content-changed",
            drift_age_s=max(0, (now_ms - since) // 1000),
            upper_bound=mtime_ms is None,
        )
    elif commit_moved and expected_digest is None and capability is not False:
        result.update(
            verdict="drift",
            reason="head-moved",
            drift_age_s=max(0, (now_ms - base_ms) // 1000),
            upper_bound=True,
        )
    if result["verdict"] != "drift" and capability is False:
        result.update(
            verdict="drift",
            reason="schema-stale",
            drift_age_s=max(0, (now_ms - base_ms) // 1000),
            upper_bound=True,
        )
    if result["verdict"] == "drift":
        result["restart_required"] = True
    elif commit_moved:
        result["verdict"] = "history-only"
        result["reason"] = "head-moved"
    elif digest_now is None or mtime_ms is None:
        result["verdict"] = "undecidable"
        result["reason"] = "tree-unreadable"
    else:
        result["verdict"] = "fresh"
        result["reason"] = None
    result["detail"] = _serve_code_detail(result)
    return result


def _serve_code_detail(v: dict) -> str:
    """One-line, grep-stable status/detail string. Contains every required
    element: expected/actual commit, drift duration, mtime pair, and the fix."""
    exp = v["expected_commit"] or "(unavailable)"
    act = v["actual_commit"] or "(unavailable)"
    digest = v["actual_digest"]
    digest_short = digest[7:19] if isinstance(digest, str) and digest.startswith("sha256:") else "(unavailable)"
    dirty = (
        "n/a"
        if v["dirty_tracked"] is None
        else f"{v['dirty_tracked']}/{v['dirty_untracked']}"
    )
    age = v["drift_age_s"]
    age_txt = "-" if age is None else (">=" if v["upper_bound"] else "") + _fmt_duration(age)
    if v["verdict"] == "drift":
        head = {
            "content-changed": "STALE CODE (content changed)",
            "head-moved": "STALE CODE (head moved)",
            "schema-stale": "CAPABILITY DRIFT (schema older than checker)",
        }.get(v["reason"], "STALE CODE")
    elif v["verdict"] == "history-only":
        head = "fresh (history-only)"
    elif v["verdict"] == "undecidable":
        head = f"unverifiable ({v['reason']})"
    else:
        head = "fresh"
    return (
        f"{head}: tree={v['tree']} schema={v['schema']}/{v['expected_schema']} "
        f"serve_pid={v['serve_pid']} started={_iso_ms(v['started_at_ms'])} "
        f"code newest mtime={_iso_ms(v['code_mtime_ms'])} (base={_iso_ms(v['base_ms'])}) "
        f"expected commit={exp} actual commit={act} drift_age={age_txt} "
        f"dirty_at_start={dirty} version={v['version'] or '?'} digest={digest_short} fix: {v['fix']}"
    )


def _format_serve_identity(identity: dict) -> str:
    """One startup line for .mw/mw.log: the identity the serve was stamped
    with (mw.log is append-only across sessions, unlike conductor.log)."""
    digest = identity.get("code_digest")
    digest_short = digest[7:19] if isinstance(digest, str) and digest.startswith("sha256:") else "unavailable"
    dirty = (
        "n/a"
        if identity.get("dirty_tracked") is None
        else f"{identity['dirty_tracked']}/{identity['dirty_untracked']}"
    )
    return (
        f"commit={identity.get('commit') or 'unavailable'} "
        f"version={identity.get('version') or '?'} schema={identity.get('schema')} "
        f"mtime={_iso_ms(identity.get('code_mtime_ms'))} digest={digest_short} dirty={dirty}"
    )


def _report_serve_code_drift(project_dir: pathlib.Path, seen: set) -> None:
    """One drift comparison for the serve loop: stderr (-> .mw/mw.log) +
    timeline `config`, rate-limited by `(code_dir, meta_commit, head_commit,
    serve_pid)` — i.e. once per drift per serve lifetime. Python never
    auto-restarts (the TS side owns interactive restart). Never raises: a
    tick must not be able to kill serve."""
    try:
        verdict = serve_code_verdict(project_dir)
        if verdict["verdict"] != "drift":
            return
        key = (
            str(verdict["tree"]),
            verdict["expected_commit"] or "-",
            verdict["actual_commit"] or "-",
            verdict["serve_pid"],
        )
        if key in seen:
            return
        seen.add(key)
        # Both channels carry the identical `detail` (the timeline is the
        # persistent record; stderr is the live one).
        print(f"[mw serve] {verdict['detail']}", file=sys.stderr, flush=True)
        _ap_timeline.Timeline(_ap_timeline.timeline_path(project_dir)).append(
            "config", detail=verdict["detail"]
        )
    except Exception:  # noqa: BLE001 - the serve loop must survive any check failure
        pass


def _serve_code_doctor_section(project_dir: pathlib.Path) -> dict:
    """`mw doctor` section for AC-005 (verdict/fields/fix)."""
    pid = _check_pid(_pid_path(project_dir))
    if pid is None:
        return {
            "running": False,
            "verdict": "n/a",
            "reason": "not-running",
            "restart_required": False,
            "tree": None,
            "schema": None,
            "expected_schema": SERVE_META_SCHEMA,
            "commit_expected": None,
            "commit_actual": None,
            "code_mtime_ms": None,
            "base_ms": None,
            "drift_age_s": None,
            "digest_expected": None,
            "digest_actual": None,
            "dirty_tracked": None,
            "dirty_untracked": None,
            "detail": "serve not running",
            "fix": "/mw restart",
        }
    v = serve_code_verdict(project_dir)
    return {
        "running": True,
        "verdict": v["verdict"],
        "reason": v["reason"],
        "restart_required": v["restart_required"],
        "tree": v["tree"],
        "schema": v["schema"],
        "expected_schema": v["expected_schema"],
        "commit_expected": v["expected_commit"],
        "commit_actual": v["actual_commit"],
        "code_mtime_ms": v["code_mtime_ms"],
        "base_ms": v["base_ms"],
        "drift_age_s": v["drift_age_s"],
        "digest_expected": v["expected_digest"],
        "digest_actual": v["actual_digest"],
        "dirty_tracked": v["dirty_tracked"],
        "dirty_untracked": v["dirty_untracked"],
        "detail": v["detail"],
        "fix": v["fix"],
        "identity_mismatch": _serve_identity_mismatch(project_dir, pid),
    }


def _serve_identity_mismatch(project_dir: pathlib.Path, pid: int) -> str | None:
    """Optional OS-probe cross-check of `meta.started_at_ms` (state face only).

    Catches a leftover meta / recycled PID: the process the PID file names may
    not be the process the meta describes. Informational — never an alarm
    (PID reuse and clock skew are real false-positive sources)."""
    started = _as_int(_read_serve_meta(project_dir).get("started_at_ms"))
    if started is None:
        return None
    os_start = process_start_ms(pid)
    if os_start is None or abs(os_start - started) <= 60_000:
        return None
    return (
        f"serve identity mismatch (PID {pid} started {_iso_ms(os_start)} but "
        f"serve.meta says {_iso_ms(started)}) - possible leftover meta or recycled PID"
    )


def process_start_ms(pid: int) -> int | None:
    """OS-reported process start time (epoch ms), independent of serve.meta.

    Optional +1 probe (design C9/E): cross-checks `meta.started_at_ms` to catch
    a leftover meta / recycled PID. Windows via ctypes GetProcessTimes (the
    same precedent as mw_common._is_alive_win32); POSIX via /proc/<pid>/stat.
    Returns None whenever the platform path cannot answer.
    """
    if pid <= 0:
        return None
    if sys.platform == "win32":
        import ctypes
        import ctypes.wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creation = ctypes.wintypes.FILETIME()
            exit_t = ctypes.wintypes.FILETIME()
            kernel_t = ctypes.wintypes.FILETIME()
            user_t = ctypes.wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_t),
                ctypes.byref(kernel_t),
                ctypes.byref(user_t),
            ):
                return None
            ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return ticks // 10_000 - 11_644_473_600_000  # 1601-01-01 -> epoch
        finally:
            kernel32.CloseHandle(handle)
    try:
        stat = pathlib.Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        after = stat.rsplit(")", 1)[1].split()
        start_ticks = int(after[19])
        btime = 0
        for line in pathlib.Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                btime = int(line.split()[1])
                break
        hz = os.sysconf("SC_CLK_TCK")
        return btime * 1000 + int(start_ticks * 1000 / hz)
    except (OSError, ValueError, IndexError):
        return None


def _update_git_counts(repo: pathlib.Path) -> dict | None:
    """(behind, ahead) of HEAD vs origin/<default branch> using LOCAL refs —
    no network. None when the repo or the origin ref is unavailable."""
    if not (repo / ".git").exists():
        return None

    def _count(rev: str) -> int | None:
        r = _git(["rev-list", "--count", rev], cwd=repo)
        if r.returncode != 0:
            return None
        try:
            return int(r.stdout.strip())
        except ValueError:
            return None

    origin_ref = f"origin/{_DEFAULT_AGENTICTASK_BRANCH}"
    behind = _count(f"HEAD..{origin_ref}")
    ahead = _count(f"{origin_ref}..HEAD")
    if behind is None or ahead is None:
        return None
    return {"behind": behind, "ahead": ahead}


def _git_dirty(repo: pathlib.Path) -> tuple[int, int]:
    """(tracked_changes, untracked_files) via git status --porcelain.
    Tracked changes are real uncommitted state installs would propagate;
    untracked strays are only reported, never flagged."""
    r = _git(["status", "--porcelain"], cwd=repo)
    if r.returncode != 0:
        return (0, 0)
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    tracked = sum(1 for ln in lines if not ln.startswith("??"))
    return (tracked, len(lines) - tracked)


def _git_head_short(repo: pathlib.Path) -> str | None:
    r = _git(["rev-parse", "--short", "HEAD"], cwd=repo)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _claude_adapter_drift(project_dir: pathlib.Path, source: pathlib.Path) -> int:
    """Count of files that differ or are missing on either side between
    <source>/claude/{commands,agents,skills,scripts} and <project>/.claude/
    (mirror of diff-installed.py's comparison; __pycache__/.pyc ignored)."""
    diff = 0
    for sub in _CLAUDE_ADAPTER_DIRS:
        src_root = source / "claude" / sub
        dst_root = project_dir / ".claude" / sub
        rels: set[str] = set()
        for root in (src_root, dst_root):
            if not root.is_dir():
                continue
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                rel = p.relative_to(root)
                if "__pycache__" in rel.parts or p.suffix in (".pyc", ".pyo"):
                    continue
                rels.add(rel.as_posix())
        for rel in sorted(rels):
            s, d = src_root / rel, dst_root / rel
            if not s.is_file() or not d.is_file() or s.read_bytes() != d.read_bytes():
                diff += 1
    return diff


def _read_framework_manifest(project_dir: pathlib.Path) -> dict[str, str]:
    """Parse <project>/.agentic-framework key=value lines (written by install.py)."""
    manifest: dict[str, str] = {}
    p = project_dir / ".agentic-framework"
    if not p.is_file():
        return manifest
    for line in p.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            manifest[key.strip()] = value.strip()
    return manifest


def _resolve_framework_source_readonly() -> pathlib.Path | None:
    """Source resolution for checks — unlike _resolve_framework_source this
    never auto-clones (no network, no prints): checkout repo > .tmp cache."""
    checkout = _checkout_framework_dir()
    if (checkout / "install.py").is_file():
        return checkout
    if (_TMP_AGENTICTASK / "install.py").is_file():
        return _TMP_AGENTICTASK
    return None


def _check_update_env(project_dir: pathlib.Path) -> dict:
    """All anchor checks from UPDATE.md §1 (A1-A8 + legacy patterns) as a
    machine-readable report. Pure reads — no network, no side effects."""
    checks: list[dict] = []

    def add(cid: str, layer: str, status: str, detail: str, fix: str = "", *, auto: bool = False) -> None:
        checks.append({"id": cid, "layer": layer, "status": status,
                       "detail": detail, "fix": fix, "auto": auto})

    initialized = (project_dir / ".agenticdoc").is_dir()
    source = _resolve_framework_source_readonly()

    # ── machine layer ──

    # A1 extension bundle (same comparison as doctor's bundle section)
    b = mw_common._doctor_bundle()
    if not b.get("available"):
        add("bundle", "machine", "warn", f"全局扩展 bundle 缺失: {b.get('note', '')}",
            "python mw.py setup（manual）")
    elif b.get("stale") is None:
        add("bundle", "machine", "info",
            f"bundle {b.get('global_bundle_mtime', '?')}（源不可比: {b.get('note', '')}）")
    elif b["stale"]:
        add("bundle", "machine", "stale",
            f"全局 bundle {b['global_bundle_mtime']} 早于源码 {b['source_newest_mtime']}",
            "重建+全局重装 bundle，随后重启 pi 窗口", auto=True)
    else:
        add("bundle", "machine", "ok",
            f"bundle {b['global_bundle_mtime']} ≥ 源码最新 {b['source_newest_mtime']}")

    # A1b repo bundle content (AC-009(b)/(c)): the tracked repo bundle's
    # GATE_KINDS set and guard behaviour markers vs the status-model source.
    # The A1/A2 mtime anchors cannot see a content-stale bundle at all.
    rb = mw_common.repo_bundle_anchor()
    rb_detail = str(rb.get("detail", ""))
    if rb.get("stale") is None:
        add("repo-bundle", "machine", "info", f"无法判定: {rb_detail}",
            "确认是完整检出（packages/multi-workers/dist + status-model.ts）")
    elif rb["stale"]:
        add("repo-bundle", "machine", "stale", rb_detail,
            "mw build（重建 repo bundle → 全局重装 → 重建 coding-agent dist），随后重启 pi 窗口",
            auto=True)
    else:
        add("repo-bundle", "machine", "ok", rb_detail)

    # A2b coding-agent dist content (AC-009(c)): every tracked *.map embeds its
    # source (inlineSources), so sourcesContent drift is detectable with no build.
    sd = mw_common.sourcemap_drift()
    sd_detail = str(sd.get("detail", ""))
    if sd.get("stale") is None:
        add("pi-dist-content", "machine", "skip", f"无法判定: {sd_detail}")
    elif sd["stale"]:
        add("pi-dist-content", "machine", "stale", sd_detail,
            "mw build --install（重建 coding-agent dist），随后重启 pi 窗口",
            auto=True)
    else:
        add("pi-dist-content", "machine", "ok", sd_detail)

    # A2 pi dist (coarse mtime heuristic; the npm-linked global pi runs from here)
    dist_dir = _repo_root() / "packages" / "coding-agent" / "dist"
    src_dir = _repo_root() / "packages" / "coding-agent" / "src"
    if dist_dir.is_dir() and src_dir.is_dir():
        dist_new = _newest_file_mtime(dist_dir)
        src_new = _newest_file_mtime(src_dir)
        if dist_new is None or src_new is None:
            add("pi-dist", "machine", "info", "dist 或 src 为空，跳过比较")
        elif src_new > dist_new + 2.0:
            add("pi-dist", "machine", "stale",
                f"dist {_ts(dist_new)} 早于 src {_ts(src_new)}（粗粒度启发式）",
                "mw build --install（含 dist 重建），随后重启 pi 窗口", auto=True)
        else:
            add("pi-dist", "machine", "ok", f"dist {_ts(dist_new)} ≥ src 最新 {_ts(src_new)}")
    else:
        add("pi-dist", "machine", "skip", "无 dist/src（非完整检出）")

    # A4 framework source repo (the live working repo on a dev machine)
    checkout = _checkout_framework_dir()
    if (checkout / "install.py").is_file():
        tracked, untracked = _git_dirty(checkout)
        counts = _update_git_counts(checkout)
        unpushed = counts["ahead"] if counts else 0
        parts = []
        if unpushed:
            parts.append(f"未推送 commit ×{unpushed}")
        if tracked:
            parts.append(f"未提交变更 ×{tracked}")
        if untracked:
            parts.append(f"未跟踪文件 ×{untracked}")
        if unpushed or tracked:
            add("framework-source", "machine", "warn",
                "；".join(parts) + " — 本机安装会携带未发布状态，他机/克隆需 push 后才可同步",
                "git commit + push（发布）")
        else:
            extra = f"，未跟踪文件 ×{untracked}" if untracked else ""
            add("framework-source", "machine", "ok",
                f"干净且已推送（HEAD {_git_head_short(checkout) or '?'}）{extra}")
    else:
        add("framework-source", "machine", "skip", "检出仓无框架目录（源解析落到 .tmp 缓存）")

    # A5 .tmp framework cache (bootstrap fallback source)
    if (_TMP_AGENTICTASK / ".git").exists():
        counts = _update_git_counts(_TMP_AGENTICTASK)
        if counts is None:
            add("tmp-cache", "machine", "warn", "缓存无 origin/master 引用（未 fetch 或非克隆）",
                "python mw.py pull-agentictask")
        elif counts["behind"] > 0 and counts["ahead"] == 0:
            add("tmp-cache", "machine", "stale",
                f".tmp 缓存落后 origin/{_DEFAULT_AGENTICTASK_BRANCH} {counts['behind']} commit",
                "python mw.py pull-agentictask", auto=True)
        elif counts["ahead"] > 0:
            add("tmp-cache", "machine", "warn",
                f".tmp 缓存领先 origin {counts['ahead']} commit（本地发散）",
                "mw push-agentictask 发布，或 pull-agentictask --force 对齐")
        else:
            add("tmp-cache", "machine", "ok", "与 origin 一致")
    else:
        add("tmp-cache", "machine", "skip", ".tmp 缓存不存在（init 按需自动克隆）")

    # ── project layer ──

    # A3 serve staleness (T-13/AC-005): the code_digest judge with meta.code_dir
    # as the baseline tree, falling back to the legacy mtime judge for old meta.
    pid = _check_pid(_pid_path(project_dir))
    if pid is None:
        hint = "打开 pi 窗口自动启动，或 python mw.py start" if initialized else "项目未初始化"
        add("serve", "project", "info", "serve 未运行（PID 文件缺失或进程不在）", hint)
    else:
        meta_p = _serve_meta_path(project_dir)
        try:
            fallback_ms = (meta_p if meta_p.exists() else _pid_path(project_dir)).stat().st_mtime * 1000
        except OSError:
            fallback_ms = None
        v = serve_code_verdict(project_dir, fallback_started_ms=fallback_ms)
        if v["verdict"] == "drift":
            add("serve", "project", "stale", v["detail"],
                "重启 serve（在飞 worker 由新 launcher 收养；本项目窗口 /mw restart）", auto=True)
        elif v["verdict"] == "undecidable":
            add("serve", "project", "info", f"运行中 (PID {pid})；无法判定代码漂移（{v['reason']}）")
        else:
            commit = v["actual_commit"] or "(unavailable)"
            add("serve", "project", "ok",
                f"运行中 (PID {pid})，代码新鲜（{v['verdict']}，commit {commit[:9]}）")

    if not initialized:
        add("project", "project", "info", "项目未初始化（无 .agenticdoc）",
            "python mw.py init --project <dir>")
    else:
        # A6 skill clone
        clone = project_dir / ".agents" / "skills" / "agentic-task"
        if not (clone / "install.py").is_file():
            add("skill-clone", "project", "stale", "skill 克隆缺失", "框架重装（install.py）", auto=True)
        else:
            counts = _update_git_counts(clone)
            if counts is None:
                add("skill-clone", "project", "warn", "克隆无 origin/master 引用，无法比较",
                    "手动检查 git 状态")
            elif counts["ahead"] > 0:
                add("skill-clone", "project", "warn",
                    f"克隆领先 origin {counts['ahead']} commit（项目侧改动）",
                    "sync_framework.py from-install 发布，或 git push")
            elif counts["behind"] > 0:
                add("skill-clone", "project", "stale",
                    f"克隆落后 origin/{_DEFAULT_AGENTICTASK_BRANCH} {counts['behind']} commit",
                    "框架重装（pull --ff-only）", auto=True)
            else:
                add("skill-clone", "project", "ok", "与 origin 一致")

        # A7 .claude adapters + A8 manifest — both against the resolved source
        if source is None:
            add("claude-adapters", "project", "warn",
                "无法解析框架源（checkout 与 .tmp 均无 install.py）",
                "python mw.py pull-agentictask")
            add("manifest", "project", "skip", "无源可比")
        else:
            drift = _claude_adapter_drift(project_dir, source)
            if drift:
                add("claude-adapters", "project", "stale",
                    f".claude 适配器与框架源差异 {drift} 个文件", "框架重装（复制 claude/）", auto=True)
            else:
                add("claude-adapters", "project", "ok", ".claude 适配器与框架源一致")
            manifest = _read_framework_manifest(project_dir)
            installed_commit = manifest.get("commit", "")
            source_head = _git_head_short(source)
            if not installed_commit:
                add("manifest", "project", "stale", ".agentic-framework 缺失或无 commit=",
                    "框架重装", auto=True)
            elif source_head and installed_commit != source_head:
                add("manifest", "project", "stale",
                    f"安装于 {installed_commit}，源 HEAD {source_head}", "框架重装", auto=True)
            else:
                add("manifest", "project", "ok",
                    f"安装时间点 = 源 HEAD（{installed_commit or '?'}）")

        # S4 legacy patterns layout (pre-efe1e44)
        legacy = [d for d in (project_dir / ".agenticdoc").glob("*/patterns") if d.is_dir()]
        if legacy:
            add("legacy-patterns", "project", "warn",
                f"检测到旧版 <key>/patterns 布局 ×{len(legacy)}（pre-efe1e44）",
                "python .agents/skills/agentic-task/scripts/migrate_patterns.py --dry-run")
        else:
            add("legacy-patterns", "project", "ok", "无旧版 patterns 布局")

    summary = {
        "ok": sum(1 for c in checks if c["status"] == "ok"),
        "stale": sum(1 for c in checks if c["status"] == "stale"),
        "warn": sum(1 for c in checks if c["status"] == "warn"),
        "healthy": all(c["status"] in ("ok", "info", "skip") for c in checks),
    }
    return {
        "project": str(project_dir),
        "framework_source": str(source) if source else None,
        "checks": checks,
        "summary": summary,
    }


def _apply_update_env(project_dir: pathlib.Path, report: dict) -> tuple[list[str], list[str]]:
    """Execute the auto-fixable checks in dependency order (UPDATE.md §4):
    bundle/dist rebuild → cache pull → framework reinstall → serve restart.
    Returns (applied, manual_notes). Window-side actions (/reload, restarting
    pi) stay manual — a CLI cannot touch live pi processes."""
    applied: list[str] = []
    manual: list[str] = []
    by_id = {c["id"]: c for c in report["checks"]}

    def stale(cid: str) -> bool:
        c = by_id.get(cid)
        return bool(c) and c["status"] == "stale" and c.get("auto")

    # S1: bundle + pi dist. Rebuild BEFORE deploying (AC-009(c)): copying a
    # stale repo bundle to the global dir only refreshes its mtime, so the
    # re-check would report healthy while the content stays old (fail-open).
    if any(stale(cid) for cid in ("repo-bundle", "bundle", "pi-dist", "pi-dist-content")):
        ok, msg = _build_bundle()
        if not ok:
            manual.append(f"bundle 重建失败: {msg} — 未部署（避免 fail-open）")
        else:
            rc = _deploy_bundle(no_dist=False)
            if rc == 0:
                applied.append("bundle+dist 重建并全局重装")
                manual.append("重启 pi 窗口以加载新 bundle/dist")
            else:
                manual.append("mw build --install 失败 — 手动排查后重试")

    # .tmp cache (before framework reinstall — the cache may be its source)
    if stale("tmp-cache"):
        ok, msg = _pull_agentictask(_DEFAULT_AGENTICTASK_REMOTE, force=False,
                                    branch=_DEFAULT_AGENTICTASK_BRANCH)
        if ok:
            applied.append(f".tmp 缓存更新: {msg}")
        else:
            manual.append(f".tmp 缓存更新失败: {msg}")

    # S3: framework reinstall (skill clone / .claude adapters / manifest).
    # Source resolution happens HERE so a cache pulled in the previous step
    # is already visible; the live checkout (when present) still wins.
    if any(stale(cid) for cid in ("skill-clone", "claude-adapters", "manifest")):
        source = _resolve_framework_source_readonly()
        if source is None:
            manual.append("框架重装跳过：无可用源 — 先 python mw.py pull-agentictask")
        else:
            ok, msg = _install_framework(project_dir, source=source)
            if ok:
                applied.append(f"框架重装: {msg}")
                manual.append("各 pi 窗口运行 /reload 刷新 skill 摘要与 goal 门禁")
            else:
                manual.append(f"框架重装失败: {msg}")

    # S2: serve restart — last, so the restarted serve is the freshest state
    if stale("serve"):
        if _stop_serve(project_dir):
            cmd_start(argparse.Namespace(
                project=str(project_dir), pi_port=7001, claude_port=7003,
                deepseek_port=None, poll_interval=5, max_workers=None, providers=None))
            applied.append("serve 已重启（在飞 worker 由新 launcher 收养）")
        else:
            manual.append("serve 30s 内未退出 — 手动 /mw restart 或 /mw doctor")

    return applied, manual


def _format_update_env_text(report: dict) -> str:
    lines = [f"[mw update-env] project: {report['project']}"]
    if report.get("framework_source"):
        lines.append(f"[mw update-env] 框架源: {report['framework_source']}")
    lines.append("(远端比较基于本地 origin 引用 — 加 --fetch 先刷新)")
    layer = None
    for c in report["checks"]:
        if c["layer"] != layer:
            layer = c["layer"]
            lines.append(f"— {'机器层' if layer == 'machine' else '项目层'} —")
        mark = _UPDATE_ENV_MARKS.get(c["status"], c["status"])
        lines.append(f"  [{mark}] {c['id']:<18} {c['detail']}")
        if c["fix"] and c["status"] != "ok":
            auto_tag = " [auto]" if c.get("auto") else ""
            lines.append(f"       ↳{auto_tag} {c['fix']}")
    s = report["summary"]
    lines.append(f"— 汇总: {s['ok']} ok / {s['stale']} stale / {s['warn']} warn — "
                 f"{'healthy' if s['healthy'] else '需要动作'}")
    if report.get("applied"):
        lines.append("— 已执行（--apply）—")
        lines.extend(f"  ✓ {a}" for a in report["applied"])
    if report.get("manual"):
        lines.append("— 待人工 —")
        lines.extend(f"  • {m}" for m in report["manual"])
    if not report.get("applied") and s["stale"]:
        lines.append("提示: python mw.py update-env --apply 可自动执行 [auto] 项")
    return "\n".join(lines)


def cmd_update_env(args: argparse.Namespace) -> int:
    """Incremental self-check over the update anchors (UPDATE.md §3/§4).

    Read-only by default: prints each anchor's state + the minimal action.
    --apply executes the auto-fixable ones (build/install/pull/reinstall/serve
    restart) and re-checks; window-side reloads stay manual. Exit 0 = healthy
    (nothing stale/warn), 1 = attention needed — like doctor."""
    project_dir = pathlib.Path(args.project).resolve()

    if args.fetch:
        for repo in (_TMP_AGENTICTASK, project_dir / ".agents" / "skills" / "agentic-task"):
            if (repo / ".git").exists():
                r = _git(["fetch", "origin"], cwd=repo)
                state = "ok" if r.returncode == 0 else (r.stderr or r.stdout).strip()[:120]
                print(f"[mw update-env] fetch {repo}: {state}")

    report = _check_update_env(project_dir)
    applied: list[str] = []
    manual_notes: list[str] = []
    if args.apply:
        applied, manual_notes = _apply_update_env(project_dir, report)
        report = _check_update_env(project_dir)  # verify against fresh anchors

    report["applied"] = applied
    report["manual"] = manual_notes + [
        f"[{c['id']}] {c['fix']}" for c in report["checks"]
        if c["status"] in ("stale", "warn") and c["fix"]
    ]

    if args.json:
        print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    else:
        print(_format_update_env_text(report))
    return 0 if report["summary"]["healthy"] else 1


def cmd_worktree(args: argparse.Namespace) -> int:
    """`mw worktree add|rm|list` (G2): the ONLY legitimate way to clean up a
    linked worktree that may carry reparse points. The six-step rm transaction
    and its dependency injection live in worktree_cmd.py."""
    return worktree_cmd.cmd_worktree(
        args,
        repo_root=_repo_root(),
        git=_git,
        npm_hydrate=_npm_hydrate,
    )


def _add_serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, help="Project directory")
    parser.add_argument("--pi-port", type=int, default=7001)
    parser.add_argument("--claude-port", type=int, default=7003)
    parser.add_argument("--deepseek-port", type=int, default=None)
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--providers", default=None)


# -- Subcommand: stats (mw-usage-monitor T-03, design 3.3 / 5 / 7) ----------

#: Formats accepted by ``--since``; echoed on a bad value (design 7: rc=2).
_STATS_SINCE_HINT = "7d / 24h / 30m / YYYY-MM-DD"

#: ``--until`` adds one form on top of ``--since`` (local wall-clock minute).
_STATS_UNTIL_HINT = _STATS_SINCE_HINT + " / YYYY-MM-DDTHH:MM"


def cmd_stats(args: argparse.Namespace) -> int:
    """`mw stats`: token + wall-clock attribution over a time window.

    The report is built by ``usage.build_report`` (design 5 contract). A
    missing ledger is not an error: session logs are still scanned and the
    text path renders ``no ledger yet`` / ``no usage in window`` (design 7).
    """
    since_text = str(args.since or "7d").strip()
    try:
        since = usage.parse_since(since_text)
    except ValueError:
        print(
            f"[mw stats] invalid --since {since_text!r}; use {_STATS_SINCE_HINT}",
            file=sys.stderr,
        )
        return 2
    until_text = str(args.until or "").strip()
    until = None
    if until_text:
        try:
            until = usage.parse_until(until_text)
        except ValueError:
            # Same rc=2 path / message shape as ``--since`` (no second dialect).
            print(
                f"[mw stats] invalid --until {until_text!r}; use {_STATS_UNTIL_HINT}",
                file=sys.stderr,
            )
            return 2
        if until <= since:
            # The read-only kernel yields an empty window; rejecting the bound
            # is the CLI's job (spec §11.2 R7).
            print("mw stats: --until must be after --since", file=sys.stderr)
            return 2
    if args.limit is not None and args.limit < 0:
        print("mw stats: --limit must be >= 0", file=sys.stderr)
        return 2
    # `--all-projects` is only the explicit spelling of the bare default, so
    # combining it with a `--project` filter is a contradiction, not a no-op.
    if args.all_projects and args.project:
        print("mw stats: --all-projects conflicts with --project", file=sys.stderr)
        return 2
    project_filter = None if args.all_projects else args.project
    # R15-R17: the HTML page is the readable view of the WHOLE window, while
    # the text table and the JSON ``runs[]`` keep the ``--limit`` cut (R10).
    # ``--json`` wins on purity: its document stays byte-identical (AC-023), so
    # the uncut ``runs_all`` row list is never built for it.
    needs_html = args.html is not None or args.detail
    if needs_html and args.json:
        print(
            "[mw stats] note: --json suppresses the full run table",
            file=sys.stderr,
        )
    report = usage.build_report(
        since=since,
        until=until,
        limit=args.limit,
        detail=args.detail,
        include_all_runs=needs_html and not args.json,
        filters={
            "window": since_text,
            "key": args.key,
            "type": args.type,
            "model": args.model,
            "project": project_filter,
            "source": args.source,
        },
    )
    if args.json:
        # `runs[]` / `runs_total` are part of the report itself (R8): the JSON
        # contract never depends on `--detail`, so nothing is trimmed here.
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(usage.format_report_text(report, detail=args.detail))
    # R11/R12: a static HTML sibling of the same report. `--detail` implies it
    # (the terminal table is a summary, the browser is the readable view).
    if needs_html:
        # AC-019 + script safety: an unnamed `--json` run never pops a window
        # (same effect as `--no-open`); an explicit `--html PATH` still does.
        explicit_path = bool(str(args.html or "").strip())
        _publish_stats_html(
            report,
            args.html or "",
            no_open=args.no_open or (args.json and not explicit_path),
            as_json=args.json,
        )
    return 0


#: Env switch that suppresses opening the report (AC-019); `0` = open again.
_STATS_NO_OPEN_ENV = "MW_STATS_NO_OPEN"


def _publish_stats_html(
    report: Mapping[str, object],
    spec: str,
    *,
    no_open: bool,
    as_json: bool,
) -> pathlib.Path | None:
    """Write the static HTML report, then open it in the browser (R11/R12).

    ``spec`` is the raw ``--html`` value: an explicit PATH, or empty for the
    default ``<usage_dir>/reports/usage-<YYYYMMDD-HHMMSS>.html`` (one fresh
    file per call, history is never overwritten). Failures here never change
    the exit code: the text/JSON report was already printed (AC-019).
    """
    explicit = spec.strip()
    if explicit:
        target = pathlib.Path(explicit).expanduser()
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = usage.usage_dir() / "reports" / f"usage-{stamp}.html"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(usage.render_html(report))
    except OSError as exc:
        print(f"[mw stats] warning: cannot write {target}: {exc}", file=sys.stderr)
        return None
    # `--json` keeps stdout a pure JSON document; the path is diagnostics.
    if as_json:
        print(f"[mw stats] html: {target}", file=sys.stderr)
    else:
        print(f"html: {target}")
    suppress = str(os.environ.get(_STATS_NO_OPEN_ENV) or "").strip()
    if no_open or (suppress and suppress != "0"):
        return target
    try:
        opened = webbrowser.open(target.as_uri())
    except Exception:  # noqa: BLE001 - no default browser is a warning, not an error
        opened = False
    if not opened:
        print(f"[mw stats] warning: cannot open {target}", file=sys.stderr)
    return target


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-Workers service manager")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    _add_serve_args(sub.add_parser("serve", help="Run in foreground"))
    _add_serve_args(sub.add_parser("start", help="Run in background"))

    for name in ("stop", "status"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)

    # `--project` stays optional: a bare `mw stats` means the whole machine
    # (RQ4 2). The window runner no longer appends a control root, so
    # `/mw stats` is machine-level too; `--all-projects` states that explicitly.
    stats_p = sub.add_parser(
        "stats",
        help="Token and wall-clock usage over a time window (worker runs + PM sessions)",
    )
    stats_p.add_argument("--since", default="7d", metavar="WINDOW",
                         help=f"Window to report: {_STATS_SINCE_HINT} (default: %(default)s)")
    stats_p.add_argument("--key", default=None, metavar="KEY",
                         help="Only runs owned by this key directory")
    stats_p.add_argument("--type", default=None, metavar="TYPE",
                         help="Only runs of this task type (coding / review / research / ...)")
    stats_p.add_argument("--model", default=None, metavar="MODEL",
                         help="Only usage whose provider/model contains this substring")
    stats_p.add_argument("--project", default=None, metavar="DIR",
                         help="Only this project (path or basename); omit for the whole machine")
    stats_p.add_argument("--all-projects", action="store_true",
                         help="Explicitly report every project on this machine (the default; "
                              "refused together with --project)")
    stats_p.add_argument("--source", default=None, choices=("worker", "pm"),
                         help="Only worker runs, or only PM window sessions")
    stats_p.add_argument("--json", action="store_true",
                         help="Emit the fixed JSON contract instead of the text brief")
    stats_p.add_argument("--until", default=None, metavar="WINDOW",
                         help="window upper bound (exclusive): 7d / 24h / 30m / "
                              "YYYY-MM-DD / YYYY-MM-DDTHH:MM (default: now)")
    stats_p.add_argument("--detail", action="store_true",
                         help="append the per-run table (key / task / type / model / tokens / wall)")
    stats_p.add_argument("--limit", type=int, default=20, metavar="N",
                         help="max runs in the detail table and JSON runs[] (0 = all, default 20)")
    stats_p.add_argument("--html", nargs="?", const="", default=None, metavar="PATH",
                         help="write a static HTML report (default: "
                              "<usage_dir>/reports/usage-YYYYMMDD-HHMMSS.html)")
    stats_p.add_argument("--no-open", action="store_true",
                         help="do not open the HTML report in the browser")

    doctor_p = sub.add_parser(
        "doctor",
        help="Full-chain diagnostic: service, proxy ports, logs, queue, credentials, bundle",
    )
    doctor_p.add_argument("--project", required=True)
    doctor_p.add_argument("--providers", default=None,
                          help="Path to providers.json (default: the mw package copy)")
    doctor_p.add_argument("--json", action="store_true", help="Emit the JSON report (used by /mw doctor)")
    doctor_p.add_argument("--fix", action="store_true", help="Auto-fix stale entries and stale PID files")
    doctor_p.add_argument("--stale-after", type=int, default=90, metavar="SEC",
                          help="Worker heartbeat staleness threshold in seconds (default: %(default)s, "
                               "in sync with the TS HEARTBEAT_STALE_MS constant)")
    doctor_p.add_argument("--worktree-scan-roots", default=None, metavar="DIR1;DIR2",
                          help="AC-009 opt-in domain (c): semicolon-separated roots to hunt for "
                               "<root>/<worktree>/node_modules junctions pointing back into this "
                               "repo (default: off; the registry and <repo>/node_modules domains "
                               "always run without this flag)")

    target_p = sub.add_parser(
        "target",
        help="Dual-workspace target config: set bootstrap fields, clear, or show the resolved view",
    )
    target_sub = target_p.add_subparsers(dest="target_action", required=True)
    target_set_p = target_sub.add_parser("set", help="Write bootstrap fields; mode becomes dual")
    target_set_p.add_argument("--project", required=True, help="Control workspace directory")
    target_set_p.add_argument("--game", required=True, metavar="DIR", help="Game root (UE project)")
    target_set_p.add_argument("--engine", default=None, metavar="DIR", help="Engine root (optional)")
    target_set_p.add_argument("--vcs", default=None, choices=("git", "p4", "none"),
                              help="Target VCS (informational, optional)")
    target_set_p.add_argument("--uproject", default=None, metavar="FILE",
                              help="Explicit .uproject (game-relative or absolute; default: unique discovery)")
    for action in ("clear", "show", "on", "off"):
        help_text = (
            "Delete target.yml (back to single)" if action == "clear"
            else "Print the resolved config" if action == "show"
            else "Switch active mode to dual (v2 files; the dual block must exist)" if action == "on"
            else "Park dual mode: active → single, dual block kept (v2 files)"
        )
        p = target_sub.add_parser(action, help=help_text)
        p.add_argument("--project", required=True, help="Control workspace directory")

    partition_p = sub.add_parser(
        "partition",
        help="Partition-workspace target config: split a big project into an independent partition dir",
    )
    partition_sub = partition_p.add_subparsers(dest="partition_action", required=True)
    partition_set_p = partition_sub.add_parser(
        "set", help="Configure + activate the partition block (migrates a v1 target.yml to v2)"
    )
    partition_set_p.add_argument("--project", required=True, help="Control workspace directory")
    partition_set_p.add_argument("--parent", default=None, metavar="DIR",
                                 help="Parent project root (required; extended writable workspace for the partition)")
    partition_set_p.add_argument("--partition", default=None, metavar="DIR",
                                 help="Independent partition directory = worker cwd (default: the control root)")
    partition_set_p.add_argument("--root", action="append", default=None, metavar="NAME=DIR",
                                 help="Named additional root (repeatable; name must match [A-Za-z0-9_-]+)")
    partition_set_p.add_argument("--vcs", default=None, choices=("git", "p4", "none"),
                                 help="Target VCS (informational, optional)")
    for action in ("show", "clear", "on", "off"):
        help_text = {
            "show": "Print the resolved partition view",
            "clear": "Remove the partition block (delete target.yml when no mode block remains)",
            "on": "Switch active mode to partition (v2 files; the partition block must exist)",
            "off": "Park partition mode: active → single, partition block kept (v2 files)",
        }[action]
        p = partition_sub.add_parser(action, help=help_text)
        p.add_argument("--project", required=True, help="Control workspace directory")

    model_p = sub.add_parser(
        "model",
        help="Dispatch model defaults: per-role models used when a task carries no explicit model",
    )
    model_sub = model_p.add_subparsers(dest="model_action", required=True)
    model_set_p = model_sub.add_parser("set", help="Set a role default (e.g. mw model set review timi/glm-5.3-air)")
    model_set_p.add_argument("--project", required=True, help="Project directory")
    model_set_p.add_argument("role", choices=mw_common.DISPATCH_ROLES, metavar="ROLE",
                             help=f"One of: {', '.join(mw_common.DISPATCH_ROLES)}")
    model_set_p.add_argument("value", metavar="PROVIDER/MODEL",
                             help="Model with provider prefix (e.g. timi/glm-5.3, claude/claude-sonnet-5, codex_cli/gpt-5.6-sol)")
    model_set_p.add_argument("--force", action="store_true",
                             help="Skip the image-capability check when setting the 'vision' role")
    model_clear_p = model_sub.add_parser("clear", help="Remove one role (or 'all')")
    model_clear_p.add_argument("--project", required=True, help="Project directory")
    model_clear_p.add_argument("role", metavar="ROLE|all",
                               help=f"One of: {', '.join(mw_common.DISPATCH_ROLES)} — or 'all'")
    model_show_p = model_sub.add_parser("show", help="Print the configured roles and the effective resolution")
    model_show_p.add_argument("--project", required=True, help="Project directory")
    model_setfb_p = model_sub.add_parser(
        "set-fallback",
        help="Set a task type's ordered fallback chain (1..4 models, tried in order once the primary exhausts)",
    )
    model_setfb_p.add_argument("--project", required=True, help="Project directory")
    model_setfb_p.add_argument(
        "role",
        choices=sorted(mw_common.FALLBACK_TASK_TYPES),
        metavar="TASK_TYPE",
        help=f"Task type (not a role): {', '.join(sorted(mw_common.FALLBACK_TASK_TYPES))}",
    )
    model_setfb_p.add_argument(
        "value",
        metavar="PREFIX/MODEL[,PREFIX/MODEL...]",
        help="Comma-separated fallback chain, tried in order (e.g. timi/deepseek-v4.1-flash,zai/glm-5.3)",
    )
    model_clearfb_p = model_sub.add_parser(
        "clear-fallback",
        help="Remove a task type's fallback chain (drops the top-level block when it was the last one)",
    )
    model_clearfb_p.add_argument("--project", required=True, help="Project directory")
    model_clearfb_p.add_argument(
        "role",
        choices=sorted(mw_common.FALLBACK_TASK_TYPES),
        metavar="TASK_TYPE",
        help=f"Task type: {', '.join(sorted(mw_common.FALLBACK_TASK_TYPES))}",
    )

    autopilot_p = sub.add_parser(
        "autopilot",
        help="Autopilot configuration (xkey verification channel)",
    )
    autopilot_sub = autopilot_p.add_subparsers(dest="autopilot_action", required=True)
    gates_p = autopilot_sub.add_parser(
        "gates",
        help="Read-only gate queue view (pending gates; --json = machine exit)",
    )
    gates_p.add_argument("--project", required=True, help="Project directory")
    gates_p.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Emit the doctor gate segment as JSON (layer-C machine exit)",
    )
    answer_p = autopilot_sub.add_parser(
        "answer",
        help="Write one human gate answer (reject is destructive and needs --confirm-destructive)",
    )
    answer_p.add_argument("--project", required=True, help="Project directory")
    answer_p.add_argument("--gate-id", required=True, help="Gate id, e.g. gate-0001")
    answer_decision = answer_p.add_mutually_exclusive_group(required=True)
    answer_decision.add_argument("--approve", action="store_true", help="Approve the gate")
    answer_decision.add_argument(
        "--reject", action="store_true",
        help="Reject the gate (destructive; needs --confirm-destructive)",
    )
    answer_p.add_argument("--note", default=None, help="Single-line answer note")
    answer_p.add_argument(
        "--answered-by", default=None,
        help="Audit identity written to answered_by (default: mw-cli@host)",
    )
    answer_p.add_argument(
        "--confirm-destructive", action="store_true", dest="confirm_destructive",
        help="Second confirmation required to actually write a reject (AC-009)",
    )
    contract_guard_p = autopilot_sub.add_parser(
        "contract-guard",
        help="Read-only G3 check: frozen AC/VC text vs answered approval records",
    )
    contract_guard_p.add_argument("--project", required=True, help="Project directory")
    contract_guard_p.add_argument(
        "--key", default=None,
        help="Single key (default: every key that carries a freeze sidecar)",
    )
    contract_guard_p.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Emit the machine-readable verdict (stable sort, no timestamp)",
    )
    contract_freeze_p = autopilot_sub.add_parser(
        "contract-freeze",
        help="Explicitly write the G3 AC/VC anchor sidecar (--force re-freezes changes)",
    )
    contract_freeze_p.add_argument("--project", required=True, help="Project directory")
    contract_freeze_p.add_argument("--key", required=True, help="Key to anchor (one key only)")
    contract_freeze_p.add_argument(
        "--block", choices=("ac", "vc", "all"), default="all",
        help="Which acceptance block to freeze (default: all)",
    )
    contract_freeze_p.add_argument(
        "--force", action="store_true",
        help="Re-freeze a block whose text changed since it was frozen",
    )
    contract_freeze_p.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Emit the machine-readable per-block receipt (stable sort)",
    )
    verify_p = autopilot_sub.add_parser(
        "verify", help="Per-project xkey verification command (set/show/clear)"
    )
    verify_sub = verify_p.add_subparsers(dest="verify_action", required=True)
    verify_set_p = verify_sub.add_parser(
        "set", help="Set the verification argv (dry-run validated under the config lock)"
    )
    verify_set_p.add_argument("--project", required=True, help="Project directory")
    verify_set_p.add_argument(
        "--timeout", type=int, default=None, metavar="SEC",
        help="Verification subprocess timeout in seconds (xkey_verify_timeout_s, >= 1)",
    )
    verify_set_p.add_argument(
        "argv", nargs=argparse.REMAINDER, metavar="ARGV",
        help="Verification argv after '--' (stored verbatim, no shell)",
    )
    verify_show_p = verify_sub.add_parser(
        "show", help="Print effective values, origins and the expanded argv/cwd"
    )
    verify_show_p.add_argument("--project", required=True, help="Project directory")
    verify_show_p.add_argument(
        "--json", action="store_true", dest="as_json", help="Emit machine-readable JSON"
    )
    verify_clear_p = verify_sub.add_parser(
        "clear", help="Remove the four xkey keys (never deletes the file)"
    )
    verify_clear_p.add_argument("--project", required=True, help="Project directory")

    init_p = sub.add_parser("init", help="Initialize project and install Extension + framework")
    init_p.add_argument("--project", required=True)
    init_p.add_argument("--no-framework", action="store_true",
                        help="Skip installing the AgenticTask framework (.claude/ + .agents/skills)")
    init_p.add_argument("--codex-scope", choices=("project", "user"), default="project",
                        help="Where to install the codex/pi skill (default: project-local .agents/skills)")
    init_p.add_argument("--sync-agentictask", default=None, metavar="SOURCE_DIR",
                        help="Install the framework from SOURCE_DIR, overriding automatic "
                             "source resolution (checkout framework repo > .tmp cache)")

    pull_p = sub.add_parser("pull-agentictask",
                            help="Clone/update the AgenticTask framework repo into the local .tmp clone")
    pull_p.add_argument("--from", dest="source", default=_DEFAULT_AGENTICTASK_REMOTE,
                        metavar="SOURCE",
                        help="Git URL to clone/update, or a local dir to copy (default: %(default)s)")
    pull_p.add_argument("--branch", default=_DEFAULT_AGENTICTASK_BRANCH,
                        help="Branch to clone/track (default: %(default)s)")
    pull_p.add_argument("--force", action="store_true",
                        help="git reset --hard to the remote branch, or replace a non-git cache")

    push_p = sub.add_parser("push-agentictask",
                            help="Commit+push local framework changes from the .tmp clone to its remote")
    push_p.add_argument("-m", "--message", default=None,
                        help="Commit message for uncommitted changes before pushing")
    push_p.add_argument("--branch", default=_DEFAULT_AGENTICTASK_BRANCH,
                        help="Branch to push (default: %(default)s)")

    setup_p = sub.add_parser("setup",
                             help="One-time machine bootstrap: clone framework + install extension globally")
    setup_p.add_argument("--from", dest="source", default=_DEFAULT_AGENTICTASK_REMOTE,
                         metavar="SOURCE",
                         help="Git URL to clone, or a local dir to copy (default: %(default)s)")
    setup_p.add_argument("--branch", default=_DEFAULT_AGENTICTASK_BRANCH,
                         help="Branch to clone/track (default: %(default)s)")
    setup_p.add_argument("--force", action="store_true", help="Refresh an existing clone (reset --hard)")
    setup_p.add_argument("--build", action="store_true",
                         help="Rebuild the extension bundle (bash-free) before installing")

    bootstrap_p = sub.add_parser(
        "bootstrap",
        help="Fresh-machine one-shot: prereqs → npm ci → build → link pi → setup → init → start → doctor",
    )
    bootstrap_p.add_argument("--project", default=None, metavar="DIR",
                             help="Project directory to init/start (default: this repo root)")
    bootstrap_p.add_argument("--from", dest="source", default=_DEFAULT_AGENTICTASK_REMOTE,
                             metavar="SOURCE",
                             help="AgenticTask framework source forwarded to setup "
                                  "(default: %(default)s)")
    bootstrap_p.add_argument("--branch", default=_DEFAULT_AGENTICTASK_BRANCH,
                             help="Framework branch to clone/track (default: %(default)s)")
    bootstrap_p.add_argument("--fast", action="store_true",
                             help="Skip npm install + repo build (credential-fix re-run; "
                                  "requires a previous full bootstrap)")
    bootstrap_p.add_argument("--no-start", dest="no_start", action="store_true",
                             help="Do not start the service (steps 1-6 + doctor only)")
    bootstrap_p.add_argument("--allow-dirty", dest="allow_dirty", action="store_true",
                             help="Run the root build despite uncommitted changes under packages/*/src")

    build_p = sub.add_parser("build",
                             help="Rebuild the extension bundle with esbuild (bash-free, cwd-independent)")
    build_p.add_argument("--install", action="store_true",
                         help="Also install the freshly built bundle into the global extensions dir")
    build_p.add_argument("--no-dist", dest="no_dist", action="store_true",
                         help="Skip rebuilding packages/coding-agent/dist (the npm-link pi runtime); "
                              "by default --install also rebuilds it")
    build_p.add_argument("--allow-dirty", dest="allow_dirty", action="store_true",
                         help="Install despite uncommitted changes under packages/coding-agent/src "
                              "(the artifacts may embed unreviewed source)")

    update_env_p = sub.add_parser(
        "update-env",
        help="Incremental self-check over the update anchors (UPDATE.md): bundle/dist/serve/"
             "framework propagation; --apply runs the safe fixes",
    )
    update_env_p.add_argument("--project", required=True)
    update_env_p.add_argument("--apply", action="store_true",
                              help="Execute the auto-fixable actions (build+install, cache pull, "
                                   "framework reinstall, serve restart) then re-check")
    update_env_p.add_argument("--json", action="store_true", help="Emit the JSON report")
    update_env_p.add_argument("--fetch", action="store_true",
                              help="git fetch origin in the framework cache + skill clone first "
                                   "(refresh the origin refs the behind/ahead counts use)")

    worktree_p = sub.add_parser(
        "worktree",
        help="Linked-worktree lifecycle with reparse-point safety: add (no junction "
             "by default), rm (six-step transaction; no step-skipping switch), "
             "list (registry + git worktree list merged view)",
    )
    worktree_sub = worktree_p.add_subparsers(dest="worktree_action", required=True)
    wt_add_p = worktree_sub.add_parser(
        "add",
        help="Create a detached linked worktree; --link-deps creates and registers "
             "the <path>/node_modules junction instead of installing dependencies",
    )
    wt_add_p.add_argument("path", metavar="PATH", help="Worktree path to create")
    wt_add_p.add_argument("--project", default=None, metavar="DIR",
                          help="Control workspace for the registry (default: this repo root)")
    wt_add_p.add_argument("--ref", default="HEAD", metavar="REF",
                          help="Commit-ish to check out (default: %(default)s)")
    wt_add_p.add_argument("--link-deps", dest="link_deps", action="store_true",
                          help="Junction <path>/node_modules -> <repo>/node_modules instead of "
                               "installing; the link is registered (AC-008)")
    wt_add_p.add_argument("--dry-run", dest="dry_run", action="store_true",
                          help="Print the plan and exit without writing anything")
    wt_add_p.add_argument("--json", action="store_true", help="Emit the machine-readable result")
    wt_rm_p = worktree_sub.add_parser(
        "rm",
        help="Remove a linked worktree via the fixed six-step transaction "
             "(enumerate, validate, unlink, recheck, remove, report); an abort "
             "preserves the scene and there is no --force/--continue switch",
    )
    wt_rm_p.add_argument("path", metavar="PATH", help="Linked worktree path to remove")
    wt_rm_p.add_argument("--project", default=None, metavar="DIR",
                         help="Control workspace for the registry (default: this repo root)")
    wt_rm_p.add_argument("--json", action="store_true", help="Emit the machine-readable six-step report")
    wt_list_p = worktree_sub.add_parser(
        "list", help="Read-only merged view: registry entries + git worktree list --porcelain")
    wt_list_p.add_argument("--project", default=None, metavar="DIR",
                           help="Control workspace for the registry (default: this repo root)")
    wt_list_p.add_argument("--json", action="store_true", help="Emit the merged view as JSON")

    toolchain_p = sub.add_parser(
        "ue-toolchain",
        help="Dual-mode UE toolchain discipline (practice guide; UE game dev: game repo + "
             "engine source repo, MSVC/UBT): run a configured command with evidence "
             "artifacts, discover UE build targets, EOL-normalized hashing",
    )
    toolchain_sub = toolchain_p.add_subparsers(dest="toolchain_action", required=True)
    tc_run_p = toolchain_sub.add_parser(
        "run",
        help="Execute toolchain.<name> from the control root; archives cmd.txt / run.log / "
             "exit.txt / errors.txt / meta.json under a fresh run dir. Error signatures "
             "(error C / LNK#### / 'error :') are the MSVC/UE set; the run-evidence "
             "discipline itself is toolchain-agnostic",
    )
    tc_run_p.add_argument("--project", required=True)
    tc_run_p.add_argument("name", metavar="NAME", help="toolchain.<NAME> command to run")
    tc_run_p.add_argument("--out", default=None, metavar="DIR",
                          help="Parent dir for the run dir (default: <control>/.mw/toolchain-runs; "
                               "point it at key evidence to archive the run)")
    tc_run_p.add_argument("--watch", action="append", default=None, metavar="PATH",
                          help="File hashed (EOL-normalized) before/after — drift proves someone "
                               "edited it while the command ran (repeatable)")
    tc_run_p.add_argument("--args", default=None, metavar="STR",
                          help="String appended verbatim to the rendered command. Use the equals "
                               "form (--args=\"-MaxParallelActions=16\") when the value starts "
                               "with '-' — argparse rejects it as an unknown flag otherwise")
    tc_run_p.add_argument("--json", action="store_true", help="Also print meta.json to stdout")
    tc_targets_p = toolchain_sub.add_parser(
        "targets", help="List UE build target names from <game>/Source/*.Target.cs (read, never guess)")
    tc_targets_p.add_argument("--project", required=True)
    tc_hash_p = toolchain_sub.add_parser(
        "hash", help="EOL-normalized sha256 (freeze/drift checks that survive CRLF→LF flips)")
    tc_hash_p.add_argument("files", nargs="+", metavar="FILE")

    rag_p = sub.add_parser(
        "rag",
        help="RAG (MCP) knowledge-base config: list the merged server table, probe the "
             "enabled set, sync the mw-rag skill (explicit install - the pi session never writes it)",
    )
    rag_sub = rag_p.add_subparsers(dest="rag_action", required=True)
    rag_init_p = rag_sub.add_parser(
        "init", help="Zero-interaction template generator: write commented "
                     "rag-servers.yml / target.yml rag: / rag-roots.json examples")
    rag_init_p.add_argument("--project", required=True, help="Control workspace directory")
    rag_init_p.add_argument("--server", default=None, metavar="NAME",
                            help=f"Server name to template (default: {rag_templates.DEFAULT_SERVER})")
    rag_init_p.add_argument("--url", default=None, metavar="URL",
                            help=f"Example MCP url (default: {rag_templates.DEFAULT_MCP_URL})")
    rag_init_p.add_argument("--token-env", dest="token_env", default=None, metavar="VAR",
                            help="Example token env var NAME (default: "
                                 f"{rag_templates.DEFAULT_TOKEN_ENV})")
    rag_init_p.add_argument("--transport", choices=("mcp", "skill", "both"), default=None,
                            help="Which transport block stays active (default: mcp)")
    rag_init_p.add_argument("--enable", action="store_true",
                            help="Write enabled: [<server>] (and default_server) instead of enabled: []")
    rag_init_p.add_argument("--machine", action="store_true",
                            help="Also write the machine layer ~/.agents/rag-servers.yml")
    rag_init_p.add_argument("--only-machine", dest="only_machine", action="store_true",
                            help="Write only the machine layer (skip project files)")
    rag_init_p.add_argument("--no-roots", dest="no_roots", action="store_true",
                            help="Do not write <project>/.mw/rag-roots.json (then every citation "
                                 "audits as unverified)")
    rag_init_p.add_argument("--force", action="store_true",
                            help="Overwrite existing files; replace an existing rag: section in place")
    rag_init_p.add_argument("--dry-run", dest="dry_run", action="store_true",
                            help="Print the intended writes and exit without changing anything")
    rag_init_p.add_argument("--print", dest="print_templates", action="store_true",
                            help="Print the templates to stdout and exit without changing anything")
    rag_list_p = rag_sub.add_parser(
        "list", help="Merged per-field server table + origin annotations + enabled set")
    rag_list_p.add_argument("--project", required=True, help="Control workspace directory")
    rag_list_p.add_argument("--json", action="store_true", help="Emit the machine-readable config")
    rag_probe_p = rag_sub.add_parser(
        "probe", help="Probe each enabled server (5s each; diagnostics only — unreachable servers still "
                       "exit 0, a config error exits 1)")
    rag_probe_p.add_argument("--project", required=True, help="Control workspace directory")
    rag_probe_p.add_argument("--json", action="store_true", help="Emit the per-server probe results")
    rag_sync_p = rag_sub.add_parser(
        "sync", help="Install/remove <project>/.pi/skills/mw-rag.md (the only writer of that file)")
    rag_sync_p.add_argument("--project", required=True, help="Control workspace directory")
    rag_audit_p = rag_sub.add_parser(
        "audit", help="Read-only citation/require audit over <key>/rag/*.md and terminal "
                      "workers' output.md/trace.log (default: stdout only)")
    rag_audit_p.add_argument("--project", required=True, help="Control workspace directory")
    rag_audit_p.add_argument("--key", default=None,
                             help="Limit the scan to one AgenticTask key directory")
    rag_audit_p.add_argument("--json", action="store_true",
                             help="Emit the machine-readable audit report")
    rag_audit_p.add_argument("--out", default=None, metavar="FILE",
                             help="Write the JSON report to FILE (default: no file is written)")

    run_detached_p = sub.add_parser(
        "run-detached",
        help="Detached background command runner: spawn CMD in a hidden console "
             "with heartbeat + marker evidence (win32 flag contract, posix "
             "start_new_session)",
    )
    run_detached_p.add_argument("--cwd", default=None, metavar="DIR",
                                help="Working directory for the command (default: current)")
    run_detached_p.add_argument("--run-dir", default=None, metavar="DIR",
                                help="Evidence run dir (default: <cwd>/.mw/runs/run-<timestamp>; "
                                     "an existing dir gets a -N suffix)")
    run_detached_p.add_argument("--timeout-min", type=float, default=None, metavar="MIN",
                                help="Kill the command tree after MIN minutes (marker rc=124, "
                                     "timed_out=true; default: no timeout)")
    run_detached_p.add_argument("--heartbeat-s", type=float, default=5, metavar="SEC",
                                help="Heartbeat write interval in seconds (default: %(default)s)")
    run_detached_p.add_argument("argv", nargs=argparse.REMAINDER, metavar="CMD",
                                help="Command argv after '--' (stored verbatim, no shell)")

    return parser.parse_args(argv)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_run_supervisor":
        # Internal detached-runner supervisor. Never registered as an argparse
        # subcommand (stays out of --help); console_run's CLI spawns it as
        # `python mw.py _run_supervisor --run-dir D ... -- <cmd...>`.
        sys.exit(console_run.run_supervisor_entry(sys.argv[2:]))
    args = _parse_args()
    dispatch = {
        "serve": cmd_serve,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "stats": cmd_stats,
        "doctor": cmd_doctor,
        "target": cmd_target,
        "partition": cmd_partition,
        "model": cmd_model,
        "autopilot": cmd_autopilot,
        "init": cmd_init,
        "pull-agentictask": cmd_pull_agentictask,
        "push-agentictask": cmd_push_agentictask,
        "setup": cmd_setup,
        "build": cmd_build,
        "bootstrap": cmd_bootstrap,
        "update-env": cmd_update_env,
        "ue-toolchain": cmd_toolchain,
        "worktree": cmd_worktree,
        "rag": cmd_rag,
        "run-detached": console_run.cmd_run_detached,
    }
    sys.exit(dispatch[args.subcommand](args))

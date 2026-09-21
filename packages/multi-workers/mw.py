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
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
from mw_common import (
    check_pid as _check_pid,
    port_is_bound as _port_is_bound,
)
from autopilot import config as _ap_config
from autopilot import conductor as _ap_conductor

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


def _serve_meta_path(project_dir: pathlib.Path) -> pathlib.Path:
    """Serve stamp for extension-side staleness detection (stale-serve fix):
    the agent-team-loop extension compares started_at_ms against the mw source
    tree's newest mtime — same pattern as doctor's bundle staleness check.
    Removed on serve exit alongside the PID file."""
    return project_dir / ".mw" / "serve.meta"


def _write_serve_meta(project_dir: pathlib.Path) -> None:
    meta = {
        "pid": os.getpid(),
        "started_at_ms": int(time.time() * 1000),
        "code_dir": str(_SCRIPT_DIR),
    }
    p = _serve_meta_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta), encoding="utf-8")


def _remove_serve_meta(project_dir: pathlib.Path) -> None:
    try:
        _serve_meta_path(project_dir).unlink()
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
    via cached_load). Returns the (possibly new) conductor proc."""
    enabled = _ap_config.cached_load(project_dir)["enabled"]
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

        _write_pid(pid_path)
        wrote_pid = True
        _write_serve_meta(project_dir)
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
        # START /B equivalent: CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS + CREATE_NO_WINDOW
        import subprocess as _sp

        proc = _sp.Popen(  # noqa: S603
            cmd,
            creationflags=_sp.DETACHED_PROCESS | _sp.CREATE_NEW_PROCESS_GROUP | _sp.CREATE_NO_WINDOW,
            close_fds=True,
        )
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
    report = mw_common.doctor_report(project_dir, fix=args.fix, config=config, stale_after_sec=args.stale_after)
    # Conductor section (D-101): informational like worker_liveness — a not
    # running conductor (autopilot disabled) is not an issue.
    report["conductor"] = _ap_conductor.conductor_status(project_dir)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(mw_common.format_doctor_text(report))
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
        "  # command templates with {game}/{engine}/{uproject} placeholders, e.g.",
        "  # build_editor: '\"{engine}/Engine/Build/BatchFiles/Build.bat\" ProjEditor Win64 Development -project=\"{uproject}\"'",
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

def _model_write(project_dir: pathlib.Path, models: dict[str, str]) -> None:
    """Write .mw/dispatch.yml from a complete role→value mapping."""
    import yaml

    path = mw_common.dispatch_config_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"models": models} if models else {}
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
            print(f"{role}: {configured}")
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
        print(f"{role}: (unset) → {effective} [{source}]")
    return 0


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


def _git(args: list[str], *, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess:
    """Run a git command, capturing output. Never raises on non-zero exit."""
    cmd = ["git"]
    if cwd is not None:
        cmd += ["-C", str(cwd)]
    cmd += args
    return subprocess.run(cmd, capture_output=True, text=True)


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
_BUILD_NODE_SCRIPT = r"""
const esbuild = require('esbuild');
const { createJiti } = require('jiti');
const url = require('url');
const SRC = process.env.MW_SRC;
const OUT = process.env.MW_OUT;
esbuild.build({
  entryPoints: [SRC],
  bundle: true,
  outfile: OUT,
  platform: 'node',
  format: 'esm',
  target: 'node18',
  external: ['node:*'],
  logLevel: 'warning',
}).then(() => {
  const j = createJiti(url.pathToFileURL(process.cwd() + '/').href, { moduleCache: false });
  return j.import(OUT, { default: true });
}).then((f) => {
  if (typeof f !== 'function') {
    console.error('Self-check FAILED: host loader expects a function, got ' + typeof f);
    process.exit(1);
  }
  console.log('built + self-check OK (' + (f.name || 'anon') + ')');
}).catch((e) => {
  console.error('Build FAILED: ' + ((e && e.message) || e));
  process.exit(1);
});
"""


def _repo_root() -> pathlib.Path:
    return _SCRIPT_DIR.parent.parent


def _build_bundle() -> tuple[bool, str]:
    """Compile the agent-team-loop extension bundle with esbuild and self-check
    that it loads as a function (the host loader contract).

    Pure Python + node: no bash, no msys `pwd -W`, and cwd-independent — all
    paths derive from mw.py's own location, so ANY pi window can rebuild mw
    regardless of its working directory. node runs with cwd=repo root so that
    require('esbuild')/require('jiti') resolve from the repo's node_modules.
    """
    repo_root = _repo_root()
    src = repo_root / _EXT_SRC_REL
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


def _deploy_bundle(no_dist: bool) -> int:
    """Install the freshly built bundle globally: bundle copy + .mw-py-path
    sidecar + /update-agentictask command + pi dist rebuild. Shared by
    `mw build --install` and `mw update-env --apply`. Returns exit code."""
    ext_dst = _global_ext_dir() / "agent-team-loop.js"
    ext_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(_bundle_path()), str(ext_dst))
    _write_mw_py_path()
    ok_u, msg_u = _agentictask_update_install()
    print(f"[mw build] {msg_u}" if ok_u else f"[mw build] Warning: {msg_u}",
          file=None if ok_u else sys.stderr)
    print(f"[mw build] installed globally: {ext_dst}")
    # The npm global `pi` links to packages/coding-agent, so the runtime
    # executes the repo's dist — rebuild it so the built-in agent-team-loop
    # copy and any pi-core changes reach the runtime (opt out: --no-dist).
    if no_dist:
        print("[mw build] dist rebuild skipped (--no-dist)")
        return 0
    dok, dmsg = _rebuild_pi_dist()
    if not dok:
        print(f"[mw build] Error: {dmsg}", file=sys.stderr)
        return 1
    print(f"[mw build] {dmsg}: {_repo_root() / 'packages' / 'coding-agent' / 'dist'}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
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
        install_cmd = [npm, "install" if node_modules.is_dir() else "ci", "--ignore-scripts"]
        if not _run_stream(install_cmd, cwd=repo_root):
            return fail("npm install failed — see the output above")

    # 3. repo build (all packages, dependency order)
    if args.fast:
        skip(3, "--fast")
    else:
        step(3, "npm run build (root; the ai build fetches models.dev — network required)")
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
_UPDATE_ENV_SKIP_DIRS = ("__pycache__", "dist", ".tmp")
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


def _mw_code_newest_mtime() -> float | None:
    """Staleness baseline for a running serve — the Python mirror of the TS
    side's mwCodeNewestMtimeMs: only runtime code (*.py|*.json), skipping
    __pycache__/dist/.tmp and test_*/_* files. .tmp is excluded on both sides:
    it is the framework cache, not serve runtime code (a cache pull must not
    turn a healthy serve stale)."""
    newest: float | None = None
    for f in _SCRIPT_DIR.rglob("*"):
        if not f.is_file():
            continue
        if any(part in _UPDATE_ENV_SKIP_DIRS for part in f.relative_to(_SCRIPT_DIR).parts[:-1]):
            continue
        if f.suffix not in (".py", ".json"):
            continue
        if f.name.startswith("test_") or f.name.startswith("_"):
            continue
        m = f.stat().st_mtime
        newest = m if newest is None else max(newest, m)
    return newest


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

    # A3 serve staleness (mirror of the extension's STALE CODE banner)
    pid = _check_pid(_pid_path(project_dir))
    if pid is None:
        hint = "打开 pi 窗口自动启动，或 python mw.py start" if initialized else "项目未初始化"
        add("serve", "project", "info", "serve 未运行（PID 文件缺失或进程不在）", hint)
    else:
        meta_p = _serve_meta_path(project_dir)
        started_ms: float | None = None
        if meta_p.is_file():
            try:
                started_ms = float(json.loads(meta_p.read_text(encoding="utf-8")).get("started_at_ms", 0)) or None
            except (json.JSONDecodeError, OSError):
                started_ms = None
        if started_ms is None:
            try:
                started_ms = (meta_p if meta_p.exists() else _pid_path(project_dir)).stat().st_mtime * 1000
            except OSError:
                started_ms = None
        code_mtime = _mw_code_newest_mtime()
        if started_ms is None or code_mtime is None:
            add("serve", "project", "info", f"运行中 (PID {pid})；无法比较代码时间")
        elif code_mtime * 1000 > started_ms + 2000:
            add("serve", "project", "stale",
                f"serve 启动 {_ts(started_ms / 1000)} 早于 mw 代码 {_ts(code_mtime)}（PID {pid}）",
                "重启 serve（在飞 worker 由新 launcher 收养）", auto=True)
        else:
            add("serve", "project", "ok", f"运行中 (PID {pid})，代码新鲜")

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

    # S1: bundle + pi dist
    if stale("bundle") or stale("pi-dist"):
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


def _add_serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, help="Project directory")
    parser.add_argument("--pi-port", type=int, default=7001)
    parser.add_argument("--claude-port", type=int, default=7003)
    parser.add_argument("--deepseek-port", type=int, default=None)
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--providers", default=None)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-Workers service manager")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    _add_serve_args(sub.add_parser("serve", help="Run in foreground"))
    _add_serve_args(sub.add_parser("start", help="Run in background"))

    for name in ("stop", "status"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)

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
    model_clear_p = model_sub.add_parser("clear", help="Remove one role (or 'all')")
    model_clear_p.add_argument("--project", required=True, help="Project directory")
    model_clear_p.add_argument("role", metavar="ROLE|all",
                               help=f"One of: {', '.join(mw_common.DISPATCH_ROLES)} — or 'all'")
    model_show_p = model_sub.add_parser("show", help="Print the configured roles and the effective resolution")
    model_show_p.add_argument("--project", required=True, help="Project directory")

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

    build_p = sub.add_parser("build",
                             help="Rebuild the extension bundle with esbuild (bash-free, cwd-independent)")
    build_p.add_argument("--install", action="store_true",
                         help="Also install the freshly built bundle into the global extensions dir")
    build_p.add_argument("--no-dist", dest="no_dist", action="store_true",
                         help="Skip rebuilding packages/coding-agent/dist (the npm-link pi runtime); "
                              "by default --install also rebuilds it")

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

    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    dispatch = {
        "serve": cmd_serve,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "doctor": cmd_doctor,
        "target": cmd_target,
        "partition": cmd_partition,
        "model": cmd_model,
        "init": cmd_init,
        "pull-agentictask": cmd_pull_agentictask,
        "push-agentictask": cmd_push_agentictask,
        "setup": cmd_setup,
        "build": cmd_build,
        "bootstrap": cmd_bootstrap,
        "update-env": cmd_update_env,
    }
    sys.exit(dispatch[args.subcommand](args))

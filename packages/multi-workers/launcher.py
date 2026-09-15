"""
launcher.py — Multi-Workers task launcher.

Polls _workers.parallel for pending tasks and spawns worker processes.
Managed by mw serve; do not run directly in production.

mw-dispatch-reliability changes (design D-001/D-004):
- A task whose credentials/route cannot be resolved is marked failed with the
  reason persisted to its worker.log; it never kills the launcher loop.
- Each poll archives queue entries whose task.md no longer exists.
- Credential resolution and the file bus live in mw_common (single source).

mw-widget-terminal-lifecycle (T-08, AC-012/AC-013):
- Each poll refreshes the launcher beat (.mw/launcher-beat.<pid>) and
  reconciles orphaned running rows (running but not in running_procs):
  positive terminal evidence (an [END] line, or a lone output.md from an old
  bundle) applies unconditionally; evidence-less rows fail as presumed dead
  after the silence window, yielding to another live launcher's fresh beat
  (design D-006~D-008).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
from mw_common import (
    acquire_lock as _acquire_lock,
    load_providers as _load_providers,
    lock_path as _lock_path,
    parse_workers_file as _parse_workers_file,
    release_lock as _release_lock,
    serialize_entry as _serialize_entry,
    update_status as _update_status,
    workers_path as _workers_path,
)

DEFAULT_POLL_INTERVAL: int = 5  # seconds — AC-001: must be <= 5

# ── Worker log helper ─────────────────────────────────────────────────────────

def _worker_log_path(entry: dict[str, str]) -> pathlib.Path:
    return pathlib.Path(entry["task_path"]).parent / "worker.log"


def _record_spawn_failure(entry: dict[str, str], msg: str) -> None:
    """Persist the spawn failure reason into the task's worker.log.

    The CLI never ran, so without this the failed status would be unexplained
    (AC-001: the reason must name the missing credential source).
    """
    try:
        log_path = _worker_log_path(entry)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[launcher] spawn failed ({mw_common.iso_now()}): {msg}\n")
    except OSError:
        pass  # best-effort; the launcher.log line still carries the reason


def _record_reconcile(entry: dict[str, str], reason: str) -> None:
    """Persist a reconcile decision into the task's worker.log.

    Same family as _record_spawn_failure: a status flip without a persisted
    reason is undiagnosable after the fact (AC-012/AC-013 both require the
    reconcile reason line in worker.log).
    """
    try:
        log_path = _worker_log_path(entry)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[launcher] reconcile ({mw_common.iso_now()}): {reason}\n")
    except OSError:
        pass  # best-effort; the queue row still carries the terminal status


# ── Provider / env helpers ────────────────────────────────────────────────────

def _stripped_env(config: dict) -> dict[str, str]:
    """Base env for a worker: full inherit minus every declared credential.

    Strip set = all env names declared in credential chains + legacy extras +
    every provider base_url_env (AC-024/AC-025 isolation semantics).
    """
    env = dict(os.environ)
    for var in mw_common.credential_env_names(config):
        env.pop(var, None)
    for var in mw_common.EXTRA_CREDENTIAL_VARS:
        env.pop(var, None)
    for cfg in config.get("providers", {}).values():
        if isinstance(cfg, dict) and cfg.get("base_url_env"):
            env.pop(str(cfg["base_url_env"]), None)
    return env


def _build_env(entry: dict[str, str], config: dict) -> dict[str, str]:
    """Build the environment dict for a worker process (AC-002~004, AC-008~010, AC-024)."""
    cli = entry["cli"].lower()
    provider = entry.get("provider", "").strip()

    # Pi + timi: use Timi credentials directly (no localhost proxy) (AC-008).
    # Source chain: env TIMI_API_KEY → pi's own ~/.pi/agent/auth.json.
    if cli == "pi" and provider == "timi":
        cred = config.get("credentials", {}).get("timi")
        value, _source = mw_common.resolve_credential(cred, os.environ)
        if value is None:
            raise RuntimeError(
                f"Timi credential is not available ({mw_common.describe_missing(cred)})."
            )
        env = _stripped_env(config)
        env["TIMI_API_KEY"] = value
        if "TIMI_BASE_URL" in os.environ:
            env["TIMI_BASE_URL"] = os.environ["TIMI_BASE_URL"]
        task_path = pathlib.Path(entry["task_path"])
        env["PI_WORKER_TASK"] = str(task_path.resolve())
        return env

    # Codex: native provider, remove all proxy credentials (AC-010)
    if cli == "codex":
        if provider not in ("", "codex"):
            raise RuntimeError(
                f"Codex workers support only an empty provider or 'codex', got {provider!r}"
            )
        return _stripped_env(config)

    # Generic port-based proxy path (pi empty provider, claude, deepseek, ...)
    route = mw_common.route_for(config, cli, provider)
    cred = config.get("credentials", {}).get(route["credential"])
    value, _source = mw_common.resolve_credential(cred, os.environ)
    if value is None:
        raise RuntimeError(
            f"Required credential for route '{route['provider_key']}' is not available "
            f"({mw_common.describe_missing(cred)})."
        )

    env = _stripped_env(config)
    env[route["base_url_env"]] = f"http://localhost:{route['port']}"
    env[route["api_key_env"]] = value

    # Pi worker also needs PI_WORKER_TASK (AC-002)
    if cli == "pi":
        task_path = pathlib.Path(entry["task_path"])
        env["PI_WORKER_TASK"] = str(task_path.resolve())

    return env


def _exit_to_status(exit_code: int) -> str:
    """Map worker exit code to _workers.parallel status (AC-006)."""
    if exit_code == 0:
        return "done"
    if exit_code == 2:
        return "needs-clarification"
    return "failed"


def _require_task_file(task_path: str) -> pathlib.Path:
    """Validate the task file exists; return its Path.

    Raises RuntimeError with a clear reason so _spawn records it into the
    task's worker.log (design D-001 isolation semantics).
    """
    p = pathlib.Path(task_path)
    if not p.exists():
        raise RuntimeError(f"task.md not found: {task_path}")
    return p


def _validate_task_path(project_dir: pathlib.Path, task_path: str) -> None:
    """Enforce the worker-task location contract.

    Valid: <project>/.agenticdoc/{ownerKey}/workers/<task_key>/task.md or
    <project>/.agenticdoc/_scratch/workers/<task_key>/task.md. The .agenticdoc
    root belongs to AgenticTask keys; task dirs found there (OverCode
    pch-migration-s1 incident: hand-written task.md + queue rows at the root
    bypassed dispatch_worker's workerTaskDir placement) must be rejected
    loudly instead of spawned.
    """
    agentic = (project_dir / ".agenticdoc").resolve()
    p = pathlib.Path(task_path).resolve()
    try:
        rel = p.relative_to(agentic)
    except ValueError:
        raise RuntimeError(f"task path is outside .agenticdoc: {task_path}") from None
    parts = rel.parts
    ok = (
        len(parts) == 4
        and parts[1] == "workers"
        and parts[3] == "task.md"
        and (parts[0] == "_scratch" or not parts[0].startswith(("_", ".")))
    )
    if not ok:
        raise RuntimeError(
            f"invalid worker-task location: {rel} - tasks must live under "
            ".agenticdoc/{key}/workers/<task_key>/task.md (or _scratch/workers/...); "
            "the .agenticdoc root belongs to AgenticTask keys"
        )


def _starter_prompt(task_path: str) -> str:
    """Build the short ASCII turn-starter pointing the worker at its task file.

    The full task body must NEVER travel through argv. On Windows the npm
    `.cmd` shims re-expand `%*` through cmd.exe: any quote / & / | / > sequence
    in a body-sized argument re-tokenizes into shell fragments. Verified
    failure mode (OverCode pch-migration-s1-refactor-2): a task containing
    `rg -n \"pch_out_dir.*\" ...` made cmd execute that fragment
    (\"'pch_out_dir.*' 不是内部或外部命令\") and the worker received a truncated
    prompt, replied with \"请提供具体任务\" and idled out. Flattening newlines
    does not help — quote parity decides, not line breaks. The worker reads the
    self-contained task.md itself instead (pi: PI_WORKER_TASK env is already
    set by _build_env and the worker-side extension reads it; claude/codex:
    the starter names the absolute path and their read tools fetch it).
    """
    p = _require_task_file(task_path)
    return (
        f"Read your task file at {p.resolve()} and execute it end-to-end. "
        "It is self-contained: full instructions, context and acceptance "
        "criteria. Do not ask for the task body; report results when done. "
        "Your final reply MUST open with a one-line conclusion: status plus "
        "key result or blocker."
    )


def _resolve_cli(name: str) -> str:
    """Resolve a worker CLI name to a full executable path.

    On Windows, pi/claude/codex are installed as npm `.cmd` shims. subprocess
    with shell=False calls CreateProcess, which only appends `.exe` to a bare
    name — so ["codex", ...] fails with FileNotFoundError (WinError 2) and every
    worker is marked "failed", i.e. no agent can be invoked. shutil.which honors
    PATHEXT and returns the `.cmd` path, which Popen can execute directly.
    On POSIX this is a harmless PATH lookup that returns the same name's path.
    """
    resolved = shutil.which(name)
    if resolved is None:
        raise RuntimeError(
            f"Worker CLI {name!r} not found on PATH. Install it or add it to PATH."
        )
    return resolved


def _build_command(entry: dict[str, str]) -> list[str]:
    cli = entry["cli"].lower()
    provider = entry.get("provider", "").strip()
    # Per-task model override (from task.md `model:` or `/worker --model`). Empty →
    # keep the historical per-cli default. Model is just a CLI flag; the provider /
    # credential wiring in _build_env is unchanged, so the model must be compatible
    # with the endpoint that (cli, provider) resolves to.
    model = entry.get("model", "").strip()
    task_path = entry["task_path"]
    starter = _starter_prompt(task_path)
    if cli == "pi":
        if provider == "timi":
            return ["pi", "--provider", "timi", "--model", model or "glm-5.3", "-p", starter]
        # Extension reads task.md via PI_WORKER_TASK; -p passes a short starter
        # pointing at the task file (never the body — see _starter_prompt).
        cmd = ["pi"]
        if model:
            cmd += ["--model", model]
        cmd += ["-p", starter]
        return cmd
    elif cli == "codex":
        if provider not in ("", "codex"):
            raise RuntimeError(
                f"Codex workers support only an empty provider or 'codex', got {provider!r}"
            )
        return ["codex", "exec", "-m", model or "gpt-5.6-sol", starter]
    elif cli == "claude":
        cmd = ["claude"]
        if model:
            cmd += ["--model", model]
        cmd += ["-p", starter]
        return cmd
    else:
        return [cli, starter]


# ── Orphan reconcile (AC-012/AC-013, design D-006~D-008) ──────────────────────

def _parse_utc_ts(raw: str) -> datetime.datetime | None:
    """Parse a UTC ISO timestamp carrying `+00:00` or `Z` (spec §5 pitfall).

    The TS side writes Date.toISOString() (`...Z`) while the Python side
    writes iso_now() (`...+00:00`); datetime.fromisoformat only accepts `Z`
    on Python 3.11+, so normalize before parsing. Naive values are read as
    UTC (spec 2.1). Unparseable/empty -> None.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        ts = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return ts


def _row_last_activity(entry: dict[str, str], task_dir: pathlib.Path) -> float | None:
    """Epoch seconds of the newest silence-rule evidence for one queue row:
    max(newest task-dir file mtime, row updated_at).

    updated_at parse failure falls back to dispatched_at; when both are
    unparseable there is no timestamp evidence at all and the caller skips
    the row rather than guessing (AC-013).
    """
    row_ts: datetime.datetime | None = None
    for field in ("updated_at", "dispatched_at"):
        row_ts = _parse_utc_ts(entry.get(field, ""))
        if row_ts is not None:
            break
    if row_ts is None:
        return None
    dir_last = mw_common.task_dir_last_activity(task_dir)
    if dir_last is None:
        return row_ts.timestamp()
    return max(dir_last, row_ts.timestamp())


def _reconcile_orphans(
    project_dir: pathlib.Path,
    running_procs: dict[str, subprocess.Popen[bytes]],
) -> None:
    """Converge orphaned running rows to a terminal status (AC-012/AC-013).

    An orphan row is status==running with task_key not in running_procs —
    spawned by another launcher, or by one that has since died. Own rows are
    never touched (the reap path owns them). Positive evidence (an [END]
    line, or a lone output.md from an old bundle) applies unconditionally
    every poll; the silence rule (presumed dead) additionally yields to
    another live launcher's fresh beat (D-008).
    """
    for entry in _parse_workers_file(_workers_path(project_dir)):
        if entry["status"] != "running":
            continue
        key = entry["task_key"]
        if key in running_procs:
            continue  # own row: never touched by reconcile
        task_dir = pathlib.Path(entry["task_path"]).parent
        end_exit = mw_common.parse_end_exit(task_dir)
        if end_exit is not None:
            status = _exit_to_status(end_exit)
            reason = f"reconcile: [END] exit={end_exit} (orphaned row)"
        elif (task_dir / "output.md").exists():
            status = "failed"
            reason = "reconcile: completed without END marker, status unverifiable — read output.md"
        else:
            # Silence rule (AC-013): no terminal evidence at all.
            last = _row_last_activity(entry, task_dir)
            if last is None:
                continue  # no parseable activity evidence — never guess
            age_min = (time.time() - last) / 60.0
            if age_min < mw_common.orphan_dead_after():
                continue  # within the silence window: keep running
            if mw_common.other_live_launcher(project_dir, os.getpid()):
                print(
                    f"[launcher] reconcile: silence rule yielded for {key!r} "
                    "(another live launcher holds a fresh beat)",
                    file=sys.stderr, flush=True,
                )
                continue
            status = "failed"
            reason = f"reconcile: presumed dead (no activity for {int(age_min)}m)"
        _record_reconcile(entry, reason)
        try:
            _update_status(project_dir, key, status)
        except Exception as exc:  # noqa: BLE001 — never kill the poll loop
            print(
                f"[launcher] reconcile status update failed for {key!r}: {exc}",
                file=sys.stderr, flush=True,
            )


# ── Main loop ─────────────────────────────────────────────────────────────────

def _poll_once(
    project_dir: pathlib.Path,
    config: dict,
    running_procs: dict[str, subprocess.Popen[bytes]],
    log_handles: dict[str, object],
    pending_queue: list[dict[str, str]],
    max_workers: int | None,
) -> None:
    """One launcher poll cycle: beat, archive stale, reap, reconcile, discover, spawn."""
    # D-008: refresh this launcher's beat first — it is how another
    # launcher's silence rule knows we are live (and ours knows of them).
    mw_common.launcher_beat_write(project_dir, os.getpid())

    archived = mw_common.archive_stale_entries(project_dir)
    if archived:
        print(
            f"[launcher] archived stale entries: {', '.join(archived)}",
            file=sys.stderr, flush=True,
        )

    # Reap finished processes
    finished = [k for k, p in running_procs.items() if p.poll() is not None]
    for key in finished:
        proc = running_procs.pop(key)
        code = proc.returncode if proc.returncode is not None else 1
        status = _exit_to_status(code)
        _update_status(project_dir, key, status)
        # Close the per-task worker.log handle now the process has exited.
        lh = log_handles.pop(key, None)
        if lh is not None:
            try:
                lh.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
        # Drain queue now a slot is free
        if pending_queue:
            next_entry = pending_queue.pop(0)
            _spawn(next_entry, project_dir, config, running_procs, log_handles)

    # Reconcile orphaned running rows (AC-012/AC-013): after reap (rows just
    # reaped are already terminal) and before discover/spawn.
    _reconcile_orphans(project_dir, running_procs)

    # Discover new pending tasks
    entries = _parse_workers_file(_workers_path(project_dir))
    for entry in entries:
        key = entry["task_key"]
        if entry["status"] != "pending":
            continue
        if key in running_procs:
            continue  # AC-008: no duplicate spawn
        # Location contract (D-001 isolation): reject root-level / misplaced
        # task dirs loudly instead of spawning them.
        try:
            _validate_task_path(project_dir, entry["task_path"])
        except RuntimeError as exc:
            _record_spawn_failure(entry, str(exc))
            try:
                _update_status(project_dir, key, "failed")
            except Exception:  # noqa: BLE001 — never mask the poll loop
                pass
            continue
        if max_workers and len(running_procs) >= max_workers:
            if not any(q["task_key"] == key for q in pending_queue):
                pending_queue.append(entry)  # AC-007
            continue
        _spawn(entry, project_dir, config, running_procs, log_handles)


def run(
    project_dir: pathlib.Path,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_workers: int | None = None,
    dry_run: bool = False,
    providers_path: pathlib.Path | None = None,
    port_overrides: dict[str, int] | None = None,
) -> None:
    """Main launcher loop. Runs until interrupted."""
    config = _load_providers(providers_path or (pathlib.Path(__file__).parent / "providers.json"))

    # Apply port overrides from CLI (--pi-port, --claude-port, etc.)
    if port_overrides:
        for provider_key, port in port_overrides.items():
            if provider_key in config.get("providers", {}):
                config["providers"][provider_key] = {
                    **config["providers"][provider_key], "port": port,
                }

    # task_key -> Popen
    running_procs: dict[str, subprocess.Popen[bytes]] = {}
    # task_key -> open worker.log handle (closed when the process is reaped)
    log_handles: dict[str, object] = {}
    # Queue for tasks waiting on max_workers limit
    pending_queue: list[dict[str, str]] = []

    if dry_run:
        _dry_run(project_dir, config)
        return

    while True:
        try:
            _poll_once(project_dir, config, running_procs, log_handles, pending_queue, max_workers)
        except Exception as exc:  # noqa: BLE001 — one bad poll must never kill the loop
            print(f"[launcher] poll error (continuing): {exc}", file=sys.stderr, flush=True)

        time.sleep(poll_interval)


def _worker_cwd(project_dir: pathlib.Path) -> pathlib.Path:
    """Dual-workspace spawn root (mw-dual-workspace D-001): worker cwd is the
    game root in dual mode, the control workspace in single mode. Fail closed:
    an unusable target.yml refuses the spawn (recorded per-task by _spawn's
    isolation handler) instead of silently falling back to the control root."""
    try:
        config = mw_common.load_target_config(project_dir)
    except mw_common.TargetConfigError as e:
        raise RuntimeError(f"target.yml is unusable ({e.kind}): {e}") from None
    if config["mode"] == "dual":
        return pathlib.Path(config["game_root"])
    return project_dir


def _spawn(
    entry: dict[str, str],
    project_dir: pathlib.Path,
    config: dict,
    running_procs: dict[str, subprocess.Popen[bytes]],
    log_handles: dict[str, object] | None = None,
) -> None:
    """Spawn one worker. Any per-task failure marks it failed and continues.

    Design D-001: a missing credential (or any other per-task error) is
    isolated to the task — it can never take down the launcher or mw serve.
    """
    try:
        env = _build_env(entry, config)
        cmd = _build_command(entry)
        # Resolve the CLI binary to a full path so Windows npm `.cmd` shims are
        # found (CreateProcess only appends `.exe`). See _resolve_cli.
        cmd[0] = _resolve_cli(cmd[0])
        # Capture worker stdout+stderr into a per-task worker.log for diagnosability
        log_file = None
        try:
            log_file = open(_worker_log_path(entry), "wb")  # noqa: SIM115 — closed at reap (or below)
        except OSError:
            log_file = None
        # subprocess.Popen with list args (no shell=True — AC-023); cwd is the
        # game root in dual mode, else the control workspace (D-001) — relative
        # tool paths stay anchored to the target project.
        spawn_kwargs: dict = {
            "env": env, "cwd": str(_worker_cwd(project_dir)),
            "stdout": log_file if log_file is not None else subprocess.DEVNULL,
            "stderr": subprocess.STDOUT if log_file is not None else subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            spawn_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        proc = subprocess.Popen(cmd, **spawn_kwargs)  # noqa: S603
        running_procs[entry["task_key"]] = proc
        if log_file is not None:
            # Keep the handle open until the process is reaped (run() closes it).
            # Without a tracker (e.g. unit tests), close now — the child kept its own fd.
            if log_handles is not None:
                log_handles[entry["task_key"]] = log_file
            else:
                log_file.close()
        _update_status(project_dir, entry["task_key"], "running")
    except Exception as exc:  # noqa: BLE001 — per-task isolation (design D-001)
        msg = str(exc)
        print(f"[launcher] spawn failed for {entry['task_key']!r}: {msg}", file=sys.stderr, flush=True)
        _record_spawn_failure(entry, msg)
        try:
            _update_status(project_dir, entry["task_key"], "failed")
        except Exception as exc2:  # noqa: BLE001 — never mask the loop
            print(f"[launcher] status update failed for {entry['task_key']!r}: {exc2}", file=sys.stderr, flush=True)


def _mask_env_value(key: str, value: str) -> str:
    lower = key.lower()
    if "key" in lower or "token" in lower or "secret" in lower or "password" in lower:
        return "***"
    return value


def _dry_run(project_dir: pathlib.Path, config: dict) -> None:
    entries = _parse_workers_file(_workers_path(project_dir))
    pending = [e for e in entries if e["status"] == "pending"]
    for entry in pending:
        try:
            cmd = _build_command(entry)
            env = _build_env(entry, config)
        except Exception as exc:  # noqa: BLE001 — report, do not crash
            print(f"[DRY-RUN] {entry['task_key']}: cannot build ({exc})")
            continue
        relevant_keys = [k for k in env if k not in os.environ or env[k] != os.environ.get(k)]
        env_display = " ".join(f"{k}={_mask_env_value(k, env[k])}" for k in relevant_keys)
        # Truncate long prompts in command display
        display_cmd = list(cmd)
        if len(display_cmd) > 2 and len(display_cmd[-1]) > 120:
            display_cmd[-1] = display_cmd[-1][:120] + "..."
        print(f"[DRY-RUN] {env_display} {' '.join(display_cmd)}")
        print(f"  task.md: {entry['task_path']}")


# ── CLI entry ─────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-Workers launcher")
    parser.add_argument("--project", required=True, help="Project directory")
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--providers", default=None, help="Path to providers.json")
    # Port overrides: map provider key to proxy port (mirrors mw serve flags)
    parser.add_argument("--pi-port", type=int, default=None, help="Override pi provider proxy port")
    parser.add_argument("--claude-port", type=int, default=None, help="Override claude-cli provider proxy port")
    parser.add_argument("--deepseek-port", type=int, default=None, help="Override deepseek provider proxy port")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    project = pathlib.Path(args.project).resolve()
    providers_path = pathlib.Path(args.providers) if args.providers else None
    port_overrides: dict[str, int] = {}
    if args.pi_port is not None:
        port_overrides["claude"] = args.pi_port  # pi CLI uses the "claude" provider key
    if args.claude_port is not None:
        port_overrides["claude-cli"] = args.claude_port
    if args.deepseek_port is not None:
        port_overrides["deepseek"] = args.deepseek_port
    run(
        project_dir=project,
        poll_interval=args.poll_interval,
        max_workers=args.max_workers,
        dry_run=args.dry_run,
        providers_path=providers_path,
        port_overrides=port_overrides or None,
    )

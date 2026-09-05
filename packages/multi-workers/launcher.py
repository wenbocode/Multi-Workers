"""
launcher.py — Multi-Workers task launcher.

Polls _workers.parallel for pending tasks and spawns worker processes.
Managed by mw serve; do not run directly in production.

mw-dispatch-reliability changes (design D-001/D-004):
- A task whose credentials/route cannot be resolved is marked failed with the
  reason persisted to its worker.log; it never kills the launcher loop.
- Each poll archives queue entries whose task.md no longer exists.
- Credential resolution and the file bus live in mw_common (single source).
"""

from __future__ import annotations

import argparse
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
        "criteria. Do not ask for the task body; report results when done."
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


# ── Main loop ─────────────────────────────────────────────────────────────────

def _poll_once(
    project_dir: pathlib.Path,
    config: dict,
    running_procs: dict[str, subprocess.Popen[bytes]],
    log_handles: dict[str, object],
    pending_queue: list[dict[str, str]],
    max_workers: int | None,
) -> None:
    """One launcher poll cycle: archive stale, reap, discover, spawn."""
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

    # Discover new pending tasks
    entries = _parse_workers_file(_workers_path(project_dir))
    for entry in entries:
        key = entry["task_key"]
        if entry["status"] != "pending":
            continue
        if key in running_procs:
            continue  # AC-008: no duplicate spawn
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
        # subprocess.Popen with list args (no shell=True — AC-023); cwd keeps relative paths consistent
        spawn_kwargs: dict = {
            "env": env, "cwd": str(project_dir),
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

"""
launcher.py — Multi-Workers task launcher.

Polls _workers.parallel for pending tasks and spawns worker processes.
Managed by mw serve; do not run directly in production.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

DEFAULT_POLL_INTERVAL: int = 5  # seconds — AC-001: must be <= 5

VALID_STATUSES = {"pending", "running", "done", "failed", "needs-clarification"}

# ── File-bus helpers ──────────────────────────────────────────────────────────

def _lock_path(project_dir: pathlib.Path) -> pathlib.Path:
    return project_dir / ".mw" / "workers.lock"


def _workers_path(project_dir: pathlib.Path) -> pathlib.Path:
    return project_dir / ".agenticdoc" / "_workers.parallel"


def _parse_workers_file(workers_path: pathlib.Path) -> list[dict[str, str]]:
    if not workers_path.exists():
        return []
    entries = []
    for line in workers_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 7:
            continue
        entries.append({
            "task_key": parts[0],
            "status": parts[1],
            "cli": parts[2],
            "provider": parts[3],
            "task_path": parts[4],
            "dispatched_at": parts[5],
            "updated_at": parts[6],
        })
    return entries


def _serialize_entry(entry: dict[str, str]) -> str:
    return " | ".join([
        entry["task_key"],
        entry["status"],
        entry["cli"],
        entry["provider"],
        entry["task_path"],
        entry["dispatched_at"],
        entry["updated_at"],
    ])


def _acquire_lock(lock_path: pathlib.Path, retries: int = 20, base_delay: float = 0.05) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries + 1):
        try:
            # O_CREAT | O_EXCL semantics: fails if file already exists
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if attempt == retries:
                raise RuntimeError(f"Could not acquire lock at {lock_path} after {retries} retries")
            time.sleep(base_delay * (2 ** attempt))


def _release_lock(lock_path: pathlib.Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def _update_status(project_dir: pathlib.Path, task_key: str, status: str) -> None:
    workers_path = _workers_path(project_dir)
    lock_path = _lock_path(project_dir)
    _acquire_lock(lock_path)
    try:
        entries = _parse_workers_file(workers_path)
        updated_at = _iso_now()
        for entry in entries:
            if entry["task_key"] == task_key:
                entry["status"] = status
                entry["updated_at"] = updated_at
        content = "\n".join(_serialize_entry(e) for e in entries) + "\n"
        tmp_path = pathlib.Path(str(workers_path) + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(workers_path)
    finally:
        _release_lock(lock_path)


# ── Provider / env helpers ────────────────────────────────────────────────────

# Credential env vars that are never registered in providers.json but must still
# be stripped from every worker env unless that worker explicitly uses them.
_EXTRA_CREDENTIAL_VARS: frozenset[str] = frozenset([
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "TIMI_API_KEY",
    "TIMI_BASE_URL",
])


def _load_providers(providers_json_path: pathlib.Path) -> dict[str, dict[str, str]]:
    if providers_json_path.exists():
        return json.loads(providers_json_path.read_text(encoding="utf-8"))
    # Fallback defaults (AC-002~004)
    return {
        "claude":     {"port": 7001, "base_url_env": "ANTHROPIC_BASE_URL",  "api_key_env": "ANTHROPIC_API_KEY"},
        "claude-cli": {"port": 7003, "base_url_env": "ANTHROPIC_BASE_URL",  "api_key_env": "ANTHROPIC_AUTH_TOKEN"},
        "deepseek":   {"port": 7004, "base_url_env": "DEEPSEEK_BASE_URL",   "api_key_env": "DEEPSEEK_API_KEY"},
    }


def _build_env(entry: dict[str, str], providers: dict[str, dict[str, str]]) -> dict[str, str]:
    """Build the environment dict for a worker process (AC-002~004, AC-008~010, AC-024)."""
    cli = entry["cli"].lower()
    provider = entry.get("provider", "").strip()

    # Pi + timi: use Timi credentials directly (no localhost proxy) (AC-008)
    if cli == "pi" and provider == "timi":
        timi_key = os.environ.get("TIMI_API_KEY")
        if timi_key is None:
            raise RuntimeError("Required environment variable 'TIMI_API_KEY' is not set.")
        env = dict(os.environ)
        # Strip all registered provider credentials
        for p in providers.values():
            env.pop(str(p.get("base_url_env", "")), None)
            env.pop(str(p.get("api_key_env", "")), None)
        # Strip extra known credential vars not in providers.json
        for var in _EXTRA_CREDENTIAL_VARS:
            env.pop(var, None)
        # Re-inject only what this path needs
        env["TIMI_API_KEY"] = timi_key
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
        env = dict(os.environ)
        for p in providers.values():
            env.pop(str(p.get("base_url_env", "")), None)
            env.pop(str(p.get("api_key_env", "")), None)
        for var in _EXTRA_CREDENTIAL_VARS:
            env.pop(var, None)
        return env

    # Generic port-based proxy path (Pi empty provider, claude, deepseek, etc.)
    # "claude" CLI binary uses claude-cli provider (port 7003, ANTHROPIC_AUTH_TOKEN)
    # "pi" without explicit provider uses claude provider (port 7001)
    _cli_default_provider = {"claude": "claude-cli"}
    provider_key = provider or _cli_default_provider.get(cli, cli)

    cfg = providers.get(provider_key) or providers.get(cli) or {}

    port = cfg.get("port", 7001)
    base_url_env: str = cfg.get("base_url_env", "ANTHROPIC_BASE_URL")
    api_key_env: str = cfg.get("api_key_env", "ANTHROPIC_API_KEY")

    base_url = f"http://localhost:{port}"
    api_key = os.environ.get(api_key_env)
    if api_key is None:
        raise RuntimeError(
            f"Required environment variable {api_key_env!r} is not set. "
            "Set it before starting mw serve."
        )

    env = dict(os.environ)

    # Remove all known provider base_url and api_key env vars to prevent leakage (AC-024, AC-025)
    all_base_url_vars = {str(p.get("base_url_env", "")) for p in providers.values() if p.get("base_url_env")}
    for var in all_base_url_vars:
        env.pop(var, None)
    all_api_key_vars = {str(p.get("api_key_env", "")) for p in providers.values() if p.get("api_key_env")}
    for var in all_api_key_vars:
        env.pop(var, None)
    # Strip extra known credential vars not in providers.json
    for var in _EXTRA_CREDENTIAL_VARS:
        env.pop(var, None)

    env[base_url_env] = base_url
    env[api_key_env] = api_key

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


def _read_task_content(task_path: str) -> str:
    p = pathlib.Path(task_path)
    if not p.exists():
        raise RuntimeError(f"task.md not found: {task_path}")
    return p.read_text(encoding="utf-8").strip()


def _build_command(entry: dict[str, str]) -> list[str]:
    cli = entry["cli"].lower()
    provider = entry.get("provider", "").strip()
    task_path = entry["task_path"]
    task_content = _read_task_content(task_path)
    if cli == "pi":
        if provider == "timi":
            return ["pi", "--provider", "timi", "--model", "gpt-5.6-sol", "-p", task_content]
        # Extension reads task.md via PI_WORKER_TASK; -p passes prompt to start the agent turn
        return ["pi", "-p", task_content]
    elif cli == "codex":
        if provider not in ("", "codex"):
            raise RuntimeError(
                f"Codex workers support only an empty provider or 'codex', got {provider!r}"
            )
        return ["codex", "exec", "-m", "gpt-5.6-sol", task_content]
    elif cli == "claude":
        return ["claude", "-p", task_content]
    else:
        return [cli, task_content]


def _iso_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(
    project_dir: pathlib.Path,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_workers: int | None = None,
    dry_run: bool = False,
    providers_path: pathlib.Path | None = None,
    port_overrides: dict[str, int] | None = None,
) -> None:
    """Main launcher loop. Runs until interrupted."""
    providers_json = providers_path or (pathlib.Path(__file__).parent / "providers.json")
    providers = _load_providers(providers_json)

    # Apply port overrides from CLI (--pi-port, --claude-port, etc.)
    if port_overrides:
        for provider_key, port in port_overrides.items():
            if provider_key in providers:
                providers[provider_key] = {**providers[provider_key], "port": port}

    # task_key -> Popen
    running_procs: dict[str, subprocess.Popen[bytes]] = {}
    # Queue for tasks waiting on max_workers limit
    pending_queue: list[dict[str, str]] = []

    if dry_run:
        _dry_run(project_dir, providers)
        return

    while True:
        try:
            # Reap finished processes
            finished = [k for k, p in running_procs.items() if p.poll() is not None]
            for key in finished:
                proc = running_procs.pop(key)
                code = proc.returncode if proc.returncode is not None else 1
                status = _exit_to_status(code)
                _update_status(project_dir, key, status)
                # Drain queue now a slot is free
                if pending_queue:
                    next_entry = pending_queue.pop(0)
                    _spawn(next_entry, project_dir, providers, running_procs)

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
                _spawn(entry, project_dir, providers, running_procs)
        except _FatalLauncherError:
            raise  # propagate out of loop → launcher exits nonzero
        except Exception as exc:
            print(f"[launcher] poll error (continuing): {exc}", file=sys.stderr, flush=True)

        time.sleep(poll_interval)


class _FatalLauncherError(Exception):
    """Unrecoverable configuration error — launcher must exit immediately."""


def _spawn(
    entry: dict[str, str],
    project_dir: pathlib.Path,
    providers: dict[str, dict[str, str]],
    running_procs: dict[str, subprocess.Popen[bytes]],
) -> None:
    try:
        env = _build_env(entry, providers)
        cmd = _build_command(entry)
        # subprocess.Popen with list args (no shell=True — AC-023); cwd keeps relative paths consistent
        proc = subprocess.Popen(cmd, env=env, cwd=str(project_dir))  # noqa: S603
        running_procs[entry["task_key"]] = proc
        _update_status(project_dir, entry["task_key"], "running")
    except RuntimeError as exc:
        msg = str(exc)
        if "Required environment variable" in msg:
            # Missing credential affects every future task of this type — exit launcher
            raise _FatalLauncherError(msg) from exc
        # Per-task errors (bad provider, missing task.md): mark failed and continue
        print(f"[launcher] spawn failed for {entry['task_key']!r}: {exc}", file=sys.stderr, flush=True)
        _update_status(project_dir, entry["task_key"], "failed")
    except Exception as exc:
        # Unexpected error (e.g. binary not found): mark task failed and continue
        print(f"[launcher] spawn error for {entry['task_key']!r}: {exc}", file=sys.stderr, flush=True)
        _update_status(project_dir, entry["task_key"], "failed")


def _mask_env_value(key: str, value: str) -> str:
    lower = key.lower()
    if "key" in lower or "token" in lower or "secret" in lower or "password" in lower:
        return "***"
    return value


def _dry_run(project_dir: pathlib.Path, providers: dict[str, dict[str, str]]) -> None:
    entries = _parse_workers_file(_workers_path(project_dir))
    pending = [e for e in entries if e["status"] == "pending"]
    for entry in pending:
        cmd = _build_command(entry)
        env = _build_env(entry, providers)
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
    try:
        run(
            project_dir=project,
            poll_interval=args.poll_interval,
            max_workers=args.max_workers,
            dry_run=args.dry_run,
            providers_path=providers_path,
            port_overrides=port_overrides or None,
        )
    except _FatalLauncherError as exc:
        print(f"[launcher] FATAL: {exc}", file=sys.stderr)
        sys.exit(1)

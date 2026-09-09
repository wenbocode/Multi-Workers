"""
mw_common.py 鈥?shared Multi-Workers core.

Single source for provider/credential config, route precheck, stale-entry
archival, and doctor diagnostics. Imported by mw.py and launcher.py so the
serve entry, the dispatcher, and both doctor frontends stay single-sourced
(design D-003/D-005 of mw-dispatch-reliability).

Credential config schema (providers.json):

    {
      "credentials": {
        "<name>": { "sources": [
          { "env": "VAR_NAME" },
          { "file": "~/path.toml", "format": "toml", "field": "auth.api_key" }
        ]}
      },
      "providers": {
        "<route>": {
          "port": 7001,                  # optional (direct routes have none)
          "base_url_env": "VAR",         # env var the worker sees as base URL
          "api_key_env": "VAR",          # env var the worker sees as key
          "credential": "<name>"         # credential chain to resolve
        }
      }
    }

Sources are tried in order; the first one that yields a value wins. `file`
sources support toml/json/plain plus a dotted `field` path. Adding a route is
a config-only change (AC-017).
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import time
import sys
from typing import Mapping

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover - very old interpreters
    tomllib = None  # type: ignore[assignment]

# Credential env vars that are never declared in providers.json but must still
# be stripped from every worker env (kept from the pre-schema launcher).
EXTRA_CREDENTIAL_VARS: frozenset[str] = frozenset([
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "TIMI_BASE_URL",
])

# Fallback credential/env wiring used when providers.json is missing or
# unreadable. Mirrors the shipped providers.json exactly.
_DEFAULT_CONFIG: dict = {
    "credentials": {
        "anthropic": {"sources": [{"env": "ANTHROPIC_API_KEY"}]},
        "anthropic-auth": {"sources": [{"env": "ANTHROPIC_AUTH_TOKEN"}]},
        "deepseek": {"sources": [{"env": "DEEPSEEK_API_KEY"}]},
        "timi": {"sources": [
            {"env": "TIMI_API_KEY"},
            {"file": "~/.pi/agent/auth.json", "format": "json", "field": "timi.key"},
        ]},
    },
    "providers": {
        "claude": {
            "port": 7001, "base_url_env": "ANTHROPIC_BASE_URL",
            "api_key_env": "ANTHROPIC_API_KEY", "credential": "anthropic",
        },
        "claude-cli": {
            "port": 7003, "base_url_env": "ANTHROPIC_BASE_URL",
            "api_key_env": "ANTHROPIC_AUTH_TOKEN", "credential": "anthropic-auth",
        },
        "deepseek": {
            "port": 7004, "base_url_env": "DEEPSEEK_BASE_URL",
            "api_key_env": "DEEPSEEK_API_KEY", "credential": "deepseek",
        },
        "timi": {"api_key_env": "TIMI_API_KEY", "credential": "timi"},
    },
}

# CLI name -> default route key when a task leaves `provider` empty.
# pi tasks default to the claude (proxied) route, claude tasks to claude-cli
# (oauth token), matching the pre-schema launcher behavior and dispatch-table.md.
CLI_DEFAULT_PROVIDER: dict[str, str] = {"pi": "claude", "claude": "claude-cli"}

STALE_FILE_NAME = "_workers.stale.parallel"
STALE_REASON = "task.md not found"

# Entries in these statuses are history: a missing task.md is harmless (the dir
# may have been cleaned up), so only non-terminal entries get archived.
_TERMINAL_STATUSES = {"done", "failed", "needs-clarification"}


def iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# 鈹€鈹€ Config loading 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def default_config() -> dict:
    """Deep-ish copy of the built-in default config."""
    return json.loads(json.dumps(_DEFAULT_CONFIG))


def load_providers(path: pathlib.Path | None) -> dict:
    """Load the providers+credentials config.

    Returns the normalized {"credentials": ..., "providers": ...} dict. Falls
    back to defaults when the file is missing or invalid. Legacy flat provider
    maps (pre-schema, api_key_env per route) are upgraded in memory.
    """
    if path is None or not path.exists():
        return default_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_config()
    if not isinstance(data, dict):
        return default_config()
    if isinstance(data.get("credentials"), dict) and isinstance(data.get("providers"), dict):
        return data
    # Legacy schema: flat {route: {port, base_url_env, api_key_env}} map.
    credentials: dict = {}
    providers: dict = {}
    for name, cfg in data.items():
        if not isinstance(cfg, dict):
            continue
        env_name = cfg.get("api_key_env", "")
        if env_name:
            credentials[f"{name}-key"] = {"sources": [{"env": env_name}]}
            providers[name] = {**cfg, "credential": f"{name}-key"}
        else:
            providers[name] = dict(cfg)
    return {"credentials": credentials, "providers": providers}


# 鈹€鈹€ Credential resolution 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _dig(data: object, dotted: str) -> object:
    """Follow a dotted path through nested dicts. Returns None on any miss."""
    cur: object = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _read_credential_file(raw_path: str, fmt: str, field: str) -> str | None:
    path = pathlib.Path(os.path.expanduser(raw_path))
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if fmt == "toml":
        if tomllib is None:
            return None
        try:
            data = tomllib.loads(text)
        except Exception:
            return None
        value = _dig(data, field) if field else data
        return value if isinstance(value, str) and value else None
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        value = _dig(data, field) if field else data
        return value if isinstance(value, str) and value else None
    # plain: whole trimmed file content
    return text.strip() or None


def resolve_credential(
    cred_cfg: dict | None,
    env: Mapping[str, str] | None = None,
) -> tuple[str | None, dict]:
    """Resolve a credential through its source chain (env -> file fallback).

    Returns (value, source) where source describes the winning source as
    {"kind": "env"|"file", ...} for precheck/doctor reporting, or {} when the
    credential could not be resolved.
    """
    if env is None:
        env = os.environ
    if not isinstance(cred_cfg, dict):
        return None, {}
    for src in cred_cfg.get("sources", []):
        if not isinstance(src, dict):
            continue
        env_name = src.get("env")
        if env_name:
            value = env.get(env_name)
            if value:
                return value, {"kind": "env", "name": env_name}
        file_path = src.get("file")
        if file_path:
            value = _read_credential_file(file_path, src.get("format", "plain"), src.get("field", ""))
            if value:
                return value, {
                    "kind": "file",
                    "path": file_path,
                    "field": src.get("field", ""),
                }
    return None, {}


def credential_env_names(config: dict) -> set[str]:
    """All env var names declared anywhere in the credential chains.

    Callers use this to derive the strip set for worker envs (AC-024/AC-025
    isolation semantics preserved).
    """
    names: set[str] = set()
    for cred in config.get("credentials", {}).values():
        if not isinstance(cred, dict):
            continue
        for src in cred.get("sources", []):
            if isinstance(src, dict) and src.get("env"):
                names.add(str(src["env"]))
    return names


def credential_inject_env(cred_cfg: dict | None) -> str | None:
    """The env var name a resolved credential is injected under in worker envs.

    Defaults to the first declared env source (the historical api_key_env).
    """
    if not isinstance(cred_cfg, dict):
        return None
    for src in cred_cfg.get("sources", []):
        if isinstance(src, dict) and src.get("env"):
            return str(src["env"])
    return None


def describe_missing(cred_cfg: dict | None) -> str:
    """Human-readable list of every source that failed, for logs/doctor."""
    if not isinstance(cred_cfg, dict) or not cred_cfg.get("sources"):
        return "no credential sources declared"
    parts: list[str] = []
    for src in cred_cfg.get("sources", []):
        if not isinstance(src, dict):
            continue
        if src.get("env"):
            parts.append(f"env {src['env']} unset")
        if src.get("file"):
            parts.append(f"file {src['file']} unreadable")
    return "; ".join(parts) if parts else "no credential sources declared"


# 鈹€鈹€ Route resolution 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def route_for(config: dict, cli: str, provider: str) -> dict:
    """Effective provider config for a (cli, provider) task route.

    Returns {"provider_key", "port", "base_url_env", "api_key_env",
    "credential"} with historical defaults when the route is undeclared.
    """
    cli = cli.lower()
    provider = (provider or "").strip()
    key = provider or CLI_DEFAULT_PROVIDER.get(cli, cli)
    cfg = config.get("providers", {}).get(key) or config.get("providers", {}).get(cli) or {}
    cred_name = cfg.get("credential") or key
    cred = config.get("credentials", {}).get(cred_name)
    api_key_env = cfg.get("api_key_env") or credential_inject_env(cred) or "ANTHROPIC_API_KEY"
    return {
        "provider_key": key,
        "port": cfg.get("port", 7001),
        "base_url_env": cfg.get("base_url_env", "ANTHROPIC_BASE_URL"),
        "api_key_env": api_key_env,
        "credential": cred_name,
    }


# 鈹€鈹€ Route precheck 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def route_precheck(config: dict, env: Mapping[str, str] | None = None) -> dict:
    """Credential availability snapshot for every dispatchable route.

    Returns {"routes": [...], "all_missing": bool}. Every route gets one entry:
    {"route", "available", "source", "missing"}. The codex-native route is
    checked via PATH lookup (it uses codex's own config, not env credentials).
    """
    if env is None:
        env = os.environ
    statuses: list[dict] = []
    for name, cfg in sorted(config.get("providers", {}).items()):
        if not isinstance(cfg, dict):
            continue
        cred_name = cfg.get("credential") or name
        cred = config.get("credentials", {}).get(cred_name)
        if cred is None:
            statuses.append({
                "route": name,
                "available": False,
                "source": {},
                "missing": f"credential '{cred_name}' not declared in config",
            })
            continue
        value, source = resolve_credential(cred, env)
        statuses.append({
            "route": name,
            "available": value is not None,
            "source": source,
            "missing": None if value is not None else describe_missing(cred),
        })
    codex_available = shutil.which("codex") is not None
    statuses.append({
        "route": "codex-native",
        "available": codex_available,
        "source": {"kind": "native"},
        "missing": None if codex_available else "codex binary not found on PATH",
    })
    return {"routes": statuses, "all_missing": all(not s["available"] for s in statuses)}


# 鈹€鈹€ File bus: _workers.parallel parse/serialize/lock/status 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def workers_path(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".agenticdoc" / "_workers.parallel"


def stale_path(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".agenticdoc" / STALE_FILE_NAME


def lock_path(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".mw" / "workers.lock"


def parse_workers_file(path: pathlib.Path) -> list[dict[str, str]]:
    """Parse _workers.parallel. Tolerates 7-column legacy and 8-column rows."""
    if not path.exists():
        return []
    entries: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) not in (7, 8):
            continue
        entries.append({
            "task_key": parts[0],
            "status": parts[1],
            "cli": parts[2],
            "provider": parts[3],
            "task_path": parts[4],
            "dispatched_at": parts[5],
            "updated_at": parts[6],
            "model": parts[7] if len(parts) == 8 else "",
        })
    return entries


def serialize_entry(entry: dict[str, str]) -> str:
    return " | ".join([
        entry["task_key"],
        entry["status"],
        entry["cli"],
        entry["provider"],
        entry["task_path"],
        entry["dispatched_at"],
        entry["updated_at"],
        entry.get("model", ""),
    ])


def acquire_lock(lock_file: pathlib.Path, retries: int = 20, base_delay: float = 0.05) -> None:
    """Exclusive lock via O_CREAT|O_EXCL. Same protocol as the TS side."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries + 1):
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if attempt == retries:
                raise RuntimeError(f"Could not acquire lock at {lock_file} after {retries} retries")
            import time
            time.sleep(base_delay * (2 ** attempt))


def release_lock(lock_file: pathlib.Path) -> None:
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass


def _write_workers_file(path: pathlib.Path, entries: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(serialize_entry(e) for e in entries) + "\n"
    tmp_path = pathlib.Path(str(path) + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def update_status(project_dir: pathlib.Path, task_key: str, status: str) -> None:
    """Update one task's status under the file lock (launcher-side writer)."""
    wpath = workers_path(project_dir)
    lock = lock_path(project_dir)
    acquire_lock(lock)
    try:
        entries = parse_workers_file(wpath)
        updated_at = iso_now()
        for entry in entries:
            if entry["task_key"] == task_key:
                entry["status"] = status
                entry["updated_at"] = updated_at
        _write_workers_file(wpath, entries)
    finally:
        release_lock(lock)


def archive_stale_entries(project_dir: pathlib.Path) -> list[str]:
    """Move queue entries whose task.md no longer exists into the stale archive.

    Appends `original line | archived_at | reason` rows to
    `.agenticdoc/_workers.stale.parallel` (never truncated) and rewrites
    `_workers.parallel` without the stale rows. Idempotent; lock-protected.
    Returns the archived task keys.
    """
    wpath = workers_path(project_dir)
    spath = stale_path(project_dir)
    lock = lock_path(project_dir)
    if not wpath.exists():
        return []
    acquire_lock(lock)
    try:
        entries = parse_workers_file(wpath)
        stale_idx = {
            i for i, e in enumerate(entries)
            if e["status"] not in _TERMINAL_STATUSES
            and not pathlib.Path(e["task_path"]).exists()
        }
        if not stale_idx:
            return []
        stale = [entries[i] for i in sorted(stale_idx)]
        kept = [e for i, e in enumerate(entries) if i not in stale_idx]
        now = iso_now()
        spath.parent.mkdir(parents=True, exist_ok=True)
        with spath.open("a", encoding="utf-8") as fh:
            for entry in stale:
                fh.write(f"{serialize_entry(entry)} | {now} | {STALE_REASON}\n")
        _write_workers_file(wpath, kept)
        return [e["task_key"] for e in stale]
    finally:
        release_lock(lock)


# ── PID / port helpers (shared by mw.py serve/status/stop and doctor) ─────────

def pid_file(project_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_dir) / ".mw" / "mw.pid"


def _is_alive_win32(pid: int) -> bool:
    """Read-only liveness check via Win32 OpenProcess + GetExitCodeProcess."""
    import ctypes
    import ctypes.wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _is_alive(pid: int) -> bool:
    if sys.platform == "win32":
        return _is_alive_win32(pid)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def check_pid(pid_path: pathlib.Path) -> int | None:
    """Live PID from a pid file, or None when absent/dead/malformed."""
    if not pid_path.exists():
        return None
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if _is_alive(pid) else None


def port_is_bound(port: int) -> bool:
    """True if something is listening on 127.0.0.1:port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def port_owner_pids(port: int) -> list[int]:
    """Best-effort netstat lookup of the PID(s) LISTENING on port."""
    cmd = ["netstat", "-ano"] if sys.platform == "win32" else ["netstat", "-an"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for line in (result.stdout or "").splitlines():
        if f":{port} " in line and "LISTEN" in line.upper():
            parts = line.split()
            try:
                pids.append(int(parts[-1]))
            except (ValueError, IndexError):
                continue
    return sorted(set(pids))


def global_ext_dir() -> pathlib.Path:
    """pi's global extensions dir: $PI_CODING_AGENT_DIR/extensions if set, else
    ~/.pi/agent/extensions (mirrors getAgentDir() in coding-agent config)."""
    env_dir = os.environ.get("PI_CODING_AGENT_DIR")
    base = pathlib.Path(env_dir).expanduser() if env_dir else (pathlib.Path.home() / ".pi" / "agent")
    return base / "extensions"


# ── Doctor ────────────────────────────────────────────────────────────────────

# Extension source dir, relative to this package (repo layout).
_EXT_SRC_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "coding-agent" / "src" / "extensions" / "agent-team-loop"
)
_TERMINAL_STATUSES = {"done", "failed", "needs-clarification"}


def doctor_fix(project_dir: pathlib.Path) -> list[str]:
    """Apply the auto-fixable findings. Returns human-readable action list.

    Auto-fixed: stale queue entries (archived), stale mw.pid (removed).
    Report-only (suggestions): expired bundle, orphan proxy."""
    actions: list[str] = []
    pfile = pid_file(project_dir)
    if pfile.exists() and check_pid(pfile) is None:
        try:
            pfile.unlink()
            actions.append(f"removed stale PID file: {pfile}")
        except OSError:
            pass
    archived = archive_stale_entries(project_dir)
    if archived:
        actions.append(f"archived stale entries: {', '.join(archived)}")
    return actions


def _doctor_service(project_dir: pathlib.Path) -> dict:
    pfile = pid_file(project_dir)
    pid = check_pid(pfile)
    return {
        "running": pid is not None,
        "pid": pid,
        "pid_file": str(pfile),
    }


def _doctor_proxy(config: dict) -> list[dict]:
    ports: list[dict] = []
    for name, cfg in sorted(config.get("providers", {}).items()):
        if isinstance(cfg, dict) and cfg.get("port"):
            port = int(cfg["port"])
            ports.append({"route": name, "port": port, "listening": port_is_bound(port)})
    return ports


def _doctor_orphan(service: dict, proxy: list[dict]) -> dict:
    if service["running"]:
        return {"detected": False, "ports": []}
    orphans = []
    for p in proxy:
        if p["listening"]:
            orphans.append({**p, "owner_pids": port_owner_pids(p["port"])})
    return {"detected": bool(orphans), "ports": orphans}


def _doctor_launcher_log(project_dir: pathlib.Path) -> dict:
    log_path = pathlib.Path(project_dir) / ".mw" / "launcher.log"
    if not log_path.exists():
        return {"exists": False, "tail": [], "error_count": 0, "fatal": False}
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"exists": False, "tail": [], "error_count": 0, "fatal": False}
    error_count = sum(1 for l in lines if "spawn failed" in l or "poll error" in l)
    fatal = any("FATAL" in l for l in lines)
    return {"exists": True, "tail": lines[-10:], "error_count": error_count, "fatal": fatal}


_HEARTBEAT_LINE_RE = re.compile(r"^\[HEARTBEAT\] (\S+) task=")


def _parse_heartbeat_ts(hb: str) -> datetime.datetime:
    """Parse a heartbeat timestamp written by the TS side.

    appendHeartbeat emits Date.toISOString() (always `...Z`), but
    datetime.fromisoformat only accepts the `Z` designator on Python 3.11+ —
    on the stated 3.10 floor every real heartbeat would raise ValueError and
    the whole liveness feature would silently degrade to no-heartbeat
    (review M3). Normalize `Z` to `+00:00` before parsing.
    """
    return datetime.datetime.fromisoformat(hb.replace("Z", "+00:00", 1) if hb.endswith("Z") else hb)


def _last_heartbeat(task_dir: pathlib.Path) -> str | None:
    """ISO timestamp of the last [HEARTBEAT] line in a worker task's trace.log,
    or None when the file/line is absent (old bundle, just started)."""
    trace = task_dir / "trace.log"
    try:
        lines = trace.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        m = _HEARTBEAT_LINE_RE.match(line)
        if m:
            return m.group(1)
    return None


def worker_liveness(project_dir: pathlib.Path, stale_after_sec: int = 90) -> list[dict]:
    """Heartbeat-based liveness verdicts for RUNNING queue rows (design D-004).

    Verdicts: alive (last heartbeat within stale_after_sec), stale (older),
    no-heartbeat (running but no [HEARTBEAT] lines — old bundle or fresh
    start). Informational only: killing stuck workers stays with the
    worker-side 30-min watchdog (GC-4). Keep the 90s default in sync with the
    TS HEARTBEAT_STALE_MS constant in agent-team-loop/shared/heartbeat.ts.
    """
    entries = parse_workers_file(workers_path(project_dir))
    verdicts: list[dict] = []
    now = time.time()
    for e in entries:
        if e["status"] != "running":
            continue
        task_dir = pathlib.Path(e["task_path"]).parent
        hb = _last_heartbeat(task_dir)
        if hb is None:
            verdicts.append(
                {"task_key": e["task_key"], "last_heartbeat": None, "age_s": None, "verdict": "no-heartbeat"}
            )
            continue
        try:
            age_s = max(0, int(now - _parse_heartbeat_ts(hb).timestamp()))
        except ValueError:
            verdicts.append(
                {"task_key": e["task_key"], "last_heartbeat": hb, "age_s": None, "verdict": "no-heartbeat"}
            )
            continue
        verdict = "stale" if age_s > stale_after_sec else "alive"
        verdicts.append(
            {"task_key": e["task_key"], "last_heartbeat": hb, "age_s": age_s, "verdict": verdict}
        )
    return verdicts


def _doctor_queue(project_dir: pathlib.Path) -> dict:
    entries = parse_workers_file(workers_path(project_dir))
    non_terminal = [
        {
            "task_key": e["task_key"],
            "status": e["status"],
            "cli": e["cli"],
            "task_md_exists": pathlib.Path(e["task_path"]).exists(),
        }
        for e in entries if e["status"] not in _TERMINAL_STATUSES
    ]
    stale_count = sum(1 for e in non_terminal if not e["task_md_exists"])
    spath = stale_path(project_dir)
    archived_total = 0
    if spath.exists():
        try:
            archived_total = len(spath.read_text(encoding="utf-8").splitlines())
        except OSError:
            archived_total = 0
    return {
        "non_terminal": non_terminal,
        "stale_count": stale_count,
        "archived_total": archived_total,
    }


def _doctor_bundle() -> dict:
    bundle = global_ext_dir() / "agent-team-loop.js"
    if not bundle.exists():
        return {"available": False, "note": f"global bundle not found: {bundle}"}
    if not _EXT_SRC_DIR.is_dir():
        return {
            "available": True,
            "global_bundle_mtime": datetime.datetime.fromtimestamp(bundle.stat().st_mtime).isoformat(),
            "source_available": False,
            "stale": None,
            "note": "extension source not found next to mw package; cannot compare",
        }
    bundle_mtime = bundle.stat().st_mtime
    newest = max(f.stat().st_mtime for f in _EXT_SRC_DIR.rglob("*") if f.is_file())
    return {
        "available": True,
        "global_bundle_mtime": datetime.datetime.fromtimestamp(bundle_mtime).isoformat(),
        "source_newest_mtime": datetime.datetime.fromtimestamp(newest).isoformat(),
        "source_available": True,
        "stale": newest > bundle_mtime,
    }


def _source_desc(source: dict) -> str:
    if not source:
        return "native"
    kind = source.get("kind")
    if kind == "env":
        return f"env {source.get('name')}"
    if kind == "file":
        return f"file {source.get('path')}"
    return str(kind or "unknown")


def _doctor_issues(report: dict) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    suggestions: list[str] = []
    if not report["service"]["running"]:
        issues.append("mw service not running (workers will not be dispatched)")
    if report["queue"]["stale_count"]:
        issues.append(
            f"{report['queue']['stale_count']} stale queue entries (task.md missing) - "
            "run 'mw.py doctor --fix' or restart mw"
        )
    if report["launcher_log"].get("fatal"):
        issues.append("launcher.log contains FATAL lines - inspect the tail")
    if report["bundle"].get("stale"):
        suggestions.append(
            "extension bundle older than source - run '/mw build' or 'mw.py build --install'"
        )
    if report["orphan_proxy"]["detected"]:
        ports = ", ".join(str(p["port"]) for p in report["orphan_proxy"]["ports"])
        suggestions.append(
            f"proxy port(s) {ports} bound while mw not running (orphan) - "
            "start mw to adopt them or kill the owning process"
        )
    missing_routes = [
        f"{r['route']} ({r['missing']})" for r in report["credentials"]["routes"] if not r["available"]
    ]
    if missing_routes:
        suggestions.append(
            "routes without credentials (env of the mw process): " + "; ".join(missing_routes)
        )
    if report["launcher_log"].get("error_count"):
        suggestions.append(
            f"launcher.log has {report['launcher_log']['error_count']} error line(s) - inspect the tail"
        )
    return issues, suggestions


def doctor_report(
    project_dir: pathlib.Path,
    fix: bool = False,
    config: dict | None = None,
    stale_after_sec: int = 90,
) -> dict:
    """Full diagnostic snapshot. Local-only checks (no network), <5s.

    Sections: service, proxy, orphan_proxy, launcher_log, queue,
    worker_liveness, credentials, bundle (+ fix when fix=True), summary.
    healthy=True iff no issues; worker_liveness is informational and never
    flips healthy/exit codes."""
    project_dir = pathlib.Path(project_dir)
    if config is None:
        config = load_providers(pathlib.Path(__file__).parent / "providers.json")
    report: dict = {}
    if fix:
        report["fix"] = {"applied": doctor_fix(project_dir)}
    report["service"] = _doctor_service(project_dir)
    report["proxy"] = _doctor_proxy(config)
    report["orphan_proxy"] = _doctor_orphan(report["service"], report["proxy"])
    report["launcher_log"] = _doctor_launcher_log(project_dir)
    report["queue"] = _doctor_queue(project_dir)
    report["worker_liveness"] = worker_liveness(project_dir, stale_after_sec)
    report["credentials"] = route_precheck(config, os.environ)
    report["bundle"] = _doctor_bundle()
    issues, suggestions = _doctor_issues(report)
    report["summary"] = {"healthy": not issues, "issues": issues, "suggestions": suggestions}
    return report


def format_doctor_text(report: dict) -> str:
    """Human-readable one-line-per-finding text output (doctor CLI)."""
    lines: list[str] = []
    svc = report["service"]
    lines.append(
        f"service: {'running (PID ' + str(svc['pid']) + ')' if svc['running'] else 'not running'}"
    )
    for p in report["proxy"]:
        lines.append(f"proxy: {p['route']} port {p['port']} {'LISTENING' if p['listening'] else 'not listening'}")
    orphan = report["orphan_proxy"]
    if orphan["detected"]:
        ports = ", ".join(
            f"{p['port']} (pid {p.get('owner_pids')})" for p in orphan["ports"]
        )
        lines.append(f"orphan_proxy: ports {ports} bound while mw not running")
    else:
        lines.append("orphan_proxy: none")
    log = report["launcher_log"]
    if log["exists"]:
        lines.append(
            f"launcher_log: {log['error_count']} error line(s), fatal={log['fatal']} "
            f"(tail: {' | '.join(log['tail'][-3:])})"
        )
    else:
        lines.append("launcher_log: no log file")
    queue = report["queue"]
    lines.append(
        f"queue: {len(queue['non_terminal'])} non-terminal task(s), "
        f"{queue['stale_count']} stale, {queue['archived_total']} archived"
    )
    liveness = report.get("worker_liveness", [])
    if liveness:
        alive = sum(1 for v in liveness if v["verdict"] == "alive")
        stale = [v["task_key"] for v in liveness if v["verdict"] == "stale"]
        no_hb = sum(1 for v in liveness if v["verdict"] == "no-heartbeat")
        parts = [f"alive {alive}"]
        if stale:
            parts.append(f"stale: {', '.join(stale)}")
        if no_hb:
            parts.append(f"no-heartbeat {no_hb}")
        lines.append("workers: " + ", ".join(parts))
    for r in report["credentials"]["routes"]:
        state = "available (" + _source_desc(r["source"]) + ")" if r["available"] else "missing (" + str(r["missing"]) + ")"
        lines.append(f"credentials: {r['route']} {state}")
    bundle = report["bundle"]
    if bundle.get("available"):
        if bundle.get("source_available"):
            lines.append(
                f"bundle: global mtime {bundle['global_bundle_mtime']}, "
                f"source newest {bundle['source_newest_mtime']}, stale={bundle['stale']}"
            )
        else:
            lines.append(f"bundle: global mtime {bundle['global_bundle_mtime']} ({bundle.get('note')})")
    else:
        lines.append(f"bundle: {bundle.get('note')}")
    if "fix" in report:
        applied = report["fix"]["applied"]
        lines.append("fix: " + ("; ".join(applied) if applied else "nothing to auto-fix"))
    summary = report["summary"]
    lines.append(f"summary: {'healthy' if summary['healthy'] else 'ISSUES: ' + '; '.join(summary['issues'])}")
    for s in summary["suggestions"]:
        lines.append(f"suggest: {s}")
    return "\n".join(lines)

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

try:
    import yaml  # PyYAML: implicit dep for target.yml (mw-dual-workspace D-010)
except ImportError:  # pragma: no cover - doctor reports this explicitly
    yaml = None  # type: ignore[assignment]

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


# --- Protected agent config (cross-window files) ----------------------------
#
# Incident 2026-09-15: a running pi session cleared ~/.pi/agent/auth.json
# while other windows were live; every window lost its credentials
# ("Provider is not configured: timi") and several hung. These files are
# live config shared by ALL pi sessions, so framework code must never write
# them. Credential/model/settings changes belong to the user, outside pi
# (plain terminal, or `pi /login` which is a core flow, not the tool layer).
# The agent-side hard block lives in the agent-team-loop extension
# (shared/protected-config.ts); this is the Python-side mirror for any
# future framework write path.

#: Protected file names inside the pi agent config dir (oauth.json is the
#: legacy pre-migration credential store, same blast radius).
PROTECTED_AGENT_CONFIG_FILES: tuple[str, ...] = (
    "auth.json",
    "models.json",
    "settings.json",
    "oauth.json",
)

#: Mirrors ENV_AGENT_DIR in coding-agent src/config.ts (getAgentDir()).
AGENT_DIR_ENV = "PI_CODING_AGENT_DIR"


def agent_config_dir(env: Mapping[str, str] | None = None) -> pathlib.Path:
    """The effective pi agent config dir: the AGENT_DIR_ENV override
    (tilde-expanded) else ~/.pi/agent. Mirrors core getAgentDir(); env is
    injectable for tests (defaults to os.environ)."""
    if env is None:
        env = os.environ
    raw = env.get(AGENT_DIR_ENV, "")
    if raw:
        return pathlib.Path(os.path.expanduser(raw))
    return pathlib.Path.home() / ".pi" / "agent"


def is_protected_agent_config(path: str | os.PathLike[str], env: Mapping[str, str] | None = None) -> bool:
    """True when `path` targets a protected file (or an agent dir itself).

    Checked against BOTH the effective agent dir and the default ~/.pi/agent
    (defense-in-depth, matching the TS guard): an env override in the calling
    process does not un-protect the default location. Pure: ~ expansion and
    cwd-relative resolution only, no fs access, never raises.
    """
    p = pathlib.Path(os.path.expanduser(str(path))).resolve()
    candidates = {agent_config_dir(env).resolve(), (pathlib.Path.home() / ".pi" / "agent").resolve()}
    for agent_dir in candidates:
        if p == agent_dir:
            return True
        if any(p == agent_dir / name for name in PROTECTED_AGENT_CONFIG_FILES):
            return True
    return False


class ProtectedConfigError(RuntimeError):
    """Raised when framework code tries to modify a protected agent config
    file. No override exists on purpose: the fix is to not write the file."""


def assert_not_protected_agent_config(
    path: str | os.PathLike[str],
    action: str = "modify",
    env: Mapping[str, str] | None = None,
) -> None:
    """Guard for any future framework write path: raises before the write
    when the target is a protected agent config file."""
    if is_protected_agent_config(path, env):
        target = os.path.expanduser(str(path))
        raise ProtectedConfigError(
            f"refusing to {action} {target}: cross-window pi config file "
            f"({', '.join(PROTECTED_AGENT_CONFIG_FILES)} under the agent dir) shared "
            "by every live pi session (2026-09-15 incident: clearing auth.json "
            "broke all open windows). Framework code never writes these files; "
            "the user changes them outside pi (plain terminal / `pi /login`)."
        )


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


def read_log_tail(path: pathlib.Path, lines: int = 10) -> list[str]:
    """Last `lines` lines of a UTF-8 text log; empty when missing/unreadable."""
    try:
        content = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return content.splitlines()[-lines:]


def _doctor_proxy_log(project_dir: pathlib.Path) -> dict:
    """Crash forensics for .mw/proxy.log. The proxy is an optional child
    (spawned only when a port-routed provider has credentials), so a leftover
    traceback is the root cause behind 'port not listening' symptoms and must
    be surfaced, not just the symptom."""
    log_path = pathlib.Path(project_dir) / ".mw" / "proxy.log"
    if not log_path.exists():
        return {"exists": False, "tail": [], "traceback_count": 0, "last_error": None}
    lines = read_log_tail(log_path, 400)
    tb_idx = [i for i, l in enumerate(lines) if l.startswith("Traceback (most recent call last)")]
    last_error = None
    if tb_idx:
        # Exception message = first NON-INDENTED non-empty line after the last
        # traceback header (frame lines are indented; the message sits at column 0).
        for l in lines[tb_idx[-1] + 1 :]:
            if l.strip() and not l[0].isspace():
                last_error = l.strip()
                break
    return {
        "exists": True,
        "tail": lines[-10:],
        "traceback_count": len(tb_idx),
        "last_error": last_error,
    }


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


# ── Terminal evidence / launcher beat (D-007/D-008, T-02) ─────────────────────

# Mirrors END_LINE_RE in agent-team-loop/shared/heartbeat.ts. Only a full
# `[END] <ts> exit=<n> elapsed=<n>s tools=<n> phases=<...>` line counts as
# terminal evidence (AC-012); the exit->status mapping itself lives in the
# launcher (T-08).
_END_LINE_RE = re.compile(r"^\[END\] (\S+) exit=(\d+) elapsed=(\d+)s tools=(\d+) phases=(\S+)$")
_TRACE_TAIL_BYTES = 64 * 1024


def parse_end_exit(task_dir: pathlib.Path) -> int | None:
    """Exit code from the last [END] line of a worker task's trace.log.

    Reads only the file tail (64KB, design section 9: stat + tail-read so
    polling stays cheap). Missing file or no [END] line -> None; the caller
    decides what unverifiable means (T-08). Later [END] lines win, mirroring
    the TS parse loop.
    """
    trace = pathlib.Path(task_dir) / "trace.log"
    try:
        with trace.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - _TRACE_TAIL_BYTES))
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    exit_code: int | None = None
    for line in tail.splitlines():
        m = _END_LINE_RE.match(line)
        if m:
            exit_code = int(m.group(2))
    return exit_code


# Launcher beat protocol (D-008): every poll overwrites
# .mw/launcher-beat.<pid> with a single `ts=<iso>` line. Before applying the
# silence rule (presumed dead), a launcher checks for another live launcher's
# fresh beat and yields. No lock: one small file per launcher, overwritten.
_BEAT_FILE_PREFIX = "launcher-beat."
_BEAT_FRESH_SEC = 30
_ORPHAN_DEAD_ENV = "PI_WORKER_ORPHAN_DEAD_MIN"
_DEFAULT_ORPHAN_DEAD_MIN = 90


def launcher_beat_write(project_dir: pathlib.Path, pid: int) -> None:
    """Refresh this launcher's beat file: .mw/launcher-beat.<pid>, single
    `ts=<iso>` (UTC) line, overwritten every poll (D-008)."""
    beat = pathlib.Path(project_dir) / ".mw" / f"{_BEAT_FILE_PREFIX}{pid}"
    beat.parent.mkdir(parents=True, exist_ok=True)
    beat.write_text(f"ts={iso_now()}\n", encoding="utf-8")


def other_live_launcher(project_dir: pathlib.Path, self_pid: int) -> bool:
    """True when another live launcher has a fresh beat (D-008).

    A beat file counts only when its pid is not ours, its ts is younger than
    30s, and the pid is alive (reuses _is_alive). Missing files, expired or
    unparseable beats, and dead pids all mean "no other live launcher", so
    the caller keeps the silence rule for itself. A beat proven expired
    whose pid is dead is unlinked along the way (hygiene, review S2: one
    stale file would otherwise accumulate per dead launcher; correctness is
    unaffected either way since expired beats are already ignored).
    """
    beat_dir = pathlib.Path(project_dir) / ".mw"
    now = time.time()
    for beat in beat_dir.glob(f"{_BEAT_FILE_PREFIX}*"):
        try:
            pid = int(beat.name[len(_BEAT_FILE_PREFIX):])
        except ValueError:
            continue  # malformed name; not ours to judge
        if pid == self_pid:
            continue
        try:
            content = beat.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.match(r"^ts=(\S+)", content.strip())
        if not m:
            continue
        try:
            ts = _parse_heartbeat_ts(m.group(1))
        except ValueError:
            continue
        if ts.tzinfo is None:  # spec 2.1: timestamps are UTC
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        if now - ts.timestamp() >= _BEAT_FRESH_SEC:
            if not _is_alive(pid):  # expired AND dead: prune the leftover beat
                try:
                    beat.unlink(missing_ok=True)
                except OSError:
                    pass  # best-effort hygiene
            continue
        if _is_alive(pid):
            return True
    return False


def orphan_dead_after(env: Mapping[str, str] | None = None) -> int:
    """Silence-rule window in minutes (D-007): env PI_WORKER_ORPHAN_DEAD_MIN
    (int >= 1), default 90. Missing/0/negative/non-numeric values fall back
    to the default so a typo can never disable or zero the rule."""
    if env is None:
        env = os.environ
    try:
        minutes = int(env.get(_ORPHAN_DEAD_ENV, ""))
    except (TypeError, ValueError):
        return _DEFAULT_ORPHAN_DEAD_MIN
    if minutes < 1:
        return _DEFAULT_ORPHAN_DEAD_MIN
    return minutes


def task_dir_last_activity(task_dir: pathlib.Path) -> float | None:
    """Newest mtime among all files in a worker task directory (D-007 silence
    rule input). None when the directory is missing or holds no files."""
    task_dir = pathlib.Path(task_dir)
    if not task_dir.is_dir():
        return None
    newest: float | None = None
    try:
        entries = list(task_dir.iterdir())
    except OSError:
        return None
    for entry in entries:
        try:
            if not entry.is_file():
                continue
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        newest = mtime if newest is None else max(newest, mtime)
    return newest


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
    plog = report.get("proxy_log") or {}
    if plog.get("last_error"):
        crash = (
            f"proxy.log records {plog['traceback_count']} crash(es), last: {plog['last_error']}"
        )
        if not report["service"]["running"]:
            issues.append(crash)
        else:
            suggestions.append(crash)
    if report["queue"]["stale_count"]:
        issues.append(
            f"{report['queue']['stale_count']} stale queue entries (task.md missing) - "
            "run 'mw.py doctor --fix' or restart mw"
        )
    if report["launcher_log"].get("fatal"):
        issues.append("launcher.log contains FATAL lines - inspect the tail")
    target = report.get("target")
    if target is not None:
        if target.get("error") is not None:
            err = target["error"]
            issues.append(f"target config error ({err['kind']}): {err['message']}")
        else:
            for check in target.get("checks") or []:
                if not check["ok"]:
                    issues.append(
                        f"target toolchain check failed: {check['name']} ({check['detail']})"
                    )
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

    Sections: service, proxy, proxy_log, orphan_proxy, launcher_log, queue,
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
    report["proxy_log"] = _doctor_proxy_log(project_dir)
    report["orphan_proxy"] = _doctor_orphan(report["service"], report["proxy"])
    report["launcher_log"] = _doctor_launcher_log(project_dir)
    report["queue"] = _doctor_queue(project_dir)
    report["worker_liveness"] = worker_liveness(project_dir, stale_after_sec)
    report["credentials"] = route_precheck(config, os.environ)
    report["bundle"] = _doctor_bundle()
    report["target"] = _doctor_target(project_dir)
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
    avail_routes = {
        r["route"] for r in report.get("credentials", {}).get("routes", []) if r.get("available")
    }
    if report["proxy"] and not any(p["route"] in avail_routes for p in report["proxy"]):
        lines.append("proxy: disabled (no proxy-routed credentials; direct routes only)")
    plog = report.get("proxy_log") or {}
    if plog.get("last_error"):
        lines.append(f"proxy_log: {plog['traceback_count']} crash(es), last: {plog['last_error']}")
    else:
        lines.append("proxy_log: ok" if plog.get("exists") else "proxy_log: no log file")
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
    # Target workspace row (mw-dual-workspace D-011/D-013)
    target = report.get("target")
    if target is not None:
        if target.get("error") is not None:
            err = target["error"]
            lines.append(f"target: ERROR {err['kind']}: {err['message']}")
        else:
            cfg = target["config"]
            roots = f"game={cfg['game_root']}"
            if cfg["engine_root"]:
                roots += f" engine={cfg['engine_root']}"
            lines.append(f"target: {cfg['mode']} (source {cfg['source']}) {roots}")
            checks = target.get("checks")
            if checks:
                state = ", ".join(
                    f"{c['name']} {'ok' if c['ok'] else 'FAIL: ' + c['detail']}" for c in checks
                )
                lines.append(f"target_toolchain: {state} ({target.get('probe_cache')})")
    # Conductor row (D-101, injected by mw.py cmd_doctor): informational —
    # not running simply means autopilot is disabled for this project.
    conductor = report.get("conductor")
    if conductor is not None:
        if conductor["running"]:
            lines.append(
                f"conductor: running (PID {conductor['pid']}, "
                f"last tick seq={conductor['last_seq']} ts={conductor['last_ts']})"
            )
        else:
            lines.append("conductor: not running")
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


# ── Dual-workspace target config (mw-dual-workspace D-002/D-010/D-011/D-014) ───

# Parity module: mirrors packages/coding-agent/src/extensions/agent-team-loop/
# shared/target-config.ts 1:1 (T-17 pattern). Field names in the returned dict
# are snake_case twins of the TS interface; parity is asserted by the shared
# fixtures under test/fixtures/target-config-cases/ (kind + key facts, not
# message text).

ENV_TARGET_GAME = "MW_TARGET_GAME"
ENV_TARGET_ENGINE = "MW_TARGET_ENGINE"

# Error kinds — the parity contract. Both sides raise these exact tokens.
_TARGET_KINDS = (
    "invalid-yaml",
    "invalid-config",
    "missing-field",
    "uproject-not-found",
    "ambiguous-uproject",
)


class TargetConfigError(Exception):
    """Fail-closed target.yml / env resolution error (see _TARGET_KINDS)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def _tc_fail(kind: str, message: str) -> None:
    raise TargetConfigError(kind, message)


def _tc_require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        _tc_fail("invalid-config", f"target.yml: field '{field}' must be a non-empty string")
    return value


def _tc_optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _tc_require_string(value, field)


def _tc_string_array(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(e, str) or e.strip() == "" for e in value
    ):
        _tc_fail("invalid-config", f"target.yml: field '{field}' must be a list of non-empty strings")
    return list(value)


def _tc_normalize_root(raw: str, control_root: str) -> str:
    """Resolve against control_root, then realpath when it exists (junction/
    case folding parity with the TS normalizeRoot)."""
    resolved = os.path.normpath(os.path.join(control_root, raw))
    return str(pathlib.Path(resolved).resolve())


def target_yml_path(control_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(control_root) / ".agenticdoc" / "target.yml"


def _tc_read_target_yml(control_root: str) -> dict:
    path = target_yml_path(control_root)
    if not path.exists():
        return {}
    if yaml is None:
        _tc_fail(
            "invalid-config",
            "PyYAML is required to read target.yml (mw doctor checks this); "
            "install it or unset MW_TARGET_GAME to stay in single mode",
        )
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        _tc_fail("invalid-yaml", f"target.yml unreadable ({path}): {e}")
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as e:  # type: ignore[union-attr]
        _tc_fail("invalid-yaml", f"target.yml is not valid YAML ({path}): {e}")
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        _tc_fail("invalid-config", "target.yml: top level must be a mapping")
    return parsed


def _tc_parse_toolchain(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        _tc_fail("invalid-config", "target.yml: 'toolchain' must be a mapping of name to command")
    out: dict[str, str] = {}
    for name, cmd in value.items():
        if not isinstance(cmd, str) or cmd.strip() == "":
            _tc_fail("invalid-config", f"target.yml: toolchain.{name} must be a non-empty string")
        out[str(name)] = cmd
    return out


def _tc_parse_ignore(value: object) -> dict:
    if value is None:
        return {"deny_globs": []}
    if not isinstance(value, dict):
        _tc_fail("invalid-config", "target.yml: 'ignore' must be a mapping")
    return {"deny_globs": _tc_string_array(value.get("deny_globs"), "ignore.deny_globs")}


def _tc_parse_contract(value: object) -> dict:
    if value is None:
        return {"forbidden_paths": [], "conventions": None, "docs": []}
    if not isinstance(value, dict):
        _tc_fail("invalid-config", "target.yml: 'contract' must be a mapping")
    conventions = value.get("conventions")
    if conventions is not None and not isinstance(conventions, str):
        _tc_fail("invalid-config", "target.yml: contract.conventions must be a string")
    return {
        "forbidden_paths": _tc_string_array(value.get("forbidden_paths"), "contract.forbidden_paths"),
        "conventions": conventions,
        "docs": _tc_string_array(value.get("docs"), "contract.docs"),
    }


def load_target_config(
    control_root: pathlib.Path | str,
    env: Mapping[str, str] | None = None,
) -> dict:
    """Resolve the dual-workspace config for a control root.

    Precedence: MW_TARGET_GAME/MW_TARGET_ENGINE env > target.yml > single
    fallback (game_root === control_root). Raises TargetConfigError on
    contradictory or unusable configuration (fail-closed, never a silent
    single fallback). Mirrors resolveWorkspaceConfig() in target-config.ts.
    """
    control_root = str(control_root)
    if env is None:
        env = os.environ
    raw = _tc_read_target_yml(control_root)

    env_game = (env.get(ENV_TARGET_GAME) or "").strip() or None
    env_engine = (env.get(ENV_TARGET_ENGINE) or "").strip() or None

    file_mode = _tc_optional_string(raw.get("mode"), "mode")
    if file_mode is not None and file_mode not in ("dual", "single"):
        _tc_fail("invalid-config", f"target.yml: 'mode' must be 'dual' or 'single', got '{file_mode}'")
    file_game = _tc_optional_string(raw.get("game"), "game")
    file_engine = _tc_optional_string(raw.get("engine"), "engine")

    game_raw = env_game if env_game is not None else file_game
    engine_raw = env_engine if env_engine is not None else file_engine

    # File-internal contradictions fail closed before precedence applies
    # (same order as the TS side — see the 001 task evidence note).
    if file_mode == "single" and file_game is not None:
        _tc_fail("invalid-config", "target.yml: mode 'single' with a 'game' field is contradictory")
    if file_mode == "dual" and file_game is None and env_game is None:
        _tc_fail(
            "invalid-config",
            "target.yml: mode 'dual' requires a game root (field 'game' or env MW_TARGET_GAME)",
        )

    mode = "dual" if game_raw is not None else "single"
    if engine_raw is not None and mode == "single":
        _tc_fail("invalid-config", "target.yml: 'engine' requires dual mode (configure 'game' first)")

    control_norm = _tc_normalize_root(control_root, control_root)
    game_root = _tc_normalize_root(game_raw, control_root) if mode == "dual" else control_norm
    if env_game is not None:
        source = "env"
    elif game_raw is not None or file_mode is not None:
        source = "target-yml"
    else:
        source = "default"
    return {
        "mode": mode,
        "control_root": control_norm,
        "game_root": game_root,
        "engine_root": None if engine_raw is None else _tc_normalize_root(engine_raw, control_root),
        "vcs": _tc_optional_string(raw.get("vcs"), "vcs"),
        "uproject": _tc_optional_string(raw.get("uproject"), "uproject"),
        "toolchain": _tc_parse_toolchain(raw.get("toolchain")),
        "ignore": _tc_parse_ignore(raw.get("ignore")),
        "contract": _tc_parse_contract(raw.get("contract")),
        "source": source,
    }


def discover_uproject(game_root: str, explicit: str | None = None) -> str:
    """Resolve {uproject} (D-014): explicit field wins (must exist on disk);
    otherwise exactly one *.uproject under the game root. 0 or many is an
    error carrying the count — never a guess."""
    if explicit is not None:
        p = os.path.normpath(os.path.join(game_root, explicit))
        if not os.path.exists(p):
            _tc_fail("uproject-not-found", f"explicit uproject '{explicit}' not found under game root {game_root}")
        return str(pathlib.Path(p).resolve())
    try:
        entries = os.listdir(game_root)
    except OSError as e:
        _tc_fail("invalid-config", f"game root is not readable ({game_root}): {e}")
    matches = [e for e in entries if e.lower().endswith(".uproject")]
    if len(matches) != 1:
        detail = f" ({', '.join(matches)})" if len(matches) > 1 else ""
        _tc_fail(
            "ambiguous-uproject",
            f"expected exactly one *.uproject under game root {game_root}, found {len(matches)}{detail}",
        )
    return str(pathlib.Path(os.path.join(game_root, matches[0])).resolve())


def render_toolchain_command(command: str, config: dict) -> str:
    """Render one toolchain command template (AC-004, fail-closed). Replaces
    {game}/{engine}/{uproject}; a token whose root is unconfigured raises
    with the field name and the original command — no game-root fallback."""
    out = command
    if "{game}" in out:
        out = out.replace("{game}", config["game_root"])
    if "{engine}" in out:
        if config["engine_root"] is None:
            _tc_fail(
                "missing-field",
                f"toolchain command references {{engine}} but engine is not configured "
                f"(dual mode requires it): {command}",
            )
        out = out.replace("{engine}", config["engine_root"])
    if "{uproject}" in out:
        uproject = discover_uproject(config["game_root"], config.get("uproject"))
        out = out.replace("{uproject}", uproject)
    return out


def toolchain_probe_path(project_dir: pathlib.Path | str) -> pathlib.Path:
    """Machine-local toolchain probe cache (mw-dual-workspace D-013)."""
    return pathlib.Path(project_dir) / ".mw" / "toolchain.json"


def probe_target_toolchain(config: dict) -> list[dict]:
    """Machine-level checks on a resolved target config (D-013): root
    readability, engine presence, {uproject} resolvability. Pure — the cache
    layer in _doctor_target decides whether to run them."""
    checks: list[dict] = []
    game = config["game_root"]
    checks.append({"name": "game_root", "ok": os.path.isdir(game), "detail": game})
    if config["engine_root"] is not None:
        engine = config["engine_root"]
        checks.append({"name": "engine_root", "ok": os.path.isdir(engine), "detail": engine})
    needs_uproject = config["uproject"] is not None or any(
        "{uproject}" in cmd for cmd in config["toolchain"].values()
    )
    if needs_uproject:
        try:
            p = discover_uproject(game, config["uproject"])
            checks.append({"name": "uproject", "ok": True, "detail": p})
        except TargetConfigError as e:
            checks.append({"name": "uproject", "ok": False, "detail": f"{e.kind}: {e}"})
    return checks


def _doctor_target(project_dir: pathlib.Path) -> dict:
    """Target config + cached toolchain probe section (mw-dual-workspace D-013).

    Probe results persist to .mw/toolchain.json and are reused while fresh
    (target.yml not newer than the probe timestamp) — the machine property
    rarely changes once the project is set up. Config load errors and failed
    probe checks become doctor issues; a single-mode default (no target.yml)
    has nothing to probe."""
    yml = target_yml_path(project_dir)
    section: dict = {"yaml_available": yaml is not None}
    try:
        config = load_target_config(project_dir)
    except TargetConfigError as e:
        section["config"] = None
        section["error"] = {"kind": e.kind, "message": str(e)}
        return section
    section["config"] = {
        "mode": config["mode"],
        "source": config["source"],
        "game_root": config["game_root"],
        "engine_root": config["engine_root"],
        "vcs": config["vcs"],
        "uproject": config["uproject"],
    }
    if config["source"] == "default":
        section["checks"] = None
        return section

    cache = toolchain_probe_path(project_dir)
    yml_mtime = yml.stat().st_mtime if yml.exists() else 0.0
    cached: dict | None = None
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = None
    if cached is not None and isinstance(cached.get("checks"), list) and cached.get("probed_at_epoch", 0.0) >= yml_mtime:
        section["checks"] = cached["checks"]
        section["probe_cache"] = "fresh"
        return section

    checks = probe_target_toolchain(config)
    section["checks"] = checks
    section["probe_cache"] = "probed"
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {"probed_at": iso_now(), "probed_at_epoch": time.time(), "checks": checks},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        section["probe_cache"] = "probed (cache write failed)"
    return section

"""Machine-level token / wall-clock ledger and stats kernel (mw-usage-monitor T-01).

Storage (machine level, one ledger for every project)::

    <usage_dir>/runs.jsonl         append-only event ledger (start | end | spawn_failed)
    <usage_dir>/runs.jsonl.lock    cross-process O_CREAT|O_EXCL lock

The ledger only carries **run metadata** (who/when/which model/how long/how it
ended). Token numbers are never stored: they are the single truth of the CLI
session logs and are joined at query time (spec D-7).

Token source of truth (spec §2):

* pi session JSONL — every ``assistant`` message is exactly one provider
  response, so usage rows are summed directly (no dedup; a failed attempt is a
  real ``EMPTY_USAGE`` message). ``compaction`` entries carry usage too and are
  counted as well. The four components stay apart; ``total`` is always derived.
* claude session JSONL — the same message is written 2-4 times, so rows are
  deduped by ``message.id`` (1.41-1.87x inflation otherwise). ``input_tokens``
  is already non-cached input.
* codex — not read in v1 (no session id, double-counted token_count pairs).

Unknown tokens are ``None`` (rendered ``-``), never ``0``. Only
``type/model/provider/timestamp/usage/message.id/header(cwd,id)`` are read;
message bodies are never touched.

Environment hooks (explicit order, no bare ``expanduser``):

* ``MW_USAGE_DIR``            whole-directory override for the ledger (tests)
* ``USERPROFILE`` / ``HOME``  home for ``~/.mw/usage``
* ``MW_PI_SESSIONS_DIR``      whole-directory override for pi sessions (tests)
* ``PI_CODING_AGENT_SESSION_DIR`` / ``PI_CODING_AGENT_DIR``  pi's own overrides
* ``MW_CLAUDE_PROJECTS_DIR``  whole-directory override for claude projects (tests)
* ``CLAUDE_CONFIG_DIR``       claude's own config dir (=> ``projects/``)
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import re
import sys
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any

from mw_common import acquire_lock, release_lock

# ── constants ────────────────────────────────────────────────────────────────

USAGE_ENV_DIR = "MW_USAGE_DIR"
PI_ENV_SESSIONS_DIR = "MW_PI_SESSIONS_DIR"
PI_ENV_SESSION_DIR = "PI_CODING_AGENT_SESSION_DIR"
PI_ENV_AGENT_DIR = "PI_CODING_AGENT_DIR"
CLAUDE_ENV_PROJECTS_DIR = "MW_CLAUDE_PROJECTS_DIR"
CLAUDE_ENV_CONFIG_DIR = "CLAUDE_CONFIG_DIR"

LEDGER_NAME = "runs.jsonl"
LOCK_NAME = "runs.jsonl.lock"

#: Four token components, always in this order (spec D-2).
TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write")

#: pi's ``assertValidSessionId`` (session-manager.ts:212-218).
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_RELATIVE_SINCE_RE = re.compile(r"^(\d+)([dhm])$")
_TIMESTAMP_RE = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')
_SLUG_MAX = 64

_RELATIVE_UNITS = {"d": timedelta(days=1), "h": timedelta(hours=1), "m": timedelta(minutes=1)}

#: Value used for the type/key group of a PM window session (not a worker run).
PM_LABEL = "pm"
UNKNOWN_LABEL = "unknown"

_LEDGER_EVENTS = ("start", "end", "spawn_failed")
_CLI_ORDER = ("pi", "claude", "codex")

_GROUP_TITLES = (
    ("model", "by model"),
    ("type", "by type"),
    ("key", "by key"),
    ("project", "by project"),
)

#: Group-row ``wall_kind`` values (design 5): ledger spawn -> reap samples
#: (``run``), header -> last entry spans (``session``), or nothing usable
#: (``none``). Text marker/footnote for the ``session`` case:
SESSION_WALL_MARK = "*"
SESSION_WALL_FOOTNOTE = "* = PM 会话跨度（header→末条），非 worker 墙钟"


# ── paths / env resolution ───────────────────────────────────────────────────


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _env_value(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _home_dir(env: Mapping[str, str] | None = None) -> pathlib.Path:
    """USERPROFILE -> HOME -> ``Path.home()`` (spec §10: no bare ``expanduser``)."""
    env = _env(env)
    for name in ("USERPROFILE", "HOME"):
        value = _env_value(env, name)
        if value:
            return pathlib.Path(value)
    return pathlib.Path.home()


def usage_dir(env: Mapping[str, str] | None = None) -> pathlib.Path:
    """Machine-level usage directory; never created here (write side does that)."""
    env = _env(env)
    override = _env_value(env, USAGE_ENV_DIR)
    if override:
        return pathlib.Path(override)
    return _home_dir(env) / ".mw" / "usage"


def ledger_path(env: Mapping[str, str] | None = None) -> pathlib.Path:
    return usage_dir(env) / LEDGER_NAME


def lock_path(env: Mapping[str, str] | None = None) -> pathlib.Path:
    return usage_dir(env) / LOCK_NAME


def pi_sessions_dir(env: Mapping[str, str] | None = None) -> pathlib.Path:
    """Root of pi session JSONL files (``<root>/<cwd-slug>/<ts>_<id>.jsonl``)."""
    env = _env(env)
    for name in (PI_ENV_SESSIONS_DIR, PI_ENV_SESSION_DIR):
        value = _env_value(env, name)
        if value:
            return pathlib.Path(value)
    agent_dir = _env_value(env, PI_ENV_AGENT_DIR)
    if agent_dir:
        return pathlib.Path(agent_dir) / "sessions"
    return _home_dir(env) / ".pi" / "agent" / "sessions"


def claude_projects_dir(env: Mapping[str, str] | None = None) -> pathlib.Path:
    """Root of claude project logs (``<root>/<cwd-slug>/<uuid>.jsonl``)."""
    env = _env(env)
    override = _env_value(env, CLAUDE_ENV_PROJECTS_DIR)
    if override:
        return pathlib.Path(override)
    config_dir = _env_value(env, CLAUDE_ENV_CONFIG_DIR)
    if config_dir:
        return pathlib.Path(config_dir) / "projects"
    return _home_dir(env) / ".claude" / "projects"


# ── small time/token helpers ─────────────────────────────────────────────────


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _as_utc(parsed)


def _iso(value: datetime) -> str:
    return _as_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_tz() -> tzinfo:
    local = datetime.now(timezone.utc).astimezone().tzinfo
    return local if local is not None else timezone.utc


def _as_int(value: Any) -> int | None:
    """Coerce a token count; unknown stays ``None`` (never fabricate a 0)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _add_tokens(target: dict[str, int | None], tokens: Mapping[str, Any]) -> None:
    for field in TOKEN_FIELDS:
        value = tokens.get(field)
        if value is None:
            continue
        current = target.get(field)
        target[field] = value if current is None else current + value


def _new_token_map() -> dict[str, int | None]:
    return dict.fromkeys(TOKEN_FIELDS)


def _token_total(tokens: Mapping[str, Any] | None) -> int:
    if not tokens:
        return 0
    return sum(int(v) for v in tokens.values() if v is not None)


def _percentile(values: Iterable[float], p: float) -> float | None:
    """Linear-interpolated percentile; ``None`` (rendered ``-``) when n < 5."""
    samples = sorted(float(v) for v in values if v is not None)
    if len(samples) < 5:
        return None
    if not 0 <= p <= 100:
        raise ValueError(f"percentile out of range: {p}")
    rank = (len(samples) - 1) * (p / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return samples[int(rank)]
    return samples[low] + (samples[high] - samples[low]) * (rank - low)


# ── ledger write side ────────────────────────────────────────────────────────


def append_event(record: Mapping[str, Any]) -> bool:
    """Append one ledger event under the cross-process lock.

    Fail-soft by contract (design §2): a broken ledger must never break a
    spawn. Returns ``False`` and warns once on stderr instead of raising.
    """
    try:
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = lock_path()
        acquire_lock(lock)
        try:
            line = json.dumps(dict(record), ensure_ascii=False, sort_keys=False)
            # One open/write/close per event + newline="\n": no CRLF doubling,
            # no interleaving between processes (design §10).
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
        finally:
            release_lock(lock)
        return True
    except Exception as exc:  # noqa: BLE001 - fail-soft contract (design §2)
        print(f"[mw usage] ledger append failed: {exc}", file=sys.stderr)
        return False


# ── session ids ──────────────────────────────────────────────────────────────


def new_session_id(key: str, pid: int, seq: int) -> str:
    """``mw-<slug(key)>-<pid>-<seq>``, validated with pi's session-id regex.

    ``pid`` + a launcher-local monotonically increasing ``seq`` make the id
    unique across restarts: reusing an id would *resume* the old session file
    (RQ1 §3), mixing two spawns into one log.
    """
    raw_key = "" if key is None else str(key)
    slug = _SLUG_RE.sub("-", raw_key.lower()).strip("-")
    if len(slug) > _SLUG_MAX:
        slug = slug[:_SLUG_MAX].strip("-")
    if not slug:
        raise ValueError(f"key {raw_key!r} has no [a-z0-9] characters to build a session id")
    session_id = f"mw-{slug}-{int(pid)}-{int(seq)}"
    if not SESSION_ID_RE.match(session_id):
        raise ValueError(
            f"invalid session id {session_id!r}: must match "
            "^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
        )
    return session_id


def _key_from_session_id(session_id: str | None) -> str | None:
    """Recover the owner key from ``mw-<key>-<pid>-<seq>`` (``None`` if absent)."""
    if not session_id or not session_id.startswith("mw-"):
        return None
    parts = session_id[3:].rsplit("-", 2)
    if len(parts) != 3:
        return None
    return parts[0] or None


def _session_id_from_path(path: pathlib.Path) -> str:
    stem = pathlib.Path(path).stem
    if "_" in stem:
        tail = stem.split("_", 1)[1].strip()
        if tail:
            return tail
    return stem


# ── --since parsing ──────────────────────────────────────────────────────────


def parse_since(text: str, now: datetime | None = None) -> datetime:
    """``7d`` / ``24h`` / ``30m`` / ``YYYY-MM-DD`` -> aware UTC datetime.

    Invalid input raises ``ValueError`` (the CLI turns that into rc=2).
    A calendar date means local midnight of that day.
    """
    now_utc = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    raw = "" if text is None else str(text).strip()
    if not raw:
        raise ValueError("empty --since value")
    relative = _RELATIVE_SINCE_RE.match(raw.lower())
    if relative:
        count = int(relative.group(1))
        return now_utc - _RELATIVE_UNITS[relative.group(2)] * count
    try:
        day = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        raise ValueError(
            f"invalid --since value {text!r} (expected 7d / 24h / 30m / YYYY-MM-DD)"
        ) from None
    return day.replace(tzinfo=_local_tz()).astimezone(timezone.utc)


def _window_label(since: datetime, now: datetime) -> str:
    seconds = int(round((now - since).total_seconds()))
    if seconds >= 86400 and seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60}m"
    return since.strftime("%Y-%m-%d")


# ── pi session scanning ──────────────────────────────────────────────────────


def _read_header(path: pathlib.Path) -> dict[str, Any] | None:
    """First JSONL line, only when it is a usable ``type:"session"`` header."""
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            first = handle.readline(65536)
    except OSError:
        return None
    if not first.strip():
        return None
    try:
        data = json.loads(first)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("type") != "session":
        return None
    if _parse_iso(data.get("timestamp")) is None:
        return None
    return data


def iter_session_files(root: pathlib.Path, since: datetime) -> Iterator[pathlib.Path]:
    """Yield pi session files that may hold activity at/after ``since``.

    Two coarse filters only (never a full JSON parse): file mtime first, then
    the first-line ``type:"session"`` header. A long-lived PM session whose
    header predates the window is still yielded on purpose — bucketing happens
    per message ``timestamp`` (RQ1 §6), so the header may not be used as a
    window cut-off.
    """
    root = pathlib.Path(root)
    if not root.is_dir():
        return
    cutoff = _as_utc(since).timestamp()
    try:
        candidates = sorted(root.rglob("*.jsonl"))
    except OSError:
        return
    for path in candidates:
        try:
            if path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        if _read_header(path) is None:
            continue
        yield path


def _pi_model_key(message: Mapping[str, Any]) -> str:
    provider = str(message.get("provider") or "").strip()
    model = str(message.get("model") or "").strip()
    if provider and model:
        return f"{provider}/{model}"
    return model or provider or UNKNOWN_LABEL


def _pi_tokens(usage: Mapping[str, Any]) -> dict[str, int | None]:
    return {
        "input": _as_int(usage.get("input")),
        "output": _as_int(usage.get("output")),
        "cache_read": _as_int(usage.get("cacheRead")),
        "cache_write": _as_int(usage.get("cacheWrite")),
    }


def scan_pi_session(path: pathlib.Path) -> dict[str, Any]:
    """Accumulate one pi session file: assistant ``message.usage`` + compaction.

    Line prefilter: only lines containing ``"assistant"`` or ``"compaction"``
    are JSON-parsed (RQ1 §5: full-corpus parse is 11 s, prefiltered is cheap).
    A torn tail or any other bad line is skipped, never fatal.
    """
    path = pathlib.Path(path)
    session_id = _session_id_from_path(path)
    header = _read_header(path)
    cwd: str | None = None
    started: datetime | None = None
    if header is not None:
        session_id = str(header.get("id") or session_id)
        cwd_value = header.get("cwd")
        cwd = str(cwd_value) if cwd_value else None
        started = _parse_iso(header.get("timestamp"))

    models: dict[str, dict[str, Any]] = {}
    events: list[tuple[str | None, str, dict[str, int | None]]] = []
    last_model: str | None = None
    last_ts: datetime | None = started
    tail = ""

    try:
        handle = path.open("r", encoding="utf-8", errors="replace", newline="")
    except OSError:
        handle = None
    if handle is None:
        return {
            "session_id": session_id,
            "cwd": cwd,
            "started_at": _iso(started) if started is not None else None,
            "ended_at": None,
            "models": {},
            "events": [],
        }

    with handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            tail = text
            if '"assistant"' not in text and '"compaction"' not in text:
                continue
            try:
                entry = json.loads(text)
            except ValueError:
                continue  # torn tail / corrupt line: skip, keep scanning
            if not isinstance(entry, dict):
                continue
            kind = entry.get("type")
            usage: Any = None
            if kind == "message":
                message = entry.get("message")
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    continue
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    continue
                model_key = _pi_model_key(message)
                last_model = model_key
            elif kind == "compaction":
                usage = entry.get("usage")
                if not isinstance(usage, dict):
                    continue
                model_key = last_model or UNKNOWN_LABEL
            else:
                continue

            stamp = _parse_iso(entry.get("timestamp"))
            if stamp is not None:
                last_ts = stamp
            tokens = _pi_tokens(usage)
            bucket = models.setdefault(model_key, {**_new_token_map(), "requests": 0})
            _add_tokens(bucket, tokens)
            bucket["requests"] += 1
            events.append((_iso(stamp) if stamp is not None else None, model_key, tokens))

    # Wall clock = header -> last entry (RQ1 §6). The last entry is usually not
    # an assistant message, so read its timestamp off the raw tail line instead
    # of parsing every line of the file.
    if tail:
        match = _TIMESTAMP_RE.search(tail)
        if match:
            tail_ts = _parse_iso(match.group(1))
            if tail_ts is not None and (last_ts is None or tail_ts > last_ts):
                last_ts = tail_ts

    return {
        "session_id": session_id,
        "cwd": cwd,
        "started_at": _iso(started) if started is not None else None,
        "ended_at": _iso(last_ts) if last_ts is not None else None,
        "models": models,
        "events": events,
    }


# ── claude session scanning ──────────────────────────────────────────────────


def _claude_model_key(message: Mapping[str, Any]) -> str:
    model = str(message.get("model") or "").strip()
    return f"claude/{model}" if model else "claude/" + UNKNOWN_LABEL


def _claude_session_files(session_id: str, roots: Iterable[pathlib.Path]) -> list[pathlib.Path]:
    """Main ``<uuid>.jsonl`` plus ``<uuid>/subagents/*.jsonl`` (design §3.1)."""
    files: list[pathlib.Path] = []
    for root in roots:
        root = pathlib.Path(root)
        # `<root>/<uuid>.jsonl` when root is the per-cwd project dir, plus
        # `<root>/<cwd-slug>/<uuid>.jsonl` when root is the projects root.
        parents = [root]
        try:
            parents.extend(sorted(p for p in root.iterdir() if p.is_dir()))
        except OSError:
            pass
        main = next(
            (parent / f"{session_id}.jsonl" for parent in parents
             if (parent / f"{session_id}.jsonl").is_file()),
            None,
        )
        if main is not None:
            files.append(main)
            files.extend(_jsonl_files(main.parent / session_id / "subagents"))
            continue
        # Subagent logs exist without a main file: still account for them.
        for parent in parents:
            files.extend(_jsonl_files(parent / session_id / "subagents"))
    seen: set[str] = set()
    unique: list[pathlib.Path] = []
    for path in files:
        marker = os.path.normcase(str(path))
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(path)
    return unique


def _jsonl_files(directory: pathlib.Path) -> list[pathlib.Path]:
    try:
        return sorted(path for path in directory.glob("*.jsonl") if path.is_file())
    except OSError:
        return []


def _claude_tokens(usage: Mapping[str, Any]) -> dict[str, int | None]:
    # claude's input_tokens is already the non-cached input (RQ3 §4).
    return {
        "input": _as_int(usage.get("input_tokens")),
        "output": _as_int(usage.get("output_tokens")),
        "cache_read": _as_int(usage.get("cache_read_input_tokens")),
        "cache_write": _as_int(usage.get("cache_creation_input_tokens")),
    }


def scan_claude_session(
    session_id: str, roots: Iterable[pathlib.Path]
) -> dict[str, Any] | None:
    """Read one claude session (main file + subagents), deduped by ``message.id``.

    The same assistant message is written 2-4 times per file; summing rows
    inflates tokens by 1.41-1.87x (RQ3 §2b). First occurrence wins.
    Returns ``None`` when no log exists, so the caller can record
    ``unknown_cli`` instead of pretending the run spent nothing.
    """
    raw_id = "" if session_id is None else str(session_id).strip()
    if not raw_id:
        return None
    if isinstance(roots, (str, pathlib.Path)):
        roots = [roots]
    files = _claude_session_files(raw_id, roots)
    if not files:
        return None

    seen: set[str] = set()
    models: dict[str, dict[str, Any]] = {}
    events: list[tuple[str | None, str, dict[str, int | None]]] = []
    cwd: str | None = None
    started: datetime | None = None
    ended: datetime | None = None

    for path in files:
        try:
            handle = path.open("r", encoding="utf-8", errors="replace", newline="")
        except OSError:
            continue
        with handle:
            for line in handle:
                text = line.strip()
                if not text or '"assistant"' not in text:
                    continue
                try:
                    entry = json.loads(text)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "assistant":
                    continue
                message = entry.get("message")
                if not isinstance(message, dict):
                    continue
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    continue
                message_id = message.get("id")
                if isinstance(message_id, str) and message_id:
                    if message_id in seen:
                        continue
                    seen.add(message_id)

                stamp = _parse_iso(entry.get("timestamp"))
                if stamp is not None:
                    if started is None or stamp < started:
                        started = stamp
                    if ended is None or stamp > ended:
                        ended = stamp
                entry_cwd = entry.get("cwd")
                if isinstance(entry_cwd, str) and entry_cwd:
                    cwd = entry_cwd

                model_key = _claude_model_key(message)
                tokens = _claude_tokens(usage)
                bucket = models.setdefault(model_key, {**_new_token_map(), "requests": 0})
                _add_tokens(bucket, tokens)
                bucket["requests"] += 1
                events.append((_iso(stamp) if stamp is not None else None, model_key, tokens))

    if not events:
        # The log exists but carries no usage rows: still an attributable run,
        # with no token group contribution.
        return {
            "session_id": raw_id,
            "cwd": cwd,
            "started_at": _iso(started) if started is not None else None,
            "ended_at": _iso(ended) if ended is not None else None,
            "models": models,
            "events": [],
        }
    return {
        "session_id": raw_id,
        "cwd": cwd,
        "started_at": _iso(started) if started is not None else None,
        "ended_at": _iso(ended) if ended is not None else None,
        "models": models,
        "events": events,
    }


# ── ledger read side ─────────────────────────────────────────────────────────


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _basename(value: str) -> str:
    return value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def _project_matches(value: Any, wanted: str) -> bool:
    """Accept a full path or its basename on either side (TS appends ``--project=<dir>``)."""
    if not value:
        return False
    have = _norm(value).replace("\\", "/").rstrip("/").lower()
    want = _norm(wanted).replace("\\", "/").rstrip("/").lower()
    if not want:
        return True
    return (
        have == want
        or _basename(have) == want
        or have == _basename(want)
        or _basename(have) == _basename(want)
    )


def _project_name(value: Any) -> str:
    name = _basename(_norm(value))
    return name or UNKNOWN_LABEL


def _run_matches(run: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    source = _norm(filters.get("source"))
    if source and _norm(run.get("source")) != source:
        return False
    key = _norm(filters.get("key"))
    if key and _norm(run.get("key")) != key:
        return False
    task_type = _norm(filters.get("type"))
    if task_type and _norm(run.get("type")) != task_type:
        return False
    model = _norm(filters.get("model")).lower()
    if model and model not in _norm(run.get("model")).lower():
        return False
    project = _norm(filters.get("project"))
    if project and not _project_matches(run.get("project"), project):
        return False
    return True


def load_runs(
    since: datetime, filters: Mapping[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the ledger and pair ``start``/``end`` events by ``run_id``.

    A run without an ``end`` event is ``open_run=True`` with ``wall_s`` left
    ``None`` (never 0, AC-004/AC-013). Bad lines are skipped and counted.
    ``spawn_failed`` events are kept as ``spawned=False`` entries so failed
    spawns stay visible in ``ledger.events`` without being counted as runs.
    """
    filters = filters or {}
    path = ledger_path()
    meta: dict[str, Any] = {
        "events": 0,
        "bad_lines": 0,
        "open_runs": 0,
        "path": str(path),
    }
    since_utc = _as_utc(since)
    if not path.exists():
        return [], meta

    slots: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    try:
        handle = path.open("r", encoding="utf-8", errors="replace", newline="")
    except OSError:
        return [], meta
    with handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                event = json.loads(text)
            except ValueError:
                meta["bad_lines"] += 1
                continue
            if not isinstance(event, dict):
                meta["bad_lines"] += 1
                continue
            run_id = event.get("run_id")
            kind = event.get("event")
            if not isinstance(run_id, str) or not run_id or kind not in _LEDGER_EVENTS:
                meta["bad_lines"] += 1
                continue
            meta["events"] += 1
            slot = slots.get(run_id)
            if slot is None:
                slot = {"start": None, "end": None, "failed": None}
                order.append(run_id)
                slots[run_id] = slot
            if kind == "end":
                slot["end"] = event
            elif kind == "start":
                if slot["start"] is None:
                    slot["start"] = event
            else:
                slot["failed"] = event

    runs: list[dict[str, Any]] = []
    for run_id in order:
        slot = slots[run_id]
        start = slot["start"] or {}
        end = slot["end"] or {}
        failed = slot["failed"] if slot["start"] is None and slot["end"] is None else None
        base = start or failed or {}

        start_ts = _parse_iso(start.get("ts"))
        end_ts = _parse_iso(end.get("ts"))
        failed_ts = _parse_iso((failed or {}).get("ts"))
        stamps = [stamp for stamp in (start_ts, end_ts, failed_ts) if stamp is not None]
        if stamps and max(stamps) < since_utc:
            continue

        wall = end.get("wall_s")
        if isinstance(wall, bool) or not isinstance(wall, (int, float)):
            wall = None
        if wall is None and start_ts is not None and end_ts is not None and end_ts >= start_ts:
            wall = (end_ts - start_ts).total_seconds()
        wall_s = float(wall) if wall is not None else None

        spawned = bool(start)
        if end:
            status = end.get("status") or "done"
        elif failed is not None:
            status = "spawn_failed"
        else:
            status = "running"

        run = {
            "run_id": run_id,
            "source": _norm(base.get("source")) or "worker",
            "project": base.get("project"),
            "key": base.get("key"),
            "task_key": base.get("task_key"),
            "type": base.get("type"),
            "role": base.get("role"),
            "cli": _norm(base.get("cli")) or UNKNOWN_LABEL,
            "attribution": _norm(base.get("attribution")) or "exact",
            "session_id": base.get("session_id"),
            "model": base.get("model"),
            "model_source": base.get("model_source"),
            "pid": base.get("pid"),
            "cwd": base.get("cwd"),
            "start_ts": _iso(start_ts) if start_ts is not None else None,
            "end_ts": _iso(end_ts) if end_ts is not None else None,
            "exit": end.get("exit") if end else None,
            "wall_s": wall_s,
            "status": status,
            "reconciled": bool(end.get("reconciled")),
            "open_run": spawned and not end,
            "spawned": spawned,
        }
        if not _run_matches(run, filters):
            continue
        runs.append(run)

    meta["open_runs"] = sum(1 for run in runs if run["open_run"])
    return runs, meta


# ── report aggregation ───────────────────────────────────────────────────────


def _window_events(
    events: Iterable[tuple[str | None, str, dict[str, int | None]]],
    since: datetime,
    now: datetime,
    model_filter: str,
) -> list[tuple[str | None, str, dict[str, int | None]]]:
    wanted = model_filter.lower()
    kept: list[tuple[str | None, str, dict[str, int | None]]] = []
    for stamp, model_key, tokens in events:
        moment = _parse_iso(stamp) if stamp else None
        # Message timestamps decide the bucket, not the file (RQ1 §6). A row
        # without a timestamp cannot be placed and is kept rather than dropped.
        if moment is not None and (moment < since or moment > now):
            continue
        if wanted and wanted not in (model_key or "").lower():
            continue
        kept.append((stamp, model_key, tokens))
    return kept


def _wall_from_session(session: Mapping[str, Any]) -> float | None:
    start = _parse_iso(session.get("started_at"))
    end = _parse_iso(session.get("ended_at"))
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds()


def _unit_matches(unit: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    source = _norm(filters.get("source"))
    if source and unit.get("source") != source:
        return False
    key = _norm(filters.get("key"))
    if key and _norm(unit.get("key")) != key:
        return False
    task_type = _norm(filters.get("type"))
    if task_type and _norm(unit.get("type")) != task_type:
        return False
    project = _norm(filters.get("project"))
    if project and not _project_matches(unit.get("project"), project):
        return False
    return True


def _new_group_entry(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "calls": 0,
        "tokens": _new_token_map(),
        "runs": 0,
        "_walls": [],
        "_session_walls": [],
    }


def _finalize_group(bucket: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Render one group row, keeping the two wall sources strictly apart.

    ``wall_kind`` names the source of ``wall_p50/wall_p90/n``: ``run`` = ledger
    spawn -> reap samples, ``session`` = header -> last entry spans. A group
    that has run samples never borrows session spans (not even to reach n >= 5),
    because a PM window can span days while a run lasts seconds (T-06).
    ``none`` means there is no usable sample or too few of them, so both
    percentiles stay ``None`` and ``n`` still reports the sample count.
    """
    rows: list[dict[str, Any]] = []
    for entry in bucket.values():
        run_walls = entry.pop("_walls")
        session_walls = entry.pop("_session_walls")
        if run_walls:
            walls: list[float] = run_walls
            wall_kind = "run"
        elif session_walls:
            walls = session_walls
            wall_kind = "session"
        else:
            walls = []
            wall_kind = "none"
        p50 = _percentile(walls, 50)
        p90 = _percentile(walls, 90)
        if p50 is None or p90 is None:
            # Fewer than 5 samples (or none): nothing is reported, so no
            # source is claimed either.
            wall_kind = "none"
        rows.append(
            {
                "name": entry["name"],
                "calls": entry["calls"],
                "tokens": {field: entry["tokens"][field] for field in TOKEN_FIELDS},
                "runs": entry["runs"],
                "wall_p50": p50,
                "wall_p90": p90,
                "n": len(walls),
                "wall_kind": wall_kind,
            }
        )
    rows.sort(key=lambda row: (-row["calls"], -_token_total(row["tokens"]), row["name"]))
    return rows


def _coverage_rows(
    runs: list[dict[str, Any]],
    claude_exact: set[str],
    pm_units: int,
) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}

    def bump(cli: str, attribution: str) -> None:
        counts[(cli, attribution)] = counts.get((cli, attribution), 0) + 1

    for run in runs:
        if not run["spawned"]:
            continue
        cli = _norm(run.get("cli")) or UNKNOWN_LABEL
        if cli == "codex":
            # codex v1 is never read (RQ3 §3/§6): token columns stay unknown.
            attribution = "unknown_cli"
        elif cli == "claude":
            attribution = "exact" if run["run_id"] in claude_exact else "unknown_cli"
        else:
            attribution = _norm(run.get("attribution")) or "exact"
        bump(cli, attribution)
    if pm_units:
        counts[("pi", "exact")] = counts.get(("pi", "exact"), 0) + pm_units

    def sort_key(item: tuple[str, str]) -> tuple[int, str, int]:
        cli, attribution = item
        try:
            rank = _CLI_ORDER.index(cli)
        except ValueError:
            rank = len(_CLI_ORDER)
        return (rank, cli, 0 if attribution == "exact" else 1)

    return [
        {"cli": cli, "runs": counts[(cli, attribution)], "attribution": attribution}
        for cli, attribution in sorted(counts, key=sort_key)
    ]


def build_report(
    now: datetime | None = None,
    since: datetime | None = None,
    filters: Mapping[str, Any] | None = None,
    *,
    pi_root: pathlib.Path | str | None = None,
    claude_roots: Iterable[pathlib.Path | str] | None = None,
) -> dict[str, Any]:
    """Join ledger + session logs into the ``mw stats --json`` contract (design §5).

    Attribution: a session id starting with ``mw-`` is a worker run and its
    owner key is parsed back out of the id; anything else is a PM window
    session. Worker wall clock prefers the ledger (spawn -> reap) and falls
    back to header -> last entry when the ledger row is missing. Each group row
    labels its wall source with ``wall_kind`` (``run`` / ``session`` / ``none``):
    a group that has ledger run walls never mixes in session spans, because a
    PM window can span days while a run lasts seconds (T-06).
    ``unknown_cli`` runs (codex, missing claude log) appear in ``coverage``
    only, never in a token group.
    """
    now_utc = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    filters = dict(filters or {})
    if since is None:
        since_utc = parse_since(_norm(filters.get("window")) or "7d", now_utc)
    else:
        since_utc = _as_utc(since)
    window = _norm(filters.get("window")) or _window_label(since_utc, now_utc)

    runs, ledger_meta = load_runs(since_utc, filters)
    by_session = {
        run["session_id"]: run
        for run in runs
        if isinstance(run.get("session_id"), str) and run["session_id"]
    }
    model_filter = _norm(filters.get("model"))

    units: list[dict[str, Any]] = []
    pm_units = 0

    # -- pi: worker sessions (mw- ids) + PM window sessions ----------------
    root = pathlib.Path(pi_root) if pi_root is not None else pi_sessions_dir()
    for path in iter_session_files(root, since_utc):
        session = scan_pi_session(path)
        if not session["events"]:
            continue
        session_id = str(session["session_id"])
        run = by_session.get(session_id)
        ledger_wall = (run or {}).get("wall_s")
        if session_id.startswith("mw-"):
            unit = {
                "source": "worker",
                "cli": _norm((run or {}).get("cli")) or "pi",
                "key": _key_from_session_id(session_id)
                or _norm((run or {}).get("key"))
                or UNKNOWN_LABEL,
                "type": _norm((run or {}).get("type")) or UNKNOWN_LABEL,
                "project": (run or {}).get("project") or session.get("cwd"),
                "session_id": session_id,
                "wall_s": ledger_wall,
            }
        else:
            unit = {
                "source": "pm",
                "cli": "pi",
                "key": PM_LABEL,
                "type": PM_LABEL,
                "project": session.get("cwd"),
                "session_id": session_id,
                "wall_s": ledger_wall,
            }
        # A ledger wall is a run sample (spawn -> reap) for worker and PM alike.
        unit["wall_kind"] = "run" if ledger_wall is not None else "none"
        if run is None:
            # No ledger row at all: the session span is the only wall we have,
            # and it is a *session* sample (never mixed into run percentiles).
            span = _wall_from_session(session)
            unit["wall_s"] = span
            unit["wall_kind"] = "session" if span is not None else "none"
        # A run that exists but has no end event keeps wall_s = None (AC-004:
        # an orphan is never reported as 0, and never guessed from the log).
        unit["project"] = _project_name(unit["project"])
        unit["events"] = _window_events(session["events"], since_utc, now_utc, model_filter)
        if not unit["events"] or not _unit_matches(unit, filters):
            continue
        units.append(unit)
        if unit["source"] == "pm":
            pm_units += 1

    # -- claude: only runs whose ledger row carries a --session-id uuid ----
    if claude_roots is None:
        claude_roots = [claude_projects_dir()]
    if isinstance(claude_roots, (str, pathlib.Path)):
        claude_roots = [claude_roots]
    claude_root_list = [pathlib.Path(root_item) for root_item in claude_roots]
    claude_exact: set[str] = set()
    for run in runs:
        if _norm(run.get("cli")) != "claude" or not run["spawned"]:
            continue
        session_id = run.get("session_id")
        session = scan_claude_session(session_id, claude_root_list) if session_id else None
        if session is None:
            continue
        claude_exact.add(run["run_id"])
        events = _window_events(session["events"], since_utc, now_utc, model_filter)
        if not events:
            continue
        unit = {
            "source": _norm(run.get("source")) or "worker",
            "cli": "claude",
            "key": _norm(run.get("key")) or UNKNOWN_LABEL,
            "type": _norm(run.get("type")) or UNKNOWN_LABEL,
            "project": _project_name(run.get("project") or session.get("cwd")),
            "session_id": session_id,
            "wall_s": run.get("wall_s"),
            "wall_kind": "run" if run.get("wall_s") is not None else "none",
            "events": events,
        }
        if not _unit_matches(unit, filters):
            continue
        units.append(unit)

    # -- aggregation ------------------------------------------------------
    buckets: dict[str, dict[str, dict[str, Any]]] = {
        "model": {},
        "type": {},
        "key": {},
        "project": {},
    }
    total_tokens = _new_token_map()
    total_calls = 0
    for unit in units:
        touched: dict[str, set[str]] = {dim: set() for dim in buckets}
        for _stamp, model_key, tokens in unit["events"]:
            total_calls += 1
            _add_tokens(total_tokens, tokens)
            names = {
                "model": model_key or UNKNOWN_LABEL,
                "type": unit["type"] or UNKNOWN_LABEL,
                "key": unit["key"] or UNKNOWN_LABEL,
                "project": unit["project"] or UNKNOWN_LABEL,
            }
            for dim, name in names.items():
                entry = buckets[dim].get(name)
                if entry is None:
                    entry = _new_group_entry(name)
                    buckets[dim][name] = entry
                entry["calls"] += 1
                _add_tokens(entry["tokens"], tokens)
                touched[dim].add(name)
        for dim in buckets:
            for name in touched[dim]:
                entry = buckets[dim][name]
                entry["runs"] += 1
                if unit["wall_s"] is None:
                    continue
                if unit.get("wall_kind") == "run":
                    entry["_walls"].append(float(unit["wall_s"]))
                elif unit.get("wall_kind") == "session":
                    entry["_session_walls"].append(float(unit["wall_s"]))

    spawned_runs = [run for run in runs if run["spawned"]]
    ledger_pm = sum(1 for run in spawned_runs if _norm(run.get("source")) == "pm")
    worker_runs = len(spawned_runs) - ledger_pm
    sources = {"worker": worker_runs, "pm": pm_units + ledger_pm}

    return {
        "generated_at": _iso(now_utc),
        "since": _iso(since_utc),
        "window": window,
        "ledger": {
            "path": ledger_meta["path"],
            "events": ledger_meta["events"],
            "bad_lines": ledger_meta["bad_lines"],
            "open_runs": ledger_meta["open_runs"],
        },
        "totals": {
            "calls": total_calls,
            "tokens": {field: total_tokens[field] for field in TOKEN_FIELDS},
            "runs": len(spawned_runs) + pm_units,
        },
        "groups": {dim: _finalize_group(buckets[dim]) for dim in buckets},
        "coverage": _coverage_rows(spawned_runs, claude_exact, pm_units),
        "sources": sources,
    }


# ── text rendering ───────────────────────────────────────────────────────────

_ROW_TEMPLATE = (
    "  {name:<24} calls {calls:<5} in {tok_in:<6} out {tok_out:<6}"
    " cacheR {tok_r:<7} cacheW {tok_w:<6} wall p50 {p50:<6} p90 {p90:<6} n {n}"
)


def _format_tokens(value: Any) -> str:
    """``1.2M`` / ``310k`` (three significant digits); ``None`` renders ``-``."""
    if value is None:
        return "-"
    number = int(value)
    if number < 1000:
        return str(number)
    units = ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "k"))
    for index, (scale, suffix) in enumerate(units):
        if number < scale:
            continue
        scaled = number / scale
        if scaled >= 999.5 and index > 0:
            # Rounding would print "1000k": step up one unit instead.
            scale, suffix = units[index - 1]
            scaled = number / scale
        if scaled < 10:
            text = f"{scaled:.2f}"
        elif scaled < 100:
            text = f"{scaled:.1f}"
        else:
            text = f"{scaled:.0f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text + suffix
    return str(number)


def _format_wall(value: Any) -> str:
    """``4m12s`` / ``11m03s``; ``None`` renders ``-``."""
    if value is None:
        return "-"
    seconds = int(round(float(value)))
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    if seconds >= 60:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds}s"


def _format_row(row: Mapping[str, Any]) -> str:
    tokens = row.get("tokens") or {}
    p90 = _format_wall(row.get("wall_p90"))
    if row.get("wall_kind") == "session":
        # Session spans are not worker wall clock: mark them (footnote below).
        p90 += SESSION_WALL_MARK
    return _ROW_TEMPLATE.format(
        name=str(row.get("name") or UNKNOWN_LABEL),
        calls=row.get("calls", 0),
        tok_in=_format_tokens(tokens.get("input")),
        tok_out=_format_tokens(tokens.get("output")),
        tok_r=_format_tokens(tokens.get("cache_read")),
        tok_w=_format_tokens(tokens.get("cache_write")),
        p50=_format_wall(row.get("wall_p50")),
        p90=p90,
        n=row.get("n", 0),
    )


def _format_coverage(coverage: Iterable[Mapping[str, Any]]) -> str:
    items = list(coverage)
    if not items:
        return "coverage: none"
    parts: list[str] = []
    for index, item in enumerate(items):
        cli = str(item.get("cli") or UNKNOWN_LABEL)
        runs = item.get("runs", 0)
        label = "exact" if item.get("attribution") == "exact" else "未统计"
        suffix = " runs" if index == 0 else ""
        parts.append(f"{cli} {runs}{suffix} ({label})")
    return "coverage: " + " · ".join(parts)


def format_report_text(report: Mapping[str, Any]) -> str:
    """Human-readable report (design §6); ``None`` renders ``-``, never ``0``."""
    ledger = report.get("ledger") or {}
    totals = report.get("totals") or {}
    sources = report.get("sources") or {}
    groups = report.get("groups") or {}
    since = _norm(report.get("since"))
    since_date = since[:10] if len(since) >= 10 else since
    lines = [
        f"usage since {since_date} ({_norm(report.get('window')) or '-'}) · "
        f"ledger {ledger.get('events', 0)} events · "
        f"runs {totals.get('runs', 0)} "
        f"(worker {sources.get('worker', 0)} / pm {sources.get('pm', 0)})"
    ]
    path = _norm(ledger.get("path"))
    if path and not pathlib.Path(path).exists():
        lines.append("no ledger yet")

    sections = [(dim, title, groups.get(dim) or []) for dim, title in _GROUP_TITLES]
    marked = False
    if not any(rows for _dim, _title, rows in sections):
        lines.append("")
        lines.append("no usage in window")
    else:
        for _dim, title, rows in sections:
            if not rows:
                continue
            lines.append("")
            lines.append(title)
            for row in rows:
                if row.get("wall_kind") == "session":
                    marked = True
                lines.append(_format_row(row))

    if marked:
        lines.append("")
        lines.append(SESSION_WALL_FOOTNOTE)
    lines.append("")
    lines.append(_format_coverage(report.get("coverage") or []))
    return "\n".join(lines)

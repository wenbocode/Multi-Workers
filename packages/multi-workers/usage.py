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

#: ``[CLAIMS]`` trace line (claim-driven-review T-05 / design D-004). It is a
#: line of its own and never folded into ``[END]``: both sides of ``[END]``
#: are anchored regexes (``heartbeat.ts:93``, ``mw_common.py:2768``). The five
#: fields keep a fixed order; trailing fields are ignored, a missing field
#: makes the line unparseable (no guessing).
_CLAIMS_LINE_RE = re.compile(
    r"^\s*\[CLAIMS\]\s+(?:\S+\s+)?"
    r"claims=(\d+)\s+"
    r"closed=(\d+)\s+"
    r"partial=(\d+)\s+"
    r"unverified=(\d+)\s+"
    r"fetches=(\d+)(?=\s|$)"
)

#: Claim counters of one run (``[CLAIMS]`` line / ``run.json#claims`` subobject).
CLAIMS_FIELDS = ("claims", "closed", "partial", "unverified", "fetches")

#: Rendered for "not computable": never ``0`` and never an approximation.
CLAIMS_NA = "n/a"

#: Run-level detail fields, verbatim (spec §11.2 R9). Missing values stay
#: ``None`` and are rendered ``-`` in text.
DETAIL_FIELDS = (
    "run_id",
    "started_at",
    "project",
    "ended_at",
    "key",
    "task_key",
    "type",
    "model",
    "calls",
    "tokens",
    "wall_s",
    "wall_kind",
    "status",
    "attribution",
    "session_id",
    "open_run",
)


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


# ── --since / --until parsing ────────────────────────────────────────────────


def _parse_bound(text: str, now: datetime | None, flag: str, *, allow_time: bool) -> datetime:
    """Parse one window bound; ``--since`` and ``--until`` share this parser.

    Relative forms (``7d`` / ``24h`` / ``30m``) are always an offset back from
    ``now``. Dates (plus ``YYYY-MM-DDTHH:MM`` for ``--until`` only) mean local
    wall-clock time. Invalid input raises ``ValueError`` (the CLI turns that
    into rc=2).
    """
    now_utc = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    raw = "" if text is None else str(text).strip()
    if not raw:
        raise ValueError(f"empty {flag} value")
    relative = _RELATIVE_SINCE_RE.match(raw.lower())
    if relative:
        count = int(relative.group(1))
        return now_utc - _RELATIVE_UNITS[relative.group(2)] * count
    patterns = ("%Y-%m-%d", "%Y-%m-%dT%H:%M") if allow_time else ("%Y-%m-%d",)
    for pattern in patterns:
        try:
            parsed = datetime.strptime(raw, pattern)
        except ValueError:
            continue
        return parsed.replace(tzinfo=_local_tz()).astimezone(timezone.utc)
    expected = "7d / 24h / 30m / YYYY-MM-DD"
    if allow_time:
        expected += " / YYYY-MM-DDTHH:MM"
    raise ValueError(f"invalid {flag} value {text!r} (expected {expected})")


def parse_since(text: str, now: datetime | None = None) -> datetime:
    """``7d`` / ``24h`` / ``30m`` / ``YYYY-MM-DD`` -> aware UTC datetime.

    Invalid input raises ``ValueError`` (the CLI turns that into rc=2).
    A calendar date means local midnight of that day.
    """
    return _parse_bound(text, now, "--since", allow_time=False)


def parse_until(text: str, now: datetime | None = None) -> datetime:
    """``--until`` upper bound: same forms as ``parse_since`` + ``YYYY-MM-DDTHH:MM``.

    The extra form is local wall-clock time of that minute ("yesterday 14:00"),
    so a review window can start and end inside one day. Relative forms keep
    ``parse_since`` semantics: ``24h`` means ``now - 24h``.
    """
    return _parse_bound(text, now, "--until", allow_time=True)


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
    since: datetime,
    filters: Mapping[str, Any] | None = None,
    *,
    until: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the ledger and pair ``start``/``end`` events by ``run_id``.

    A run without an ``end`` event is ``open_run=True`` with ``wall_s`` left
    ``None`` (never 0, AC-004/AC-013). Bad lines are skipped and counted.
    ``spawn_failed`` events are kept as ``spawned=False`` entries so failed
    spawns stay visible in ``ledger.events`` without being counted as runs.

    The window is half-open ``[since, until)``: a run is kept when any of its
    event stamps is ``>= since`` and any is ``< until`` (an unstamped event
    counts as placeable). A run whose events all fall at/after ``until`` is
    gone from every downstream view, not only from the detail table.
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
    until_utc = _as_utc(until) if until is not None else None
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
        if until_utc is not None and stamps and min(stamps) >= until_utc:
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
        # Optional claim metadata (claim-driven-review T-05): a ledger event may
        # carry the run's claim counters (a ``claims`` subobject as in run.json,
        # or its ``[CLAIMS]`` line). Absent on both events -> the key is not
        # added and the run dict is exactly what it was before T-05.
        for claim_key in ("claims", "claims_line"):
            value = end.get(claim_key) if end.get(claim_key) is not None else base.get(claim_key)
            if value is not None:
                run[claim_key] = value
        if not _run_matches(run, filters):
            continue
        runs.append(run)

    meta["open_runs"] = sum(1 for run in runs if run["open_run"])
    return runs, meta


# ── claim coverage metrics (claim-driven-review T-05, design §3.4) ──────────


def parse_claims_line(line: str) -> dict[str, int] | None:
    """Parse one ``[CLAIMS]`` trace line into its five counters, or ``None``.

    Shape (T-04, design D-004): ``[CLAIMS] <ts> claims=<n> closed=<n>
    partial=<n> unverified=<n> fetches=<n>``. The field order is fixed, so a
    reordered line is not parsed; extra trailing fields are ignored. A line
    without all five counters returns ``None`` (an old bundle has no
    ``[CLAIMS]`` line at all, and a half line is not a measurement).
    """
    if not isinstance(line, str):
        return None
    match = _CLAIMS_LINE_RE.match(line)
    if match is None:
        return None
    return {field: int(value) for field, value in zip(CLAIMS_FIELDS, match.groups())}


def parse_claims_lines(lines: Iterable[str]) -> dict[str, int] | None:
    """Counters of the last parseable ``[CLAIMS]`` line in ``lines``.

    A trace can hold more than one line (a retried run); the last one is the
    settled measurement, so later lines win. ``None`` when no line parses.
    """
    found: dict[str, int] | None = None
    for line in lines:
        parsed = parse_claims_line(line)
        if parsed is not None:
            found = parsed
    return found


def _run_claims_counts(run: Mapping[str, Any] | None) -> dict[str, int] | None:
    """Claim counters carried by one run mapping, or ``None``.

    A pre-parsed ``claims`` subobject (``run.json`` / a ledger event) wins;
    otherwise the run's ``[CLAIMS]`` line is parsed from ``claims_line`` or
    from the multiline ``trace`` text. Nothing to read means no measurement —
    the caller must not infer one.
    """
    if not isinstance(run, Mapping):
        return None
    payload = run.get("claims")
    if isinstance(payload, Mapping):
        counts: dict[str, int] = {}
        for field in CLAIMS_FIELDS:
            # run.json names the total `total` (design §3.4); a trace-shaped
            # dict may spell it `claims`. Both are the same counter.
            value = _as_int(payload.get(field))
            if value is None and field == "claims":
                value = _as_int(payload.get("total"))
            if value is None:
                return None
            counts[field] = value
        return counts
    for key in ("claims_line", "trace"):
        text = run.get(key)
        if isinstance(text, str) and text.strip():
            return parse_claims_lines(text.splitlines())
    return None


def _claims_tokens(session: Mapping[str, Any] | None) -> int | None:
    """Tokens of one joined session, or ``None`` when it cannot be attributed.

    The join is the existing one (``runs.jsonl`` ``start.session_id`` -> pi
    session header ``id``); a run without a session log, or a log whose rows
    carry no usage, stays unattributable rather than becoming ``0``.
    """
    if not isinstance(session, Mapping):
        return None
    events = session.get("events") or []
    if not events:
        return None
    tokens = _new_token_map()
    for _stamp, _model_key, event_tokens in events:
        _add_tokens(tokens, event_tokens)
    if all(value is None for value in tokens.values()):
        return None
    return _token_total(tokens)


def claims_metrics(
    run: Mapping[str, Any] | None,
    session: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Claim-coverage metrics of one run (design §3.4), or ``None``.

    ``run`` supplies the claim counters (``claims`` subobject or ``[CLAIMS]``
    line), ``session`` is the joined session scan that supplies ``tokens``.
    ``tokens_per_closed_claim = Σtokens / Σclosed``; it is ``"n/a"`` (never
    ``0``) when the session cannot be attributed (then ``tokens=None`` and
    ``attributable=False``) or when ``closed == 0``. A run with no
    ``[CLAIMS]`` line yields ``None`` as a whole: no inference, no defaults.
    """
    counts = _run_claims_counts(run)
    if counts is None:
        return None
    tokens = _claims_tokens(session)
    closed = counts["closed"]
    return {
        "claims": counts["claims"],
        "closed": closed,
        "partial": counts["partial"],
        "unverified": counts["unverified"],
        "fetches": counts["fetches"],
        "tokens": tokens,
        "tokens_per_closed_claim": (
            CLAIMS_NA if tokens is None or closed == 0 else tokens / closed
        ),
        "attributable": tokens is not None,
    }


# ── report aggregation ───────────────────────────────────────────────────────


def _window_events(
    events: Iterable[tuple[str | None, str, dict[str, int | None]]],
    since: datetime,
    until: datetime,
    model_filter: str,
) -> list[tuple[str | None, str, dict[str, int | None]]]:
    """Keep events in the half-open window ``[since, until)`` (R7)."""
    wanted = model_filter.lower()
    kept: list[tuple[str | None, str, dict[str, int | None]]] = []
    for stamp, model_key, tokens in events:
        moment = _parse_iso(stamp) if stamp else None
        # Message timestamps decide the bucket, not the file (RQ1 §6). A row
        # without a timestamp cannot be placed and is kept rather than dropped.
        if moment is not None and (moment < since or moment >= until):
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


def _detail_tokens(unit: Mapping[str, Any] | None) -> tuple[int | None, dict[str, int | None]]:
    """``(calls, tokens)`` of one unit's in-window events; ``None`` when unknown.

    ``None`` (not 0) means "cannot attribute": 0 would claim that the run
    really made no request.
    """
    if unit is None:
        return None, _new_token_map()
    tokens = _new_token_map()
    calls = 0
    for _stamp, _model_key, event_tokens in unit.get("events") or []:
        calls += 1
        _add_tokens(tokens, event_tokens)
    return calls, tokens


def _unit_model(unit: Mapping[str, Any] | None) -> str | None:
    """Session model only when it is unambiguous (otherwise no guessing)."""
    models = (unit or {}).get("models") or {}
    if len(models) == 1:
        return next(iter(models))
    return None


def _run_attribution(run: Mapping[str, Any], claude_exact: set[str]) -> str:
    """Same attribution rule as ``coverage`` (codex / missing claude log: unknown)."""
    cli = _norm(run.get("cli")) or UNKNOWN_LABEL
    if cli == "codex":
        return "unknown_cli"
    if cli == "claude":
        return "exact" if run.get("run_id") in claude_exact else "unknown_cli"
    return _norm(run.get("attribution")) or "exact"


def _detail_sort_key(row: Mapping[str, Any]) -> tuple[bool, str]:
    """ISO-Z stamps sort chronologically as strings; undated rows sink last."""
    started = row.get("started_at")
    return (bool(started), str(started or ""))


def _run_detail_row(
    run: Mapping[str, Any],
    unit: Mapping[str, Any] | None,
    claude_exact: set[str],
) -> dict[str, Any]:
    """One ledger run as a detail row (R9).

    An open run keeps ``wall_s=None`` / ``wall_kind="none"``: the ledger has
    no reap yet and the session span must never be used to fill it in
    (T-06 / AC-016). A run whose claims were measured (``[CLAIMS]`` line /
    ``claims`` subobject) grows an extra ``claims`` key; a run without one
    keeps the R9 key set byte-for-byte, so old reports are unchanged.

    ``project`` (R18) is the same raw value the ``by project`` grouping joins
    (``build_report`` line that builds a unit): ledger ``start.project`` first,
    then the session header ``cwd``, else ``None`` -- never an empty string, so
    an old ledger row renders ``-`` instead of a fake project.
    """
    calls, tokens = _detail_tokens(unit)
    open_run = bool(run.get("open_run"))
    wall_s = None if open_run else run.get("wall_s")
    row = {
        "run_id": run.get("run_id"),
        "started_at": run.get("start_ts"),
        "project": run.get("project")
        or (unit or {}).get("project")
        or (unit or {}).get("cwd")
        or None,
        "ended_at": run.get("end_ts"),
        "key": run.get("key"),
        "task_key": run.get("task_key"),
        "type": run.get("type"),
        "model": run.get("model") or _unit_model(unit),
        "calls": calls,
        "tokens": tokens,
        "wall_s": wall_s,
        "wall_kind": "run" if wall_s is not None else "none",
        "status": run.get("status"),
        "attribution": _run_attribution(run, claude_exact),
        "session_id": run.get("session_id"),
        "open_run": open_run,
    }
    claims = claims_metrics(run, unit)
    if claims is not None:
        # Only measured runs carry the key (no ``claims: null`` padding): the
        # JSON/text of a project without ``[CLAIMS]`` lines stays unchanged.
        row["claims"] = claims
    return row


def _pm_detail_row(unit: Mapping[str, Any]) -> dict[str, Any]:
    """A PM window session without a ledger row.

    ``totals.runs`` counts it, so the detail table must carry it too, otherwise
    ``sum(runs.tokens) == totals.tokens`` would break (AC-015). Its span is a
    *session* wall (``*`` marker), never a run sample.
    """
    calls, tokens = _detail_tokens(unit)
    span = _wall_from_session(
        {"started_at": unit.get("started_at"), "ended_at": unit.get("ended_at")}
    )
    return {
        "run_id": None,
        "started_at": unit.get("started_at"),
        # R18/AC-025: a PM session's project *is* its header cwd (no ledger row).
        "project": unit.get("project") or unit.get("cwd") or None,
        "ended_at": unit.get("ended_at"),
        "key": unit.get("key"),
        "task_key": None,
        "type": unit.get("type"),
        "model": _unit_model(unit),
        "calls": calls,
        "tokens": tokens,
        "wall_s": span,
        "wall_kind": "session" if span is not None else "none",
        "status": None,
        "attribution": "exact",
        "session_id": unit.get("session_id"),
        "open_run": False,
    }


def _detail_rows(
    spawned_runs: list[dict[str, Any]],
    units: list[dict[str, Any]],
    by_session: Mapping[str, dict[str, Any]],
    claude_exact: set[str],
) -> list[dict[str, Any]]:
    """Run-level detail rows, newest first (R8-R10, AC-015/AC-016).

    Coverage: every spawned ledger run gets a row (a missing session log keeps
    ``calls``/``tokens`` at ``None``), plus every PM window session that has no
    ledger row. That makes ``runs_total == totals.runs`` and lets the token
    columns sum to ``totals.tokens`` before ``limit`` truncation.
    """
    by_unit_session: dict[str, dict[str, Any]] = {
        str(unit["session_id"]): unit for unit in units if unit.get("session_id")
    }
    rows: list[dict[str, Any]] = []
    for run in spawned_runs:
        session_id = run.get("session_id")
        unit = by_unit_session.get(str(session_id)) if session_id else None
        rows.append(_run_detail_row(run, unit, claude_exact))
    for unit in units:
        if unit.get("source") != "pm":
            continue
        if str(unit.get("session_id") or "") in by_session:
            continue  # already covered by its ledger run row
        rows.append(_pm_detail_row(unit))
    rows.sort(key=_detail_sort_key, reverse=True)
    return rows


def build_report(
    now: datetime | None = None,
    since: datetime | None = None,
    filters: Mapping[str, Any] | None = None,
    *,
    pi_root: pathlib.Path | str | None = None,
    claude_roots: Iterable[pathlib.Path | str] | None = None,
    until: datetime | None = None,
    limit: int | None = 20,
    detail: bool = False,
    include_all_runs: bool = False,
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

    Window is half-open ``[since, until)`` with ``until`` defaulting to ``now``
    (R7). ``runs``/``runs_total`` are the run-level detail (R8-R10): the list is
    always in the JSON (``detail`` only drives text rendering in
    :func:`format_report_text`), newest first, cut to ``limit`` rows (``None``
    or ``0`` = no cut) while ``runs_total`` keeps the uncut count. ``tokens``
    and ``calls`` are the same joined events the groups use, so with no cut
    ``sum(runs.tokens) == totals.tokens`` (AC-015). An ``until`` earlier than
    ``since`` yields an empty window; rejecting it with rc=2 belongs to the
    CLI (R7), not to this read-only kernel.

    ``include_all_runs`` is the delivery channel for the HTML report (R15/R16):
    the uncut row list is already built here, so asking for it costs nothing
    extra and the same objects (same order) back both keys. With ``True`` the
    report additionally carries ``runs_all`` (``len(runs_all) == runs_total``,
    ``runs_all[:k] == build_report(limit=k)["runs"]``, AC-023/AC-024) while
    ``runs`` stays cut, so the JSON/text contract does not widen. ``False``
    (default) leaves the returned key set exactly as before: no ``runs_all``,
    no JSON bloat.
    """
    now_utc = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    filters = dict(filters or {})
    if since is None:
        since_utc = parse_since(_norm(filters.get("window")) or "7d", now_utc)
    else:
        since_utc = _as_utc(since)
    until_utc = _as_utc(until) if until is not None else now_utc
    window = _norm(filters.get("window")) or _window_label(since_utc, until_utc)

    runs, ledger_meta = load_runs(since_utc, filters, until=until_utc)
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
        unit["started_at"] = session.get("started_at")
        unit["ended_at"] = session.get("ended_at")
        unit["models"] = session.get("models") or {}
        unit["events"] = _window_events(session["events"], since_utc, until_utc, model_filter)
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
        events = _window_events(session["events"], since_utc, until_utc, model_filter)
        if not events:
            continue
        unit = {
            "source": _norm(run.get("source")) or "worker",
            "cli": "claude",
            "key": _norm(run.get("key")) or UNKNOWN_LABEL,
            "type": _norm(run.get("type")) or UNKNOWN_LABEL,
            "project": run.get("project") or session.get("cwd") or None,
            "session_id": session_id,
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "models": session.get("models") or {},
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
                # Display name only: the raw path stays on the unit so the run
                # detail row and this group join the exact same value (R19).
                "project": _project_name(unit["project"]),
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

    # -- run-level detail (R8-R10) ----------------------------------------
    detail_rows = _detail_rows(spawned_runs, units, by_session, claude_exact)
    runs_total = len(detail_rows)
    if limit is None:
        shown_runs = detail_rows
    else:
        limit_count = int(limit)
        if limit_count < 0:
            raise ValueError(f"limit must be >= 0 (0 = no limit), got {limit!r}")
        shown_runs = detail_rows if limit_count == 0 else detail_rows[:limit_count]

    report: dict[str, Any] = {
        "generated_at": _iso(now_utc),
        "since": _iso(since_utc),
        "until": _iso(until_utc),
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
        "runs_total": runs_total,
        "runs": shown_runs,
    }
    if include_all_runs:
        # Same list object the cut above sliced, so `runs_all[:k]` and
        # `build_report(limit=k)["runs"]` are field-for-field equal (AC-024).
        report["runs_all"] = detail_rows
    return report


# ── text rendering ───────────────────────────────────────────────────────────

_ROW_TEMPLATE = (
    "  {name:<24} calls {calls:<5} in {tok_in:<6} out {tok_out:<6}"
    " cacheR {tok_r:<7} cacheW {tok_w:<6} wall p50 {p50:<6} p90 {p90:<6} n {n}"
)

#: Run-detail row: same compact style as ``_ROW_TEMPLATE`` (no new dependency).
_DETAIL_TEMPLATE = (
    "  {started:<16}  {project:<16}  {key:<24}  {task:<28}  {type:<9}  {model:<26}"
    "  calls {calls:<5}  in {tok_in:<6}  out {tok_out:<6}"
    "  cacheR {tok_r:<7}  cacheW {tok_w:<6}  wall {wall:<6}  {status}"
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


def _format_local_stamp(value: Any) -> str:
    """ISO-Z -> local ``YYYY-MM-DDTHH:MM`` (JSON keeps UTC, text reads local)."""
    moment = _parse_iso(value)
    if moment is None:
        return "-"
    return moment.astimezone(_local_tz()).strftime("%Y-%m-%dT%H:%M")


def _project_tail(value: Any) -> str:
    """Path tail of a run's project (``None`` renders ``-``, R19/AC-026)."""
    path = _norm(value)
    return _basename(path) if path else "-"


def _format_detail_row(row: Mapping[str, Any]) -> str:
    tokens = row.get("tokens") or {}
    wall = _format_wall(row.get("wall_s"))
    if row.get("wall_kind") == "session":
        wall += SESSION_WALL_MARK
    calls = row.get("calls")
    return _DETAIL_TEMPLATE.format(
        started=_format_local_stamp(row.get("started_at")),
        project=_project_tail(row.get("project")),
        key=_norm(row.get("key")) or UNKNOWN_LABEL,
        task=_norm(row.get("task_key")) or "-",
        type=_norm(row.get("type")) or UNKNOWN_LABEL,
        model=_norm(row.get("model")) or "-",
        calls="-" if calls is None else calls,
        tok_in=_format_tokens(tokens.get("input")),
        tok_out=_format_tokens(tokens.get("output")),
        tok_r=_format_tokens(tokens.get("cache_read")),
        tok_w=_format_tokens(tokens.get("cache_write")),
        wall=wall,
        status=_norm(row.get("status")) or "-",
    )


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


def format_report_text(report: Mapping[str, Any], detail: bool = False) -> str:
    """Human-readable report (design §6); ``None`` renders ``-``, never ``0``.

    ``detail=True`` appends the per-run table before ``coverage`` (R8: the JSON
    always carries ``runs[]``; this flag only decides whether the text renders
    it). A ``limit`` cut is stated in the table head, and a ``session`` wall
    cell carries the same ``*`` marker / footnote as the group rows.
    """
    ledger = report.get("ledger") or {}
    totals = report.get("totals") or {}
    sources = report.get("sources") or {}
    groups = report.get("groups") or {}
    since = _norm(report.get("since"))
    until = _norm(report.get("until"))
    since_date = since[:10] if len(since) >= 10 else since
    window = _norm(report.get("window")) or "-"
    head_tail = (
        f" · ledger {ledger.get('events', 0)} events · "
        f"runs {totals.get('runs', 0)} "
        f"(worker {sources.get('worker', 0)} / pm {sources.get('pm', 0)})"
    )
    if until:
        # Half-open window: show both bounds (R7).
        first = f"usage {_format_local_stamp(since)} → {_format_local_stamp(until)} ({window})"
    else:
        # Backward compatible wording for a report built without ``until``.
        first = f"usage since {since_date} ({window})"
    lines = [first + head_tail]
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

    detail_marked = False
    if detail:
        rows = list(report.get("runs") or [])
        total = report.get("runs_total")
        lines.append("")
        lines.append("runs (newest first)")
        if isinstance(total, int) and total > len(rows):
            # Never let a cut table pass for the whole window (R10).
            lines.append(f"showing {len(rows)} of {total} runs (--limit 0 for all)")
        for row in rows:
            if row.get("wall_kind") == "session":
                detail_marked = True
            lines.append(_format_detail_row(row))

    if marked or detail_marked:
        lines.append("")
        lines.append(SESSION_WALL_FOOTNOTE)
    lines.append("")
    lines.append(_format_coverage(report.get("coverage") or []))
    return "\n".join(lines)


# ── HTML rendering (spec §12 R11-R14) ───────────────────────────────────────

#: Inline stylesheet: single file, no external font / CDN / @import.
_HTML_STYLE = """
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 24px 16px 48px;
  background: #fafafa;
  color: #1b1b1f;
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
main { max-width: 1400px; margin: 0 auto; }
h1 { margin: 0 0 12px; font-size: 20px; }
h2 { margin: 28px 0 8px; font-size: 16px; }
h3 { margin: 0 0 6px; font-size: 13px; color: #5b5b66; font-weight: 600; }
.meta {
  margin: 0 0 8px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #e2e2e8;
  border-radius: 6px;
}
.meta dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 3px 16px;
  margin: 0;
}
.meta dt { color: #5b5b66; }
.meta dd { margin: 0; }
.path { word-break: break-all; font-family: ui-monospace, Consolas, monospace; }
.coverage { margin: 10px 0 0; color: #3a3a44; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0 0; padding: 0; list-style: none; }
.card {
  flex: 1 1 150px;
  padding: 12px 14px;
  background: #fff;
  border: 1px solid #e2e2e8;
  border-radius: 6px;
}
.card .label { color: #5b5b66; font-size: 12px; }
.card .value { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
.card .sub { color: #5b5b66; font-size: 12px; font-variant-numeric: tabular-nums; }
table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border: 1px solid #e2e2e8;
}
th, td { padding: 6px 10px; border-bottom: 1px solid #ececf1; text-align: left; vertical-align: top; }
thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f2f2f6;
  font-weight: 600;
  white-space: nowrap;
}
tbody tr:nth-child(even) { background: #fbfbfd; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
td.mono { font-family: ui-monospace, Consolas, monospace; }
td.empty { padding: 16px; text-align: center; color: #5b5b66; }
.note, .footnote, .no-group { color: #5b5b66; font-size: 12px; }
.note { margin: 8px 0 0; }
.footnote { margin: 10px 0 0; }
.no-group { margin: 12px 0 0; }
"""

_HTML_GROUP_HEADERS = (
    ("name", ""),
    ("calls", "num"),
    ("in", "num"),
    ("out", "num"),
    ("cacheR", "num"),
    ("cacheW", "num"),
    ("runs", "num"),
    ("wall p50", "num"),
    ("wall p90", "num"),
    ("n", "num"),
    ("wall_kind", ""),
)

#: Row count above which the HTML runs table adds a browser ``Ctrl+F`` hint
#: (R15: still renders every row, the hint only points at in-page search).
HTML_SEARCH_HINT_ROWS = 2000

_HTML_RUN_HEADERS = (
    ("started_at", ""),
    ("project", ""),
    ("wall", "num"),
    ("status", ""),
    ("key", ""),
    ("task_key", ""),
    ("type", ""),
    ("model", ""),
    ("calls", "num"),
    ("in", "num"),
    ("out", "num"),
    ("cacheR", "num"),
    ("cacheW", "num"),
    ("session_id", ""),
)

#: Filters shown in the header block, in CLI order (``window`` is in the head).
_HTML_FILTER_ORDER = ("key", "type", "model", "project", "source")


def _html_escape(value: Any) -> str:
    """Escape one interpolated value (ledger/session text is untrusted, R14)."""
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _html_int(value: Any) -> str:
    """A count cell; unknown stays ``-`` (never a fabricated ``0``)."""
    if value is None:
        return "-"
    return _html_escape(value)


def _html_local_datetime(value: Any) -> str:
    """ISO-Z -> local ``YYYY-MM-DD HH:MM:SS`` (header: generated time)."""
    moment = _parse_iso(value)
    if moment is None:
        return "-"
    return moment.astimezone(_local_tz()).strftime("%Y-%m-%d %H:%M:%S")


class _HtmlCell:
    """A table cell that renders its own ``<td>`` (needs a per-cell attribute).

    ``_html_table`` wraps plain strings in ``<td>``; a cell carrying e.g.
    ``title`` supplies the finished tag instead. Its HTML is already escaped
    by the caller (`_html_project_cell`), same contract as a string cell.
    """

    __slots__ = ("html",)

    def __init__(self, html: str) -> None:
        self.html = html


def _html_table(
    headers: tuple[tuple[str, str], ...],
    rows: Iterable[Iterable[str | _HtmlCell]],
    empty_message: str | None = None,
) -> str:
    """One table; every cell value is already escaped by the caller."""
    head = "".join(
        f'<th class="{css}">{_html_escape(label)}</th>' if css else f"<th>{_html_escape(label)}</th>"
        for label, css in headers
    )
    body: list[str] = []
    for row in rows:
        cells: list[str] = []
        for (_label, css), value in zip(headers, row):
            if isinstance(value, _HtmlCell):
                cells.append(value.html)
            elif css:
                cells.append(f'<td class="{css}">{value}</td>')
            else:
                cells.append(f"<td>{value}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    if not body and empty_message is not None:
        body.append(
            f'<tr><td class="empty" colspan="{len(headers)}">'
            f"{_html_escape(empty_message)}</td></tr>"
        )
    return (
        "<table>\n<thead><tr>"
        + head
        + "</tr></thead>\n<tbody>\n"
        + "\n".join(body)
        + "\n</tbody>\n</table>"
    )


def _html_filter_text(report: Mapping[str, Any]) -> str:
    """Effective filters from ``report["filters"]``; empty when absent.

    ``build_report`` does not echo its filters, so the HTML header only shows
    this line when the report actually carries them (no guessing, no second
    data read).
    """
    filters = report.get("filters")
    if not isinstance(filters, Mapping):
        return ""
    keys = [name for name in _HTML_FILTER_ORDER if name in filters]
    keys.extend(str(name) for name in filters if name not in _HTML_FILTER_ORDER)
    parts: list[str] = []
    for name in keys:
        if name == "window":
            continue  # already rendered as part of the window line
        value = _norm(filters.get(name))
        if value:
            parts.append(f"{name}={value}")
    return " · ".join(parts)


def _html_group_row(row: Mapping[str, Any]) -> list[str]:
    tokens = row.get("tokens") or {}
    p90 = _format_wall(row.get("wall_p90"))
    if row.get("wall_kind") == "session":
        # Same marker as the text renderer (see SESSION_WALL_FOOTNOTE).
        p90 += SESSION_WALL_MARK
    return [
        _html_escape(str(row.get("name") or UNKNOWN_LABEL)),
        _html_int(row.get("calls")),
        _html_escape(_format_tokens(tokens.get("input"))),
        _html_escape(_format_tokens(tokens.get("output"))),
        _html_escape(_format_tokens(tokens.get("cache_read"))),
        _html_escape(_format_tokens(tokens.get("cache_write"))),
        _html_int(row.get("runs")),
        _html_escape(_format_wall(row.get("wall_p50"))),
        _html_escape(p90),
        _html_int(row.get("n")),
        _html_escape(_norm(row.get("wall_kind")) or "-"),
    ]


def _html_project_cell(value: Any) -> str | _HtmlCell:
    """basename text plus ``title="<full path>"`` (R19); ``None`` is plain ``-``."""
    path = _norm(value)
    if not path:
        return "-"
    return _HtmlCell(
        f'<td title="{_html_escape(path)}">{_html_escape(_basename(path))}</td>'
    )


def _html_run_row(row: Mapping[str, Any]) -> list[str | _HtmlCell]:
    tokens = row.get("tokens") or {}
    wall = _format_wall(row.get("wall_s"))
    if row.get("wall_kind") == "session":
        wall += SESSION_WALL_MARK
    if row.get("open_run"):
        status = "running"  # never render the raw None of an open run
    else:
        status = _norm(row.get("status")) or "-"
    return [
        _html_escape(_format_local_stamp(row.get("started_at"))),
        _html_project_cell(row.get("project")),
        _html_escape(wall),
        _html_escape(status),
        _html_escape(_norm(row.get("key")) or UNKNOWN_LABEL),
        _html_escape(_norm(row.get("task_key")) or "-"),
        _html_escape(_norm(row.get("type")) or UNKNOWN_LABEL),
        _html_escape(_norm(row.get("model")) or "-"),
        _html_int(row.get("calls")),
        _html_escape(_format_tokens(tokens.get("input"))),
        _html_escape(_format_tokens(tokens.get("output"))),
        _html_escape(_format_tokens(tokens.get("cache_read"))),
        _html_escape(_format_tokens(tokens.get("cache_write"))),
        _html_escape(_norm(row.get("session_id")) or "-"),
    ]


def render_html(report: Mapping[str, Any], *, title: str | None = None) -> str:
    """Render the report as one self-contained HTML document (R11-R14).

    Pure string rendering of an existing report dict: no I/O and no second
    data read (AC-020). Semantics mirror :func:`format_report_text` — the same
    ``_format_tokens`` / ``_format_wall`` helpers, ``None`` renders ``-``
    (never ``0``), a ``session`` wall carries ``*`` plus
    ``SESSION_WALL_FOOTNOTE``, an open run reads ``running``. Every
    interpolated ledger/session string goes through :func:`_html_escape`
    (R14/AC-021).

    The run table reads ``report["runs_all"]`` first (the uncut list of R15,
    so the row count is ``runs_total`` and the heading carries that total); a
    report without it falls back to ``report["runs"]``, which is what every
    caller built before v0.5. Above :data:`HTML_SEARCH_HINT_ROWS` rows the
    table still renders in full and only gains a ``Ctrl+F`` line.
    """
    ledger = report.get("ledger") or {}
    totals = report.get("totals") or {}
    sources = report.get("sources") or {}
    groups = report.get("groups") or {}
    total_tokens = totals.get("tokens") or {}
    since = _format_local_stamp(report.get("since"))
    until = _format_local_stamp(report.get("until"))
    window = _norm(report.get("window")) or "-"
    doc_title = title if title is not None else f"mw usage — {since} → {until}"

    meta_cells = [
        ("生成时间", _html_escape(_html_local_datetime(report.get("generated_at")))),
        ("窗口", _html_escape(f"{since} → {until} ({window})")),
        (
            "ledger",
            f'<span class="path">{_html_escape(_norm(ledger.get("path")) or "-")}</span>'
            f" · events {_html_int(ledger.get('events'))}"
            f" · bad_lines {_html_int(ledger.get('bad_lines'))}"
            f" · open_runs {_html_int(ledger.get('open_runs'))}",
        ),
    ]
    filter_text = _html_filter_text(report)
    if filter_text:
        meta_cells.append(("过滤", _html_escape(filter_text)))

    cards = (
        (
            "runs",
            _html_int(totals.get("runs")),
            f"worker {_html_int(sources.get('worker'))} / pm {_html_int(sources.get('pm'))}",
        ),
        ("calls", _html_int(totals.get("calls")), ""),
        ("input", _html_escape(_format_tokens(total_tokens.get("input"))), ""),
        ("output", _html_escape(_format_tokens(total_tokens.get("output"))), ""),
        ("cacheR", _html_escape(_format_tokens(total_tokens.get("cache_read"))), ""),
        ("cacheW", _html_escape(_format_tokens(total_tokens.get("cache_write"))), ""),
    )

    group_sections: list[str] = []
    for dim, label in _GROUP_TITLES:
        rows = groups.get(dim) or []
        if not rows:
            continue  # empty groups are not rendered at all
        group_sections.append(
            f"<section>\n<h2>{_html_escape(label)}</h2>\n"
            f"{_html_table(_HTML_GROUP_HEADERS, (_html_group_row(row) for row in rows))}\n"
            "</section>"
        )

    # R15/R17: the detail table is the whole window, never the `--limit` slice.
    # ``runs_all`` is the uncut list ``build_report(include_all_runs=True)``
    # hands over; a report built without it (older call path) still renders its
    # ``runs`` slice instead of exploding. No re-sort, no second token pass:
    # rows are already newest first and pre-computed.
    runs_all = report.get("runs_all")
    has_all_runs = isinstance(runs_all, list)
    run_rows = list(runs_all if has_all_runs else (report.get("runs") or []))
    runs_table = _html_table(
        _HTML_RUN_HEADERS,
        (_html_run_row(row) for row in run_rows),
        empty_message="窗口内没有运行",
    )

    lines = [
        "<!doctype html>",
        '<html lang="zh">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_html_escape(doc_title)}</title>",
        f"<style>{_HTML_STYLE}</style>",
        "</head>",
        "<body>",
        "<main>",
        "<h1>mw usage</h1>",
        '<div class="meta">',
        "<dl>",
    ]
    for name, value in meta_cells:
        lines.append(f"<dt>{_html_escape(name)}</dt><dd>{value}</dd>")
    lines.extend(
        [
            "</dl>",
            f'<p class="coverage">{_html_escape(_format_coverage(report.get("coverage") or []))}</p>',
            "</div>",
            "<h2>summary</h2>",
            '<ul class="cards">',
        ]
    )
    for label, value, sub in cards:
        sub_html = f'<div class="sub">{sub}</div>' if sub else ""
        lines.append(
            f'<li class="card"><div class="label">{_html_escape(label)}</div>'
            f'<div class="value">{value}</div>{sub_html}</li>'
        )
    lines.append("</ul>")
    if group_sections:
        lines.extend(group_sections)
    else:
        lines.append('<p class="no-group">no usage in window</p>')
    total_runs = report.get("runs_total")
    # A full-run table states its own size (R15). The fallback path keeps the
    # legacy heading because its `runs` list may still be cut.
    heading = "runs (newest first)"
    if has_all_runs:
        heading = f"runs (newest first) · {len(run_rows)}"
    lines.extend(
        [
            "<section>",
            f"<h2>{_html_escape(heading)}</h2>",
        ]
    )
    if len(run_rows) > HTML_SEARCH_HINT_ROWS:
        # No second cut: the page is long, the browser is the pager (R15).
        lines.append(
            f'<p class="note">共 {len(run_rows)} 行，可用浏览器 Ctrl+F'
            " 搜索 key / task_key</p>"
        )
    if not has_all_runs and isinstance(total_runs, int) and total_runs > len(run_rows):
        # Legacy slice only: kept for a report that never asked for `runs_all`,
        # so an old caller is still told its table is not the whole window.
        lines.append(
            f'<p class="note">showing {len(run_rows)} of {total_runs} runs'
            " (--limit 0 for all)</p>"
        )
    lines.extend(
        [
            runs_table,
            '<p class="footnote">`-` = 无数据/不适用</p>',
            f'<p class="footnote">{_html_escape(SESSION_WALL_FOOTNOTE)}</p>',
            "</section>",
            "</main>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(lines)

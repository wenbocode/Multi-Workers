"""autopilot/timeline.py — event timeline append/query/rotate (D-109, T-04).

The timeline is one JSONL file — ``.agenticdoc/_autopilot/timeline.jsonl`` —
holding one line per conductor state transition plus one ``beat`` line per
tick (AC-017/AC-019). Line schema (field set; the writer emits this order):

    {"ts": "<iso8601>", "seq": <int>, "ev": "<type>", "key": "<str>",
     "stage": <int|null>, "detail": "<str>"}

Protocol (D-109 seq/watermark/rotation):

- **seq** — monotonically increasing, assigned by the conductor (the sole
  writer). A :class:`Timeline` recovers its counter at construction from the
  tail line of the current file (rotated generations as fallback), so a
  restart continues the sequence — never regressing, never duplicating. A
  failed append consumes no seq, keeping the sequence dense; the pruned count
  in :func:`query_events` relies on that density.
- **key sentinel** — key-level events carry the key; stage-level/global
  events carry the stage number or ``-``; never ``null`` (AC-017 erratum).
  :meth:`Timeline.append` derives it: an explicit non-empty key wins, else
  ``str(stage)`` when a stage is given, else ``-``.
- **rotation** — when the current file reaches ``ROTATE_THRESHOLD_BYTES``
  (10MB) it is atomically renamed into the generation chain
  (``timeline.jsonl.1`` = newest rotation … ``timeline.jsonl.N`` = oldest),
  keeping ``ROTATE_GENERATIONS`` (2) generations; older ones are dropped.
  Rotated files are never rewritten (rename/unlink only); the current file is
  append-only.
- **query/replay** — rotated files oldest→newest, then the current file;
  filter ``seq > watermark``; sort by seq ascending. A watermark predating
  the oldest retained line yields a non-zero ``pruned`` count — never a
  silent gap (超 2 代轮转).
- **fault tolerance (§9)** — append/rotate failures (disk full, unwritable
  path, …) are logged to stderr and reported as ``None``/``False``; they
  never propagate to the caller, so a conductor tick always survives them.

UTF-8 + newline symmetry: every write uses append mode with explicit
``encoding="utf-8", newline="\\n"`` — no ``\\r\\n`` doubling on Windows
(spec §5 坑点).

All paths are explicit parameters; this module never derives a project root
on its own and never imports autopilot.config (T-02 lands in parallel).

Public surface (T-06 dispatch reuses ``append``):

    timeline_path(project_root) -> pathlib.Path
    Timeline(path, *, rotate_threshold_bytes=ROTATE_THRESHOLD_BYTES,
             generations=ROTATE_GENERATIONS)
        .append(ev, key=None, stage=None, detail="") -> int | None
        .rotate() -> bool
        .next_seq -> int
    query_events(path, watermark=0, *, ev_filter=None) -> TimelineQuery
    recover_seq(path) -> int
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os
import pathlib
import sys
from collections.abc import Iterable

# Event type vocabulary (D-109). Used for filtering — the console's default
# view hides `beat` — NOT for rejection: unknown ev values append fine.
EVENT_TYPES: frozenset[str] = frozenset({
    "beat",
    "dispatch",
    "worker-terminal",
    "advance",
    "gate-created",
    "gate-answered",
    "stalled",
    "skip",
    "stage-close",
    "config",
    "goal-halt",
    "goal-snapshot",
    "type-rejected",
    "target-config-rejected",
    "reconcile",
    "resume",
    "l3-no-verdict",
})

# `key` value for stage-level/global events (AC-017 erratum: the key field
# is never null — every line must stay attributable).
KEY_SENTINEL = "-"

# Rotation policy: the current file rotates once it reaches this size, and
# that many rotated generations are retained (older ones are dropped).
ROTATE_THRESHOLD_BYTES = 10 * 1024 * 1024
ROTATE_GENERATIONS = 2


def timeline_path(project_root: pathlib.Path) -> pathlib.Path:
    """Default timeline location: `.agenticdoc/_autopilot/timeline.jsonl`.

    Pure path computation (no IO, nothing created) — kept beside the IO
    functions so the conductor (T-06) and tests share one path contract.
    """
    return pathlib.Path(project_root) / ".agenticdoc" / "_autopilot" / "timeline.jsonl"


def _iso_now() -> str:
    # Same shape as mw_common.iso_now (UTC, second precision): the TS console
    # parses it with Date(), and mw_common helpers can parse it back.
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _log_stderr(message: str) -> None:
    print(f"[timeline] {message}", file=sys.stderr)


def _rotated_path(path: pathlib.Path, generation: int) -> pathlib.Path:
    return path.with_name(f"{path.name}.{generation}")


def _rotation_chain(path: pathlib.Path) -> list[pathlib.Path]:
    """Existing rotated generations, oldest → newest (`.N` → `.1`).

    Discovered by directory scan rather than a fixed generation count, so
    queries keep working if the configured retention ever changes.
    """
    prefix = path.name + "."
    found: list[tuple[int, pathlib.Path]] = []
    try:
        entries = list(path.parent.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.name.startswith(prefix):
            continue
        suffix = entry.name[len(prefix):]
        if suffix.isdigit() and entry.is_file():
            found.append((int(suffix), entry))
    found.sort(key=lambda item: item[0], reverse=True)  # higher gen = older
    return [entry for _, entry in found]


def _is_seq(value: object) -> bool:
    """True for a usable seq value (int, not bool)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _tail_seq(path: pathlib.Path) -> int | None:
    """Last parseable seq in a JSONL file, or None.

    Reads a growing tail window — a 10MB current file costs one small read —
    and walks backwards past torn trailing lines left by a mid-write crash.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return None
    window = 4096
    while True:
        offset = max(0, size - window)
        try:
            with open(path, "rb") as fh:
                fh.seek(offset)
                chunk = fh.read()
        except OSError:
            return None
        for raw in reversed(chunk.split(b"\n")):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(obj, dict) and _is_seq(obj.get("seq")):
                return obj["seq"]
        if offset == 0:
            return None  # whole file scanned, nothing parseable
        window *= 8


def _read_events(path: pathlib.Path) -> tuple[list[dict], int]:
    """Parse one JSONL file → (events, unparseable-line count).

    Torn lines (mid-write crash, concurrent append) are counted, never
    silently dropped (F12: 半写行校验失败 → 计数暴露). Lines are decoded
    individually so one torn multibyte character cannot take the whole file
    down with it. An unreadable file contributes nothing; the pruned count
    in query_events surfaces the retention gap instead of hiding it.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return [], 0
    events: list[dict] = []
    skipped = 0
    for raw in data.split(b"\n"):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            skipped += 1
            continue
        if not isinstance(obj, dict) or not _is_seq(obj.get("seq")):
            skipped += 1
            continue
        events.append(obj)
    return events, skipped


def recover_seq(path: pathlib.Path) -> int:
    """Highest seq retained anywhere in the chain (0 when nothing retained).

    The current file's tail usually wins; rotated generations are consulted
    as well so a restart landing right after a rotation (current file gone)
    still continues the sequence instead of restarting at 1.
    """
    best = 0
    for candidate in [pathlib.Path(path), *_rotation_chain(pathlib.Path(path))]:
        seq = _tail_seq(candidate)
        if seq is not None and seq > best:
            best = seq
    return best


@dataclasses.dataclass(frozen=True)
class TimelineQuery:
    """Result of :func:`query_events`.

    - ``events``: parsed lines with ``seq > watermark``, sorted ascending.
    - ``pruned``: events with ``seq > watermark`` that are no longer
      retained — non-zero exactly when the watermark predates the oldest
      retained line (超 2 代轮转). Lower bound when the whole chain is empty
      but the watermark is non-zero.
    - ``skipped``: unparseable (torn) lines encountered — counted, not
      silently dropped.
    """

    events: list[dict]
    pruned: int
    skipped: int


def _write_line(path: pathlib.Path, line: str) -> None:
    """One append-mode write. Separate function so tests can inject failures.

    ``newline="\\n"`` keeps LF on Windows — no ``\\r\\n`` doubling.
    """
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)


class Timeline:
    """Append-only timeline writer with seq recovery and size rotation.

    The conductor is the sole writer (D-109); one instance per process owns
    the seq counter. Construction recovers it from the file chain, so a
    restart continues the sequence — no regress, no duplicate seq.
    """

    def __init__(
        self,
        path: pathlib.Path | str,
        *,
        rotate_threshold_bytes: int = ROTATE_THRESHOLD_BYTES,
        generations: int = ROTATE_GENERATIONS,
    ) -> None:
        self.path = pathlib.Path(path)
        self.rotate_threshold_bytes = max(1, int(rotate_threshold_bytes))
        self.generations = max(1, int(generations))
        self._next_seq = recover_seq(self.path) + 1
        self._tail_terminated = False  # unknown until the first append checks

    @property
    def next_seq(self) -> int:
        """Seq the next successful append will get."""
        return self._next_seq

    def append(
        self,
        ev: str,
        key: str | None = None,
        stage: int | None = None,
        detail: str = "",
    ) -> int | None:
        """Append one event line; returns its seq, or None on failure.

        Never raises (§9 tick fault tolerance): failures — disk full,
        unwritable path, … — are logged to stderr so the caller's tick keeps
        running. A failed append consumes no seq, keeping the sequence dense
        (query_events' pruned count relies on that).

        Key sentinel derivation (AC-017 erratum — the stored key is never
        null): an explicit non-empty ``key`` wins (key-level event); else
        ``str(stage)`` when a stage is given (stage-level event); else ``-``
        (global event).
        """
        try:
            stage_value = None if stage is None else int(stage)
            if isinstance(key, str) and key:
                key_value = key
            else:
                key_value = str(stage_value) if stage_value is not None else KEY_SENTINEL
            self._maybe_rotate()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_tail_terminated()
            seq = self._next_seq
            line = json.dumps(
                {
                    "ts": _iso_now(),
                    "seq": seq,
                    "ev": str(ev),
                    "key": key_value,
                    "stage": stage_value,
                    "detail": "" if detail is None else str(detail),
                },
                ensure_ascii=False,
            ) + "\n"
            _write_line(self.path, line)
            self._next_seq = seq + 1
            return seq
        except Exception as exc:  # noqa: BLE001 — must never break a tick (§9)
            self._tail_terminated = False
            _log_stderr(f"append failed: {exc!r}")
            return None

    def rotate(self) -> bool:
        """Rotate the current file into the generation chain.

        Shifts ``.{g-1}`` → ``.{g}`` from the oldest generation down —
        dropping whatever falls past ``generations`` — then atomically renames
        the current file to ``.1``. No content is ever rewritten: rotated
        files stay byte-identical, the current file stays append-only.
        Returns True when a rotation happened; False when there is no current
        file or the rotation failed (logged to stderr — §9).
        """
        try:
            if not self.path.exists():
                return False
            for generation in range(self.generations, 0, -1):
                src = self.path if generation == 1 else _rotated_path(self.path, generation - 1)
                dst = _rotated_path(self.path, generation)
                if dst.exists():
                    dst.unlink()  # the generation falling off the chain
                if src.exists():
                    os.replace(str(src), str(dst))
            self._tail_terminated = False
            return True
        except OSError as exc:
            _log_stderr(f"rotate failed: {exc!r}")
            return False

    def _maybe_rotate(self) -> None:
        """Auto-rotate when the current file has reached the threshold."""
        try:
            if self.path.stat().st_size >= self.rotate_threshold_bytes:
                self.rotate()
        except OSError:
            pass  # no current file yet — nothing to rotate

    def _ensure_tail_terminated(self) -> None:
        """Guarantee the current file ends with a newline before appending.

        A previous process may have died mid-write leaving a torn line
        without its newline; appending directly would glue the new line onto
        it. Append a bare newline so the torn line stays its own (skipped)
        line — still append-only. Runs once per instance (and after each
        rotation); our own writes always terminate with a newline.
        """
        if self._tail_terminated:
            return
        try:
            size = self.path.stat().st_size
            if size:
                with open(self.path, "rb") as fh:
                    fh.seek(size - 1)
                    terminated = fh.read(1) == b"\n"
                if not terminated:
                    _write_line(self.path, "\n")
            self._tail_terminated = True
        except OSError:
            pass  # absent/unreadable: the append itself will surface failures


def query_events(
    path: pathlib.Path,
    watermark: int = 0,
    *,
    ev_filter: Iterable[str] | None = None,
) -> TimelineQuery:
    """Replay timeline events with ``seq > watermark`` (D-109 回放协议).

    Reads rotated generations oldest → newest, then the current file; returns
    the union filtered by seq, sorted ascending. ``ev_filter`` is an
    include-set of event types (pass ``EVENT_TYPES - {"beat"}`` for the
    console's default beat-free view); None keeps every type.

    A watermark predating the oldest retained line yields a non-zero
    ``pruned`` count — the replay explicitly reports what was lost to
    rotation instead of silently starting mid-history.
    """
    path = pathlib.Path(path)
    try:
        mark = max(0, int(watermark))
    except (TypeError, ValueError):
        mark = 0
    wanted = frozenset(ev_filter) if ev_filter is not None else None

    all_events: list[dict] = []
    skipped = 0
    for source in [*_rotation_chain(path), path]:
        events, bad = _read_events(source)
        all_events.extend(events)
        skipped += bad
    all_events.sort(key=lambda event: event["seq"])

    if all_events:
        pruned = max(0, all_events[0]["seq"] - mark - 1)
    elif mark > 0:
        # Empty chain but a non-zero watermark: every event the console ever
        # saw is gone. The exact total is unknowable — report at least the
        # watermark's worth (lower bound), never silence.
        pruned = mark
    else:
        pruned = 0

    events = [
        event
        for event in all_events
        if event["seq"] > mark and (wanted is None or event.get("ev") in wanted)
    ]
    return TimelineQuery(events=events, pruned=pruned, skipped=skipped)


def tail_events(
    path: pathlib.Path,
    *,
    max_bytes: int = 512 * 1024,
    limit: int = 400,
) -> list[dict]:
    """Newest parsed events from the *current* file, via a bounded tail read.

    Rotated generations are deliberately not consulted: callers (the advance
    stall guard, the monitor panel) ask "what just happened", and reading a
    window at the end of one file keeps that question O(window) instead of
    O(history) — the live 10MB/21k-line case costs one bounded read.

    Torn/partial lines are skipped; when the window does not start at offset
    0 its first line is dropped (it is cut mid-record). Returns at most
    ``limit`` events, oldest → newest. Never raises: an absent or unreadable
    file yields an empty list.
    """
    path = pathlib.Path(path)
    window = max(4096, int(max_bytes))
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size <= 0:
        return []
    offset = max(0, size - window)
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
    except OSError:
        return []
    lines = chunk.split(b"\n")
    if offset > 0:
        lines = lines[1:]
    events: list[dict] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(obj, dict) and _is_seq(obj.get("seq")):
            events.append(obj)
    if limit > 0 and len(events) > limit:
        events = events[-limit:]
    return events

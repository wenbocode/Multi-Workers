"""autopilot/state.py — zero-private-state derivation (D-102/D-103/D-111/D-115).

The conductor keeps no state file of its own: every fact it needs is derived
from the shared files on each tick. This module is that derivation layer:

  - key phase/status/claim  <- ``.agenticdoc/_index.parallel`` (7-column
    markdown table, legacy 5-column rows migrated gracefully — parser mirrors
    the framework's update_index._parse_row)
  - claim liveness          <- claimId ``host:pid`` semantics
  - loop round budgets      <- ``{key}/workers/*/task.md`` frontmatter
    ``loop:``/``attempt:`` labels (D-102: dispatch history persists in the
    task files; a round = one distinct attempt per loop)
  - worker process identity <- ``trace.log`` ``[START] pid=<pid>`` lines
    (D-115: process-uniqueness is line count + pid liveness, never a
    line-count proxy alone)
  - orphan reconciliation   <- ap- queue rows vs conductor-origin task.md
    (D-102: an orphan is a task.md with ``origin: conductor`` and no queue
    row — the row can only vanish via stale-archive, which requires the
    task.md to be gone, so no row means it was never spawned)
  - artifact mtimes         <- spec/design/plan/tasks snapshot for the
    AC-014/AC-022 "unchanged" assertions

Claim semantics note (deliberate asymmetry): the TS claimState
(ui-bridge.ts) treats a foreign-host claim as held-live because a human may
be there and takeover needs --force. The conductor side (this module, per
T-07/D-103) treats a foreign-host claim as *dead*: the conductor runs on
this machine against this checkout and cannot verify a foreign pid, and a
conservative skip would let a crashed foreign window block a key forever.
Live means: parseable ``host:pid`` AND host == this host AND pid alive.
Unparseable (legacy) claim ids read back as stale (F9).
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re
import socket
import sys
from collections.abc import Sequence

# Script-mode bootstrap: `python autopilot/conductor.py` puts autopilot/ on
# sys.path, not its parent — mw_common lives in the parent.
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)


# ── Key phase/claim derivation (_index.parallel) ─────────────────────────────

_INDEX_HEADER_RE = re.compile(r"^\|[\s:\-|]+\|?\s*$")
_CLAIM_RE = re.compile(r"^([^:]+):(\d+)$")

# claim verdicts
CLAIM_FREE = "free"        # no claim / placeholder / self
CLAIM_LIVE = "live"        # this host, pid alive — blocks the conductor
CLAIM_DEAD = "dead"        # parseable but host mismatch or pid gone
CLAIM_STALE = "stale"      # unparseable (legacy) — F9: treat as not-live


@dataclasses.dataclass(frozen=True)
class KeyState:
    """One row of _index.parallel plus its derived claim verdict."""

    key: str
    status: str
    phase: str
    claim_id: str
    claim: str


def _parse_index_row(line: str) -> dict | None:
    """Mirror of update_index._parse_row: 7-col schema, legacy 5-col graceful."""
    if not line.startswith("|"):
        return None
    if _INDEX_HEADER_RE.match(line):
        return None
    cols = [c.strip() for c in line.strip("|").split("|")]
    if len(cols) < 5 or cols[0] in ("Key", ""):
        return None
    if len(cols) >= 7:
        return {
            "key": cols[0], "status": cols[1], "phase": cols[2],
            "claim_id": cols[3], "deps": cols[4], "desc": cols[5],
            "updated": cols[6],
        }
    return {
        "key": cols[0], "status": cols[1], "phase": "—",
        "claim_id": cols[2], "deps": "—", "desc": cols[3],
        "updated": cols[4],
    }


def read_index(project_root: pathlib.Path) -> list[dict]:
    """All rows of _index.parallel ([] when absent). Trailing-space and blank
    lines are filtered; parse tolerance matches the framework parser."""
    path = pathlib.Path(project_root) / ".agenticdoc" / "_index.parallel"
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        row = _parse_index_row(line)
        if row:
            rows.append(row)
    return rows


def claim_state(claim_id: str, self_id: str = "") -> str:
    """Conductor-side liveness verdict for one claim id.

    free  — empty/placeholder/dash, or equal to self_id (own claim)
    live  — parseable host:pid, host == this host, pid alive
    dead  — parseable but foreign host or dead pid
    stale — unparseable (legacy claim ids; F9)
    """
    trimmed = (claim_id or "").strip()
    if not trimmed or trimmed in ("—", "-") or (self_id and trimmed == self_id):
        return CLAIM_FREE
    m = _CLAIM_RE.match(trimmed)
    if not m:
        return CLAIM_STALE
    pid_text = m.group(2)
    if not pid_text.isdigit() or int(pid_text) <= 0:
        return CLAIM_STALE
    if m.group(1) != socket.gethostname():
        return CLAIM_DEAD  # conductor-side rule: foreign host is not live
    return CLAIM_LIVE if mw_common._is_alive(int(pid_text)) else CLAIM_DEAD


def read_key_states(project_root: pathlib.Path, self_id: str = "") -> dict[str, KeyState]:
    """key -> KeyState from _index.parallel, with derived claim verdicts."""
    states: dict[str, KeyState] = {}
    for row in read_index(project_root):
        claim_id = row.get("claim_id", "")
        states[row["key"]] = KeyState(
            key=row["key"],
            status=row.get("status", ""),
            phase=row.get("phase", "—"),
            claim_id=claim_id,
            claim=claim_state(claim_id, self_id=self_id),
        )
    return states


# ── Worker task frontmatter (loop/attempt/origin labels) ─────────────────────

_FM_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*?)[ \t]*$")


def parse_task_labels(task_md: pathlib.Path) -> dict[str, str]:
    """Frontmatter scalar labels of one task.md (loop/attempt/origin/type...).

    Lenient by design: worker-authored content must never crash state
    derivation — a missing frontmatter or malformed line simply yields no
    label. Nested blocks (read_scope lists) are skipped, not parsed.
    """
    try:
        text = pathlib.Path(task_md).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    labels: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = _FM_LINE_RE.match(line)
        if m is None:
            continue  # list item / nested block / prose — skip
        labels[m.group(1)] = m.group(2)
    return labels


@dataclasses.dataclass(frozen=True)
class WorkerTaskInfo:
    """One worker task dir under .agenticdoc (conductor- or manually owned)."""

    task_dir: pathlib.Path
    owner: str            # owning key ("_scratch" for keyless dispatches)
    task_key: str         # task dir name (stem identity)
    loop: str | None
    attempt: int | None
    origin: str | None
    task_type: str | None


def _task_info(task_md: pathlib.Path, owner: str) -> WorkerTaskInfo:
    labels = parse_task_labels(task_md)
    attempt_raw = labels.get("attempt", "")
    try:
        attempt = int(attempt_raw) if attempt_raw.strip() else None
    except ValueError:
        attempt = None
    return WorkerTaskInfo(
        task_dir=task_md.parent,
        owner=owner,
        task_key=task_md.parent.name,
        loop=labels.get("loop") or None,
        attempt=attempt,
        origin=labels.get("origin") or None,
        task_type=labels.get("type") or None,
    )


def scan_worker_tasks(project_root: pathlib.Path) -> list[WorkerTaskInfo]:
    """Every legal task.md: .agenticdoc/{owner}/workers/{task_key}/task.md.

    The keyed-layout contract (launcher._validate_task_path) means this glob
    covers exactly the spawnable locations; anything else is not a task.
    """
    agenticdoc = pathlib.Path(project_root) / ".agenticdoc"
    if not agenticdoc.is_dir():
        return []
    found: list[WorkerTaskInfo] = []
    for task_md in sorted(agenticdoc.glob("*/workers/*/task.md")):
        found.append(_task_info(task_md, owner=task_md.parts[-4]))
    return found


def used_rounds(workers_dirs: Sequence[pathlib.Path]) -> dict[str, int]:
    """Per-loop used-round counts from task.md loop/attempt labels.

    A round = one distinct attempt value within a loop (D-111 round table).
    Same-attempt repair dispatches (e.g. a phase-writer evidence patch that
    belongs to the verifier's round) and orphan re-insertions of the same
    attempt therefore do not add rounds. A task.md whose attempt label is
    missing degrades to D-102's file-count semantics (each file = one unit),
    keyed by its directory so rewrites of the same dir never double-count.
    In-flight dispatches count as consumed: their task.md exists from the
    dispatch transaction on.
    """
    units: dict[str, set[str]] = {}
    for workers_dir in workers_dirs:
        workers_dir = pathlib.Path(workers_dir)
        if not workers_dir.is_dir():
            continue
        for task_md in sorted(workers_dir.glob("*/task.md")):
            labels = parse_task_labels(task_md)
            loop = labels.get("loop")
            if not loop:
                continue
            attempt = labels.get("attempt", "").strip()
            unit = attempt if attempt else f"@{task_md.parent.name}"
            units.setdefault(loop, set()).add(unit)
    return {loop: len(attempts) for loop, attempts in units.items()}


# ── [START] process observation (D-115) ──────────────────────────────────────

_START_RE = re.compile(r"^\[START\] pid=(\d+)\s*$")


def start_pids(task_dir: pathlib.Path) -> list[int]:
    """Pids from the [START] lines of one task dir's trace.log, in order.

    Every spawn appends exactly one line, so the list length is the spawn
    count; liveness of each pid is the caller's check (D-115: uniqueness is
    line count + pid liveness, never line count alone)."""
    trace = pathlib.Path(task_dir) / "trace.log"
    try:
        lines = trace.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    pids: list[int] = []
    for line in lines:
        m = _START_RE.match(line)
        if m:
            pids.append(int(m.group(1)))
    return pids


def live_start_pids(task_dir: pathlib.Path) -> list[int]:
    """Only the [START] pids that are still running (process-uniqueness view)."""
    return [pid for pid in start_pids(task_dir) if mw_common._is_alive(pid)]


# ── Orphan reconciliation helpers (D-102) ────────────────────────────────────

def _norm(path: pathlib.Path | str) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def find_orphans(project_root: pathlib.Path) -> list[WorkerTaskInfo]:
    """Conductor-origin task.md files with no live queue row.

    Queue rows only ever disappear via stale-archive, which requires the
    task.md to be gone — so a conductor-origin task.md without a row was
    never spawned and is safe to re-insert as pending with the same
    loop/attempt (does not consume a new round). Rows without a task.md are
    NOT orphans; that is stale-archive territory (mw_common).
    """
    project_root = pathlib.Path(project_root)
    rows = mw_common.parse_workers_file(mw_common.workers_path(project_root))
    row_paths = {_norm(r["task_path"]) for r in rows}
    orphans: list[WorkerTaskInfo] = []
    for info in scan_worker_tasks(project_root):
        if info.origin != "conductor":
            continue
        if _norm(info.task_dir / "task.md") not in row_paths:
            orphans.append(info)
    return orphans


# ── Artifact mtime snapshots (AC-014/AC-022) ─────────────────────────────────

@dataclasses.dataclass(frozen=True)
class ArtifactMtimes:
    """mtime snapshot of a key's phase artifacts; None = file absent."""

    spec: float | None
    design: float | None
    plan: float | None
    tasks: dict[str, float]  # task stem -> mtime, sorted by stem


def artifact_mtimes(key_dir: pathlib.Path) -> ArtifactMtimes:
    """Snapshot point for the "completed phases are not redone" assertions:
    compare snapshots across a conductor kill/restart or a takeover and the
    mtimes must be identical."""
    key_dir = pathlib.Path(key_dir)

    def mtime(rel: str) -> float | None:
        path = key_dir / rel
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    tasks_dir = key_dir / "tasks"
    tasks: dict[str, float] = {}
    if tasks_dir.is_dir():
        for task_md in sorted(tasks_dir.glob("*.md")):
            tasks[task_md.stem] = task_md.stat().st_mtime
    return ArtifactMtimes(
        spec=mtime("spec.md"),
        design=mtime("design.md"),
        plan=mtime("plan.md"),
        tasks=tasks,
    )

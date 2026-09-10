"""autopilot/dispatch.py — typed dispatch registry + task/queue writer
(goal-autopilot T-06, D-107/D-111/D-104).

Typed registry (conductor side, D-107): every autopilot dispatch goes through
an explicit type -> tool set -> cli/provider entry. An unregistered type is
refused — zero queue rows, a ``type-rejected`` timeline event, and never a
fallback to the full tool set (GC-8: the *manual* fallback path stays
untouched; this module simply is not that path). The Python registry's tool
sets must stay exactly equal to the TS-side ``TOOL_ALLOWLISTS`` entries added
in T-14; the L0 parity test (T-17) locks that equality.

Task identity (D-111): the queue task key is ``ap-{owner}-{stem}``. The
``ap-`` prefix is globally unique to conductor dispatches — manual task keys
can never collide with it, and stale/legacy rows stay distinguishable.

Dispatch transaction (D-102): the task.md is written first, then the queue
row under ``.mw/workers.lock`` (O_CREAT|O_EXCL, mw_common protocol), then a
read-back verifies the row. The two writes are deliberately non-atomic: a
crash between them leaves exactly the orphan shape (task.md with
``origin: conductor`` and no row) that per-tick reconciliation re-inserts as
pending with the same loop/attempt — no round consumed, no work duplicated.

task.md frontmatter (worker protocol extension, backward compatible):
``origin: conductor`` makes the TS dispatcher skip the task (D-104) and is
the worker-side fail-closed anchor; ``loop:``/``attempt:`` are the round
budget labels state.py derives budgets from; ``read_scope:`` is mandatory
for ``verifier`` (D-106 containment) and omitted otherwise.
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys
from collections.abc import Sequence

# Script-mode bootstrap (same rationale as state.py).
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)

from autopilot import timeline as timeline_mod  # noqa: E402

# ── Typed registry (D-107) ────────────────────────────────────────────────────

_CODING_TOOLS = ("read", "write", "edit", "bash", "find", "grep", "ls")
_REVIEW_TOOLS = ("read", "find", "grep", "ls")


@dataclasses.dataclass(frozen=True)
class DispatchType:
    """One registry entry: type -> tools + route."""

    name: str
    tools: tuple[str, ...]
    cli: str
    provider: str  # "" = route default (CLI_DEFAULT_PROVIDER at spawn time)
    requires_read_scope: bool


REGISTRY: dict[str, DispatchType] = {
    # Writes the _roadmap.md proposal: file tools, no shell.
    "roadmap-writer": DispatchType(
        "roadmap-writer",
        ("read", "write", "edit", "find", "grep", "ls"),
        "pi", "", False,
    ),
    # Evidence/artifact patches: full coding set.
    "phase-writer": DispatchType(
        "phase-writer", _CODING_TOOLS, "pi", "", False,
    ),
    # L2 gate verdicts: review set + mandatory read_scope (D-106).
    "verifier": DispatchType(
        "verifier", _REVIEW_TOOLS, "pi", "", True,
    ),
    # L3 final verdicts: review set.
    "reviewer": DispatchType(
        "reviewer", _REVIEW_TOOLS, "pi", "", False,
    ),
    # Post-below repair: full coding set.
    "repair": DispatchType(
        "repair", _CODING_TOOLS, "pi", "", False,
    ),
}

SCRATCH_OWNER = "_scratch"


def tool_set(task_type: str) -> tuple[str, ...]:
    """Tool set of a registered type; () for unregistered types."""
    entry = REGISTRY.get(task_type)
    return entry.tools if entry else ()


def registry_snapshot() -> dict[str, tuple[str, ...]]:
    """type -> tools snapshot for the L0 parity test (T-17)."""
    return {name: entry.tools for name, entry in REGISTRY.items()}


# ── task.md rendering ─────────────────────────────────────────────────────────

def render_task_md(
    task_type: str,
    prompt: str,
    *,
    loop: str,
    attempt: int,
    read_scope: Sequence[str] = (),
    model: str = "",
) -> str:
    """Render one conductor task.md: frontmatter labels + prompt body.

    Every conductor dispatch carries origin/loop/attempt (design §4.1);
    read_scope renders as a YAML block list (verifier requires it —
    dispatch() enforces, this renderer just renders)."""
    lines = [
        "---",
        f"type: {task_type}",
    ]
    if model:
        lines.append(f"model: {model}")
    lines += [
        "origin: conductor",
        f"loop: {loop}",
        f"attempt: {attempt}",
    ]
    if read_scope:
        lines.append("read_scope:")
        lines.extend(f"  - {item}" for item in read_scope)
    lines += ["---", "", prompt.strip(), ""]
    return "\n".join(lines) + "\n"


# ── dispatch ──────────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class DispatchResult:
    """Outcome of one dispatch attempt.

    ok=True  — task.md + queue row written and the row read back verified.
    ok=False — nothing entered the queue (rows stays 0); ``reason`` names why:
    unknown-type | verifier-read-scope-required | lock-unavailable.
    A failure after the task.md was written (lock-unavailable) leaves the
    orphan shape on purpose — reconciliation re-inserts it next tick."""

    ok: bool
    reason: str
    task_key: str
    task_md: pathlib.Path | None
    row_verified: bool


def task_key_for(owner: str, stem: str) -> str:
    """Queue/task-dir identity: ap-{owner}-{stem} (D-111; ap- is globally
    unique to conductor dispatches, manual keys cannot collide)."""
    return f"ap-{owner}-{stem}"


def _timeline_key(owner: str) -> str | None:
    """Key field for timeline events: the owner key, or None (= '-'
    sentinel) for _scratch (stage-level) dispatches."""
    return None if owner == SCRATCH_OWNER else owner


def dispatch(
    project_root: pathlib.Path,
    owner: str,
    stem: str,
    task_type: str,
    prompt: str,
    *,
    loop: str,
    attempt: int,
    read_scope: Sequence[str] = (),
    model: str = "",
    timeline: timeline_mod.Timeline | None = None,
) -> DispatchResult:
    """Dispatch one typed worker task: write task.md, then the queue row
    under workers.lock, then verify the row by reading it back.

    Rejections (zero queue rows, timeline type-rejected event):
      - unregistered type (never a tool-set fallback, GC-8/D-107)
      - verifier without a non-empty read_scope (D-106)
    On success a ``dispatch`` timeline event is appended (AC-017: every
    dispatch leaves a timeline trace), when a timeline writer is given.
    """
    project_root = pathlib.Path(project_root)
    task_key = task_key_for(owner, stem)

    def reject(reason: str, detail: str) -> DispatchResult:
        if timeline is not None:
            timeline.append(
                "type-rejected", key=_timeline_key(owner), detail=f"{task_key}: {detail}"
            )
        return DispatchResult(
            ok=False, reason=reason, task_key=task_key, task_md=None, row_verified=False
        )

    entry = REGISTRY.get(task_type)
    if entry is None:
        return reject(
            "unknown-type",
            f"unknown dispatch type {task_type!r} "
            f"(registered: {', '.join(sorted(REGISTRY))})",
        )
    scope = [str(item) for item in read_scope if str(item).strip()]
    if entry.requires_read_scope and not scope:
        return reject(
            "verifier-read-scope-required",
            "verifier dispatches require a non-empty read_scope (D-106)",
        )

    # 1. task.md (before the queue row — the crash gap is the orphan shape
    #    that reconciliation heals; see module docstring / D-102).
    task_dir = project_root / ".agenticdoc" / owner / "workers" / task_key
    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = task_dir / "task.md"
    task_md.write_text(
        render_task_md(
            task_type, prompt, loop=loop, attempt=attempt, read_scope=scope, model=model
        ),
        encoding="utf-8",
        newline="\n",
    )

    # 2. queue row under workers.lock — upsert by task_key: replace the
    #    first existing row (a retry requeues the same identity; matches the
    #    TS-side WorkerStore.upsert, so no duplicate-key rows ever appear)
    #    or append when the key is new.
    wpath = mw_common.workers_path(project_root)
    lock = mw_common.lock_path(project_root)
    row = {
        "task_key": task_key,
        "status": "pending",
        "cli": entry.cli,
        "provider": entry.provider,
        "task_path": str(task_md),
        "dispatched_at": mw_common.iso_now(),
        "updated_at": mw_common.iso_now(),
        "model": model,
    }
    try:
        mw_common.acquire_lock(lock)
    except (OSError, RuntimeError) as exc:
        return DispatchResult(
            ok=False,
            reason=f"lock-unavailable: {exc}",
            task_key=task_key,
            task_md=task_md,
            row_verified=False,
        )
    try:
        wpath.parent.mkdir(parents=True, exist_ok=True)
        existing = mw_common.parse_workers_file(wpath)
        idx = next(
            (i for i, e in enumerate(existing) if e["task_key"] == task_key), None
        )
        if idx is None:
            existing.append(row)
        else:
            existing[idx] = row
        with wpath.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(mw_common.serialize_entry(e) + "\n" for e in existing))
    except OSError as exc:
        return DispatchResult(
            ok=False,
            reason=f"queue-write-failed: {exc}",
            task_key=task_key,
            task_md=task_md,
            row_verified=False,
        )
    finally:
        mw_common.release_lock(lock)

    # 3. read-back verification: exactly one row with the right identity.
    row_verified = False
    matches = 0
    for queued in mw_common.parse_workers_file(wpath):
        if queued["task_key"] == task_key:
            matches += 1
            row_verified = (
                queued["task_path"] == str(task_md)
                and queued["cli"] == entry.cli
                and queued["status"] == "pending"
            )
    row_verified = row_verified and matches == 1

    if timeline is not None:
        timeline.append(
            "dispatch",
            key=_timeline_key(owner),
            detail=f"{task_key} type={task_type} loop={loop} attempt={attempt}",
        )
    return DispatchResult(
        ok=True, reason="", task_key=task_key, task_md=task_md, row_verified=row_verified
    )

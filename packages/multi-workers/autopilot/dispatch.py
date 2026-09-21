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
import os
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
    provider: str  # explicit route; "" = route default (CLI_DEFAULT_PROVIDER at spawn time)
    requires_read_scope: bool


REGISTRY: dict[str, DispatchType] = {
    # Writes the _roadmap.md proposal: file tools, no shell.
    "roadmap-writer": DispatchType(
        "roadmap-writer",
        ("read", "write", "edit", "find", "grep", "ls"),
        "pi", "timi", False,
    ),
    # Evidence/artifact patches: full coding set.
    "phase-writer": DispatchType(
        "phase-writer", _CODING_TOOLS, "pi", "timi", False,
    ),
    # L2 gate verdicts: review set + mandatory read_scope (D-106).
    "verifier": DispatchType(
        "verifier", _REVIEW_TOOLS, "pi", "timi", True,
    ),
    # L3 final verdicts: review set.
    "reviewer": DispatchType(
        "reviewer", _REVIEW_TOOLS, "pi", "timi", False,
    ),
    # Post-below repair: full coding set.
    "repair": DispatchType(
        "repair", _CODING_TOOLS, "pi", "timi", False,
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
    deny_globs: Sequence[str] = (),
    model: str = "",
) -> str:
    """Render one conductor task.md: frontmatter labels + prompt body.

    Every conductor dispatch carries origin/loop/attempt (design §4.1);
    read_scope renders as a YAML block list (verifier requires it —
    dispatch() enforces, this renderer just renders). deny_globs (mw-
    dual-workspace AC-006) renders single-quoted: a leading ``*`` is a YAML
    alias marker, and single-quote style has no escape sequences — the
    worker-side parser (worker-mode.ts) strips one quote pair."""
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
    if deny_globs:
        lines.append("deny_globs:")
        lines.extend(f"  - '{item}'" for item in deny_globs)
    lines += ["---", "", prompt.strip(), ""]
    return "\n".join(lines) + "\n"


# ── workspace-profile injection (mw-dual-workspace D-005/D-007) ────────────────

def _expand_read_scope(
    scope: list[str], config: dict, project_root: pathlib.Path
) -> list[str]:
    """D-007 (mw-dual-workspace) + D-006 (mw-target-partition) + AC-001
    (mw-partition-parent-extended): dual mode anchors relative entries
    against the game root and partition mode against the partition root
    (the worker cwd in both), then appends the control root when absent
    (D-005: profile authorization — the worker must be able to read
    target.yml / task context files; never appended to an empty scope —
    that would create containment the dispatch never asked for). The
    parent root IS appended in partition mode: parent is the extended
    writable workspace (mw-partition-parent-extended AC-001 — the carved-
    out functionality lives in the parent and is developed directly),
    with the same absent-only append + normcase dedup as the control root.
    Single mode: scope passes through unchanged — relative entries anchor
    cwd = the (single) control root, so expansion would only churn output."""
    mode = config["mode"]
    if mode not in ("dual", "partition") or not scope:
        return scope
    anchor = pathlib.Path(config["game_root"] if mode == "dual" else config["partition_root"])
    expanded = [
        item if pathlib.Path(item).is_absolute() else str((anchor / item).resolve())
        for item in scope
    ]
    # Only widen an ALREADY-configured containment: appending the control
    # root to an empty scope would create containment the dispatch never
    # asked for (scopeless types keep full access — AC-012 red line).
    control = str(project_root.resolve())
    if all(os.path.normcase(s) != os.path.normcase(control) for s in expanded):
        expanded.append(control)
    if mode == "partition":
        # Extended workspace (AC-001): the parent root joins the containment
        # with the same absent-only append + normcase dedup as the control
        # root. Order: [...entries, control, parent].
        parent = config.get("parent_root")
        if parent:
            parent_abs = str(pathlib.Path(parent).resolve())
            if all(os.path.normcase(s) != os.path.normcase(parent_abs) for s in expanded):
                expanded.append(parent_abs)
    return expanded


def _resolve_deny_globs(config: dict, explicit: Sequence[str] | None) -> list[str]:
    """AC-006 generation side: deny globs default from target.yml's
    ignore.deny_globs (any mode — a single-root UE project can still deny
    its DDC); an explicit per-task list (including empty) wins."""
    if explicit is not None:
        return [str(g) for g in explicit]
    return [str(g) for g in config.get("ignore", {}).get("deny_globs", [])]


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
    deny_globs: Sequence[str] | None = None,
    model: str = "",
    timeline: timeline_mod.Timeline | None = None,
) -> DispatchResult:
    """Dispatch one typed worker task: write task.md, then the queue row
    under workers.lock, then verify the row by reading it back.

    Rejections (zero queue rows, timeline type-rejected event):
      - unregistered type (never a tool-set fallback, GC-8/D-107)
      - verifier without a non-empty read_scope (D-106)
      - unusable target.yml (mw-dual-workspace fail-closed: never a silently
        un-injected task.md; event kind target-config-rejected)
    On success a ``dispatch`` timeline event is appended (AC-017: every
    dispatch leaves a timeline trace), when a timeline writer is given.
    """
    project_root = pathlib.Path(project_root)
    task_key = task_key_for(owner, stem)

    def reject(reason: str, detail: str, ev: str = "type-rejected") -> DispatchResult:
        if timeline is not None:
            timeline.append(
                ev, key=_timeline_key(owner), detail=f"{task_key}: {detail}"
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

    # Workspace-profile injection (mw-dual-workspace D-005/D-007): the
    # resolved config drives scope expansion + deny_globs defaults. The
    # unusable-config message is shape-dynamic (mw-target-partition D-007):
    # v1/no-file keeps the historical text, a v2 file names its active mode.
    try:
        config = mw_common.load_target_config(project_root)
    except mw_common.TargetConfigError as exc:
        return reject(
            "target-config-unusable",
            mw_common.describe_target_error(exc, project_root),
            ev="target-config-rejected",
        )
    scope = _expand_read_scope(scope, config, project_root)
    globs = _resolve_deny_globs(config, deny_globs)

    # mw-target-partition FIX-1 (AC-007/AC-020): the TS dispatcher skips
    # origin: conductor tasks (D-104), so the conductor must inject the v2
    # profile block itself — without it the launcher sees an un-profiled
    # task, and an active-mode switch between dispatch and spawn silently
    # moves the spawn cwd past the tear check. The block mirrors
    # mw_common.render_partition_profile_md (the TS renderPartitionProfileBlock
    # line protocol); dual/single keep the historical no-injection shape
    # (AC-016d zero change). Rendered BEFORE any task-dir side effect so a
    # fail-closed render (undefined placeholder) rejects the dispatch with
    # nothing written and nothing queued; ignore_enforced mirrors the TS
    # ownDenyGlobs rule — the firewall section renders only when the task
    # carries no deny_globs of its own (an explicit list, including empty,
    # wins and skips it).
    content = render_task_md(
        task_type, prompt, loop=loop, attempt=attempt, read_scope=scope,
        deny_globs=globs, model=model,
    )
    if config["mode"] == "partition":
        try:
            profile = mw_common.render_partition_profile_md(
                config, ignore_enforced=deny_globs is None
            )
        except mw_common.TargetConfigError as exc:
            return reject(
                "target-config-unusable",
                mw_common.describe_target_error(exc, project_root),
                ev="target-config-rejected",
            )
        content = content.rstrip() + "\n\n" + profile + "\n"

    # 1. task.md (before the queue row — the crash gap is the orphan shape
    #    that reconciliation heals; see module docstring / D-102).
    task_dir = project_root / ".agenticdoc" / owner / "workers" / task_key
    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = task_dir / "task.md"
    task_md.write_text(content, encoding="utf-8", newline="\n")

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
        # Queue write goes through mw_common._write_workers_file (content
        # fully precomputed, then tmp + os.replace): a serialization error
        # must never truncate _workers.parallel — open("w") truncates before
        # the write expression is evaluated (pitfalls P-003 / PM defect #50).
        mw_common._write_workers_file(wpath, existing)
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

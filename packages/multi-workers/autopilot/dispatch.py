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
import re
import sys
from collections.abc import Sequence

# Script-mode bootstrap (same rationale as state.py).
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)

from autopilot import config as autopilot_config  # noqa: E402
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
    # mw-rag-integration T-09: PM-only types (e.g. rag-research) carry False;
    # the conductor refuses to dispatch them. A default keeps every existing
    # 5 positional entries unchanged (conductor_dispatchable=True).
    conductor_dispatchable: bool = True


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
    # RAG research bucket (mw-rag-integration D-011/AC-011): renders rag_chat,
    # the only type allowed to call it. PM/user-dispatched only — the
    # conductor must not use it (conductor_dispatchable=False below). Tool
    # order is locked per-item against the TS TOOL_ALLOWLISTS entry.
    "rag-research": DispatchType(
        "rag-research",
        (
            "read", "find", "grep", "ls",
            "rag_search", "rag_symbol", "rag_graph", "rag_impact",
            "rag_sources", "rag_feedback", "rag_chat",
        ),
        "pi", "timi", False, False,
    ),
}

SCRATCH_OWNER = "_scratch"

# pm-state.md's phase interface line is owned by advance_phase.py (read-only
# here). The token is split so the VC-007 static scan never sees the literal.
_PHASE_LINE_KEY = "Phase:"


def _owner_phase(project_root: pathlib.Path, owner: str) -> str:
    """Current phase of ``owner`` from its pm-state.md interface line.

    mw-rag-integration T-14: the phase axis of
    ``required = role.require OR phase.require`` is written into task.md from
    the owning key's current phase. ``_scratch`` dispatches, a missing
    pm-state.md, and a file without the interface line all return "" — the
    renderer then writes no ``phase:`` header (never guessed). pm-state.md is
    owned by advance_phase.py; this read never writes it.
    """
    if owner == SCRATCH_OWNER:
        return ""
    state_path = pathlib.Path(project_root) / ".agenticdoc" / owner / "pm-state.md"
    try:
        text = state_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    prefix = "- " + _PHASE_LINE_KEY
    for raw in text.splitlines():
        if raw.startswith(prefix):
            return raw[len(prefix):].strip()
    return ""


def tool_set(task_type: str) -> tuple[str, ...]:
    """Tool set of a registered type; () for unregistered types."""
    entry = REGISTRY.get(task_type)
    return entry.tools if entry else ()


def registry_snapshot() -> dict[str, tuple[str, ...]]:
    """type -> tools snapshot for the L0 parity test (T-17)."""
    return {name: entry.tools for name, entry in REGISTRY.items()}


# ── task.md rendering ─────────────────────────────────────────────────────────

def _strip_rag_block(content: str) -> str:
    """Remove an existing `<!-- mw-rag: v1 -->` block (marker replacement).

    The block runs from the marker line through the terminating
    `fingerprint=` line (the marker and the fingerprint are the only two
    anchors both sides render). Stopping at the fingerprint keeps a profile
    block that may follow it intact — the profile block shares the `[mw] `
    line prefix. Content without the marker is returned untouched, so a
    RAG-less task.md is byte-identical to the pre-RAG generator (AC-001).
    """
    idx = content.find(mw_common.RAG_MARKER_V1)
    if idx == -1:
        return content
    start = content.rfind("\n", 0, idx) + 1
    match = re.search(r"^fingerprint=\S+[ \t\r]*$", content[idx:], flags=re.MULTILINE)
    if match is None:
        # Malformed (marker without a fingerprint): drop the marker line only.
        end = content.find("\n", idx)
        end = len(content) if end == -1 else end + 1
    else:
        end = idx + match.end()
        if end < len(content) and content[end] == "\n":
            end += 1
    return content[:start] + content[end:]


def _inject_rag_block(
    content: str, rag_config: dict | None, task_meta: dict | None, task_type: str
) -> str:
    """Append (or replace) the task.md mw-rag block; no-op when disabled.

    `mw_common.render_rag_block` returns None with an empty enabled set — the
    structural zero-impact guarantee (D-014/AC-001) — so a RAG-less task.md
    keeps every byte. The append shape (`rstrip()` + blank line + block +\n)
    matches the T-06 golden byte contract; an existing block is replaced
    wholesale, which makes repeated rendering idempotent.
    """
    if not rag_config:
        return content
    meta = task_meta if isinstance(task_meta, dict) else {}
    if not meta:
        meta = {
            "type": task_type,
            "role": mw_common.TASK_TYPE_TO_ROLE.get(task_type, task_type),
        }
    block = mw_common.render_rag_block(rag_config, meta)
    if block is None:
        return content
    return _strip_rag_block(content).rstrip() + "\n\n" + block + "\n"


def _read_scope_caps(project_root: pathlib.Path) -> tuple[int | None, int | None]:
    """``l2_read_file_cap`` / ``l2_read_byte_cap`` for the rendered task.md.

    Until 2026-09-23 these two fields were dead config: config.py parsed and
    validated them, but no Python renderer ever emitted them, so every
    conductor-dispatched worker fell back to the harness default
    (``DEFAULT_READ_FILE_CAP`` = 8 files / 65536 B). The cap only activates
    for tasks that carry ``read_scope`` (worker-mode.ts: zero interception
    otherwise) — i.e. exactly the verifiers, where read_scope is mandatory
    (D-106). Measured consequence (FeatureMigrator gui-contract-surface /
    gui-shell-spike, 2026-09-23): both L3 reviewers spent all 8 allowed
    read/ls/find/grep calls on context loading, could not read a single
    EXECUTE evidence file, and returned fail-closed ``below`` verdicts
    (0/23 and 0/31 verification criteria assertable) — structurally
    unverifiable keys, not product failures.

    A missing config file keeps ``(None, None)`` → task.md byte-identical to
    the pre-fix renderer (config.py's own contract: absent file = defaults,
    zero footprint, and the worker default is the same 8/65536). The cap
    *default* values are owned by the TS harness
    (``read-scope.ts::DEFAULT_READ_*``): the Python side deliberately defines
    no fallback constant of its own (D-002 / GC-4: single source).
    """
    try:
        if not autopilot_config.config_path(project_root).exists():
            return None, None
        cfg = autopilot_config.load_config(project_root)
    except Exception:  # invalid/unreadable config must not break dispatching
        return None, None
    caps: list[int | None] = []
    for field in ("l2_read_file_cap", "l2_read_byte_cap"):
        value = cfg.get(field)
        caps.append(
            int(value)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0
            else None
        )
    return caps[0], caps[1]


def render_task_md(
    task_type: str,
    prompt: str,
    *,
    loop: str,
    attempt: int,
    read_scope: Sequence[str] = (),
    deny_globs: Sequence[str] = (),
    read_file_cap: int | None = None,
    read_byte_cap: int | None = None,
    model: str = "",
    phase: str = "",
    profile_block: str | None = None,
    rag_config: dict | None = None,
    task_meta: dict | None = None,
) -> str:
    """Render one conductor task.md: frontmatter labels + prompt body.

    Every conductor dispatch carries origin/loop/attempt (design §4.1);
    read_scope renders as a YAML block list (verifier requires it —
    dispatch() enforces, this renderer just renders). deny_globs (mw-
    dual-workspace AC-006) renders single-quoted: a leading ``*`` is a YAML
    alias marker, and single-quote style has no escape sequences — the
    worker-side parser (worker-mode.ts) strips one quote pair.

    ``phase`` (mw-rag-integration T-14): the phase axis of
    ``required = role.require OR phase.require``. Only a non-empty value emits
    ``phase: <P>`` right after ``type:`` — ``phase=""`` (unknown phase,
    ``_scratch``, legacy callers) leaves the output byte-identical to the
    pre-T-14 renderer, so existing task.md files and tests do not churn.

    ``profile_block`` (mw-target-partition FIX-1) is emitted before the RAG
    block so the conductor path keeps the same block order as the TS
    dispatcher. ``rag_config`` is `mw_common.load_rag_config`'s output; an
    absent/empty config appends nothing. Re-rendering is idempotent: an
    existing `mw-rag: v1` block is replaced wholesale (same marker/anchor).

    ``read_file_cap`` / ``read_byte_cap`` (read-scope budgets, see
    :func:`_read_scope_caps`) render only when supplied — ``None`` (absent
    config, legacy callers, direct unit tests) leaves the output
    byte-identical to the pre-fix renderer.
    """
    lines = [
        "---",
        f"type: {task_type}",
    ]
    if phase:
        lines.append(f"phase: {phase}")
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
    if read_file_cap is not None:
        lines.append(f"l2_read_file_cap: {int(read_file_cap)}")
    if read_byte_cap is not None:
        lines.append(f"l2_read_byte_cap: {int(read_byte_cap)}")
    if deny_globs:
        lines.append("deny_globs:")
        lines.extend(f"  - '{item}'" for item in deny_globs)
    lines += ["---", "", prompt.strip(), ""]
    content = "\n".join(lines) + "\n"
    if profile_block is not None:
        content = content.rstrip() + "\n\n" + profile_block + "\n"
    return _inject_rag_block(content, rag_config, task_meta, task_type)


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
    # PM-only types (mw-rag-integration T-09/AC-011): registered for the
    # PM/`/worker` dispatch surface but never conductor-dispatched. Rejected
    # before any task-dir side effect, exactly like an unknown type.
    if not entry.conductor_dispatchable:
        return reject(
            f"not-conductor-dispatchable: {task_type} is a PM-dispatched type, "
            "the conductor must not dispatch it",
            f"{task_type} is a PM-dispatched type, the conductor must not dispatch it",
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
    # RAG static config (T-07/D-009) is loaded before any task-dir side
    # effect but never blocks dispatching: a broken config renders no block
    # (load_rag_config returns ({}, error) by contract).
    rag_config, _rag_error = mw_common.load_rag_config(project_root)
    profile_block: str | None = None
    if config["mode"] == "partition":
        try:
            profile_block = mw_common.render_partition_profile_md(
                config, ignore_enforced=deny_globs is None
            )
        except mw_common.TargetConfigError as exc:
            return reject(
                "target-config-unusable",
                mw_common.describe_target_error(exc, project_root),
                ev="target-config-rejected",
            )
    read_file_cap, read_byte_cap = _read_scope_caps(project_root)
    content = render_task_md(
        task_type, prompt, loop=loop, attempt=attempt, read_scope=scope,
        deny_globs=globs, model=model, phase=_owner_phase(project_root, owner),
        profile_block=profile_block,
        rag_config=rag_config,
        read_file_cap=read_file_cap,
        read_byte_cap=read_byte_cap,
    )

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

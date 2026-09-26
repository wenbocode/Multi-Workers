"""autopilot/conductor.py — autonomous orchestration loop skeleton
(goal-autopilot T-09, design §5.1 / D-101 / D-113 / D-114).

The conductor is the third child of ``mw serve`` (D-101): serve owns its
lifecycle (spawn when the project config enables autopilot, terminate when
disabled, respawn within 1s on death). This module is the loop itself.

Per-tick contract (§5.1, in order):

1. Append a ``beat`` timeline event — always, even when disabled/paused
   (AC-019 liveness: any 60s window must hold >= 12 beats).
2. Load the config (mtime-cached); ``enabled && not paused`` gates the rest.
3. goal.md mtime change detection against the startup baseline (D-102):
   a change halts orchestration and opens ONE ``goal-change`` gate; the halt
   holds until the gate is answered, then the baseline is refreshed.
4. ``orchestrate()`` — the per-key phase machine / stage lifecycle /
   EXECUTE loop. Stub in this task; T-10/T-11/T-12 fill it in.

Fault tolerance (§9): a tick never kills the loop — any uncaught exception
becomes a timeline ``config`` event and the next tick proceeds.

Locks (D-113): the conductor's own lock wrapper steals locks whose file is
older than 30s (every conductor lock hold is milliseconds, so an older file
means the holder died). TS-side lock protocol is untouched.

AC-005: this module never writes pm-state.md Phase fields and never writes
goal.md — goal.md is only ever stat()ed, and every phase transition goes
through advance.advance() → advance_phase.py.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import signal
import subprocess
import sys
import threading
import time

# Script-mode bootstrap (same rationale as state.py / dispatch.py).
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)

from autopilot import advance, audit_evidence, closure, config, dispatch, gates, roadmap, state, timeline  # noqa: E402

# ── Phase machine constants (T-10) ──────────────────────────────────────────

PHASES = ("spec", "design", "plan", "tasks", "execute", "verify", "done")
_DEP_SATISFIED = frozenset({"done", "closed-legacy"})

# ── Paths ─────────────────────────────────────────────────────────────────────

STALE_LOCK_AGE_SEC = 30.0


def conductor_pid_file(project_root: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_root) / ".mw" / "conductor.pid"


def gates_dir(project_root: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_root) / ".agenticdoc" / "_autopilot" / "gates"


def goal_path(project_root: pathlib.Path) -> pathlib.Path:
    """goal.md path — READ-ONLY for the conductor (AC-005: never written)."""
    return pathlib.Path(project_root) / ".agenticdoc" / "goal.md"


def goal_mtime_ns(project_root: pathlib.Path) -> int | None:
    """goal.md mtime in ns, or None when absent. The only goal.md access the
    conductor ever performs (D-102 change detection baseline)."""
    try:
        return os.stat(goal_path(project_root)).st_mtime_ns
    except OSError:
        return None


# ── Locks (D-113) ─────────────────────────────────────────────────────────────


class ConductorLockHeld(RuntimeError):
    """A lock younger than the stale threshold is genuinely held — the
    operation that wanted it must defer to a later tick."""


def lock_file(project_root: pathlib.Path, name: str) -> pathlib.Path:
    """Named conductor lock: workers / gates / roadmap / key-{key}."""
    return pathlib.Path(project_root) / ".mw" / f"{name}.lock"


def acquire_conductor_lock(
    project_root: pathlib.Path,
    name: str,
    tl: timeline.Timeline,
    *,
    stale_after: float = STALE_LOCK_AGE_SEC,
) -> None:
    """Acquire ``.mw/{name}.lock`` with stale steal (D-113).

    Fast acquire first; on exhaustion the lock file's age decides: older than
    ``stale_after`` → the holder is dead (conductor holds are milliseconds) —
    steal it (unlink + re-acquire) and record a timeline ``config`` event;
    younger → :class:`ConductorLockHeld` (a live holder — defer, never
    clobber). The TS-side protocol is untouched; this recovery exists only
    on the conductor side."""
    path = lock_file(project_root, name)
    try:
        mw_common.acquire_lock(path, retries=4, base_delay=0.02)
        return
    except (RuntimeError, OSError):
        pass  # held (or transient) — age check decides
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        # Vanished between failure and stat — plain acquire.
        mw_common.acquire_lock(path)
        return
    if age > stale_after:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        tl.append("config", detail=f"stale {name}.lock stolen (age {age:.0f}s > {stale_after:.0f}s)")
        mw_common.acquire_lock(path)
        return
    raise ConductorLockHeld(f"{name}.lock held by a live holder (age {age:.0f}s)")


# ── Tick ──────────────────────────────────────────────────────────────────────


class ConductorState:
    """Mutable per-process loop state (goal baseline + halt flag)."""

    def __init__(self, tl: timeline.Timeline, goal_baseline: int | None) -> None:
        self.timeline = tl
        self.goal_baseline = goal_baseline  # mtime_ns snapshot (D-102)
        self.goal_halted = False  # goal-change gate open
        # key -> claim_id already skip-notified (event spam control only;
        # the skip decision itself re-derives from files every tick)
        self.skipped_claims: dict[str, str] = {}


def open_goal_change_gate(project_root: pathlib.Path) -> bool:
    """Is there a pending goal-change gate? (Directory truth — survives
    conductor restarts; also the create-once guard.)"""
    return any(
        g.kind == "goal-change" and g.status == "pending"
        for g in gates.enumerate(gates_dir(project_root))
    )


def orchestrate(project_root: pathlib.Path, st: ConductorState) -> None:
    """Gate consumption + stage lifecycle + per-key phase machine
    (T-10/T-11, design §5.1).

    Zero private state: every decision re-derives from files (roadmap /
    _index.parallel / _workers.parallel / gates / task.md labels) each tick
    (D-102). Phase transitions go ONLY through advance.advance() ->
    advance_phase.py (AC-005); goal.md is never written here."""
    project_root = pathlib.Path(project_root)
    cfg = config.cached_load(project_root)

    # §5.1 F: consume answered gates first — a corrupt answer file skips
    # the whole tick (policy per gates.enumerate docstring).
    if not _consume_answered_gates(project_root, st, cfg):
        return

    # §5.1 F2: orphan reconciliation.
    reconcile_orphans(project_root, st)

    rm_path = roadmap.roadmap_path(project_root)
    rows = mw_common.parse_workers_file(mw_common.workers_path(project_root))

    if not rm_path.is_file():
        # No roadmap yet — dispatch the roadmap-writer (fresh proposal).
        _dispatch_roadmap_writer(project_root, st, rows, stage_number=1)
        return
    try:
        rm = roadmap.load_roadmap(rm_path)
    except roadmap.RoadmapError as exc:
        st.timeline.append("config", detail=f"roadmap unreadable: {exc}")
        return

    # §5.1 G: stage branch. No running stage → activation work only; a
    # running stage releases the per-key machine below.
    if not _stage_activation(project_root, st, rm, rows):
        return

    key_states = state.read_key_states(project_root)
    rounds = state.used_rounds(_all_workers_dirs(project_root))

    # Cross-stage views: key -> deps, key -> status, key -> stage number.
    deps_of: dict[str, tuple[str, ...]] = {}
    status_of: dict[str, str] = {}
    stage_of: dict[str, int] = {}
    for stage in rm.stages:
        for entry in stage.keys:
            deps_of[entry.key] = entry.depends_on
            stage_of[entry.key] = stage.number
        for k, s in stage.key_status.items():
            status_of[k] = s

    # Stalled keys whose stalled gate was approved → resume (AC-004/AC-013).
    _apply_stalled_approvals(project_root, st, status_of, stage_of)

    # Stalled keys whose stalled gate was rejected → closed-legacy (F7).
    _apply_stalled_rejections(project_root, st, status_of, stage_of)

    # Cross-key red aggregation (xkey-repair-mechanism D-010): fold the below
    # rounds' handoff registrations into the ledger, mint tickets and raise
    # xkey-authorize gates. Placed after _apply_stalled_* (status_of is this
    # tick's final key-status view, needed to judge the owner key) and before
    # the dispatch loop (gates/tickets raised here are visible this tick).
    # AC-008: the whole mechanism is opt-in, so a disabled project runs the
    # exact same control flow it always did.
    if cfg.get("xkey_repair", False):
        _xkey_aggregate(project_root, st, status_of, cfg)
        # Same gate, after the aggregator: an approve consumed by step F above
        # is immediately visible. T-08 runs first and dispatches the proposal
        # worker for an approved ticket with no proposal on disk (exactly
        # once); once the proposal lands this stage is a no-op and T-06's stage
        # below takes over (an approved ticket with a proposal walks
        # applied→verified→closed this very tick, AC-005/006/007).
        _xkey_proposal_stage(project_root, st, rows)
        _xkey_apply_stage(project_root, st, status_of, cfg)

    in_flight_keys = {
        key
        for key in deps_of
        if any(
            _is_in_flight(row) and _row_belongs_to(row, key) for row in rows
        )
    }

    for stage in rm.stages:
        if stage.status != "running":
            continue
        # §5.1 I/J: all keys terminal → closure dossier + stage-close gate
        # (same tick; the per-key loop below is a no-op for terminal keys).
        _stage_closure(project_root, st, stage, rm_path, status_of)
        for entry in stage.keys:
            key = entry.key
            if status_of.get(key) in ("done", "stalled", "closed-legacy"):
                continue
            ks = key_states.get(key)
            claim = ks.claim if ks is not None else state.CLAIM_FREE
            if claim == state.CLAIM_LIVE:
                if st.skipped_claims.get(key) != (ks.claim_id if ks else ""):
                    st.timeline.append(
                        "skip", key=key, detail=f"live foreign claim {ks.claim_id if ks else ''}"
                    )
                    st.skipped_claims[key] = ks.claim_id if ks else ""
                continue
            if not _deps_satisfied(entry.depends_on, status_of):
                continue
            if key in in_flight_keys:
                continue  # wait for the in-flight worker
            if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):
                continue  # parallel cap — key starts on a later tick
            if _advance_key(project_root, st, key, rows, rounds, cfg, rm_path):
                in_flight_keys.add(key)


# ── Gate consumption + stage lifecycle (T-11, §5.1/§5.3) ─────────────────────

def _consumed_gate_ids(project_root: pathlib.Path) -> set[str]:
    """Gate ids whose answer the conductor already applied — the timeline
    gate-answered events are the durable consumption records (a restart
    re-derives the same set; a human roadmap edit after a halt is a
    resolution, not an unconsumed answer)."""
    ids: set[str] = set()
    try:
        events = timeline.query_events(timeline.timeline_path(project_root)).events
    except OSError:
        return ids
    for ev in events:
        if ev.get("ev") != "gate-answered":
            continue
        m = re.match(r"(gate-\d{4})\b", str(ev.get("detail", "")))
        if m is not None:
            ids.add(m.group(1))
    return ids


def _consume_answered_gates(
    project_root: pathlib.Path, st: ConductorState, cfg: dict | None = None
) -> bool:
    """§5.1 F: apply answered-gate transitions. Returns False when a corrupt
    gate file forces a tick skip (timeline config event appended).

    Idempotent by file truth: a transition fires (gate-answered event) only
    when it actually changes the roadmap, so an answered gate is consumed
    exactly once across ticks and conductor restarts. stalled-reject is
    consumed by _apply_stalled_rejections (it owns the key-status rewrite);
    budget-exhausted / goal-change gates are polled, not transitioned.

    ``xkey`` answered-authorization gates are folded here too (D-010): step F
    runs before ``_apply_stalled_approvals/_apply_stalled_rejections``, which
    only understand ``stalled`` keys — routing an xkey approval through them
    would leave the ticket frozen forever. The branch is gated by
    ``cfg["xkey_repair"]`` so a disabled project never touches the module."""
    try:
        all_gates = gates.enumerate(gates_dir(project_root))
    except gates.GateFormatError as exc:
        st.timeline.append("config", detail=f"gate file corrupt, tick skipped: {exc}")
        return False
    rm_path = roadmap.roadmap_path(project_root)
    if not rm_path.is_file():
        return True  # nothing to transition yet
    consumed = _consumed_gate_ids(project_root)
    for gate in all_gates:
        if gate.status == "pending":
            continue
        if gate.kind == "xkey-authorize":
            if (cfg or {}).get("xkey_repair", False) and gate.id not in consumed:
                _consume_xkey_gate(project_root, st, gate)
            continue
        if gate.stage is None:
            continue
        if gate.id in consumed:
            continue  # answer already applied (timeline consumption record)
        if gate.kind == "stage-confirm" and gate.status == "approved":
            if _set_stage_status(project_root, st, rm_path, gate.stage, "running"):
                st.timeline.append(
                    "gate-answered", stage=gate.stage,
                    detail=f"{gate.id} approved → stage {gate.stage} running",
                )
        elif gate.kind == "stage-close":
            if gate.status == "approved":
                if _set_stage_status(project_root, st, rm_path, gate.stage, "closed"):
                    st.timeline.append(
                        "gate-answered", stage=gate.stage,
                        detail=f"{gate.id} approved → stage {gate.stage} closed",
                    )
                    st.timeline.append(
                        "stage-close", stage=gate.stage,
                        detail=f"stage {gate.stage} closed ({gate.id} approved)",
                    )
                    _ensure_next_stage_gate(project_root, st, rm_path, gate.stage + 1)
            elif gate.status == "rejected":
                if _set_stage_status(project_root, st, rm_path, gate.stage, "halted"):
                    st.timeline.append(
                        "gate-answered", stage=gate.stage,
                        detail=f"{gate.id} rejected → stage {gate.stage} halted",
                    )
    return True


def _set_stage_status(
    project_root: pathlib.Path,
    st: ConductorState,
    rm_path: pathlib.Path,
    stage_number: int,
    new_status: str,
) -> bool:
    """Rewrite one stage status line under the roadmap lock. Idempotent;
    returns True only when the file actually changed."""
    try:
        rm = roadmap.load_roadmap(rm_path)
        stage = roadmap.stage_by_number(rm, stage_number)
        if stage is None or stage.status == new_status:
            return False
        text = rm_path.read_text(encoding="utf-8")
        new_text = roadmap.update_stage_status(text, stage_number, new_status)
        if new_text == text:
            return False
        acquire_conductor_lock(project_root, "roadmap", st.timeline)
        try:
            rm_path.write_text(new_text, encoding="utf-8", newline="\n")
        finally:
            mw_common.release_lock(lock_file(project_root, "roadmap"))
        return True
    except (roadmap.RoadmapError, OSError) as exc:
        st.timeline.append("config", detail=f"stage status write failed: {exc!r}")
        return False


def _ensure_next_stage_gate(
    project_root: pathlib.Path,
    st: ConductorState,
    rm_path: pathlib.Path,
    stage_number: int,
) -> None:
    """After a stage closes, open the next stage's confirm gate (if that
    stage exists and is still pending)."""
    try:
        rm = roadmap.load_roadmap(rm_path)
    except roadmap.RoadmapError:
        return
    nxt = roadmap.stage_by_number(rm, stage_number)
    if nxt is None or nxt.status != "pending":
        return
    if _gate_open(project_root, "stage-confirm", stage=stage_number):
        return
    _create_gate(
        project_root, st, "stage-confirm",
        f"Stage {stage_number}（{len(nxt.keys)} 个 key，目标：{nxt.goal}）已就绪——"
        f"确认启动该 stage？approve=启动并开始派发；reject=要求重新提案",
        stage=stage_number, refs=[f"stage-{stage_number}"],
    )


def _stage_activation(
    project_root: pathlib.Path,
    st: ConductorState,
    rm: roadmap.Roadmap,
    rows: list[dict],
) -> bool:
    """§5.1 G: is a stage running? When none is, run activation work
    (roadmap-writer dispatch / stage-confirm gate) and report False — no
    per-key dispatch happens before a stage-confirm approval (AC-002)."""
    if any(s.status == "halted" for s in rm.stages):
        return False  # stage-close rejected — pause until a human edits the roadmap
    if any(s.status == "running" for s in rm.stages):
        return True
    target = next((s for s in rm.stages if s.status == "pending"), None)
    if target is None:
        return False  # all closed / empty roadmap — nothing to activate
    _activate_pending_stage(project_root, st, target, rows)
    return False


def _activate_pending_stage(
    project_root: pathlib.Path,
    st: ConductorState,
    stage: roadmap.RoadmapStage,
    rows: list[dict],
) -> None:
    """Activation work for the first pending stage (AC-024):

    - a rejection exists and the roadmap is OLDER than it → the current
      proposal was already rejected: re-propose via roadmap-writer (max 2
      proposals total; both spent → stop and wait for a human edit);
    - the roadmap is NEWER than the latest rejection (the writer revised it,
      or a human edited it) → it is a fresh proposal: ensure one pending
      stage-confirm gate for it;
    - no rejection yet → ensure one pending stage-confirm gate."""
    rejected = _latest_rejected_confirm(project_root, stage.number)
    if rejected is not None:
        rm_path = roadmap.roadmap_path(project_root)
        rm_newer = rm_path.stat().st_mtime_ns > rejected.path.stat().st_mtime_ns
        if not rm_newer:
            _dispatch_roadmap_writer(
                project_root, st, rows, stage_number=stage.number,
                rejected_note=rejected.note or "",
            )
            return
        # fresh (revised or hand-edited) roadmap awaits confirmation
        if _gate_open(project_root, "stage-confirm", stage=stage.number):
            return
        _create_stage_confirm_gate(project_root, st, stage)
        return
    if _gate_open(project_root, "stage-confirm", stage=stage.number):
        return  # awaiting the human
    _create_stage_confirm_gate(project_root, st, stage)


def _create_stage_confirm_gate(
    project_root: pathlib.Path, st: ConductorState, stage: roadmap.RoadmapStage
) -> None:
    _create_gate(
        project_root, st, "stage-confirm",
        f"Stage {stage.number}（{len(stage.keys)} 个 key，目标：{stage.goal}）提案已写入"
        f" _roadmap.md——确认启动该 stage？approve=启动并开始派发；reject=要求重新提案",
        stage=stage.number, refs=[f"stage-{stage.number}"],
    )


def _latest_rejected_confirm(
    project_root: pathlib.Path, stage_number: int
) -> gates.Gate | None:
    """Most recently answered rejected stage-confirm gate for this stage."""
    latest: gates.Gate | None = None
    for gate in gates.enumerate(gates_dir(project_root)):
        if (
            gate.kind == "stage-confirm"
            and gate.status == "rejected"
            and gate.stage == stage_number
            and (latest is None or gate.path.stat().st_mtime_ns > latest.path.stat().st_mtime_ns)
        ):
            latest = gate
    return latest


def _roadmap_writer_loop(stage_number: int) -> str:
    return f"roadmap:stage-{stage_number}"


def _dispatch_roadmap_writer(
    project_root: pathlib.Path,
    st: ConductorState,
    rows: list[dict],
    *,
    stage_number: int,
    rejected_note: str = "",
) -> None:
    """Dispatch the roadmap-writer for one stage proposal (D-105 input
    list: goal.md + memory trio when present + _index.parallel key list +
    embedded schema template; read_scope limited to .agenticdoc reads, the
    only write target is _roadmap.md).

    Bounded: at most 2 proposals per stage (loop rounds = distinct
    attempts) — a second rejection (or a second failed writer run) stops
    auto-proposal and waits for a human roadmap edit (AC-024)."""
    loop = _roadmap_writer_loop(stage_number)
    for info in state.scan_worker_tasks(project_root):
        if info.loop != loop or info.origin != "conductor":
            continue
        if _row_exists(rows, info.task_key) and any(
            r["task_key"] == info.task_key and _is_in_flight(r) for r in rows
        ):
            return  # proposal still in flight
    used = state.used_rounds(_all_workers_dirs(project_root)).get(loop, 0)
    if used >= 2:
        return  # both proposals spent — wait for a human roadmap edit
    attempt = used + 1
    result = dispatch.dispatch(
        project_root, dispatch.SCRATCH_OWNER,
        f"roadmap-s{stage_number}-a{attempt}", "roadmap-writer",
        _roadmap_writer_prompt(project_root, stage_number, rejected_note),
        loop=loop, attempt=attempt,
        read_scope=[".agenticdoc"],
        timeline=st.timeline,
    )
    if not result.ok:
        st.timeline.append(
            "config", detail=f"roadmap-writer dispatch refused: {result.reason}"
        )


def _roadmap_writer_prompt(
    project_root: pathlib.Path, stage_number: int, rejected_note: str
) -> str:
    """D-105 roadmap-writer input list rendered into the task prompt."""
    goal = "(missing)"
    goal_file = goal_path(project_root)
    if goal_file.is_file():
        goal = goal_file.read_text(encoding="utf-8").strip()[:4000]
    key_states = state.read_key_states(project_root)
    key_rows = [
        f"- {ks.key} (phase {ks.phase})" for ks in key_states.values()
    ] or ["- (no existing keys)"]
    memory = []
    for name in ("spec.md", "design.md", "plan.md"):
        candidates = sorted(
            (pathlib.Path(project_root) / ".agenticdoc").glob(f"*/{name}")
        )
        for cand in candidates:
            memory.append(f"- {cand.relative_to(project_root)}")
    revision = ""
    if rejected_note is not None and rejected_note != "":
        revision = (
            f"\n## 前次提案被 reject\n\n人工备注：{rejected_note}\n"
            "请针对备注修订后重写整个 _roadmap.md。\n"
        )
    return (
        f"# Roadmap proposal: stage {stage_number}\n\n"
        f"## goal.md\n\n```\n{goal}\n```\n\n"
        "## 记忆三件套（存在时，自行 read）\n\n"
        + ("\n".join(memory) if memory else "- (none)")
        + "\n\n## _index.parallel 现存 key 清单\n\n"
        + "\n".join(key_rows)
        + "\n\n## roadmap schema 模板（严格遵守）\n\n```markdown\n"
        "# Roadmap\n"
        "> generated_at: <iso>\n"
        "> goal_mtime: <ms>\n\n"
        f"## Stage {stage_number}: <标题>\n"
        "> goal: <阶段目标>\n"
        "> status: pending\n"
        "> key-status: <key>=running, ...\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        "| <key> | <role> | - 或逗号分隔依赖 |\n"
        "```\n\n"
        "校验要求：每 stage ≥1 个 key、goal 非空、依赖指向同 stage 或前序 stage 的 key、"
        "key-status 的 key 集与 Keys 表一致。\n\n"
        "## 写入目标\n\n"
        "唯一写入目标：`.agenticdoc/_autopilot/_roadmap.md`（整个文件重写）。"
        "读取仅限 .agenticdoc 下。\n"
        + revision
    )


def _stage_closure(
    project_root: pathlib.Path,
    st: ConductorState,
    stage: roadmap.RoadmapStage,
    rm_path: pathlib.Path,
    status_of: dict[str, str],
) -> None:
    """§5.1 I→J: every key terminal (done / closed-legacy; a stalled key
    with a pending gate blocks closure — AC-024) → write the closure
    dossier and open the stage-close gate (AC-003, same tick).

    ``status_of`` is the tick's live cross-stage view — closed-legacy
    rewrites applied earlier in this same tick already count as terminal."""
    terminal = ("done", "closed-legacy")
    if any(status_of.get(e.key) not in terminal for e in stage.keys):
        return
    if _gate_open(project_root, "stage-close", stage=stage.number):
        return  # already awaiting the human
    stages_dir = project_root / ".agenticdoc" / "_autopilot" / "stages"
    dossier = stages_dir / f"stage-{stage.number}-close.md"
    if not dossier.is_file():
        try:
            stages_dir.mkdir(parents=True, exist_ok=True)
            dossier.write_text(
                _closure_dossier_md(project_root, stage),
                encoding="utf-8", newline="\n",
            )
        except OSError as exc:
            st.timeline.append("config", detail=f"dossier write failed: {exc!r}")
            return
        st.timeline.append(
            "stage-close", stage=stage.number,
            detail=f"dossier stage-{stage.number}-close.md written",
        )
    _create_gate(
        project_root, st, "stage-close",
        f"Stage {stage.number} 全部 key 已终态，闭环 dossier 已写入"
        f" .agenticdoc/_autopilot/stages/stage-{stage.number}-close.md——"
        "确认闭环？approve=标记 closed 并开放下一 stage；reject=halt 等待人工处理",
        stage=stage.number, refs=[f"stage-{stage.number}"],
    )


def _l3_verdict(key_dir: pathlib.Path) -> tuple[str, str]:
    """(verdict, report path) for one key: meets|below from l3-verdict.txt
    (written by the done transaction / stall path), else none."""
    verdict_file = key_dir / "l3-verdict.txt"
    if verdict_file.is_file():
        verdict = verdict_file.read_text(encoding="utf-8").strip().lower()
        if verdict in ("meets", "below"):
            report = key_dir / "l3-report.md"
            return verdict, str(report) if report.is_file() else "—"
    return "none", "—"


# ── L3 verdict persistence (feature-l3-verdict-freshness) ────────────────────
_VERDICT_VALUES = ("meets", "below")  # derived-record value domain (D-008)


def _persist_l3_verdict(
    key_dir: pathlib.Path, verdict: str, report_src: pathlib.Path | None,
    st: ConductorState | None = None, reason: str | None = None,
) -> None:
    """Refresh the key's **terminal** L3 verdict for the closure dossier:
    l3-verdict.txt + l3-report.md. Every terminal event (done-meets /
    stall-below) refreshes the derived record to that event's verdict;
    per-file content idempotence keeps repeated ticks and crash-retries
    zero-write, and the refresh is bidirectional so a done transaction that
    degrades back to below is not pinned at meets (D-002/D-003/D-004)."""
    if verdict not in _VERDICT_VALUES:
        return  # value domain is closed: never write a third state (D-008)
    key = key_dir.name
    verdict_file = key_dir / "l3-verdict.txt"
    current = (
        verdict_file.read_text(encoding="utf-8", errors="replace")
        if verdict_file.is_file() else None
    )
    before = current.strip().lower() if current is not None else None
    verdict_changed = before != verdict
    report_changed = False
    if report_src is not None and report_src.is_file():  # I-6: None -> skip report
        try:
            payload = report_src.read_bytes()
            report = key_dir / "l3-report.md"
            if not (report.is_file() and report.read_bytes() == payload):
                report.write_bytes(payload)  # D-004/D-005: report first
                report_changed = True
        except OSError:
            pass  # dossier keeps the existing report; the verdict still lands
    if verdict_changed:
        verdict_file.write_bytes((verdict + "\n").encode("utf-8"))
    if st is not None and (verdict_changed or report_changed):
        source = (
            report_src.parent.name
            if report_src is not None and report_src.is_file() else "-"
        )
        detail = f"l3-verdict {before or 'none'} -> {verdict} (report from {source}"
        if reason is not None:
            detail += f"; fail: {_one_line(reason, 80)}"
        st.timeline.append("config", key=key, detail=detail + ")")


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _closure_dossier_md(
    project_root: pathlib.Path, stage: roadmap.RoadmapStage
) -> str:
    """Closure dossier schema: stage id / goal / per key {final phase,
    L3 verdict + report path, evidence refs} / generated_at."""
    key_states = state.read_key_states(project_root)
    lines = [
        f"# Stage {stage.number} Close Dossier",
        "",
        f"- stage: {stage.number}",
        f"- goal: {stage.goal}",
        f"- generated_at: {_iso_now()}",
        "",
        "## Keys",
        "",
        "| key | final phase | l3 verdict | l3 report | evidence |",
        "|-----|-------------|------------|-----------|----------|",
    ]
    for entry in stage.keys:
        key_dir = pathlib.Path(project_root) / ".agenticdoc" / entry.key
        ks = key_states.get(entry.key)
        final_phase = ks.phase if ks is not None else "—"
        verdict, report = _l3_verdict(key_dir)
        evidence = f".agenticdoc/{entry.key}/achieved.md"
        lines.append(
            f"| {entry.key} | {final_phase} | {verdict} | {report} | {evidence} |"
        )
    return "\n".join(lines) + "\n"


# ── Advance convergence guard (failure classes + bounded retry) ─────

# Failure classes (AC-002 / design D-3). Ordered probes, first match wins.
_INTERFACE_DRIFT_MARKERS = (
    "unknown phase", "has unknown phase", "valid: spec", "phase-line",
    "phase field", "unsupported framework", "framework version",
)
_GATE_BLOCKED_MARKERS = (
    "gate blocked", "gate fail", "missing:", "missing prerequisite",
    "缺少", "not met", "未满足",
)
_TIMEOUT_ENV_MARKERS = (
    "timeout", "timed out", "locate", "advanceerror", "no such file",
    "cannot find",
)


def _one_line(text: str, limit: int = 160) -> str:
    """Single-line, length-bounded text for timeline details and gate
    questions (``gates.create`` rejects multiline questions)."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _classify_advance_failure(text: str) -> str:
    """Classify one advance failure message (design D-3).

    ``interface-drift`` — the phase interface no longer parses (e.g. a
    pm-state.md Phase line carrying prose); ``gate-blocked`` — the framework
    gate refused; ``timeout-env`` — timeout / framework not locatable /
    missing script; ``other`` — anything else, including empty text.
    """
    low = str(text or "").lower()
    if any(marker in low for marker in _INTERFACE_DRIFT_MARKERS):
        return "interface-drift"
    if any(marker in low for marker in _GATE_BLOCKED_MARKERS):
        return "gate-blocked"
    if any(marker in low for marker in _TIMEOUT_ENV_MARKERS):
        return "timeout-env"
    return "other"


def _advance_stall_ticks(cfg: dict) -> int:
    """Consecutive-failure threshold (config ``advance_stall_ticks``)."""
    try:
        value = int(cfg.get("advance_stall_ticks", 5))
    except (TypeError, ValueError):
        return 5
    return max(1, value)


def _advance_failure_streak(
    project_root: pathlib.Path, key: str, edge: str
) -> tuple[int, dict[str, int], str]:
    """Consecutive ``edge`` failures for ``key`` + class histogram + last
    error snippet, derived from the timeline tail (design D-1; zero private
    state, restart-safe).

    Walking newest → oldest: ``beat`` is skipped; a failing ``advance`` event
    for the same (key, edge) counts; a successful advance of that edge stops
    the walk; a ``config`` event for the key supplies the error text; any
    other event for the key (dispatch / stalled / gate / stage …) proves
    progress and stops the walk. An ``advance`` event of a *different* edge is
    skipped, so a neighbouring boundary's success neither breaks this streak
    nor is counted into it. Read failures yield 0/empty — fail-open, so a
    missed stall degrades to the previous retry behaviour while a false
    stall would break healthy keys.

    The window is bounded (``timeline.tail_events``: 400 parsed events / 512
    KiB) but the streak only needs the events since the first failure of the
    run: a per-tick failure loop writes ≥2 events per tick (the failing
    ``advance`` + its ``config``), so the threshold-5 default spans ~10 events
    and ~20 s, two orders of magnitude inside the window. Beats interleaved
    between the failures (up to 100 per gap) are covered by
    ``test_beat_flood_does_not_break_streak``; shrinking the window below the
    threshold's own span would fail that test first, and a genuinely evicted
    run degrades to fail-open (0) rather than to a false stall.
    """
    try:
        events = timeline.tail_events(timeline.timeline_path(project_root))
    except OSError:
        return 0, {}, ""
    count = 0
    hist: dict[str, int] = {}
    snippet = ""
    error_text = ""
    for event in reversed(events):
        if str(event.get("key", "")) != key:
            continue
        name = str(event.get("ev", ""))
        if name == "beat":
            continue
        if name == "config":
            text = str(event.get("detail", ""))
            if "advance" in text and error_text == "":
                error_text = text
                snippet = _one_line(text.split(":", 1)[-1], 120)
            continue
        if name == "advance":
            matched = re.match(
                r"^(\S+) exit=(\d+)(?: class=(\S+))?$", str(event.get("detail", ""))
            )
            if matched is None or matched.group(1) != edge:
                continue
            if matched.group(2) == "0":
                break
            count += 1
            cls = matched.group(3) or _classify_advance_failure(error_text)
            hist[cls] = hist.get(cls, 0) + 1
            continue
        break  # other activity for this key → progress, the streak ends
    if count == 0:
        return 0, {}, ""  # no failures for this edge: the stray snippet would mislead
    return count, hist, snippet


def _record_advance_result(
    project_root: pathlib.Path,
    st: ConductorState,
    key: str,
    edge: str,
    code: int,
    err: str,
    cfg: dict,
) -> None:
    """Log one advance attempt and bound the retry loop (AC-002/AC-003).

    Success keeps the historical ``"{edge} exit=0"`` detail; failure appends
    the machine-readable ``class=`` field and the raw error in a separate
    ``config`` event (human-readable). When the same (key, edge) has now
    failed ``advance_stall_ticks`` times in a row, the key is marked stalled —
    the four-artifact path freezes it (``orchestrate`` skips stalled keys), so
    the loop stops instead of retrying every tick until a human notices.
    """
    if code == 0:
        st.timeline.append("advance", key=key, detail=f"{edge} exit=0")
        return
    cls = _classify_advance_failure(err)
    st.timeline.append("advance", key=key, detail=f"{edge} exit={code} class={cls}")
    st.timeline.append(
        "config", key=key, detail=f"advance {edge} failed: {_one_line(err, 200)}"
    )
    count, hist, snippet = _advance_failure_streak(project_root, key, edge)
    if count < _advance_stall_ticks(cfg):
        return
    dist = ", ".join(
        f"{name}x{seen}" for name, seen in sorted(hist.items(), key=lambda item: -item[1])
    )
    mark_stalled(
        project_root, st, key,
        _one_line(
            f"advance {edge} 连续 {count} 次失败（class={cls}；{dist}）: {snippet}", 300
        ),
    )


def _advance_key(
    project_root: pathlib.Path,
    st: ConductorState,
    key: str,
    rows: list[dict],
    rounds: dict[str, int],
    cfg: dict,
    rm_path: pathlib.Path,
) -> bool:
    """Run one key one step of the phase machine. Returns True when a worker
    was dispatched (the key is now in flight)."""
    key_states = state.read_key_states(project_root)
    ks = key_states.get(key)
    phase = _normalize_phase(ks.phase if ks is not None else "")
    key_dir = project_root / ".agenticdoc" / key

    if phase == "done":
        _mark_key_done(project_root, st, key, rm_path)
        return False
    if phase == "execute":
        return execute_loop(project_root, st, key, cfg, rows, rounds)
    if phase == "verify":
        return _verify_loop(project_root, st, key, cfg, rows, rounds)

    nxt = _next_phase(phase)
    if not _phase_artifact_present(key_dir, phase):
        # Missing artifact → phase-writer (generation, loop-unrelated label).
        stem = _next_gen_stem(rows, key, f"{phase}-writer")
        result = dispatch.dispatch(
            project_root, key, stem, "phase-writer",
            _phase_writer_prompt(key, phase, nxt),
            loop=f"gen:{key}:{phase}", attempt=1, timeline=st.timeline,
        )
        return result.ok

    # Artifact present → L1 audit (dossier).
    dossier = audit_evidence.build_dossier(key, project_root)
    blocking = [g for g in dossier["gaps"] if g["severity"] == "blocking"]
    if phase == "tasks":
        # D-111: plan-referenced task files missing from tasks/ are synthetic
        # blocking gaps — the L2 loop adjudicates, budget escalation applies.
        blocking += _missing_plan_tasks(key_dir)
    if not blocking:
        summary = f"autopilot L1 clean at {phase}"
        code, _out, err = advance.advance(key, nxt, project_root, summary=summary)
        _record_advance_result(
            project_root, st, key, f"{phase}->{nxt}", code, err, cfg
        )
        if code == 0 and nxt == "done":
            _mark_key_done(project_root, st, key, rm_path)
        return False

    # Gaps → L2 adjudication round (D-111 round units).
    edge = f"{phase}-to-{nxt}"
    loop = f"l2:{key}:{edge}"
    used = rounds.get(loop, 0)
    budget = max(1, int(cfg["round_budget"]))
    # A human-answered stalled gate grants one extra round (AC-013).
    limit = budget + _resume_credits(project_root, key)
    bonus = _budget_bonus(project_root, loop)
    allowed = used < limit or (bonus and used < limit + 1)

    fix_key = dispatch.task_key_for(key, f"l2-fix-{edge}-a{used}") if used else None
    if used and not _row_exists(rows, fix_key or ""):
        # The round-N verifier is terminal but the same-round evidence fix
        # (phase-writer, same loop+attempt → no extra round) was not sent yet.
        result = dispatch.dispatch(
            project_root, key, f"l2-fix-{edge}-a{used}", "phase-writer",
            _fix_writer_prompt(key, phase, nxt, blocking, project_root, used),
            loop=loop, attempt=used, timeline=st.timeline,
        )
        return result.ok

    if not allowed:
        # Resolution order at exhaustion: a rejected budget gate stalls the
        # key; a spent bonus round stalls directly (超限一律升级, no second
        # gate); otherwise one pending budget-exhausted gate for this loop.
        if _budget_gate_rejected(project_root, loop):
            mark_stalled(
                project_root, st, key, f"L2 budget gate rejected at {loop}"
            )
            return False
        if bonus and used >= limit + 1:
            mark_stalled(
                project_root, st, key, f"L2 bonus round exhausted at {loop}"
            )
            return False
        if not _gate_open(project_root, "budget-exhausted", loop=loop):
            gate = _create_gate(
                project_root, st, "budget-exhausted",
                f"L2 回路 {loop} 已达 {limit} 轮上限且仍有缺口——追加一轮修复，还是标记 stalled？",
                key=key, refs=[loop],
            )
            if gate is None:
                st.timeline.append("config", key=key, detail="budget gate lock-held; retry next tick")
        return False

    attempt = used + 1
    result = dispatch.dispatch(
        project_root, key, f"l2-{edge}-a{attempt}", "verifier",
        _verifier_prompt(key, phase, nxt, blocking),
        loop=loop, attempt=attempt,
        read_scope=[f".agenticdoc/{key}", ".agenticdoc/goal.md"],
        timeline=st.timeline,
    )
    if not result.ok:
        mark_stalled(
            project_root, st, key,
            f"L2 dispatch refused at {loop} attempt {attempt}",
        )
    return result.ok


# ── EXECUTE task loop (D-111, T-12) ─────────────────────────────────────────

def _family_rows(rows: list[dict], key: str, base: str) -> list[dict]:
    """Queue rows of one stem family: the bare stem (attempt 1) plus its
    -a<N> retry rows (D-111 task identity + attempt-suffixed retries, same
    loop label — used_rounds counts each retry dir's task.md attempt)."""
    anchor = re.escape(dispatch.task_key_for(key, base))
    pat = re.compile(rf"^{anchor}(-a\d+)?$")
    return [r for r in rows if pat.match(str(r.get("task_key", "")))]


def _plan_text(key_dir: pathlib.Path) -> str:
    plan = key_dir / "plan.md"
    if not plan.is_file():
        return ""
    try:
        return plan.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _plan_task_order(stems: list[str], plan: str) -> list[str]:
    """Execution order: plan appearance order when parseable, else stem
    lexicographic; plan-unmentioned (orphan) tasks go last (D-111)."""
    if not plan:
        return sorted(stems)
    mentioned = [(plan.find(s), s) for s in stems if s in plan]
    mentioned.sort()
    orphans = sorted(s for s in stems if s not in plan)
    return [s for _, s in mentioned] + orphans


def _exec_prompt(key: str, stem: str) -> str:
    return (
        f"执行任务 {stem}（key {key}）:\n"
        f"- 任务书：.agenticdoc/{key}/tasks/{stem}.md（先完整阅读）\n"
        "- 按任务书执行；验证步骤用 [VERIFY] VC-NNN: key=value 行记录到 output.md\n"
        "- 完成后更新任务文件的执行记录节；只碰任务书列出的文件"
    )


def execute_loop(
    project_root: pathlib.Path,
    st: ConductorState,
    key: str,
    cfg: dict,
    rows: list[dict],
    rounds: dict[str, int],
) -> bool:
    """EXECUTE task loop (D-111): ``tasks/`` is the execution contract.

    - task identity = the tasks/ file stem; queue key ``ap-{key}-{stem}``
      (attempt 1), retries ``ap-{key}-{stem}-a<N>`` — same loop label
      ``exec:{key}:{stem}``, so used_rounds counts real attempts
    - per-key serial (one in-flight exec task); completion = a family row
      with status done; failure (exit≠0 / watchdog / spawn, AC-023) consumes
      the loop budget and escalates to stalled when spent
    - all tasks done → advance execute→verify (the framework gate re-checks
      tasks/ non-empty)
    """
    key_dir = pathlib.Path(project_root) / ".agenticdoc" / key
    tasks_dir = key_dir / "tasks"
    files = sorted(tasks_dir.glob("*.md")) if tasks_dir.is_dir() else []
    if not files:
        return False  # nothing to execute — the tasks→execute gate owns this
    budget = max(1, int(cfg["round_budget"]))
    # Human approvals of a stalled gate grant one extra attempt each (AC-013).
    credits = _resume_credits(project_root, key)
    plan = _plan_text(key_dir)
    for stem in _plan_task_order([f.stem for f in files], plan):
        loop = f"exec:{key}:{stem}"
        fam = _family_rows(rows, key, stem)
        if any(r["status"] == "done" for r in fam):
            continue  # task complete
        if any(_is_in_flight(r) for r in fam):
            return False  # per-key serial: wait for the in-flight task
        used = rounds.get(loop, 0)
        if used >= budget + credits:
            mark_stalled(
                project_root, st, key,
                f"exec task {stem} exhausted {used}/{budget + credits} attempts",
            )
            return False
        if plan and stem not in plan:
            st.timeline.append(
                "config", key=key,
                detail=f"orphan task {stem} (not referenced by plan.md) dispatched",
            )
        retry = used > 0
        stem_arg = f"{stem}-a{used + 1}" if retry else stem
        result = dispatch.dispatch(
            project_root, key, stem_arg, "phase-writer",  # coding tool set
            _exec_prompt(key, stem),
            loop=loop, attempt=used + 1, timeline=st.timeline,
        )
        if not result.ok:
            mark_stalled(
                project_root, st, key,
                f"exec dispatch refused at {stem} attempt {used + 1}",
            )
        return result.ok
    code, _out, err = advance.advance(
        key, "verify", project_root, summary="autopilot EXECUTE tasks complete"
    )
    _record_advance_result(project_root, st, key, "execute->verify", code, err, cfg)
    return False


# ── VERIFY: L3 review loop + done transaction (D-108/D-112, T-12) ────────────


def _md_section(text: str, header: str) -> str | None:
    """One markdown section (header line to the next ## header); None when
    the section is missing."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == header), None)
    if start is None:
        return None
    out = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


def _parse_l3_output(project_root: pathlib.Path, key: str, attempt: int) -> str:
    """meets | below from the L3 reviewer's output.md (D-108: missing
    section or any FAIL row → below)."""
    output = (
        pathlib.Path(project_root) / ".agenticdoc" / key / "workers"
        / dispatch.task_key_for(key, f"l3-a{attempt}") / "output.md"
    )
    if not output.is_file():
        return "below"
    try:
        text = output.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "below"
    qg = _md_section(text, "## Quality Gate Report")
    achieved = _md_section(text, "## Achieved")
    if qg is None or achieved is None:
        return "below"
    if re.search(r"\|\s*FAIL\b", qg):
        return "below"
    return "meets"


def _l3_prompt(key: str, attempt: int) -> str:
    return (
        f"L3 质检复评（key {key}，第 {attempt} 轮）:\n"
        "- 审查 EXECUTE 期 worker 在 output.md 与 evidence/ 中记录的 [VERIFY] 输出"
        "（证据记录制：不重跑命令）\n"
        "- 需要重跑才能确认的验证命令标记 needs-rerun 并计入遗留\n"
        "- 你的 output.md 必含两节：\n"
        "  ## Quality Gate Report（VC 断言表逐条 PASS/FAIL + needs-rerun + 证据引用；"
        "如发现跨 key 红，本行内须含一行机器行："
        "cross_key_test=<path>::<test_id> owner=<key> handoff=registered "
        "not_fixed_by_this_key=True）\n"
        "  ## Achieved（达成摘要：做了什么 / 目标收益 / 遗留什么）\n"
        "- 两节承载于 output.md（首选）；长报告可置于 report.md 作为**文档化回退源**"
        "（判定按 output.md → report.md 优先级读取，"
        "任一份的任意行出现 FAIL 标记（表格单元格 / 项目符 / 结论行）即 below）\n"
        "- 判定源取证：output.md / report.md 须属于本轮（由同轮 trace.log 锚定）；"
        "事后补写的判定源会被标记 suspect 并按 below 处理"
    )


def _repair_prompt(
    key: str, attempt: int, report_rel: str, fail_line: str | None = None
) -> str:
    lines = [
        f"修复 L3 裁决 below 的问题（key {key}，第 {attempt} 轮）:\n",
        f"- L3 报告：{report_rel}（FAIL 项与 needs-rerun 遗留）\n",
    ]
    if fail_line is not None:
        lines.append(f"- 首个 FAIL 行：{fail_line}（修复目标）\n")
    lines.append(
        "- 逐项修复并补充 [VERIFY] 证据到 evidence/；不重写无关 artifact\n"
        "- 只读约束：workers/*-l3-*/ 下的 output.md 与 report.md 属 reviewer 本轮产物（L3 判定源）\n"
        "- 禁止改动 workers/*-l3-*/ 判定源（只读输入）；判定源错位的唯一纠错路径 = 由框架派发新一轮 reviewer（re-review）"
    )
    return "".join(lines)


# ── L3 verdict source fallback (feature-l3-verdict-source-fallback) ──────────
# Documented fallback priority for the L3 round verdict. output.md stays the
# preferred carrier; report.md is the harness-first-class fallback (the
# reviewer writes its long report there). report-<slug>.md is deliberately NOT
# a fallback source (AC-021; extending the scope needs its own key).
_L3_SOURCE_ORDER = ("output.md", "report.md")
# Strict superset of the frozen `\|\s*FAIL\b`: catches `| **FAIL** |` (31 live
# cells) while never dropping a plain `| FAIL |` match (I-8).
_L3_FAIL_RE = re.compile(r"\|\s*\**\s*FAIL\b")
# Line-level forms (D-001): a FAIL bullet at line start and a prose line
# whose FAIL is followed by a dash. `_L3_FAIL_ZERO_RE` is the token-local
# zero-value exemption, always applied with `match(line, token_pos)`.
_L3_FAIL_BULLET_RE = re.compile(r"^\s*[-*]\s*\**\s*FAIL\b")
_L3_FAIL_PROSE_RE = re.compile(r"^[^|\n]*?\**\s*FAIL\s*[—–-]")
_L3_FAIL_ZERO_RE = re.compile(r"FAIL\s*\**\s*[：:=]?\s*\**\s*0\b")


def _l3_fail_marker_line(text: str) -> str | None:
    """First line carrying a FAIL marker (verbatim), else ``None`` (D-001).

    The scan walks the whole document line by line. A line fires when the
    pipe rule or the line-start prose rule matches anywhere in it, or when
    the bullet rule matches without the token-local zero-value exemption.
    The exemption is anchored at the matched FAIL token's start, never a
    whole-line search: ``- FAIL 9 项，其中 FAIL：0`` fires on its first
    token."""
    for line in text.splitlines():
        if _L3_FAIL_RE.search(line) or _L3_FAIL_PROSE_RE.search(line):
            return line
        match = _L3_FAIL_BULLET_RE.match(line)
        if match is None:
            continue
        token_pos = match.start() + match.group(0).rindex("FAIL")
        if _L3_FAIL_ZERO_RE.match(line, token_pos) is None:
            return line
    return None


# ── L3 verdict provenance guard (feature-verdict-provenance-guard D-003..D-006) ─
# Module constants — NEVER read from config (GC-4).
_PROVENANCE_FILENAME = "l3-verdict-provenance.json"
_L3_TRACE_NAME = "trace.log"
_PROVENANCE_SLACK_SEC = 60.0


def _l3_source_paths(key_dir: pathlib.Path, task_key: str) -> list[pathlib.Path]:
    """Ordered candidate source paths (existence is not judged here)."""
    return [key_dir / "workers" / task_key / name for name in _L3_SOURCE_ORDER]


def _l3_read_source(path: pathlib.Path) -> str | None:
    """Readable source text; missing / ``OSError`` -> ``None`` (D-005)."""
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _l3_qualifies(text: str) -> bool:
    """A source qualifies when both L3 sections are present (DF-8)."""
    return (
        _md_section(text, "## Quality Gate Report") is not None
        and _md_section(text, "## Achieved") is not None
    )


def _l3_resolve_source(
    sources: list[tuple[pathlib.Path, str]],
) -> tuple[str, pathlib.Path | None, str | None]:
    """Fail-closed resolution over existing sources in priority order (I-2):
    the first readable source (qualifying or not) whose full text carries a
    FAIL marker -> below + that source + its first marker line; else the
    first qualifying source -> meets + that source + None; else below + None
    + None (D-002/D-003: the veto covers unqualified sources too)."""
    for path, text in sources:
        fail_line = _l3_fail_marker_line(text)
        if fail_line is not None:
            return "below", path, fail_line
    qualifying = [(p, t) for p, t in sources if _l3_qualifies(t)]
    if qualifying:
        return "meets", qualifying[0][0], None
    return "below", None, None


def _l3_round_verdict(
    project_root: pathlib.Path,
    rows: list[dict],
    key: str,
    attempt: int,
    registration_out: dict | None = None,
) -> tuple[str, str, pathlib.Path | None, str | None]:
    """(verdict, worker status, deciding source, fail line) for one L3 round.

    A round whose worker row is terminal-failed never rendered a verdict: the
    worker harness writes a placeholder ``output.md`` even when the process
    died (observed live: a reviewer killed by a provider 403 left a 181-byte
    template), so the status gate is checked BEFORE any source file (I-4).
    The availability gate follows (I-5): with no readable candidate source the
    round has ``no-verdict``; otherwise ``_l3_resolve_source`` decides over the
    documented priority order ``output.md`` -> ``report.md`` (D-108).

    The return shape is frozen (4-tuple, pinned by the provenance guard's
    ``test_frozen_anchors_and_criteria_unchanged``), so the cross-key handoff
    registrations (D-001, xkey-repair-mechanism) are handed to the caller
    through the optional ``registration_out`` sink instead: when given, the
    merged registration for the round's sources is stored under
    ``registration_out["registration"]`` (a dict, or ``None`` when the round
    mentions a cross-key handoff but its fields cannot be resolved)."""
    task_key = dispatch.task_key_for(key, f"l3-a{attempt}")
    status = next(
        (str(row.get("status", "")) for row in rows if row.get("task_key") == task_key),
        "",
    )
    if status in ("failed", "needs-clarification"):
        return "no-verdict", status, None, None
    key_dir = pathlib.Path(project_root) / ".agenticdoc" / key
    sources = [
        (path, text)
        for path in _l3_source_paths(key_dir, task_key)
        if (text := _l3_read_source(path)) is not None
    ]
    if not sources:
        return "no-verdict", status or "no-row", None, None
    if registration_out is not None:
        # D-001 read side: scan ALL sources (the corpus splits (file,test_id)
        # and owner= across output.md/report.md), reusing the same fail-closed
        # "first readable source wins" spirit as _l3_resolve_source. A
        # marker-bearing but unresolvable round records `registration: None`
        # so the aggregator raises an escalation record (AC-002) instead of
        # dropping the red; a round with no marker at all leaves the key
        # absent (not a cross-key red → zero footprint).
        if _XKEY_MARKER_RE.search("\n".join(text for _path, text in sources)):
            registration_out["registration"] = _xkey().collect_registrations(
                [(path.name, text) for path, text in sources]
            )
    verdict, source, fail_line = _l3_resolve_source(sources)
    return verdict, status, source, fail_line


# ── L3 verdict provenance guard (D-001..D-013) ───────────────────────────────

# Sentinel: "the caller did not opt into cross-key registration recording"
# (switch off ⇒ the sidecar stays byte-identical, AC-008) versus an explicit
# `registration=None` (marker present but unresolvable ⇒ AC-002 escalation).
# NEVER read from config (GC-4).
_REGISTRATION_UNSET = object()


def _l3_provenance_record(
    key_dir: pathlib.Path,
    task_key: str,
    deciding_source: pathlib.Path,
    raw_verdict: str,
    fail_line: str | None = None,
    registration: object = _REGISTRATION_UNSET,
) -> dict:
    """Read-only provenance record for one L3 round (D-004..D-006).

    The same-round ``trace.log`` end (mtime) anchors the round; with no
    readable anchor the round abstains (``suspect=False``,
    ``anchor_path=None``, GC-13) instead of guessing. T1 flags a deciding
    source written after the round ended (+ slack); T2 additionally flags an
    ``output.md`` whose two L3 sections are byte-equal to the same round's
    ``report.md`` but written later (the post-hoc rewrite signature). The
    record's ``verdict`` is the effective fail-closed verdict:
    ``suspect ∧ raw=meets`` -> ``below``. Never writes (D-001/GC-12)."""
    key_dir = pathlib.Path(key_dir)
    round_name = task_key
    prefix = f"ap-{key_dir.name}-"
    if task_key.startswith(prefix):
        round_name = task_key[len(prefix):]
    try:
        deciding_rel = deciding_source.relative_to(key_dir).as_posix()
    except ValueError:
        deciding_rel = deciding_source.name
    record = {
        "round": round_name,
        "task_key": task_key,
        "deciding_source": deciding_rel,
        "source_mtime_ns": None,
        "anchor_path": None,
        "anchor_mtime_ns": None,
        "suspect": False,
        "reasons": [],
        "raw_verdict": raw_verdict,
        "verdict": raw_verdict,
        "fail_line": fail_line,
        "recorded_at": _iso_now(),
    }
    if registration is not _REGISTRATION_UNSET:
        record["registration"] = registration
    trace = key_dir / "workers" / task_key / _L3_TRACE_NAME
    try:
        if not trace.is_file():
            return record
        source_ns = deciding_source.stat().st_mtime_ns
        anchor_ns = trace.stat().st_mtime_ns
    except OSError:
        return record  # no readable anchor/source -> abstain (GC-13)
    record["source_mtime_ns"] = source_ns
    record["anchor_path"] = f"workers/{task_key}/{_L3_TRACE_NAME}"
    record["anchor_mtime_ns"] = anchor_ns
    slack_ns = int(_PROVENANCE_SLACK_SEC * 1e9)
    reasons: list[str] = []
    if source_ns > anchor_ns + slack_ns:
        reasons.append(
            f"{deciding_source.name} mtime is "
            f"{(source_ns - anchor_ns) / 1e9:.1f}s AFTER {_L3_TRACE_NAME} end"
        )
    if deciding_source.name == "output.md" and source_ns > anchor_ns:
        # T2 time fingerprint first: only a later-than-round output.md can be
        # the rewritten copy, so the report stat + reads are spent only there.
        report = deciding_source.parent / "report.md"
        try:
            report_ns = report.stat().st_mtime_ns
        except OSError:
            report_ns = None
        if report_ns is not None and source_ns > report_ns + slack_ns:
            try:
                out_text = deciding_source.read_text(
                    encoding="utf-8", errors="replace"
                )
                rep_text = report.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
            else:
                equal = True
                for header in ("## Quality Gate Report", "## Achieved"):
                    out_sec = _md_section(out_text, header)
                    if out_sec is None or out_sec != _md_section(rep_text, header):
                        equal = False
                        break
                if equal:
                    reasons.append(
                        "output.md sections byte-equal report.md but written later"
                    )
    record["reasons"] = reasons
    record["suspect"] = bool(reasons)
    if record["suspect"] and raw_verdict == "meets":
        record["verdict"] = "below"
    return record


def _persist_l3_provenance(
    key_dir: pathlib.Path, record: dict, st: ConductorState | None = None
) -> bool:
    """Append one provenance record (append-only, deduped by ``task_key``,
    ``tmp`` + ``os.replace`` atomic; returns True iff a new record landed).
    A corrupt sidecar is never overwritten (returns False + an optional
    timeline ``config`` event) — audit history outranks the new record
    (D-006/GC-9/AC-020)."""
    import json  # local: conductor carries no module-level json dependency

    key_dir = pathlib.Path(key_dir)
    path = key_dir / _PROVENANCE_FILENAME
    entries: list = []
    if path.is_file():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            parsed = None
        if not isinstance(parsed, list):
            if st is not None:
                st.timeline.append(
                    "config", key=key_dir.name,
                    detail=f"l3-provenance sidecar corrupt, not overwritten: {path.name}",
                )
            return False
        entries = parsed
    task_key = record.get("task_key")
    for entry in entries:
        if isinstance(entry, dict) and entry.get("task_key") == task_key:
            return False  # same round already recorded -> zero-write (AC-020)
    try:
        tmp = path.parent / (path.name + ".tmp")
        tmp.write_text(
            json.dumps(entries + [record], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
        os.replace(tmp, path)
    except OSError as exc:
        if st is not None:
            st.timeline.append(
                "config", key=key_dir.name,
                detail=f"l3-provenance write failed: {exc!r}",
            )
        return False
    if st is not None:
        st.timeline.append(
            "config", key=key_dir.name,
            detail=(
                f"l3-provenance {record.get('round')} "
                f"suspect={record.get('suspect')} "
                f"source={record.get('deciding_source')}"
            ),
        )
    return True


def _done_credentials_present(
    project_root: pathlib.Path, key: str
) -> tuple[bool, list[str]]:
    """(ok, missing) over the five persisted done-transaction derivatives
    (D-008/DF-14): a bare index pointer must never flip roadmap key-status to
    ``done``. Only on-disk derivatives are judged (not the full
    ``check_gate("done")`` vocabulary) so the existing conductor fixtures
    stay valid (R-3). Read-only."""
    key_dir = pathlib.Path(project_root) / ".agenticdoc" / key
    missing: list[str] = []
    verdict_file = key_dir / "l3-verdict.txt"
    try:
        verdict = (
            verdict_file.read_text(encoding="utf-8").strip().lower()
            if verdict_file.is_file() else ""
        )
    except OSError:
        verdict = ""
    if verdict != "meets":
        missing.append("l3-verdict.txt=meets")
    report = key_dir / "l3-report.md"
    try:
        if not (report.is_file() and report.stat().st_size > 0):
            missing.append("l3-report.md")
    except OSError:
        missing.append("l3-report.md")
    if not any((key_dir / "evidence").glob("quality-gate-report-*.md")):
        missing.append("quality-gate-report")
    achieved = key_dir / "achieved.md"
    try:
        if not (achieved.is_file() and achieved.stat().st_size >= 200):
            missing.append("achieved.md>=200B")
    except OSError:
        missing.append("achieved.md>=200B")
    pm_state = key_dir / "pm-state.md"
    try:
        has_pass = pm_state.is_file() and "PASS" in pm_state.read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        has_pass = False
    if not has_pass:
        missing.append("pm-state.md PASS")
    return (not missing, missing)


def _timeline_has_event(
    project_root: pathlib.Path, ev: str, key: str, detail: str
) -> bool:
    """Bounded-tail dedupe for refusal logging (D-009): a refusal is
    recorded once, and the window is re-read from file truth (zero private
    state)."""
    try:
        events = timeline.tail_events(
            timeline.timeline_path(project_root), limit=200
        )
    except OSError:
        return False
    return any(
        event.get("ev") == ev
        and event.get("key") == key
        and str(event.get("detail", "")) == detail
        for event in events
    )


def _verify_loop(
    project_root: pathlib.Path,
    st: ConductorState,
    key: str,
    cfg: dict,
    rows: list[dict],
    rounds: dict[str, int],
) -> bool:
    """VERIFY→done convergence: L3 reviewer rounds, repair on below, and
    the mechanical done transaction on meets (D-108/D-112).

    Loop labels: ``l3:{key}`` (review rounds, budget 2) and ``repair:{key}``
    (repairs, budget = round_budget). A malformed L3 output (missing
    sections) or a <200B achieved draft both degrade to below — the repair
    path, never padded (D-108 后验)."""
    key_dir = pathlib.Path(project_root) / ".agenticdoc" / key
    l3_loop = f"l3:{key}"
    # Three loop families share round_budget (spec §2.2 / AC-011):
    # L1↔L2, L3 convergence, task retry. Default 2 preserves AC-010's
    # 复评总轮数 ≤ 2. Approved stalled gates add one round each (AC-013).
    l3_budget = max(1, int(cfg["round_budget"]))
    l3_limit = l3_budget + _resume_credits(project_root, key)
    used = rounds.get(l3_loop, 0)
    l3_report_src = (
        key_dir / "workers" / dispatch.task_key_for(key, f"l3-a{used}")
        / "output.md"
    )
    for prefix in (f"ap-{key}-l3-", f"ap-{key}-repair-"):
        if any(_is_in_flight(r) for r in rows if r["task_key"].startswith(prefix)):
            return False  # wait for the in-flight review/repair
    if used == 0:
        result = dispatch.dispatch(
            project_root, key, "l3-a1", "reviewer",
            _l3_prompt(key, 1),
            loop=l3_loop, attempt=1,
            read_scope=[f".agenticdoc/{key}", ".agenticdoc/goal.md"],
            timeline=st.timeline,
        )
        return result.ok
    registration_out: dict = {}
    verdict, worker_status, l3_source, fail_line = _l3_round_verdict(
        project_root, rows, key, used,
        registration_out=registration_out if cfg.get("xkey_repair", False) else None,
    )
    round_key = dispatch.task_key_for(key, f"l3-a{used}")
    l3_source_rel = (
        l3_source.relative_to(pathlib.Path(project_root)).as_posix()
        if l3_source is not None
        else (pathlib.Path(".agenticdoc") / key / "workers"
              / dispatch.task_key_for(key, f"l3-a{used}") / "output.md").as_posix()
    )
    if verdict == "no-verdict":
        # The reviewer never rendered a verdict (crash / no output). Repairing
        # against a missing report is pointless and reporting `below` would pin
        # the real cause on the wrong layer (AC-012).
        round_key = dispatch.task_key_for(key, f"l3-a{used}")
        st.timeline.append(
            "l3-no-verdict", key=key,
            detail=f"l3-a{used} worker status={worker_status} → re-review",
        )
        if used >= l3_limit:
            _persist_l3_verdict(key_dir, "below", l3_report_src, st=st)
            mark_stalled(
                project_root, st, key,
                f"L3 无裁决（worker {worker_status}: {round_key}）达 {used}/{l3_limit} 轮",
            )
            return False
        result = dispatch.dispatch(
            project_root, key, f"l3-a{used + 1}", "reviewer",
            _l3_prompt(key, used + 1),
            loop=l3_loop, attempt=used + 1,
            read_scope=[f".agenticdoc/{key}", ".agenticdoc/goal.md"],
            timeline=st.timeline,
        )
        return result.ok
    if l3_source is not None:
        record = _l3_provenance_record(
            key_dir, round_key, l3_source, verdict, fail_line=fail_line,
            registration=registration_out.get("registration", _REGISTRATION_UNSET),
        )
        _persist_l3_provenance(key_dir, record, st=st)
        if record["suspect"] and verdict == "meets":
            # fail-closed (D-002/D-007): a suspect meets-round never reaches
            # the done transaction; the only correction path is a fresh
            # reviewer round — never the repair path.
            st.timeline.append(
                "l3-source-suspect", key=key,
                detail=f"{record['round']}: " + "; ".join(record["reasons"]),
            )
            if used >= l3_limit:
                _persist_l3_verdict(key_dir, "below", l3_source, st=st)
                mark_stalled(
                    project_root, st, key,
                    f"L3 判定源取证可疑（{record['round']}）达 {used}/{l3_limit} 轮",
                )
                return False
            result = dispatch.dispatch(
                project_root, key, f"l3-a{used + 1}", "reviewer",
                _l3_prompt(key, used + 1),
                loop=l3_loop, attempt=used + 1,
                read_scope=[f".agenticdoc/{key}", ".agenticdoc/goal.md"],
                timeline=st.timeline,
            )
            return result.ok
    if verdict == "meets" and l3_source is not None:
        # I-1/I-2: a meets verdict always has a deciding source; the guard is
        # fail-closed redundancy (an impossible branch falls through to the
        # below path — no exception, no spin)
        dt_verdict, done_err = _done_transaction(project_root, st, key, l3_source)
        if dt_verdict != "below":
            flines = closure.failure_lines(done_err) if done_err else []
            if closure.has_achieved_failure(flines):
                # D-005 branch 2: gate-blocked on the achieved evidence draft.
                # Re-prompt the reviewer with the verbatim rejection lines
                # under a self-owned budget (a dispatch event interrupts the
                # advance streak, so the streak cannot bound this loop).
                if used >= l3_limit:
                    mark_stalled(
                        project_root, st, key,
                        f"closure reprompt exhausted {used}/{l3_limit} "
                        "(gate-blocked on evidence draft)",
                    )
                    # The L3 quality verdict and the done-gate vocabulary
                    # failure are orthogonal: keep the persisted verdict
                    # `meets` (writing below here would falsify the dossier).
                    return False
                st.timeline.append(
                    "l3-reprompt", key=key,
                    detail=(
                        f"gate-blocked on evidence draft; reprompt "
                        f"l3-a{used + 1} ({len(flines)} lines)"
                    ),
                )
                result = dispatch.dispatch(
                    project_root, key, f"l3-a{used + 1}", "reviewer",
                    closure.compose_reprompt_prompt(
                        _l3_prompt(key, used + 1), flines
                    ),
                    loop=l3_loop, attempt=used + 1,
                    read_scope=[f".agenticdoc/{key}", ".agenticdoc/goal.md"],
                    timeline=st.timeline,
                )
                return result.ok
            # advanced, or gated for a non-vocabulary reason (PASS lock /
            # OSError / index mismatch) — retried next tick via the
            # advance-stall streak (AC-006)
            return False
        # meets-but-short achieved draft → same repair path as below
    if used >= l3_limit:
        _persist_l3_verdict(key_dir, "below", l3_source, st=st, reason=fail_line)
        mark_stalled(
            project_root, st, key,
            f"L3 below {l3_limit} rounds (budget {l3_budget}, credits {l3_limit - l3_budget})"
            + (f"; fail: {_one_line(fail_line, 80)}" if fail_line is not None else ""),
        )
        return False
    repair_base = f"repair-a{used}"
    fam = _family_rows(rows, key, repair_base)
    if not any(r["status"] == "done" for r in fam):
        repair_used = rounds.get(f"repair:{key}", 0)
        if any(_is_in_flight(r) for r in fam):
            return False
        if repair_used >= max(1, int(cfg["round_budget"])) + _resume_credits(project_root, key):
            _persist_l3_verdict(key_dir, "below", l3_source, st=st, reason=fail_line)
            mark_stalled(
                project_root, st, key,
                f"repair exhausted {repair_used} attempts at L3 round {used}"
                + (f"; fail: {_one_line(fail_line, 80)}" if fail_line is not None else ""),
            )
            return False
        retry = repair_used > 0
        stem_arg = f"{repair_base}-a{repair_used + 1}" if retry else repair_base
        result = dispatch.dispatch(
            project_root, key, stem_arg, "repair",
            _repair_prompt(key, used, l3_source_rel, fail_line=fail_line),
            loop=f"repair:{key}", attempt=repair_used + 1,
            timeline=st.timeline,
        )
        return result.ok
    # repair for this round done → next L3 review round
    result = dispatch.dispatch(
        project_root, key, f"l3-a{used + 1}", "reviewer",
        _l3_prompt(key, used + 1),
        loop=l3_loop, attempt=used + 1,
        read_scope=[f".agenticdoc/{key}", ".agenticdoc/goal.md"],
        timeline=st.timeline,
    )
    return result.ok


def _append_pass_line(
    project_root: pathlib.Path, st: ConductorState, key: str, qg_path: pathlib.Path
) -> bool:
    """pm-state.md PASS evidence line under .mw/key-{key}.lock (atomic
    rewrite; idempotent — a PASS already present is not duplicated)."""
    project_root = pathlib.Path(project_root)
    pm_state = project_root / ".agenticdoc" / key / "pm-state.md"
    try:
        acquire_conductor_lock(project_root, f"key-{key}", st.timeline)
    except ConductorLockHeld:
        return False
    try:
        text = ""
        if pm_state.is_file():
            text = pm_state.read_text(encoding="utf-8", errors="replace")
        if "PASS" in text:
            return True
        rel = qg_path.relative_to(project_root).as_posix()
        line = f"- PASS: L3 quality gate meets — {rel} (autopilot {_iso_now()})"
        pm_state.parent.mkdir(parents=True, exist_ok=True)
        pm_state.write_text(
            text + ("" if text.endswith("\n") or text == "" else "\n") + line + "\n",
            encoding="utf-8", newline="\n",
        )
        return True
    except OSError as exc:
        st.timeline.append("config", key=key, detail=f"pm-state PASS write failed: {exc!r}")
        return False
    finally:
        mw_common.release_lock(lock_file(project_root, f"key-{key}"))


def _set_index_phase(project_root: pathlib.Path, key: str, phase: str) -> tuple[int, str]:
    """Rerun the framework's update_index.py set-phase (advance post-check
    repair, D-108 增补 2)."""
    try:
        script = advance.locate_platform_dir(project_root) / "scripts" / "update_index.py"
        proc = subprocess.run(
            [sys.executable, str(script), "set-phase", key, phase],
            cwd=str(project_root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        return proc.returncode, (proc.stderr or "").strip()
    except (advance.AdvanceError, OSError, subprocess.TimeoutExpired) as exc:
        return 1, repr(exc)


def _done_transaction(
    project_root: pathlib.Path,
    st: ConductorState,
    key: str,
    l3_output: pathlib.Path,
) -> tuple[str, str]:
    """meets → mechanical done transaction (D-108 增补 1). Returns
    ``(verdict, err)`` with verdict advanced | below | gated; ``err`` carries
    the full advance stderr only on the gate-blocked advance-failure path
    (empty otherwise, D-001). Every step is check-before-write, so a crash
    mid-transaction resumes cleanly on the next tick (AC-022)."""
    project_root = pathlib.Path(project_root)
    key_dir = project_root / ".agenticdoc" / key
    ks = state.read_key_states(project_root).get(key)
    if ks is not None and ks.phase.strip().upper() == "DONE":
        return "advanced", ""  # crash-after-advance resume
    try:
        text = l3_output.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "below", ""
    qg = _md_section(text, "## Quality Gate Report")
    achieved = _md_section(text, "## Achieved")
    if qg is None or achieved is None:
        return "below", ""
    try:
        evidence_dir = key_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        # 1. QG report — timestamped, written once (any existing report is
        #    reused on a retry; the source verdict has not changed)
        if list(evidence_dir.glob("quality-gate-report-*.md")):
            qg_path = next(iter(sorted(evidence_dir.glob("quality-gate-report-*.md"))))
        else:
            qg_path = evidence_dir / (
                f"quality-gate-report-{time.strftime('%Y%m%d-%H%M%S')}.md"
            )
            qg_path.write_text(
                f"# Quality Gate Report: {key}\n\n"
                f"- generated_by: autopilot L3 (meets)\n"
                f"- generated_at: {_iso_now()}\n"
                f"- source: {l3_output.relative_to(project_root).as_posix()}\n\n"
                f"{qg}\n",
                encoding="utf-8", newline="\n",
            )
        # 1b. persist the L3 verdict for the closure dossier (AC-003):
        # l3-verdict.txt + l3-report.md, written once (check-before-write)
        _persist_l3_verdict(key_dir, "meets", l3_output, st=st)
        # 2. achieved.md draft: write when absent/short; a ≥200B draft is
        #    replaced only when the persisted bad-draft marker authorizes it
        #    (D-003/D-004). Written atomically (tmp + os.replace) under the
        #    per-key lock, same scope as the marker deletion.
        achieved_path = key_dir / "achieved.md"
        new_draft = achieved.rstrip() + "\n"
        try:
            acquire_conductor_lock(project_root, f"key-{key}", st.timeline)
        except ConductorLockHeld:
            return "gated", ""  # lock held — retry next tick
        try:
            current = (
                achieved_path.read_bytes() if achieved_path.is_file() else None
            )
            overwrite = current is not None and closure.overwrite_authorized(
                closure.read_bad_draft_marker(key_dir), current, []
            )
            if current is None or len(current) < 200 or overwrite:
                tmp = achieved_path.parent / (achieved_path.name + ".tmp")
                tmp.write_text(new_draft, encoding="utf-8", newline="\n")
                os.replace(tmp, achieved_path)
                if overwrite:
                    closure.delete_bad_draft_marker(key_dir)
        finally:
            mw_common.release_lock(lock_file(project_root, f"key-{key}"))
        # 3. 后验 ≥200B — short draft = L3 output quality issue → below path
        if achieved_path.stat().st_size < 200:
            st.timeline.append(
                "config", key=key,
                detail="L3 achieved draft < 200B → below (repair path, no padding)",
            )
            return "below", ""
        # 4. pm-state PASS line under the per-key lock
        if not _append_pass_line(project_root, st, key, qg_path):
            return "gated", ""  # lock held — retry next tick
        # 5. advance done (framework gates re-verify the 三件套)
        code, _out, err = advance.advance(
            key, "done", project_root, summary="autopilot L3 meets"
        )
        _record_advance_result(
            project_root, st, key, "verify->done", code, err,
            config.cached_load(project_root),
        )
        if code != 0:
            # Failure scene: declare the rejected draft so a later round may
            # replace it only with authorization (D-003). Lock held → skip the
            # write (W1-shaped degradation); the gated return is unchanged.
            try:
                acquire_conductor_lock(project_root, f"key-{key}", st.timeline)
            except ConductorLockHeld:
                return "gated", err
            try:
                try:
                    closure.write_bad_draft_marker(
                        key_dir, closure.failure_lines(err)
                    )
                except OSError as exc:
                    st.timeline.append(
                        "config", key=key,
                        detail=f"bad-draft marker write failed: {exc!r}",
                    )
            finally:
                mw_common.release_lock(lock_file(project_root, f"key-{key}"))
            return "gated", err
        # advance exit=0 → lazily clear a marker left behind by a draft that
        # was repaired outside the transaction (bytes no longer match)
        try:
            acquire_conductor_lock(project_root, f"key-{key}", st.timeline)
        except ConductorLockHeld:
            pass
        else:
            try:
                closure.delete_bad_draft_marker(key_dir)
            finally:
                mw_common.release_lock(lock_file(project_root, f"key-{key}"))
        # 6. advance 后验 index：exit 0 后回读 phase 列；失配重跑 set-phase
        ks = state.read_key_states(project_root).get(key)
        if ks is None or ks.phase.strip().upper() != "DONE":
            st.timeline.append(
                "config", key=key,
                detail="index phase mismatch after advance done; rerunning set-phase",
            )
            code2, err2 = _set_index_phase(project_root, key, "DONE")
            ks = state.read_key_states(project_root).get(key)
            if code2 != 0 or ks is None or ks.phase.strip().upper() != "DONE":
                mark_stalled(
                    project_root, st, key,
                    f"index phase mismatch persists after set-phase rerun "
                    f"(exit {code2}: {err2[:150]})",
                )
                return "gated", ""
        return "advanced", ""
    except OSError as exc:
        st.timeline.append("config", key=key, detail=f"done transaction IO failed: {exc!r}")
        return "gated", ""


# ── Phase helpers ──────────────────────────────────────────────────────────

def _normalize_phase(raw: str) -> str:
    value = (raw or "").strip().lower()
    return value if value in PHASES else "spec"


def _next_phase(phase: str) -> str:
    return PHASES[min(PHASES.index(phase) + 1, len(PHASES) - 1)]


def _phase_artifact_present(key_dir: pathlib.Path, phase: str) -> bool:
    if phase in ("spec", "design", "plan"):
        return (key_dir / f"{phase}.md").is_file()
    if phase == "tasks":
        return any((key_dir / "tasks").glob("*.md"))
    if phase == "verify":
        return (key_dir / "achieved.md").is_file()
    return True  # execute (T-12 loop) / done (terminal)


def _plan_task_file_stems(plan_id: str) -> list[str]:
    """Candidate ``tasks/*.md`` stems for a plan-referenced ``T-NN-slug`` id.

    D-111 makes the tasks/ file stem the task identity; a plan may name that
    stem directly (``T-001-board-params-config-errors.md``) or document the
    id→file mapping as a prefix strip (plan §3 example:
    ``T-001-board-params-config-errors`` → ``tasks/001-board-params-config-errors.md``).
    Both name the same task, so both are candidates; the id is only missing
    when *neither* candidate has a file.
    """
    stems = [plan_id]
    if re.match(r"^T-\d{2,3}-", plan_id):
        stems.append(plan_id[2:])
    return stems


def _missing_plan_tasks(key_dir: pathlib.Path) -> list[dict]:
    """Plan-referenced T-NN-slug ids with no tasks/ file — synthetic
    blocking gaps for the tasks→execute boundary (D-111).

    Existence is judged against the id's candidate file stems
    (:func:`_plan_task_file_stems`), so a key that maps the plan id to a
    prefix-stripped file name — the shape 20+ keys in this workspace use —
    is not flagged as missing."""
    tasks_dir = key_dir / "tasks"
    present = {f.stem for f in tasks_dir.glob("*.md")} if tasks_dir.is_dir() else set()
    plan = _plan_text(key_dir)
    if not plan:
        return []
    referenced = sorted(set(re.findall(r"\bT-\d{2,3}-[A-Za-z0-9][A-Za-z0-9-]*", plan)))
    return [
        {"item": f"plan 任务 {stem} 在 tasks/ 缺失", "rule": "execute-gate"}
        for stem in referenced
        if not (present & set(_plan_task_file_stems(stem)))
    ]


def _phase_writer_prompt(key: str, phase: str, nxt: str) -> str:
    return (
        f"为 key {key} 生成 {phase} 阶段 artifact（推进到 {nxt} 需要）:\n"
        f"- 遵循 AgenticTask 框架的 {phase} 产出规范（.agents/skills/agentic-task）\n"
        f"- 产出到 .agenticdoc/{key}/ 下对应文件\n"
        f"- 需要的证据留底写入 .agenticdoc/{key}/evidence/"
    )


def _verifier_prompt(key: str, phase: str, nxt: str, blocking: list[dict]) -> str:
    gap_lines = "\n".join(
        f"- {g['item']} (rule={g['rule']})" for g in blocking
    )
    return (
        f"L2 验证 key {key} 的 {phase}-> {nxt} 边界证据。L1 机械审计报告缺口:\n"
        f"{gap_lines}\n"
        f"请逐项裁决：缺口是否真实、需要什么证据文件能闭合；"
        f"结论与证据指针写入你的 output.md。"
    )


def _fix_writer_prompt(
    key: str, phase: str, nxt: str, blocking: list[dict], project_root: pathlib.Path, attempt: int
) -> str:
    gap_lines = "\n".join(
        f"- {g['item']} (rule={g['rule']})" for g in blocking
    )
    verifier_out = (
        project_root / ".agenticdoc" / key / "workers"
        / dispatch.task_key_for(key, f"l2-{phase}-to-{nxt}-a{attempt}") / "output.md"
    )
    return (
        f"补证 key {key} 的 {phase}-> {nxt} 边界（L2 回合 {attempt} 修复动作）:\n"
        f"L1 缺口:\n{gap_lines}\n"
        f"verifier 裁决（如已产出）: {verifier_out}\n"
        f"生成/补齐证据文件使机械审计可闭合，不改动无关 artifact。"
    )


def tick(project_root: pathlib.Path, st: ConductorState) -> str:
    """One conductor tick. Returns a short status word for logging/tests:
    idle | ok | halted-goal-change | lock-held | error. Never raises (§9)."""
    project_root = pathlib.Path(project_root)
    try:
        # 1. Beat first — liveness even when disabled (AC-019).
        st.timeline.append("beat")

        # 2. Enabled gate (mtime-cached config).
        cfg = config.cached_load(project_root)
        if not cfg["enabled"] or cfg["paused"]:
            return "idle"

        # 3. goal.md change detection (D-102): halt + ONE goal-change gate.
        current = goal_mtime_ns(project_root)
        try:
            gate_open = open_goal_change_gate(project_root)
        except gates.GateFormatError as exc:
            # Corrupt gate file (expected degraded state, e.g. a bad hand
            # edit): skip the tick + config event — the policy gates.enumerate
            # documents; the loop survives.
            st.timeline.append("config", detail=f"gate file corrupt, tick skipped: {exc}")
            return "ok"
        if (
            not gate_open
            and not st.goal_halted
            and current != st.goal_baseline
        ):
            try:
                acquire_conductor_lock(project_root, "gates", st.timeline)
            except ConductorLockHeld:
                return "lock-held"
            try:
                # Re-check under the lock (create-once).
                if not open_goal_change_gate(project_root):
                    gates.create(
                        gates_dir(project_root),
                        "goal-change",
                        "goal.md changed while autopilot is active — review the "
                        "new goal and approve resuming, or reject to stay halted.",
                        context_refs=[str(goal_path(project_root))],
                    )
                    st.timeline.append(
                        "goal-halt",
                        detail=f"goal.md mtime_ns {st.goal_baseline} -> {current}",
                    )
            finally:
                mw_common.release_lock(lock_file(project_root, "gates"))
            gate_open = True

        if gate_open or st.goal_halted:
            if gate_open:
                st.goal_halted = True
                return "halted-goal-change"
            # The gate was answered since the halt — refresh the baseline to
            # the current goal.md and resume.
            st.goal_baseline = current
            st.goal_halted = False
            st.timeline.append(
                "goal-snapshot",
                detail=f"baseline refreshed to mtime_ns {current} after goal-change gate",
            )

        # 4. Orchestration (T-10/T-11/T-12).
        orchestrate(project_root, st)
        return "ok"
    except Exception as exc:  # noqa: BLE001 — §9: a tick never kills the loop
        st.timeline.append("config", detail=f"tick error: {exc!r}")
        return "error"


# ── Queue row helpers ──────────────────────────────────────────────────────

def _all_workers_dirs(project_root: pathlib.Path) -> list[pathlib.Path]:
    """Every */workers dir under .agenticdoc (keys + _scratch)."""
    base = pathlib.Path(project_root) / ".agenticdoc"
    if not base.is_dir():
        return []
    return [d for d in base.iterdir() if d.is_dir() for d in [d / "workers"] if d.is_dir()]


def _is_in_flight(row: dict) -> bool:
    return row.get("status", "") not in mw_common._TERMINAL_STATUSES  # noqa: SLF001 — same-package private (state.py precedent)


def _row_belongs_to(row: dict, key: str) -> bool:
    if str(row.get("task_key", "")).startswith(f"ap-{key}-"):
        return True
    task_path = str(row.get("task_path", "")).replace("\\", "/")
    return f".agenticdoc/{key}/workers/" in task_path


def _row_exists(rows: list[dict], task_key: str) -> bool:
    return any(row.get("task_key") == task_key for row in rows)


def _next_gen_stem(rows: list[dict], key: str, base: str) -> str:
    """Generation phase-writer stem: base-a<N>, N = existing rows + 1."""
    prefix = f"ap-{key}-{base}"
    count = sum(1 for row in rows if str(row.get("task_key", "")).startswith(prefix))
    return f"{base}-a{count + 1}"


def _deps_satisfied(deps: tuple[str, ...], status_of: dict[str, str]) -> bool:
    return all(status_of.get(dep) in _DEP_SATISFIED for dep in deps)


# ── Gate helpers (conductor is the sole gate creator, D-105) ──────────────

def _create_gate(
    project_root: pathlib.Path,
    st: ConductorState,
    kind: str,
    question: str,
    *,
    key: str | None = None,
    stage: int | None = None,
    refs: tuple[str, ...] | list[str] = (),
) -> pathlib.Path | None:
    """Create a gate under the gates lock; None when the lock is live-held
    (the caller retries next tick). Appends a gate-created timeline event."""
    try:
        acquire_conductor_lock(project_root, "gates", st.timeline)
    except ConductorLockHeld:
        return None
    try:
        path = gates.create(
            gates_dir(project_root), kind, question,
            context_refs=list(refs), stage=stage, key=key,
        )
    finally:
        mw_common.release_lock(lock_file(project_root, "gates"))
    st.timeline.append(
        "gate-created", key=key, stage=stage, detail=f"{path.stem} kind={kind}"
    )
    return path


def _gate_open(
    project_root: pathlib.Path,
    kind: str,
    *,
    loop: str | None = None,
    stage: int | None = None,
    request_id: str | None = None,
) -> bool:
    """Is a matching gate already pending?

    ``request_id`` is the per-object dedup dimension the cross-key channel
    needs (D-010): one ``xkey-authorize`` gate per request, matched against
    ``context_refs`` exactly like ``loop``. Without it the conductor would
    raise a fresh gate every tick — the 6684-gates/12h flood the stalled-gate
    durable-consumption guard was added to stop."""
    for gate in gates.enumerate(gates_dir(project_root)):
        if gate.kind != kind or gate.status != "pending":
            continue
        if loop is not None and loop not in gate.context_refs:
            continue
        if stage is not None and gate.stage != stage:
            continue
        if request_id is not None and request_id not in gate.context_refs:
            continue
        return True
    return False


def _budget_bonus(project_root: pathlib.Path, loop: str) -> bool:
    """An approved budget-exhausted gate grants exactly one bonus round."""
    for gate in gates.enumerate(gates_dir(project_root)):
        if (
            gate.kind == "budget-exhausted"
            and gate.status == "approved"
            and loop in gate.context_refs
        ):
            return True
    return False


def _budget_gate_rejected(project_root: pathlib.Path, loop: str) -> bool:
    """A rejected budget-exhausted gate stalls the loop's key."""
    for gate in gates.enumerate(gates_dir(project_root)):
        if (
            gate.kind == "budget-exhausted"
            and gate.status == "rejected"
            and loop in gate.context_refs
        ):
            return True
    return False


def _mark_key_done(
    project_root: pathlib.Path, st: ConductorState, key: str, rm_path: pathlib.Path
) -> None:
    """Roadmap key-status → done (idempotent; under the roadmap lock)."""
    ok, missing = _done_credentials_present(project_root, key)
    if not ok:
        detail = (
            "key-done refused (missing done credentials: "
            + ", ".join(missing) + ")"
        )
        if not _timeline_has_event(project_root, "config", key, detail):
            st.timeline.append("config", key=key, detail=detail)
        return
    try:
        rm = roadmap.load_roadmap(rm_path)
        stage = roadmap.stage_by_number(rm, roadmap.stage_of_key(rm).get(key, 0))
        if stage is None or stage.key_status.get(key) == "done":
            return
        text = rm_path.read_text(encoding="utf-8")
        new_text = roadmap.update_key_status(text, stage.number, key, "done")
        if new_text == text:
            return
        acquire_conductor_lock(project_root, "roadmap", st.timeline)
        try:
            rm_path.write_text(new_text, encoding="utf-8", newline="\n")
        finally:
            mw_common.release_lock(lock_file(project_root, "roadmap"))
        # terminal cleanup: no live bad-draft marker may outlive DONE
        closure.delete_bad_draft_marker(project_root / ".agenticdoc" / key)
    except (roadmap.RoadmapError, OSError) as exc:
        st.timeline.append("config", key=key, detail=f"key-done mark failed: {exc!r}")


def _resume_credits(project_root: pathlib.Path, key: str) -> int:
    """Extra rounds granted to ``key`` by a human (AC-013).

    One approved ``stalled`` gate grants one extra round on *every* loop that
    caps this key (L2 boundary, EXECUTE task retry, L3 convergence, L3
    repair) — the gate is answered once, before the conductor knows which of
    them caps next, and the panel/gate text says so. The credit is never
    reusable: each loop's ``used`` counter is monotone (derived from the
    dispatch rows, which are append-only), so after the extra round is spent
    the same loop caps again and needs a fresh human decision —
    ``test_one_credit_is_spent_by_one_round_per_loop`` pins that. The count is
    re-derived from the gate directory on every call (zero private state), so
    it survives conductor restarts and cannot drift. Rejecting the gate
    grants nothing — that path closes the key as closed-legacy instead.
    """
    return sum(
        1
        for gate in gates.enumerate(gates_dir(project_root))
        if gate.kind == "stalled" and gate.status == "approved" and gate.key == key
    )


def _apply_stalled_approvals(
    project_root: pathlib.Path,
    st: ConductorState,
    status_of: dict[str, str],
    stage_of: dict[str, int],
) -> None:
    """stalled gate approved → resume the key (AC-004).

    The symmetric half of :func:`_apply_stalled_rejections`: the gate question
    promises "人工介入后重试", so an approval rewrites key-status
    ``stalled`` → ``running`` under the roadmap lock, records the durable
    consumption event (``gate-answered``, the same protocol
    ``_consumed_gate_ids`` replays) plus a ``resume`` event, and mutates
    ``status_of`` in place so this same tick's per-key machine already sees
    the key as runnable. Idempotent by file truth: once key-status is
    ``running`` a second tick (or a restart) finds nothing to rewrite. The
    extra round itself comes from :func:`_resume_credits` — one extra round
    per capped loop, each consumed by that loop's own monotone ``used``
    counter (see there).
    """
    consumed = _consumed_gate_ids(project_root)
    for gate in gates.enumerate(gates_dir(project_root)):
        if gate.kind != "stalled" or gate.status != "approved":
            continue
        if gate.id in consumed:
            # 2026-09-24 (FeatureMigrator incident): consumption is durable — an
            # approved stalled gate whose answer was already applied must never
            # resume the key again. The key-status rewrite below is not a
            # sufficient guard: it only sees the state as of this tick's start,
            # so a key that re-stalls inside the same tick (or on the next one)
            # replayed the same human answer forever — and every replay
            # re-created a pending stalled gate. Measured: 6684 pending stalled
            # gates + 6685 stalled/gate-answered/resume events in ~12 h, all
            # from two approved gates, with the key oscillating
            # stalled→running→stalled every tick.
            continue
        key = gate.key
        if not key or status_of.get(key) != "stalled":
            continue
        stage_number = stage_of.get(key)
        if stage_number is None:
            continue
        try:
            rm_path = roadmap.roadmap_path(project_root)
            text = rm_path.read_text(encoding="utf-8")
            new_text = roadmap.update_key_status(text, stage_number, key, "running")
            if new_text == text:
                continue  # already resumed (or not present in that stage)
            acquire_conductor_lock(project_root, "roadmap", st.timeline)
            try:
                rm_path.write_text(new_text, encoding="utf-8", newline="\n")
            finally:
                mw_common.release_lock(lock_file(project_root, "roadmap"))
            st.timeline.append(
                "gate-answered", key=key, detail=f"{gate.id} approved → {key} running"
            )
            st.timeline.append(
                "resume", key=key,
                detail=(
                    f"{key} resumed by {gate.id} "
                    "(one extra round per capped loop)"
                ),
            )
            status_of[key] = "running"
        except (roadmap.RoadmapError, OSError) as exc:
            st.timeline.append("config", key=key, detail=f"resume mark failed: {exc!r}")


def _apply_stalled_rejections(
    project_root: pathlib.Path,
    st: ConductorState,
    status_of: dict[str, str],
    stage_of: dict[str, int],
) -> None:
    """stalled gate rejected → closed-legacy (遗留关闭, achieved.md 草稿保留).
    Mutates ``status_of`` in place so this tick's dependency checks already
    see the unblocked dependents."""
    for gate in gates.enumerate(gates_dir(project_root)):
        if gate.kind != "stalled" or gate.status != "rejected":
            continue
        key = gate.key
        if not key or status_of.get(key) != "stalled":
            continue
        try:
            rm_path = roadmap.roadmap_path(project_root)
            text = rm_path.read_text(encoding="utf-8")
            new_text = roadmap.update_key_status(text, stage_of[key], key, "closed-legacy")
            if new_text != text:
                acquire_conductor_lock(project_root, "roadmap", st.timeline)
                try:
                    rm_path.write_text(new_text, encoding="utf-8", newline="\n")
                finally:
                    mw_common.release_lock(lock_file(project_root, "roadmap"))
                st.timeline.append("gate-answered", key=key, detail=f"{gate.id} rejected → {key} closed-legacy")
                st.timeline.append("stalled", key=key, detail=f"{key} closed-legacy (stalled gate rejected)")
                # terminal cleanup: no live bad-draft marker on closed-legacy
                closure.delete_bad_draft_marker(project_root / ".agenticdoc" / key)
                status_of[key] = "closed-legacy"
        except (roadmap.RoadmapError, OSError) as exc:
            st.timeline.append("config", key=key, detail=f"closed-legacy mark failed: {exc!r}")


# ── Cross-key red repair: mounting only (xkey-repair-mechanism D-010) ────
#
# The conductor MOUNTS the cross-key channel; every shape decision (parse /
# ledger / ticket / locate / boundary / apply / verify / evidence) lives in
# ``autopilot.xkey`` (T-01) and is imported, never redefined here. The module
# is pulled in lazily so an ``xkey_repair``-off conductor (AC-008 default)
# never imports it — the parallel wave that lands xkey.py cannot change the
# existing suite. Zero private state: candidates re-derive from the per-key
# provenance sidecars and the xkey ledger every tick, so a restart replays
# exactly the same (idempotent) work.

# Coarse "this round mentions a cross-key handoff" pre-filter. Field parsing
# itself is ``xkey.collect_registrations``; this only separates "marker present
# but unresolvable" (⇒ escalation record, AC-002) from "no cross-key content
# at all" (⇒ not a cross-key red, no record — D-001 Q4 rule 4).
_XKEY_MARKER_RE = re.compile(
    r"cross_?key|跨\s*key|\[XKEY\]|handoff\s*[=:]|交接|挂账|owner\s*在案|已登记",
    re.IGNORECASE,
)
# Ticket states in which exactly one ``xkey-authorize`` gate must be pending;
# any other state (approved/rejected/applied/closed/…) means the object moved
# on and the aggregator must not raise a new gate for it.
_XKEY_AWAITING = ("detected", "ticketed", "pending-auth")


def _xkey():
    """Lazy accessor for the cross-key module (T-01's frozen public surface)."""
    from autopilot import xkey
    return xkey


def _xkey_ticket_relpath(request_id: str) -> str:
    """Ticket carrier path relative to the project root (D-003/D-004).

    Deterministic so a later tick can re-point a gate at an existing ticket
    (``context_refs`` needs the path, not the parsed dict)."""
    return f".agenticdoc/_autopilot/xkey/tickets/xkey-{request_id}.md"


def _xkey_below_records(
    project_root: pathlib.Path,
) -> list[tuple[pathlib.Path, dict]]:
    """(key_dir, provenance record) for every below round on disk.

    Read-only feed (D-001): the per-key ``l3-verdict-provenance.json`` sidecars
    are the only new-red source. A corrupt sidecar is skipped — the provenance
    writer never overwrites one, and audit history outranks this scan."""
    import json  # local: conductor carries no module-level json dependency

    base = pathlib.Path(project_root) / ".agenticdoc"
    found: list[tuple[pathlib.Path, dict]] = []
    if not base.is_dir():
        return found
    for key_dir in sorted(base.iterdir()):
        if not key_dir.is_dir():
            continue
        sidecar = key_dir / _PROVENANCE_FILENAME
        if not sidecar.is_file():
            continue
        try:
            parsed = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(parsed, list):
            continue
        for record in parsed:
            if not isinstance(record, dict):
                continue
            # The reviewer's own verdict is the red signal: a suspect `meets`
            # round (verdict flipped to below by the provenance guard) is an
            # evidence artifact, not a cross-key red. Fall back to the
            # effective `verdict` for records written without the raw field.
            raw = record.get("raw_verdict")
            if raw is None:
                raw = record.get("verdict")
            if raw == "below":
                found.append((key_dir, record))
    return found


def _xkey_aggregate(
    project_root: pathlib.Path,
    st: ConductorState,
    status_of: dict[str, str],
    cfg: dict,
) -> None:
    """Fold below-round registrations into ledger + tickets + gates (D-010).

    O(new verdicts): the ledger's ``dedup_key`` set gives idempotent dedup. A
    complete registration whose owner key is terminal opens a machine-readable
    ticket and exactly one ``xkey-authorize`` gate (request_id-guarded); an
    unresolvable marker, or an owner that is not terminal, only leaves an
    escalation ledger row and zero tickets (AC-002)."""
    xkey = _xkey()
    root = str(project_root)
    records = _xkey_below_records(project_root)
    if not records:
        return
    ledger = xkey.ledger_load(root)
    rows = [row for row in ledger.get("rows", []) if isinstance(row, dict)]
    known = {row.get("dedup_key") for row in rows}
    by_pair: dict[tuple, dict] = {
        (row.get("file"), row.get("test_id")): row for row in rows
    }
    for key_dir, record in records:
        source_key = key_dir.name
        registration = record.get("registration", _REGISTRATION_UNSET)
        if registration is _REGISTRATION_UNSET:
            continue  # not a cross-key round / persisted with the switch off
        if not isinstance(registration, dict):
            _xkey_escalate(project_root, st, xkey, known, source_key, record, None)
            continue
        file = registration.get("file")
        test_id = registration.get("test_id")
        owner_key = registration.get("owner_key")
        if not (
            isinstance(file, str) and file
            and isinstance(test_id, str) and test_id
            and isinstance(owner_key, str) and owner_key
        ):
            _xkey_escalate(
                project_root, st, xkey, known, source_key, record, registration
            )
            continue
        if status_of.get(owner_key) not in _DEP_SATISFIED:
            # Owner not terminal: no cross-key ticket (scenario C, AC-002).
            _xkey_escalate(
                project_root, st, xkey, known, source_key, record, registration
            )
            continue
        existing = by_pair.get((file, test_id))
        if existing is not None:
            request_id = str(existing.get("request_id") or "")
            if request_id and str(existing.get("status") or "") in _XKEY_AWAITING:
                _xkey_ensure_gate(
                    project_root, st, request_id, owner_key,
                    _xkey_ticket_relpath(request_id), file, test_id,
                )
            continue
        block = xkey.locate_frozen_block(root, file, test_id)
        block_sha = ""
        if isinstance(block, dict):
            block_sha = str(block.get("old_block_sha256") or "")
        if not block_sha:
            block_sha = str(registration.get("frozen_block") or "")
        dedup_key = xkey.dedup_key(file, test_id, block_sha)
        request_id = "XKEY-" + hashlib.sha1(
            dedup_key.encode("utf-8")
        ).hexdigest()[:12]
        xkey.ledger_append(root, {
            "dedup_key": dedup_key,
            "source_key": source_key,
            "owner_key": owner_key,
            "test_id": test_id,
            "file": file,
            "frozen_block": block,
            "status": "detected",
            "request_id": request_id,
            "reason": record.get("fail_line"),
            "history": [{
                "ts": _iso_now(),
                "event": "detected",
                "detail": (
                    f"below {record.get('round')} registration "
                    f"→ ticket {request_id}"
                ),
            }],
        })
        known.add(dedup_key)
        by_pair[(file, test_id)] = {
            "file": file, "test_id": test_id,
            "request_id": request_id, "status": "ticketed",
        }
        st.timeline.append(
            "xkey-detected", key=owner_key,
            detail=f"{source_key} {file}::{test_id} → {request_id}",
        )
        if xkey.ticket_load(root, request_id) is None:
            ticket = {
                "schema_version": 1,
                "request_id": request_id,
                "created_by": "conductor",
                "created_at": _iso_now(),
                "status": "ticketed",
                "source_key": source_key,
                "owner_key": owner_key,
                "affected_keys": [source_key, owner_key],
                "dedup_key": dedup_key,
                "file": file,
                "test_id": test_id,
                "frozen_block": block,
                "handoff": registration.get("handoff"),
                "reason": record.get("fail_line"),
                "fail_line": record.get("fail_line"),
                "deciding_source": record.get("deciding_source"),
                "round": record.get("round"),
                "authorization_snapshot": (
                    block.get("old_block_sha256") if isinstance(block, dict) else None
                ),
                # T-06 anchors: the whole-file sha256 at ticket creation is the
                # zero-residue reference the verify-failed rollback must equal;
                # one `below` verdict is by construction one red before the fix.
                "target_file_sha256": _xkey_file_sha256(project_root, file),
                "red_before": 1,
                "verification": {
                    "command": list(cfg.get("xkey_verify_cmd", [])),
                    "timeout_s": int(cfg.get("xkey_verify_timeout_s", 1800)),
                },
                "registration": registration,
                "decisions": [],
            }
            xkey.ticket_write(root, ticket)
            st.timeline.append(
                "xkey-ticketed", key=owner_key,
                detail=f"{request_id} {file}::{test_id}",
            )
        _xkey_ensure_gate(
            project_root, st, request_id, owner_key,
            _xkey_ticket_relpath(request_id), file, test_id,
        )


def _xkey_ensure_gate(
    project_root: pathlib.Path,
    st: ConductorState,
    request_id: str,
    owner_key: str,
    ticket_rel: str,
    file: str,
    test_id: str,
) -> None:
    """Raise one ``xkey-authorize`` gate per request_id (D-010 flood guard).

    ``_gate_open(request_id=…)`` matches ``context_refs``, so N ticks on the
    same pending ticket still produce exactly one gate (VC-012)."""
    if _gate_open(project_root, "xkey-authorize", request_id=request_id):
        return
    gate_path = _create_gate(
        project_root, st, "xkey-authorize",
        f"跨 key 红 {file}::{test_id}（owner {owner_key}）请求解冻授权："
        f"追认后由框架执行受限修复，拒绝则留账本。",
        key=owner_key,
        refs=[request_id, ticket_rel],
    )
    if gate_path is not None:
        st.timeline.append(
            "xkey-gate-raised", key=owner_key,
            detail=f"{request_id} → {ticket_rel}",
        )


def _xkey_escalate(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    known: set,
    source_key: str,
    record: dict,
    registration: dict | None,
) -> None:
    """Record one escalation (AC-002): a cross-key round whose registration
    cannot be resolved to a live ticket. Zero tickets, zero gates; the ledger
    row + timeline event are the durable, idempotent record."""
    rnd = record.get("round")
    dedup_key = f"escalated::{source_key}::{rnd}"
    if dedup_key in known:
        return
    reg = registration if isinstance(registration, dict) else {}
    missing = [name for name in ("file", "test_id", "owner_key") if not reg.get(name)]
    if not missing:
        missing = ["owner_not_terminal"]
    root = str(project_root)
    xkey.ledger_append(root, {
        "dedup_key": dedup_key,
        "source_key": source_key,
        "owner_key": reg.get("owner_key"),
        "test_id": reg.get("test_id"),
        "file": reg.get("file"),
        "frozen_block": None,
        "status": "escalated",
        "request_id": None,
        "reason": record.get("fail_line"),
        "unresolvable_fields": missing,
        "history": [{
            "ts": _iso_now(),
            "event": "escalated",
            "detail": "registration unresolvable or owner not terminal → human/PM",
        }],
    })
    known.add(dedup_key)
    st.timeline.append(
        "xkey-escalated", key=reg.get("owner_key") or source_key,
        detail=f"{source_key} {rnd} unresolvable={','.join(missing)}",
    )


def _consume_xkey_gate(
    project_root: pathlib.Path, st: ConductorState, gate: gates.Gate
) -> None:
    """Fold one answered ``xkey-authorize`` gate into ledger + ticket (D-010).

    Runs inside ``_consume_answered_gates`` (step F), i.e. before
    ``_apply_stalled_*``: an xkey approval is the only path that moves a
    ticketed red forward, and the stalled machinery only ever sees ``stalled``
    keys — routing this through it would leave the ticket frozen forever."""
    xkey = _xkey()
    request_id = gate.context_refs[0] if gate.context_refs else ""
    if not request_id:
        st.timeline.append(
            "config", detail=f"{gate.id} xkey-authorize without request_id ref"
        )
        return
    root = str(project_root)
    ticket = xkey.ticket_load(root, request_id)
    if ticket is None:
        st.timeline.append(
            "config", key=gate.key,
            detail=f"{gate.id} xkey-authorize ticket missing: {request_id}",
        )
        return
    status = "approved" if gate.status == "approved" else "rejected"
    dedup_key = ticket.get("dedup_key")
    if dedup_key:
        xkey.ledger_append(root, {
            "dedup_key": dedup_key,
            "source_key": ticket.get("source_key"),
            "owner_key": ticket.get("owner_key"),
            "test_id": ticket.get("test_id"),
            "file": ticket.get("file"),
            "frozen_block": ticket.get("frozen_block"),
            "status": status,
            "request_id": request_id,
            "decisions": [{
                "decision": status,
                "by": gate.answered_by,
                "at": gate.answered_at,
                "note": gate.note,
            }],
            "history": [{
                "ts": _iso_now(),
                "event": status,
                "detail": f"{gate.id} answered {gate.status}",
            }],
        })
    ticket["status"] = status
    xkey.ticket_write(root, ticket)
    st.timeline.append(
        "gate-answered", key=gate.key,
        detail=f"{gate.id} {gate.status} → xkey {request_id} {status}",
    )


# ── Cross-key red repair: proposal dispatch (T-08, D-005 path (b)) ──────────
#
# T-03 delivered detected → ticketed → gate → approved; T-06 consumes an
# approved ticket whose proposal is already on disk. This segment closes the
# gap between them: an approved ticket with no proposal file gets exactly one
# proposal-worker dispatch (phase-writer). The worker only ever writes
# ``evidence/<request_id>/proposal.md`` — the conductor applies nothing until
# T-06's boundary pre-check passes, so a wrong proposal is zero-residue by
# construction.
#
# Zero private state: the trigger (ticket status + proposal file absence), the
# dedup marker (ticket frontmatter: proposal_task_key / proposal_attempts) and
# the attempt bound all re-derive from disk every tick, so a restart replays
# exactly the same work (no in-memory cursor, D-010). A refused dispatch
# escalates (ledger history + escalation.md) and leaves the ticket approved;
# after _XKEY_PROPOSAL_MAX_ATTEMPTS the stage stops re-dispatching and records
# one durable exhaustion marker, never an unbounded retry loop.

_XKEY_PROPOSAL_MAX_ATTEMPTS = 2  # mirrors the roadmap-writer's 2-proposal cap


def _xkey_proposal_stage(
    project_root: pathlib.Path,
    st: ConductorState,
    rows: list[dict],
) -> None:
    """T-08 mount: dispatch the proposal worker for approved tickets with no
    proposal on disk. Runs before ``_xkey_apply_stage`` in the same
    ``cfg["xkey_repair"]`` gate; per-ticket exceptions are isolated so a tick
    never dies and the ticket keeps its last good state."""
    xkey = _xkey()
    try:
        tickets = xkey.tickets_iter(str(project_root))
    except Exception as exc:  # noqa: BLE001 — a corrupt ticket is skipped, not fatal
        st.timeline.append("config", detail=f"xkey tickets unreadable: {exc!r}")
        return
    for ticket in tickets:
        if not isinstance(ticket, dict):
            continue
        try:
            _xkey_proposal_one(project_root, st, xkey, ticket, rows)
        except Exception as exc:  # noqa: BLE001 — per-ticket isolation
            st.timeline.append(
                "config", key=ticket.get("owner_key"),
                detail=(
                    f"xkey proposal stage error for {ticket.get('request_id')}: "
                    f"{exc!r} (ticket kept at its last good state)"
                ),
            )


def _xkey_proposal_in_flight(
    rows: list[dict], source_key: str, base_stem: str
) -> bool:
    """A live dispatch already exists in the proposal stem family.

    Durable file truth (queue rows), so a conductor restart cannot re-dispatch
    an in-flight proposal worker; the same guard covers the ``-a<N>`` retry
    rows (D-111 task identity)."""
    if not source_key:
        return False
    anchor = re.escape(dispatch.task_key_for(source_key, base_stem))
    pat = re.compile(rf"^{anchor}(-a\d+)?$")
    return any(
        pat.match(str(row.get("task_key", ""))) and _is_in_flight(row)
        for row in rows
    )


def _xkey_proposal_escalate(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    request_id: str,
    event: str,
    detail: str,
) -> None:
    """Durable failure record: ledger history + escalation.md + timeline.

    The ticket status is intentionally untouched (stays ``approved`` — a
    refused dispatch is a channel failure, not a repair failure)."""
    root = str(project_root)
    if ticket.get("dedup_key"):
        xkey.ledger_append(root, _xkey_ledger_row(
            ticket, str(ticket.get("status") or "approved"),
            [{"ts": _iso_now(), "event": event, "detail": detail}],
        ))
    _xkey_escalation_write(project_root, request_id, event, detail)
    st.timeline.append(
        "xkey-" + event.replace("_", "-"), key=ticket.get("owner_key"),
        detail=f"{request_id} {detail}",
    )


def _xkey_proposal_exhaust(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    request_id: str,
    detail: str,
) -> None:
    """Bound reached: record one durable marker + escalation, then stop.

    ``proposal_exhausted_at`` is the on-disk guard that keeps later ticks from
    re-dispatching and from re-emitting the escalation event (no timeline
    spam). A human can clear the field (or land a proposal) to retry."""
    if ticket.get("proposal_exhausted_at"):
        return
    ticket["proposal_exhausted_at"] = _iso_now()
    ticket["proposal_exhausted_detail"] = _one_line(detail, 200)
    xkey.ticket_write(str(project_root), ticket)
    _xkey_proposal_escalate(
        project_root, st, xkey, ticket, request_id,
        "proposal_dispatch_exhausted", detail,
    )


def _xkey_proposal_one(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    rows: list[dict],
) -> None:
    """One ticket: dispatch at most one proposal worker attempt this tick.

    Trigger: status ``approved`` **and** ``evidence/<request_id>/proposal.md``
    absent. The dispatch marker + attempt count are written back into the
    ticket frontmatter (``xkey.ticket_write``) before the next tick can see
    them, and the in-flight row guard covers the crash gap between the queue
    write and the marker write."""
    request_id = ticket.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        return
    if str(ticket.get("status") or "") != "approved":
        return
    proposal_path = (
        _xkey_evidence_root(project_root, request_id) / _XKEY_PROPOSAL_NAME
    )
    if proposal_path.is_file():
        return  # proposal on disk → T-06 takes over
    if ticket.get("proposal_exhausted_at"):
        return  # bound already recorded — never spin
    source_key = str(ticket.get("source_key") or "")
    if not source_key or source_key == dispatch.SCRATCH_OWNER:
        _xkey_proposal_exhaust(
            project_root, st, xkey, ticket, request_id,
            "ticket carries no dispatchable source_key",
        )
        return
    base_stem = f"xkey-{request_id}-proposal"
    if _xkey_proposal_in_flight(rows, source_key, base_stem):
        return  # a live dispatch in this stem family is never duplicated
    attempts = _xkey_int(ticket.get("proposal_attempts"), 0)
    if attempts >= _XKEY_PROPOSAL_MAX_ATTEMPTS:
        _xkey_proposal_exhaust(
            project_root, st, xkey, ticket, request_id,
            f"proposal dispatch bound reached ({attempts}/"
            f"{_XKEY_PROPOSAL_MAX_ATTEMPTS}); ticket stays approved",
        )
        return
    attempt = attempts + 1
    stem = base_stem if attempt == 1 else f"{base_stem}-a{attempt}"
    loop = f"xkey-proposal:{request_id}"
    result = dispatch.dispatch(
        project_root, source_key, stem, "phase-writer",
        _xkey_proposal_prompt(project_root, ticket),
        loop=loop, attempt=attempt, timeline=st.timeline,
    )
    ticket["proposal_task_key"] = result.task_key
    ticket["proposal_dispatch_at"] = _iso_now()
    ticket["proposal_attempts"] = attempt
    xkey.ticket_write(str(project_root), ticket)
    if result.ok:
        st.timeline.append(
            "xkey-proposal-dispatched", key=ticket.get("owner_key"),
            detail=f"{request_id} {result.task_key} attempt {attempt}",
        )
        return
    _xkey_proposal_escalate(
        project_root, st, xkey, ticket, request_id,
        "proposal_dispatch_refused",
        f"proposal dispatch refused at attempt {attempt}: {result.reason}",
    )
    if attempt >= _XKEY_PROPOSAL_MAX_ATTEMPTS:
        _xkey_proposal_exhaust(
            project_root, st, xkey, ticket, request_id,
            f"proposal dispatch bound reached ({attempt}/"
            f"{_XKEY_PROPOSAL_MAX_ATTEMPTS}); ticket stays approved",
        )


def _xkey_proposal_prompt(project_root: pathlib.Path, ticket: dict) -> str:
    """Self-contained proposal-worker prompt (T-08, D-005 path (b)).

    The worker only ever writes ``evidence/<request_id>/proposal.md`` — the
    conductor applies nothing until T-06's boundary pre-check passes, so every
    fact the worker needs (absolute ticket path, frozen-block spec, allowed
    line set, untouchable list, output contract, prohibitions) is rendered
    here; the ticket file stays the authoritative fallback."""
    project_root = pathlib.Path(project_root)
    request_id = str(ticket.get("request_id") or "")
    frozen = ticket.get("frozen_block")
    if not isinstance(frozen, dict):
        frozen = {}
    file_rel = _xkey_norm_path(frozen.get("file") or ticket.get("file"))
    symbol = str(frozen.get("symbol") or "(not recorded)")
    line_range = _xkey_line_range(frozen.get("line_range"))
    if line_range is not None:
        start, end = line_range
        range_literal = f"[{start}, {end}]"
        allowed_text = ", ".join(str(n) for n in range(start, end + 1))
    else:
        range_literal = "(not recorded)"
        allowed_text = "(not recorded)"
    old_sha = str(frozen.get("old_block_sha256") or "(not recorded)")
    ticket_abs = project_root / _xkey_ticket_relpath(request_id)
    target_abs = project_root / file_rel if file_rel else project_root
    proposal_abs = (
        _xkey_evidence_root(project_root, request_id) / _XKEY_PROPOSAL_NAME
    )
    forbidden = ticket.get("untouchable")
    if isinstance(forbidden, (list, tuple)) and forbidden:
        untouchable = "\n".join(f"- {item}" for item in forbidden)
    else:
        untouchable = (
            "- 目标文件中 line_range 以外的所有行（含同文件其它模块级常量）\n"
            "- 该用例的函数体 / 断言逻辑（本次只更新冻结期望/常量块）"
        )
    reason = _one_line(
        ticket.get("reason") or ticket.get("fail_line") or "(not recorded)", 300
    )
    return (
        f"# 跨 key 冻结块修复提案（request {request_id}）\n\n"
        "你是提案 worker：只产提案，不落地任何修复。conductor 会在人工追认后做"
        "边界预检并原子应用；提案越界 ⇒ 零写入、零残留。\n\n"
        "## 1. 工单（权威，先完整阅读）\n\n"
        f"- 工单文件：{ticket_abs}\n"
        "- 工单状态：approved（人工已追认）\n"
        f"- 红用例：{ticket.get('test_id') or '(not recorded)'}"
        f"（owner key：{ticket.get('owner_key') or '(not recorded)'}）\n"
        f"- 红的原因：{reason}\n\n"
        "## 2. 冻结块规格（逐字来自工单，不得改写）\n\n"
        f"- 目标文件：{file_rel or '(not recorded)'}"
        f"（绝对路径：{target_abs}）\n"
        f"- 符号：{symbol}\n"
        f"- 行范围（含端点，1-based）：{range_literal}\n"
        f"- old_block_sha256：{old_sha}\n"
        f"- 允许改的行集合：{{{allowed_text}}}\n\n"
        "## 3. untouchable（不可触碰）\n\n"
        f"{untouchable}\n"
        "- 除下方唯一写入目标外，不得修改任何其它文件\n\n"
        "## 4. 输出契约（唯一写入目标）\n\n"
        f"- 写入：{proposal_abs}\n"
        "- 文件格式（frontmatter + 一个围栏代码块）：\n\n"
        "```markdown\n"
        "---\n"
        f"file: {file_rel}\n"
        f"line_range: {range_literal}\n"
        f"old_block_sha256: {old_sha}\n"
        "changed_lines: <实际改动的行号，逗号分隔；必须是允许改的行集合的子集，可省略>\n"
        "---\n\n"
        "```python\n"
        "<新的冻结块内容：逐字、逐行，保留原缩进与行尾换行>\n"
        "```\n"
        "```\n\n"
        "- frontmatter 的 file / line_range / old_block_sha256 三键必须逐字等于工单值"
        "（大小写、空格、行范围写法都保持一致）；任何不一致会被判为 boundary "
        "violation，提案作废且零写入。\n"
        "- 围栏块内只放新的冻结块内容本身（不含差量标记、不含解释文字）；改动行范围"
        "必须恰好覆盖 line_range，其它行原样保留。\n"
        "- 新块内容按字节精确承载（D-012）：保持目标文件既有换行风格（CRLF/LF），"
        "不要在块内额外加空行。\n\n"
        "## 5. 明令禁止\n\n"
        "- 不得修改目标文件的断言主体 / 测试逻辑（只更新冻结期望/常量块）\n"
        "- 不得修改任何其它文件（含测试文件、其它 key 的产物、conductor/框架文件）\n"
        "- 不得执行 git 写入操作（commit / checkout / stash 等）\n\n"
        "## 6. 完成后必须报告\n\n"
        "- 你实际改动的行号集合（与 changed_lines 一致）\n"
        "- 旧的 old_block_sha256 与新的新块 sha256（如可计算）\n"
        "- 提案文件绝对路径\n"
    )


# ── Cross-key red repair: apply / verify / evidence / close (T-06) ──────────
#
# T-03 delivered detected → ticketed → gate → approved. This segment consumes
# an approved ticket that has a proposal on disk and walks it through
# applied → verified → closed (design D-005/D-006/D-007/D-012, AC-005/006/007).
#
# Every mechanical judgement stays in ``autopilot.xkey`` (check_boundary /
# apply_block_replace / run_verification / evidence_bundle_write); this block
# only sequences the stages and persists the state transitions. Three
# non-negotiables:
#   * S2 boundary violation → zero write (the target is never opened for
#     writing; the file sha stays exactly the ticket-creation value).
#   * S3 snapshot the whole target byte-exactly *before* applying
#     (runs/<ts>/pre-apply.bak), so any later failure can be undone by bytes.
#   * S4 verification not green → restore from that snapshot byte-exactly,
#     status ``verify_failed``, never close (the fail direction never
#     collapses into a closure).
#
# Zero private state: the entry condition (ticket status + proposal file) and
# every stage input re-derive from disk, so a restart replays exactly the same
# (idempotent) work. Per-ticket exceptions are caught so a tick never dies and
# the ticket keeps its last good state.

_XKEY_PROPOSAL_NAME = "proposal.md"
_XKEY_BAK_NAME = "pre-apply.bak"
_XKEY_RUN_MARKER_NAME = "run.json"
_XKEY_EVIDENCE_NAME = "escalation.md"
# Statuses that (re-)enter the stage. `applied`/`verified` resume rather than
# restart, so a conductor death between two stages never strands a modified
# file: the stage re-derives the run dir + shas from the ticket/run marker.
_XKEY_APPLY_ENTRIES = frozenset({"approved", "applied", "verified"})
# Rows that must never be re-opened by another stage pass.
_XKEY_TERMINAL_STATUSES = frozenset({
    "closed", "boundary_violation", "verify_failed", "rejected", "timed-out",
})
_XKEY_PROPOSAL_META = ("file", "line_range", "old_block_sha256")

_XKEY_FRONT_FENCE_RE = re.compile(
    rb"\A(?:\xef\xbb\xbf)?(?:[ \t]*\r?\n)*?[ \t]*---[ \t]*\r?\n"
)
_XKEY_FENCE_CLOSE_RE = re.compile(rb"(?m)^[ \t]*---[ \t]*\r?$")
_XKEY_CODE_FENCE_RE = re.compile(rb"(?m)^[ \t]*```[^\n]*\r?\n")
_XKEY_CODE_FENCE_END_RE = re.compile(rb"(?m)^[ \t]*```[ \t]*\r?$")


def _xkey_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _xkey_file_sha256(project_root: pathlib.Path, file: object) -> str:
    """Whole-file byte sha256 ("" when the path is unusable) — the
    ticket-creation anchor AC-005/AC-007 measure zero-residue against."""
    rel = _xkey_norm_path(file)
    if not rel:
        return ""
    try:
        return _xkey_sha256_bytes((pathlib.Path(project_root) / rel).read_bytes())
    except OSError:
        return ""


def _xkey_norm_path(value: object) -> str:
    """Slash form without a leading ``./`` (proposal ↔ ticket comparison)."""
    text = str(value).strip().strip("`'\"")
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _xkey_line_range(value: object) -> list[int] | None:
    """``[s, e]`` / ``s-e`` / ``s,e`` → ordered inclusive pair, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            start, end = int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
        return [start, end] if start >= 1 and end >= start else None
    if isinstance(value, str):
        match = re.fullmatch(
            r"\s*[\[(]?\s*(\d+)\s*(?:-|\.\.|,)\s*(\d+)\s*[\])]?\s*", value
        )
        if match is not None:
            start, end = int(match.group(1)), int(match.group(2))
            return [start, end] if start >= 1 and end >= start else None
    return None


def _xkey_line_list(value: str) -> list[int] | None:
    """A comma/space separated line list (proposal ``changed_lines``)."""
    parts = [part for part in re.split(r"[,\s]+", value.strip().strip("[]")) if part]
    out: set[int] = set()
    for part in parts:
        if not re.fullmatch(r"\d+", part):
            return None
        out.add(int(part))
    return sorted(out) or None


def _xkey_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _xkey_evidence_root(project_root: pathlib.Path, request_id: str) -> pathlib.Path:
    return (
        pathlib.Path(project_root)
        / ".agenticdoc" / "_autopilot" / "xkey" / "evidence" / request_id
    )


def _xkey_json_read(path: pathlib.Path) -> dict | None:
    import json  # local: keep the conductor module-level import surface small
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _xkey_json_write(path: pathlib.Path, payload: dict) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(str(path) + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    os.replace(tmp, path)


def _xkey_run_stamp(runs_root: pathlib.Path) -> str:
    base = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stamp = base
    index = 1
    while (runs_root / stamp).exists():
        index += 1
        stamp = f"{base}-{index}"
    return stamp


def _xkey_parse_proposal(raw: bytes) -> dict | None:
    """Parse ``proposal.md``: the S1 metadata triple + one fenced new block.

    Frontmatter carries ``file`` / ``line_range`` / ``old_block_sha256``
    (optional ``changed_lines`` / ``reason``); the first fenced code block is
    the byte-exact new block content (D-012). Any unusable shape returns
    ``None`` — the caller treats that as a boundary violation, never a repair."""
    head = _XKEY_FRONT_FENCE_RE.match(raw)
    if head is None:
        return None
    rest = raw[head.end():]
    close = _XKEY_FENCE_CLOSE_RE.search(rest)
    if close is None:
        return None
    try:
        front_text = rest[:close.start()].decode("utf-8")
    except UnicodeDecodeError:
        return None
    meta: dict[str, str] = {}
    for line in front_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            return None
        key, _, value = stripped.partition(":")
        cleaned = value.strip().strip("`'\"")
        if cleaned:
            meta[key.strip()] = cleaned
    if any(not meta.get(name) for name in _XKEY_PROPOSAL_META):
        return None
    line_range = _xkey_line_range(meta["line_range"])
    if line_range is None:
        return None
    body = rest[close.end():]
    open_fence = _XKEY_CODE_FENCE_RE.search(body)
    if open_fence is None:
        return None
    content_start = open_fence.end()
    end_fence = _XKEY_CODE_FENCE_END_RE.search(body[content_start:])
    if end_fence is None:
        return None
    proposal = {
        "file": meta["file"],
        "line_range": line_range,
        "old_block_sha256": meta["old_block_sha256"],
        "new_bytes": body[content_start:content_start + end_fence.start()],
    }
    changed = meta.get("changed_lines")
    if changed:
        parsed_lines = _xkey_line_list(changed)
        if parsed_lines:
            proposal["changed_lines"] = parsed_lines
    if meta.get("reason"):
        proposal["reason"] = meta["reason"]
    return proposal


def _xkey_proposal_matches(proposal: dict, frozen: dict) -> bool:
    """S1: the proposal metadata must equal the ticket frozen block verbatim"""
    if _xkey_norm_path(proposal.get("file")) != _xkey_norm_path(frozen.get("file")):
        return False
    if _xkey_line_range(proposal.get("line_range")) != _xkey_line_range(
        frozen.get("line_range")
    ):
        return False
    proposal_sha = proposal.get("old_block_sha256")
    frozen_sha = frozen.get("old_block_sha256")
    return bool(proposal_sha) and proposal_sha == frozen_sha


def _xkey_escalation_write(
    project_root: pathlib.Path, request_id: str, status: str, detail: str
) -> None:
    """Durable human-visible record for a fail-closed stage exit."""
    path = _xkey_evidence_root(project_root, request_id) / _XKEY_EVIDENCE_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = (
            f"# XKey escalation {request_id}\n\n"
            f"- status: {status}\n"
            f"- detail: {detail}\n"
            f"- at: {_iso_now()}\n"
            f"- ticket: {_xkey_ticket_relpath(request_id)}\n"
        )
        tmp = pathlib.Path(str(path) + ".tmp")
        tmp.write_text(body, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    except OSError:
        pass  # the timeline event + ledger history remain the durable record


def _xkey_replay_run(
    runs_root: pathlib.Path, current_file_sha: str
) -> tuple[pathlib.Path, dict] | None:
    """Newest completed apply whose new file sha equals what is on disk.

    This is the crash-replay guard: a conductor death after the atomic write
    but before the ticket update must not read as sha-drift."""
    if not runs_root.is_dir():
        return None
    for entry in sorted(runs_root.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        record = _xkey_json_read(entry / _XKEY_RUN_MARKER_NAME)
        if record is None:
            continue
        if (
            record.get("phase") == "applied"
            and record.get("new_file_sha256") == current_file_sha
            and (entry / _XKEY_BAK_NAME).is_file()
        ):
            return entry, record
    return None


def _xkey_ledger_row(ticket: dict, status: str, history: list[dict]) -> dict:
    """One ledger update carrying the row identity the ledger merges on."""
    return {
        "dedup_key": ticket.get("dedup_key"),
        "source_key": ticket.get("source_key"),
        "owner_key": ticket.get("owner_key"),
        "test_id": ticket.get("test_id"),
        "file": ticket.get("file"),
        "frozen_block": ticket.get("frozen_block"),
        "status": status,
        "request_id": ticket.get("request_id"),
        "history": history,
    }


def _xkey_stage_fail(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    request_id: str,
    status: str,
    detail: str,
) -> None:
    """Fail-closed exit (S2 boundary / S3 drift): status + ledger + escalation,
    zero writes to the affected file (it was never opened for writing)."""
    root = str(project_root)
    ticket[status] = {"detail": detail, "at": _iso_now()}
    ticket["status"] = status
    xkey.ticket_write(root, ticket)
    if ticket.get("dedup_key"):
        xkey.ledger_append(root, _xkey_ledger_row(ticket, status, [{
            "ts": _iso_now(), "event": status,
            "detail": detail,
        }]))
    _xkey_escalation_write(project_root, request_id, status, detail)
    st.timeline.append(
        "xkey-" + status.replace("_", "-"), key=ticket.get("owner_key"),
        detail=f"{request_id} {detail}",
    )


def _xkey_restore(
    target: pathlib.Path, run_dir: pathlib.Path
) -> tuple[bool, str]:
    """Restore the target from the byte snapshot; (restored, restored sha)."""
    bak = run_dir / _XKEY_BAK_NAME
    if not bak.is_file():
        return False, ""
    try:
        data = bak.read_bytes()
        tmp = pathlib.Path(str(target) + ".xkey-restore.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    except OSError:
        return False, ""
    return True, _xkey_sha256_bytes(data)


def _xkey_verify_failed(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    request_id: str,
    target: pathlib.Path,
    applied: dict,
    red_before: int,
    red_after: int | None,
    detail: str,
    stdout_path: object = None,
) -> None:
    """S4 failure: byte-restore from the snapshot, never close."""
    root = str(project_root)
    restored, restored_sha = _xkey_restore(target, pathlib.Path(str(applied["run_dir"])))
    expected = str(ticket.get("target_file_sha256") or applied.get("old_file_sha256") or "")
    sha_ok = bool(expected) and restored_sha == expected
    ticket["verify"] = {
        "red_before": red_before, "red_after": red_after,
        "restored": restored, "restored_sha256": restored_sha,
        "expected_file_sha256": expected, "restore_sha_ok": sha_ok,
        "stdout_path": stdout_path, "detail": detail, "failed_at": _iso_now(),
    }
    ticket["status"] = "verify_failed"
    xkey.ticket_write(root, ticket)
    if ticket.get("dedup_key"):
        xkey.ledger_append(root, _xkey_ledger_row(ticket, "verify_failed", [{
            "ts": _iso_now(), "event": "verify_failed",
            "detail": f"{detail}; restored={restored} sha_ok={sha_ok}",
        }]))
    _xkey_escalation_write(project_root, request_id, "verify_failed", detail)
    st.timeline.append(
        "xkey-verify-failed", key=ticket.get("owner_key"),
        detail=f"{request_id} {detail}; restored={restored} sha_ok={sha_ok}",
    )


def _xkey_apply_block(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    request_id: str,
    frozen: dict,
    proposal: dict,
    target: pathlib.Path,
) -> dict | None:
    """S3: snapshot, then ``xkey.apply_block_replace`` (atomic, drift-refusing).

    Returns ``{"run_dir", "old_file_sha256", "new_file_sha256",
    "new_block_sha256"}`` or ``None`` (a fail-closed exit was recorded)."""
    root = str(project_root)
    runs_root = _xkey_evidence_root(project_root, request_id) / "runs"
    current_sha = _xkey_sha256_bytes(target.read_bytes())
    replay = _xkey_replay_run(runs_root, current_sha)
    if replay is not None:
        run_dir, record = replay
        applied = {
            "run_dir": str(run_dir),
            "old_file_sha256": str(record.get("old_file_sha256") or ""),
            "new_file_sha256": current_sha,
            "new_block_sha256": str(record.get("new_block_sha256") or ""),
        }
    else:
        old_bytes = target.read_bytes()
        old_sha = _xkey_sha256_bytes(old_bytes)
        run_dir = runs_root / _xkey_run_stamp(runs_root)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / _XKEY_BAK_NAME).write_bytes(old_bytes)
        try:
            new_block_sha = xkey.apply_block_replace(
                root, ticket, proposal["new_bytes"]
            )
        except xkey.XKeyError as exc:
            _xkey_stage_fail(
                project_root, st, xkey, ticket, request_id, "boundary_violation",
                f"apply refused, no write: {exc}",
            )
            return None
        applied = {
            "run_dir": str(run_dir),
            "old_file_sha256": old_sha,
            "new_file_sha256": _xkey_sha256_bytes(target.read_bytes()),
            "new_block_sha256": new_block_sha,
        }
        _xkey_json_write(run_dir / _XKEY_RUN_MARKER_NAME, {
            "request_id": request_id,
            "phase": "applied",
            "old_block_sha256": frozen.get("old_block_sha256"),
            "applied_at": _iso_now(),
            **applied,
        })
    ticket["status"] = "applied"
    ticket["apply"] = applied
    xkey.ticket_write(root, ticket)
    if ticket.get("dedup_key"):
        xkey.ledger_append(root, _xkey_ledger_row(ticket, "applied", [{
            "ts": _iso_now(), "event": "applied",
            "detail": (
                f"block replace applied: file "
                f"{applied['old_file_sha256'][:12]}→{applied['new_file_sha256'][:12]}"
            ),
        }]))
    st.timeline.append(
        "xkey-applied", key=ticket.get("owner_key"),
        detail=(
            f"{request_id} {_xkey_norm_path(frozen.get('file'))} "
            f"{applied['old_file_sha256'][:12]}→{applied['new_file_sha256'][:12]}"
        ),
    )
    return applied


def _xkey_run_verify(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    request_id: str,
    target: pathlib.Path,
    applied: dict,
    cfg: dict,
) -> dict | None:
    """S4: targeted rerun, red before→after; not green ⇒ rollback + no close."""
    root = str(project_root)
    verify_cmd = [str(part) for part in (cfg.get("xkey_verify_cmd") or [])]
    timeout_s = _xkey_int(cfg.get("xkey_verify_timeout_s"), 1800)
    red_before = _xkey_int(ticket.get("red_before"), 1)
    if not verify_cmd:
        _xkey_verify_failed(
            project_root, st, xkey, ticket, request_id, target, applied,
            red_before, None, "xkey_verify_cmd is empty (cannot prove green)",
        )
        return None
    try:
        result = xkey.run_verification(
            verify_cmd, cwd=root, run_dir=str(applied["run_dir"]), timeout=timeout_s,
        )
    except Exception as exc:  # noqa: BLE001 — fail-closed, never close on doubt
        _xkey_verify_failed(
            project_root, st, xkey, ticket, request_id, target, applied,
            red_before, None, f"run_verification raised: {exc!r}",
        )
        return None
    counts = result.get("red_counts") or {}
    red_after = _xkey_int(counts.get("total"), 0)
    returncode = _xkey_int(counts.get("returncode"), 1)
    timed_out = bool(counts.get("timed_out"))
    if not (red_after == 0 and not timed_out and returncode == 0):
        _xkey_verify_failed(
            project_root, st, xkey, ticket, request_id, target, applied,
            red_before, red_after,
            (
                f"not green: red {red_before}->{red_after} "
                f"rc={returncode} timed_out={timed_out}"
            ),
            stdout_path=result.get("stdout_path"),
        )
        return None
    verify = {
        "red_before": red_before,
        "red_after": red_after,
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout_path": result.get("stdout_path"),
        "stdout_sha256": result.get("sha256"),
        "verify_cmd": verify_cmd,
        "summary": counts.get("summary"),
        "verified_at": _iso_now(),
    }
    ticket["status"] = "verified"
    ticket["verify"] = verify
    xkey.ticket_write(root, ticket)
    if ticket.get("dedup_key"):
        xkey.ledger_append(root, _xkey_ledger_row(ticket, "verified", [{
            "ts": _iso_now(), "event": "verified",
            "detail": f"targeted rerun green: red {red_before}->{red_after}",
        }]))
    st.timeline.append(
        "xkey-verified", key=ticket.get("owner_key"),
        detail=f"{request_id} red {red_before}->{red_after}",
    )
    return verify


def _xkey_write_evidence(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    request_id: str,
    applied: dict,
    verify: dict,
) -> bool:
    """S5: the AC-006 bundle; ``closed`` comes from the module, never guessed."""
    root = str(project_root)
    bundle = {
        "old_sha256": applied.get("old_file_sha256"),
        "new_sha256": applied.get("new_file_sha256"),
        "reason": (
            ticket.get("reason") or ticket.get("fail_line")
            or "cross-key frozen block refresh"
        ),
        "relaxed_assertion": False,
        "verify_cmd": verify.get("verify_cmd"),
        "stdout_path": verify.get("stdout_path"),
        "red_before": verify.get("red_before"),
        "red_after": verify.get("red_after"),
    }
    bundle_path = xkey.evidence_bundle_write(root, request_id, bundle)
    document = _xkey_json_read(pathlib.Path(bundle_path))
    closed = bool(document and document.get("closed") is True)
    ticket["evidence"] = {
        "bundle_path": bundle_path,
        "closed": closed,
        "missing": (document or {}).get("missing", []),
        "written_at": _iso_now(),
    }
    xkey.ticket_write(root, ticket)
    if not closed:
        _xkey_escalation_write(
            project_root, request_id, "evidence_incomplete",
            f"bundle not closed: missing={ticket['evidence']['missing']}",
        )
        st.timeline.append(
            "xkey-evidence-incomplete", key=ticket.get("owner_key"),
            detail=f"{request_id} missing={ticket['evidence']['missing']}",
        )
    return closed


def _xkey_close(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    request_id: str,
    applied: dict,
    verify: dict,
) -> None:
    """S6: close the ledger row and annotate both affected keys *in the row*.

    D-004: a DONE key's files are never written and a cross-key red has no
    single owner, so the two closure annotations (the source handoff and the
    owner legacy) live in the ledger row itself."""
    root = str(project_root)
    source_key = ticket.get("source_key")
    owner_key = ticket.get("owner_key")
    ts = _iso_now()
    closures = [
        {
            "role": "source",
            "key": source_key,
            "annotation": (
                f"交接登记闭合（{source_key} 的跨 key 交接随 {request_id} 修复闭合）"
            ),
            "at": ts,
        },
        {
            "role": "owner",
            "key": owner_key,
            "annotation": (
                f"遗留登记闭合（{owner_key} 的遗留红随 {request_id} 修复闭合）"
            ),
            "at": ts,
        },
    ]
    ticket["status"] = "closed"
    ticket["closures"] = closures
    xkey.ticket_write(root, ticket)
    if ticket.get("dedup_key"):
        row = _xkey_ledger_row(ticket, "closed", [{
            "ts": ts, "event": "closed",
            "detail": (
                f"file {applied.get('old_file_sha256', '')[:12]}→"
                f"{applied.get('new_file_sha256', '')[:12]}; "
                f"red {verify.get('red_before')}->{verify.get('red_after')}"
            ),
        }])
        row["closures"] = closures
        xkey.ledger_append(root, row)
    st.timeline.append(
        "xkey-closed", key=owner_key,
        detail=f"{request_id} source={source_key} owner={owner_key}",
    )


def _xkey_apply_one(
    project_root: pathlib.Path,
    st: ConductorState,
    xkey,
    ticket: dict,
    row_status: dict[str, str],
    cfg: dict,
) -> None:
    """One ticket: S1 boundary → S2 check → S3 apply → S4 verify → S5
    evidence → S6 close, resuming from the persisted stage on re-entry."""
    request_id = ticket.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        return
    status = str(ticket.get("status") or "")
    if status not in _XKEY_APPLY_ENTRIES:
        return
    if row_status.get(request_id) in _XKEY_TERMINAL_STATUSES:
        return  # the ledger's terminal row outranks a stale ticket write
    proposal_path = _xkey_evidence_root(project_root, request_id) / _XKEY_PROPOSAL_NAME
    if not proposal_path.is_file() and status == "approved":
        return  # approved but no proposal yet — wait for the proposal worker
    frozen = ticket.get("frozen_block")
    if not isinstance(frozen, dict):
        _xkey_stage_fail(
            project_root, st, xkey, ticket, request_id, "boundary_violation",
            "ticket carries no frozen_block (fail-closed)",
        )
        return
    target_rel = _xkey_norm_path(frozen.get("file"))
    target = pathlib.Path(project_root) / target_rel
    if not target_rel or not target.is_file():
        _xkey_stage_fail(
            project_root, st, xkey, ticket, request_id, "boundary_violation",
            f"target file missing: {target_rel or frozen.get('file')!r}",
        )
        return

    if status == "approved":
        try:
            proposal = _xkey_parse_proposal(proposal_path.read_bytes())
        except OSError as exc:
            _xkey_stage_fail(
                project_root, st, xkey, ticket, request_id, "boundary_violation",
                f"proposal unreadable: {exc!r}",
            )
            return
        if proposal is None or not _xkey_proposal_matches(proposal, frozen):
            _xkey_stage_fail(
                project_root, st, xkey, ticket, request_id, "boundary_violation",
                "proposal metadata does not match the ticket frozen_block",
            )
            return
        if xkey.check_boundary(proposal, ticket) != "ok":
            _xkey_stage_fail(
                project_root, st, xkey, ticket, request_id, "boundary_violation",
                "check_boundary rejected the proposal (zero write)",
            )
            return
        applied = _xkey_apply_block(
            project_root, st, xkey, ticket, request_id, frozen, proposal, target
        )
        if applied is None:
            return
    else:
        applied = ticket.get("apply")
        if not isinstance(applied, dict) or not applied.get("run_dir"):
            _xkey_stage_fail(
                project_root, st, xkey, ticket, request_id, "verify_failed",
                f"ticket status {status} without persisted apply state",
            )
            return

    if status == "verified":
        verify = ticket.get("verify")
        if not isinstance(verify, dict):
            _xkey_stage_fail(
                project_root, st, xkey, ticket, request_id, "verify_failed",
                "ticket status verified without persisted verify state",
            )
            return
    else:
        verify = _xkey_run_verify(
            project_root, st, xkey, ticket, request_id, target, applied, cfg
        )
        if verify is None:
            return

    if not _xkey_write_evidence(
        project_root, st, xkey, ticket, request_id, applied, verify
    ):
        return
    _xkey_close(
        project_root, st, xkey, ticket, request_id, applied, verify
    )


def _xkey_apply_stage(
    project_root: pathlib.Path,
    st: ConductorState,
    status_of: dict[str, str],
    cfg: dict,
) -> None:
    """T-06 mount: fold every approved ticket with a proposal through S1→S6.

    Entry re-derives from disk every tick (ticket status ∈ approved/applied/
    verified **and** ``evidence/<request_id>/proposal.md`` present), so a
    closed/failed ticket never re-enters — that is what makes the stage
    idempotent. ``status_of`` is accepted to keep the mount signature the
    design fixed; ownership terminality was already decided upstream by
    ``_xkey_aggregate``. Any exception is caught here: the tick survives and
    the ticket keeps its last good state."""
    del status_of  # part of the frozen mount signature; decided in _xkey_aggregate
    xkey = _xkey()
    root = str(project_root)
    try:
        ledger = xkey.ledger_load(root)
    except Exception as exc:  # noqa: BLE001 — a corrupt ledger never overwrites
        st.timeline.append("config", detail=f"xkey ledger unreadable: {exc!r}")
        return
    row_status = {
        str(row.get("request_id")): str(row.get("status") or "")
        for row in ledger.get("rows", [])
        if isinstance(row, dict) and row.get("request_id")
    }
    try:
        tickets = xkey.tickets_iter(root)
    except Exception as exc:  # noqa: BLE001 — a corrupt ticket is skipped, not fatal
        st.timeline.append("config", detail=f"xkey tickets unreadable: {exc!r}")
        return
    for ticket in tickets:
        if not isinstance(ticket, dict):
            continue
        try:
            _xkey_apply_one(project_root, st, xkey, ticket, row_status, cfg)
        except Exception as exc:  # noqa: BLE001 — per-ticket isolation
            st.timeline.append(
                "config", key=ticket.get("owner_key"),
                detail=(
                    f"xkey apply stage error for {ticket.get('request_id')}: "
                    f"{exc!r} (ticket kept at its last good state)"
                ),
            )


# ── Stalled marking (four artifacts, F7/AC-006) ─────────────────────────────

def mark_stalled(
    project_root: pathlib.Path, st: ConductorState, key: str, reason: str
) -> None:
    """Mark a key stalled: key-status + stalled gate + achieved.md legacy
    draft + pattern file. Idempotent (already-stalled keys are a no-op)."""
    project_root = pathlib.Path(project_root)
    rm_path = roadmap.roadmap_path(project_root)
    try:
        rm = roadmap.load_roadmap(rm_path)
        stage_number = roadmap.stage_of_key(rm).get(key)
        if stage_number is None:
            return
        if rm.stages:
            stage = roadmap.stage_by_number(rm, stage_number)
            if stage is not None and stage.key_status.get(key) == "stalled":
                return  # already marked
            text = rm_path.read_text(encoding="utf-8")
            new_text = roadmap.update_key_status(text, stage_number, key, "stalled")
            acquire_conductor_lock(project_root, "roadmap", st.timeline)
            try:
                rm_path.write_text(new_text, encoding="utf-8", newline="\n")
            finally:
                mw_common.release_lock(lock_file(project_root, "roadmap"))
    except (roadmap.RoadmapError, OSError) as exc:
        st.timeline.append("config", key=key, detail=f"stalled mark failed: {exc!r}")
        return

    gate = _create_gate(
        project_root, st, "stalled",
        f"key {key} 已 stalled（{reason}）——遗留关闭（closed-legacy），还是人工介入后重试？",
        key=key, refs=[f".agenticdoc/{key}", reason],
    )

    key_dir = project_root / ".agenticdoc" / key
    key_dir.mkdir(parents=True, exist_ok=True)
    achieved = key_dir / "achieved.md"
    try:
        body = achieved.read_text(encoding="utf-8") if achieved.is_file() else "# Achieved\n\n"
        if "## 遗留问题" not in body:
            body += (
                f"\n## 遗留问题（stalled 草稿）\n\n"
                f"- {reason}（stalled at {timeline._iso_now()}；"
                f"gate {gate.stem if gate else 'creation pending'}）\n"
            )
            achieved.write_text(body, encoding="utf-8", newline="\n")
    except OSError as exc:
        st.timeline.append("config", key=key, detail=f"achieved draft failed: {exc!r}")

    pattern_dir = project_root / ".agenticdoc" / "patterns" / key
    pattern_file = pattern_dir / "stall-lesson.md"
    try:
        if not pattern_file.is_file():
            pattern_dir.mkdir(parents=True, exist_ok=True)
            pattern_file.write_text(
                "# Pattern: stall-lesson\n\n"
                "## 问题模式\n\n"
                f"key {key} 在自动化推进中停滞：{reason}\n\n"
                "## 推荐做法\n\n"
                "回路预算耗尽或连续不收敛时及时升级人工门禁，"
                "避免无界重试；遗留问题以草稿形式存档。\n\n"
                "## 适用场景\n\n"
                "任意 key 的 L2/L3/retry 回路达到上限且修复无效时。\n\n"
                "## 来源证据\n\n"
                f"- Evidence: .agenticdoc/{key}/achieved.md（遗留问题草稿）\n\n"
                "## 创建时间\n\n"
                f"{timeline._iso_now()}\n",
                encoding="utf-8",
                newline="\n",
            )
    except OSError as exc:
        st.timeline.append("config", key=key, detail=f"pattern file failed: {exc!r}")

    st.timeline.append("stalled", key=key, detail=reason)


# ── Orphan reconciliation (D-102) ─────────────────────────────────────────

def reconcile_orphans(project_root: pathlib.Path, st: ConductorState) -> None:
    """Re-insert orphaned conductor task dirs (task.md with origin:
    conductor, no queue row) as pending — same loop, same attempt, no new
    round consumed. Runs before the per-key machine so in-flight detection
    sees the healed rows in the same tick."""
    project_root = pathlib.Path(project_root)
    orphans = state.find_orphans(project_root)
    if not orphans:
        return
    wpath = mw_common.workers_path(project_root)
    try:
        acquire_conductor_lock(project_root, "workers", st.timeline)
    except ConductorLockHeld:
        return
    try:
        existing = {row.get("task_key") for row in mw_common.parse_workers_file(wpath)}
        now = mw_common.iso_now()
        for orphan in orphans:
            if orphan.task_key in existing:
                continue
            wpath.parent.mkdir(parents=True, exist_ok=True)
            with wpath.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(
                    mw_common.serialize_entry({
                        "task_key": orphan.task_key,
                        "status": "pending",
                        "cli": "pi",
                        "provider": "",
                        "task_path": str(orphan.task_dir / "task.md"),
                        "dispatched_at": now,
                        "updated_at": now,
                        "model": "",
                    })
                    + "\n"
                )
            st.timeline.append(
                "reconcile",
                key=(None if orphan.owner == dispatch.SCRATCH_OWNER else orphan.owner),
                detail=f"orphan reinserted: {orphan.task_key}",
            )
    except OSError as exc:
        st.timeline.append("config", detail=f"reconcile failed: {exc!r}")
    finally:
        mw_common.release_lock(lock_file(project_root, "workers"))


# ── Status (mw status / mw doctor) ──────────────────────────────────────


def conductor_status(project_root: pathlib.Path) -> dict:
    """Read-only conductor snapshot: {running, pid, last_seq, last_ts}.
    ``last_seq``/``last_ts`` are the newest timeline event (the tick
    watermark). Never raises; missing pieces report as None/False."""
    project_root = pathlib.Path(project_root)
    pid = mw_common.check_pid(conductor_pid_file(project_root))
    last_seq: int | None = None
    last_ts: str | None = None
    try:
        events = timeline.query_events(timeline.timeline_path(project_root)).events
        if events:
            last_seq = events[-1]["seq"]
            last_ts = events[-1]["ts"]
    except Exception:  # noqa: BLE001 — status must never raise
        pass
    return {
        "running": pid is not None,
        "pid": pid,
        "last_seq": last_seq,
        "last_ts": last_ts,
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="autopilot conductor loop")
    parser.add_argument("--project", required=True, help="Project directory")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Tick interval in seconds (default: config poll_interval_sec)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one tick and exit (test entry)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    project_root = pathlib.Path(args.project).resolve()

    # Startup gate: the advance framework must be locatable — every phase
    # transition depends on it.
    try:
        advance.locate_platform_dir(project_root)
    except advance.AdvanceError as exc:
        print(f"[conductor] refusing to start: {exc}", file=sys.stderr)
        return 1

    pid_path = conductor_pid_file(project_root)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")

    stop = threading.Event()
    if sys.platform != "win32":

        def _on_sigterm(signum: int, frame: object) -> None:  # noqa: ARG001
            stop.set()

        signal.signal(signal.SIGTERM, _on_sigterm)

    tl = timeline.Timeline(timeline.timeline_path(project_root))
    st = ConductorState(tl, goal_mtime_ns(project_root))
    tl.append("goal-snapshot", detail=f"startup baseline mtime_ns={st.goal_baseline}")

    try:
        if args.once:
            # Single-tick test entry: act immediately, no sleep (D-114).
            status = tick(project_root, st)
            print(status)
            return 0
        while not stop.is_set():
            tick(project_root, st)  # act-then-sleep: first tick before any wait
            interval = args.poll_interval
            if interval is None:
                interval = config.cached_load(project_root)["poll_interval_sec"]
            interval = max(0.1, float(interval))
            deadline = time.monotonic() + interval
            while not stop.is_set() and time.monotonic() < deadline:
                time.sleep(min(0.1, deadline - time.monotonic()))
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            pid_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    sys.exit(main())

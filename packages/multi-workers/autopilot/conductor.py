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

from autopilot import advance, audit_evidence, config, dispatch, gates, roadmap, state, timeline  # noqa: E402

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
    if not _consume_answered_gates(project_root, st):
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

    # Stalled keys whose stalled gate was rejected → closed-legacy (F7).
    _apply_stalled_rejections(project_root, st, status_of, stage_of)

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


def _consume_answered_gates(project_root: pathlib.Path, st: ConductorState) -> bool:
    """§5.1 F: apply answered-gate transitions. Returns False when a corrupt
    gate file forces a tick skip (timeline config event appended).

    Idempotent by file truth: a transition fires (gate-answered event) only
    when it actually changes the roadmap, so an answered gate is consumed
    exactly once across ticks and conductor restarts. stalled-reject is
    consumed by _apply_stalled_rejections (it owns the key-status rewrite);
    budget-exhausted / goal-change gates are polled, not transitioned."""
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
        if gate.status == "pending" or gate.stage is None:
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
    when the T-12 EXECUTE loop wrote it, else none (T-11 dossier shape)."""
    verdict_file = key_dir / "l3-verdict.txt"
    if verdict_file.is_file():
        verdict = verdict_file.read_text(encoding="utf-8").strip().lower()
        if verdict in ("meets", "below"):
            report = key_dir / "l3-report.md"
            return verdict, str(report) if report.is_file() else "—"
    return "none", "—"


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
        st.timeline.append(
            "advance", key=key, detail=f"{phase}->{nxt} exit={code}"
        )
        if code != 0:
            st.timeline.append("config", key=key, detail=f"advance failed: {err.strip()[:200]}")
        elif nxt == "done":
            _mark_key_done(project_root, st, key, rm_path)
        return False

    # Gaps → L2 adjudication round (D-111 round units).
    edge = f"{phase}-to-{nxt}"
    loop = f"l2:{key}:{edge}"
    used = rounds.get(loop, 0)
    budget = max(1, int(cfg["round_budget"]))
    bonus = _budget_bonus(project_root, loop)
    allowed = used < budget or (bonus and used < budget + 1)

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
        if bonus and used >= budget + 1:
            mark_stalled(
                project_root, st, key, f"L2 bonus round exhausted at {loop}"
            )
            return False
        if not _gate_open(project_root, "budget-exhausted", loop=loop):
            gate = _create_gate(
                project_root, st, "budget-exhausted",
                f"L2 回路 {loop} 已达 {budget} 轮上限且仍有缺口——追加一轮修复，还是标记 stalled？",
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
    plan = _plan_text(key_dir)
    for stem in _plan_task_order([f.stem for f in files], plan):
        loop = f"exec:{key}:{stem}"
        fam = _family_rows(rows, key, stem)
        if any(r["status"] == "done" for r in fam):
            continue  # task complete
        if any(_is_in_flight(r) for r in fam):
            return False  # per-key serial: wait for the in-flight task
        used = rounds.get(loop, 0)
        if used >= budget:
            mark_stalled(
                project_root, st, key,
                f"exec task {stem} exhausted {used}/{budget} attempts",
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
    st.timeline.append("advance", key=key, detail=f"execute->verify exit={code}")
    if code != 0:
        st.timeline.append(
            "config", key=key, detail=f"advance verify failed: {err.strip()[:200]}"
        )
    return False


# ── VERIFY: L3 review loop + done transaction (D-108/D-112, T-12) ────────────

_L3_BUDGET = 2  # 复评总轮数 ≤ 2 (AC-010)


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
        "  ## Quality Gate Report（VC 断言表逐条 PASS/FAIL + needs-rerun + 证据引用）\n"
        "  ## Achieved（达成摘要：做了什么 / 目标收益 / 遗留什么）"
    )


def _repair_prompt(key: str, attempt: int) -> str:
    return (
        f"修复 L3 裁决 below 的问题（key {key}，第 {attempt} 轮）:\n"
        f"- L3 报告：.agenticdoc/{key}/workers/ap-{key}-l3-a{attempt}/output.md"
        "（## Quality Gate Report 的 FAIL 项与 needs-rerun 遗留）\n"
        "- 逐项修复并补充 [VERIFY] 证据到 evidence/；不重写无关 artifact"
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
    used = rounds.get(l3_loop, 0)
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
    verdict = _parse_l3_output(project_root, key, used)
    if verdict == "meets":
        l3_output = (
            key_dir / "workers" / dispatch.task_key_for(key, f"l3-a{used}") / "output.md"
        )
        if _done_transaction(project_root, st, key, l3_output) != "below":
            return False  # advanced (or gated — retried next tick)
        # meets-but-short achieved draft → same repair path as below
    if used >= _L3_BUDGET:
        mark_stalled(
            project_root, st, key,
            f"L3 below {_L3_BUDGET} rounds (budget {_L3_BUDGET})",
        )
        return False
    repair_base = f"repair-a{used}"
    fam = _family_rows(rows, key, repair_base)
    if not any(r["status"] == "done" for r in fam):
        repair_used = rounds.get(f"repair:{key}", 0)
        if any(_is_in_flight(r) for r in fam):
            return False
        if repair_used >= max(1, int(cfg["round_budget"])):
            mark_stalled(
                project_root, st, key,
                f"repair exhausted {repair_used} attempts at L3 round {used}",
            )
            return False
        retry = repair_used > 0
        stem_arg = f"{repair_base}-a{repair_used + 1}" if retry else repair_base
        result = dispatch.dispatch(
            project_root, key, stem_arg, "repair",
            _repair_prompt(key, used),
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
) -> str:
    """meets → mechanical done transaction (D-108 增补 1). Returns
    advanced | below | gated. Every step is check-before-write, so a crash
    mid-transaction resumes cleanly on the next tick (AC-022)."""
    project_root = pathlib.Path(project_root)
    key_dir = project_root / ".agenticdoc" / key
    ks = state.read_key_states(project_root).get(key)
    if ks is not None and ks.phase.strip().upper() == "DONE":
        return "advanced"  # crash-after-advance resume
    try:
        text = l3_output.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "below"
    qg = _md_section(text, "## Quality Gate Report")
    achieved = _md_section(text, "## Achieved")
    if qg is None or achieved is None:
        return "below"
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
        # 2. achieved.md draft (only when absent/short — never clobbers a
        #    ≥200B draft from an earlier attempt of the same verdict)
        achieved_path = key_dir / "achieved.md"
        if not (achieved_path.is_file() and achieved_path.stat().st_size >= 200):
            achieved_path.write_text(
                achieved.rstrip() + "\n", encoding="utf-8", newline="\n"
            )
        # 3. 后验 ≥200B — short draft = L3 output quality issue → below path
        if achieved_path.stat().st_size < 200:
            st.timeline.append(
                "config", key=key,
                detail="L3 achieved draft < 200B → below (repair path, no padding)",
            )
            return "below"
        # 4. pm-state PASS line under the per-key lock
        if not _append_pass_line(project_root, st, key, qg_path):
            return "gated"  # lock held — retry next tick
        # 5. advance done (framework gates re-verify the 三件套)
        code, _out, err = advance.advance(
            key, "done", project_root, summary="autopilot L3 meets"
        )
        st.timeline.append("advance", key=key, detail=f"verify->done exit={code}")
        if code != 0:
            st.timeline.append(
                "config", key=key, detail=f"advance done failed: {err.strip()[:200]}"
            )
            return "gated"
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
                return "gated"
        return "advanced"
    except OSError as exc:
        st.timeline.append("config", key=key, detail=f"done transaction IO failed: {exc!r}")
        return "gated"


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


def _missing_plan_tasks(key_dir: pathlib.Path) -> list[dict]:
    """Plan-referenced T-NN-slug stems with no tasks/ file — synthetic
    blocking gaps for the tasks→execute boundary (D-111)."""
    tasks_dir = key_dir / "tasks"
    present = {f.stem for f in tasks_dir.glob("*.md")} if tasks_dir.is_dir() else set()
    plan = _plan_text(key_dir)
    if not plan:
        return []
    referenced = sorted(set(re.findall(r"\bT-\d{2,3}-[A-Za-z0-9][A-Za-z0-9-]*", plan)))
    return [
        {"item": f"plan 任务 {stem} 在 tasks/ 缺失", "rule": "execute-gate"}
        for stem in referenced
        if stem not in present
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
) -> bool:
    for gate in gates.enumerate(gates_dir(project_root)):
        if gate.kind != kind or gate.status != "pending":
            continue
        if loop is not None and loop not in gate.context_refs:
            continue
        if stage is not None and gate.stage != stage:
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
    except (roadmap.RoadmapError, OSError) as exc:
        st.timeline.append("config", key=key, detail=f"key-done mark failed: {exc!r}")


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
                status_of[key] = "closed-legacy"
        except (roadmap.RoadmapError, OSError) as exc:
            st.timeline.append("config", key=key, detail=f"closed-legacy mark failed: {exc!r}")


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

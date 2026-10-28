"""test_mdc_e2e.py - MDC B4 end-to-end concurrency refutation + quantification.

Card: `.agenticdoc/mw-dynamic-concurrency/tasks/T-C-M06-e2e-concurrency.md`
key : `mw-dynamic-concurrency` (batch B4)

This file adds **no production behaviour**. It drives the real
``conductor.tick`` -> ``execute_loop`` path over constructed fixtures, reads
the *measured* dispatch rows out of the real queue file
(``.agenticdoc/_workers.parallel`` via ``mw_common.parse_workers_file``), and
quantifies the four B4 questions with raw, reproducible samples:

* VC-105  N >= 4 parallel start; the in-flight rows are recomputed with the
          write-face judgement **body** (``dispatch._parse_inflight_write_face``
          -> ``write_face.overlap`` -> ``dispatch._write_face_verdict``), never
          a second overlap algorithm.  Same-file multi-writer pairs must be 0.
* VC-106  concurrent injection on ONE ``task_key`` through two real processes
          (direct entry) and the conductor dispatch-loop entry with a stale
          snapshot.  Exactly 1 grant, 1 queue row, 1 ``dispatch`` event; the
          refused side's reason has the ``duplicate-dispatch:`` prefix.
* VC-109  real ``advance_phase.py`` subprocess samples (the M-02 harness shape:
          probe must run from ``packages/multi-workers/`` so ``FRAMEWORK`` is
          derived from ``__file__``), then
          ``window_share = sum(advance_ms) / (sum(advance_ms) + n*idle_tick_ms)``.
* AC-002  the cross-tick top-up window: while any row of the key is still in
          flight the freed slots are NOT refilled.  Measured in tick turns and
          idle slot-ticks.  Quantification only - ``orchestrate`` /
          ``execute_loop`` are not touched.

Only injected seam: ``advance.advance`` (no-op returning exit 0) in the
frontier/dispatch tests, exactly like ``test_mdc_concurrency.py``.  VC-109
deliberately does NOT inject it (it must spawn the real subprocess).

Run: cd packages/multi-workers; python -m pytest -q test_mdc_e2e.py
     (add -s to capture the [VERIFY] raw-sample lines)
"""
from __future__ import annotations

import itertools
import json
import pathlib
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import mw_common  # noqa: E402
from autopilot import advance as advance_mod  # noqa: E402
from autopilot import config, conductor, dispatch, timeline, write_face  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
FRAMEWORK = REPO_ROOT / ".agents" / "skills" / "agentic-task"


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


# ---------------------------------------------------------------------------
# harness (same shape as the M-02 probe / test_mdc_concurrency.py)
# ---------------------------------------------------------------------------


def _project(root: pathlib.Path) -> pathlib.Path:
    """Minimal enabled autopilot project."""
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(root, cfg)
    return root


def _roadmap(project: pathlib.Path, keys: dict[str, str | None]) -> None:
    """One running stage; ``keys`` maps key -> depends_on (None = '-')."""
    key_status = ", ".join(f"{key}=running" for key in keys)
    rows = "\n".join(f"| {key} | worker | {dep or '-'} |" for key, dep in keys.items())
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        "# Roadmap\n> generated_at: t\n> goal_mtime: 1\n\n"
        "## Stage 1: work\n> goal: deliver\n> status: running\n"
        f"> key-status: {key_status}\n### Keys\n"
        "| key | role | depends_on |\n|-----|------|-----------|\n"
        f"{rows}\n",
        encoding="utf-8",
    )
    index = "\n".join(
        f"| {key} | active | EXECUTE | \u2014 | - | d | 2026-09-10T00:00:00 |"
        for key in keys
    )
    (project / ".agenticdoc" / "_index.parallel").write_text(index + "\n", encoding="utf-8")


def _card(
    project: pathlib.Path,
    key: str,
    stem: str,
    *,
    deps: list[str] | None = None,
    faces: list[str] | None = None,
) -> None:
    """One real task card; ``faces`` -> the ``## 写入允许面`` section."""
    tasks_dir = project / ".agenticdoc" / key / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# {stem}", ""]
    if deps:
        lines += [f"- deps: {', '.join(deps)}", ""]
    if faces:
        lines += ["## 写入允许面", ""]
        lines += [f"- `{face}`" for face in faces]
        lines += [""]
    lines += [
        "## 上下文", "", "MDC e2e corpus.", "",
        "## 要求", "", "Do the work.", "",
        "## 交付格式", "", "Write output.md.", "",
    ]
    (tasks_dir / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _set_bounds(
    project: pathlib.Path,
    *,
    max_parallel_keys: int | None = None,
    max_workers_per_key: int | None = None,
) -> None:
    cfg = config.load_config(project)
    if max_parallel_keys is not None:
        cfg["max_parallel_keys"] = max_parallel_keys
    if max_workers_per_key is not None:
        cfg["max_workers_per_key"] = max_workers_per_key
    config.save_config(project, cfg)


def _noop_advance(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """No-op ``advance.advance`` (auto-restored); never spawn the real phase
    machine in the frontier/dispatch tests."""
    calls: list[tuple[str, str]] = []

    def fake(key: str, phase: str, root, summary=None):  # noqa: ANN001, ARG001
        calls.append((key, phase))
        return 0, "", ""

    monkeypatch.setattr(conductor.advance, "advance", fake)
    return calls


def _state(project: pathlib.Path) -> conductor.ConductorState:
    return conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(project)),
        conductor.goal_mtime_ns(project),
    )


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _rows(project: pathlib.Path, prefix: str = "ap-") -> list[dict]:
    """Measured rows from the REAL ``.agenticdoc/_workers.parallel`` file."""
    return [
        row
        for row in mw_common.parse_workers_file(mw_common.workers_path(project))
        if str(row["task_key"]).startswith(prefix)
    ]


def _key_rows(project: pathlib.Path, key: str) -> list[dict]:
    return _rows(project, f"ap-{key}-")


def _task_keys(project: pathlib.Path, key: str) -> set[str]:
    return {row["task_key"] for row in _key_rows(project, key)}


def _set_row(project: pathlib.Path, task_key: str, status: str) -> None:
    wpath = mw_common.workers_path(project)
    entries = mw_common.parse_workers_file(wpath)
    for entry in entries:
        if entry["task_key"] == task_key:
            entry["status"] = status
    wpath.write_text(
        "\n".join(mw_common.serialize_entry(entry) for entry in entries) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _stalled_events(project: pathlib.Path) -> list[dict]:
    return [event for event in _events(project) if event["ev"] == "stalled"]


# ---------------------------------------------------------------------------
# VC-105: N >= 4 parallel start, same-file multi-writer pairs = 0
# ---------------------------------------------------------------------------


def test_vc105_n5_disjoint_write_faces_zero_multi_writer_pairs(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corpus: one running key, 6 dep-free cards whose write faces are
    pairwise disjoint, per-key upper bound 5.  One real ``conductor.tick``
    starts min(5, 6) = 5 workers (N >= 4).  The in-flight set is then taken
    from the real queue and re-judged with the production write-face body:
    ``dispatch._parse_inflight_write_face`` -> ``write_face.overlap`` (the
    operator the gate itself calls), plus a per-row re-run of the real
    ``dispatch._write_face_verdict``.  Zero multi-writer pairs must survive.
    """
    project = _project(tmp_path)
    _roadmap(project, {"k1": None})
    for index in range(6):
        _card(project, "k1", f"T-{index + 1}", faces=[f"src/mod{index}/**"])
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=5)
    _noop_advance(monkeypatch)
    st = _state(project)

    assert conductor.tick(project, st) == "ok"
    rows = _key_rows(project, "k1")
    started = sorted(row["task_key"] for row in rows)
    # corpus invariant: 6 independent disjoint-face tasks, bound 5 => 5
    assert len(started) == 5, started

    # Re-judge the REAL in-flight rows with the production parse + operator.
    base = dispatch.write_face_base(project)
    case_insensitive = dispatch.write_face_case_insensitive()
    parsed: dict[str, write_face.WriteFace] = {}
    for row in rows:
        face = dispatch._parse_inflight_write_face(
            row, base=base, case_insensitive=case_insensitive
        )
        assert isinstance(face, write_face.WriteFace), (row["task_key"], face)
        parsed[row["task_key"]] = face

    judgements = 0
    collisions: list[tuple[str, str, str]] = []
    for left, right in itertools.combinations(sorted(parsed), 2):
        judgements += 1
        verdict = write_face.overlap(parsed[left], parsed[right])
        if write_face.is_overlap(verdict):
            collisions.append((left, right, repr(verdict)))

    # Cross-check through the gate body itself: for each in-flight row, ask the
    # REAL ``_write_face_verdict`` whether its own task.md would be refused
    # against every other in-flight same-owner row (its own task_key is excluded
    # by identity).  ``None`` == admitted, i.e. no overlap.
    gate_verdicts = []
    for row in rows:
        task_md = pathlib.Path(str(row["task_path"])).read_text(
            encoding="utf-8", errors="replace"
        )
        gate_verdicts.append(
            dispatch._write_face_verdict(
                project,
                "k1",
                str(row["task_key"]),
                task_md,
                card_backed=True,
                timeline=None,
            )
        )

    print(f"[VERIFY] VC-105 started_rows={len(rows)} row_set={started}")
    for task_key in sorted(parsed):
        print(
            f"[VERIFY] VC-105 face {task_key}={list(parsed[task_key].allow_entries)}"
        )
    print(
        f"[VERIFY] VC-105 overlap_judgements={judgements} "
        f"collision_pairs={len(collisions)} collisions={collisions} "
        f"gate_none={sum(1 for verdict in gate_verdicts if verdict is None)}"
        f"/{len(gate_verdicts)}"
    )
    _verify(
        "VC-105",
        corpus="6 dep-free cards, pairwise disjoint faces",
        per_key_bound=5,
        started_rows=len(rows),
        overlap_judgements=judgements,
        collision_pairs=len(collisions),
        gate_refusals=sum(1 for verdict in gate_verdicts if verdict is not None),
    )

    assert judgements == 10, judgements  # C(5,2)
    assert collisions == [], collisions
    assert all(verdict is None for verdict in gate_verdicts), gate_verdicts
    assert _stalled_events(project) == []


# ---------------------------------------------------------------------------
# VC-106: concurrent injection on ONE task_key -> exactly one identity
# ---------------------------------------------------------------------------

_OWNER = "k1"
_STEM = "T-01-x"
_TASK_KEY = dispatch.task_key_for(_OWNER, _STEM)

_VC106_CARD = (
    "# T-01-x\n"
    "\n"
    "## 上下文\n"
    "\n"
    "VC-106 corpus.\n"
    "\n"
    "## 要求\n"
    "\n"
    "Do the work.\n"
    "\n"
    "## 写入允许面\n"
    "\n"
    "- `packages/vc106/**`\n"
)

_VC106_CHILD = r"""
import json, os, pathlib, sys, time

pkg, root, owner, stem, barrier = sys.argv[1:6]
sys.path.insert(0, pkg)
from autopilot import dispatch, timeline as tl_mod

root = pathlib.Path(root)
barrier = pathlib.Path(barrier)
(barrier / ("ready-" + str(os.getpid()))).write_text("1", encoding="utf-8")
deadline = time.time() + 60
while not (barrier / "start").exists():
    if time.time() > deadline:
        raise SystemExit("barrier timeout")
    time.sleep(0.005)
tl = tl_mod.Timeline(root / ".agenticdoc" / "_autopilot" / "timeline.jsonl")
r = dispatch.dispatch(
    root, owner, stem, "phase-writer", "Do the work.",
    loop="exec:" + owner + ":" + stem, attempt=1, timeline=tl,
)
print(json.dumps({"ok": r.ok, "reason": r.reason}))
"""


def _bare_project(project: pathlib.Path) -> pathlib.Path:
    """Card-only project for the direct ``dispatch()`` entry (no roadmap)."""
    (project / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    card_dir = project / ".agenticdoc" / _OWNER / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / f"{_STEM}.md").write_text(_VC106_CARD, encoding="utf-8", newline="\n")
    return project


def _conductor_project(project: pathlib.Path) -> pathlib.Path:
    """Conductor harness shape (roadmap + index + card), config enabled."""
    _project(project)
    _roadmap(project, {_OWNER: None})
    card_dir = project / ".agenticdoc" / _OWNER / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    (card_dir / f"{_STEM}.md").write_text(_VC106_CARD, encoding="utf-8", newline="\n")
    return project


def _race_direct(project: pathlib.Path) -> list[dict]:
    """Two real processes race one identity through a file barrier; the
    ``workers.lock`` is never mocked."""
    barrier = project / "_barrier"
    barrier.mkdir()
    procs = [
        subprocess.Popen(
            [
                sys.executable, "-c", _VC106_CHILD, str(HERE), str(project),
                _OWNER, _STEM, str(barrier),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(2)
    ]
    deadline = time.time() + 60
    while len(list(barrier.glob("ready-*"))) < 2:
        if time.time() > deadline:
            break
        time.sleep(0.005)
    (barrier / "start").write_text("go", encoding="utf-8")
    results: list[dict] = []
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, (proc.returncode, err)
        lines = [line for line in out.splitlines() if line.strip()]
        results.append(json.loads(lines[-1]))
    return results


def _vc106_summary(project: pathlib.Path, results: list[dict]) -> dict:
    events = [event["ev"] for event in _events(project)]
    rows = [row for row in _rows(project) if row["task_key"] == _TASK_KEY]
    grants = [result for result in results if result["ok"]]
    refusals = [result for result in results if not result["ok"]]
    return {
        "grants": len(grants),
        "refusals": len(refusals),
        "rows": len(rows),
        "dispatch_events": events.count("dispatch"),
        "refusal_reasons": [result["reason"] for result in refusals],
    }


def test_vc106_direct_entry_two_process_race_single_identity(
    tmp_path: pathlib.Path,
) -> None:
    """Two real ``dispatch()`` processes on the same ``task_key``: exactly one
    grant, one queue row, one ``dispatch`` event; the loser is refused with the
    ``duplicate-dispatch:`` prefix (zero side effects)."""
    project = _bare_project(tmp_path)
    results = _race_direct(project)
    summary = _vc106_summary(project, results)
    _verify(
        "VC-106-direct",
        task_key=_TASK_KEY,
        grants=summary["grants"],
        refusals=summary["refusals"],
        rows=summary["rows"],
        dispatch_events=summary["dispatch_events"],
        reason=summary["refusal_reasons"][0] if summary["refusal_reasons"] else "",
    )

    assert summary["grants"] == 1, results
    assert summary["refusals"] == 1, results
    assert summary["rows"] == 1, summary
    assert summary["dispatch_events"] == 1, summary
    assert summary["refusal_reasons"][0].startswith("duplicate-dispatch:"), summary


def test_vc106_conductor_entry_stale_snapshot_single_identity(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The conductor's dispatch-loop entry (``execute_loop``, the tick's only
    dispatch call site) run twice with the SAME stale ``rows`` snapshot - the
    real window between the tick's queue read and ``dispatch``'s lock re-read.
    Grants/refusals are measured from the real ``DispatchResult`` values via a
    spy, and the refusal must be a wait-class refusal (no ``mark_stalled``)."""
    project = _conductor_project(tmp_path)
    st = _state(project)
    cfg = conductor._load_effective_config(project)  # noqa: SLF001 - probe seam
    stale_rows = _rows(project)  # snapshot taken before either write
    seen: list[dict] = []
    real = dispatch.dispatch

    def spy(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        result = real(*args, **kwargs)
        seen.append({"ok": result.ok, "reason": result.reason})
        return result

    monkeypatch.setattr(dispatch, "dispatch", spy)
    rounds: dict[str, int] = {}
    conductor.execute_loop(project, st, _OWNER, cfg, stale_rows, rounds)
    conductor.execute_loop(project, st, _OWNER, cfg, stale_rows, rounds)

    summary = _vc106_summary(project, seen)
    stalled = _stalled_events(project)
    _verify(
        "VC-106-conductor",
        task_key=_TASK_KEY,
        grants=summary["grants"],
        refusals=summary["refusals"],
        rows=summary["rows"],
        dispatch_events=summary["dispatch_events"],
        stalled_events=len(stalled),
        reason=summary["refusal_reasons"][0] if summary["refusal_reasons"] else "",
    )

    assert summary["grants"] == 1, seen
    assert summary["refusals"] == 1, seen
    assert summary["rows"] == 1, summary
    assert summary["dispatch_events"] == 1, summary
    assert summary["refusal_reasons"][0].startswith("duplicate-dispatch:"), summary
    assert stalled == [], stalled


# ---------------------------------------------------------------------------
# VC-109: real advance_phase.py wall clock + window_share
# ---------------------------------------------------------------------------

_VC109_SPEC = (
    "# Spec: probe\n\n## §0 Goal Alignment\n\n- 对齐：probe\n- 预期收益：probe\n\n"
    "## §1 概述\n\n" + ("x" * 600) + "\n\n## §3 验收标准（AC）\n\n"
    "| AC 编号 | 描述 |\n|--------|------|\n| AC-001 | probe 通过 design 门禁 |\n\n"
    "### 可复用资产\n- probe\n\n### 需规避坑点\n- probe\n"
)
_VC109_RESEARCH = (
    "# Research: probe (spec)\n## 决策问题\n根定位\n## 调研方法与出处\nprobe\n"
)


def _advance_sample(root: pathlib.Path, index: int) -> tuple[int, str, str, int]:
    """One real ``advance_phase.py design`` subprocess (M-02 harness shape).

    ``FRAMEWORK`` is derived from ``__file__`` and written into the temp
    project's ``.agentic-framework`` marker, so the probe MUST run from
    ``packages/multi-workers/`` (a moved copy cannot find the framework)."""
    project = root / f"adv{index}" / "proj"
    key = f"ap-probe-{index}"
    key_dir = project / ".agenticdoc" / key
    (key_dir / "evidence" / "research").mkdir(parents=True)
    (key_dir / "spec.md").write_text(_VC109_SPEC, encoding="utf-8")
    (key_dir / "evidence" / "research" / "spec-probe.md").write_text(
        _VC109_RESEARCH, encoding="utf-8"
    )
    (project / ".agentic-framework").write_text(
        f"framework=AgenticTask\nrepo={FRAMEWORK}\n", encoding="utf-8"
    )
    advance_mod.invalidate_script_cache()
    return conductor._timed_advance(  # noqa: SLF001 - the timed public seam
        key, "design", project, summary="M-06 VC-109 advance sample"
    )


def test_vc109_advance_wall_clock_window_share(tmp_path: pathlib.Path) -> None:
    """Three real ``advance_phase.py`` subprocess samples + idle-tick ms.

    ``window_share = sum(advance_ms) / (sum(advance_ms) + n*idle_tick_ms)``
    answers "how much of the tick wall clock one synchronous advance eats".
    """
    samples: list[tuple[int, int]] = []
    for index in range(3):
        code, _out, err, ms = _advance_sample(tmp_path, index)
        samples.append((code, ms))
        print(
            f"[VERIFY] VC-109 advance_sample[{index}] exit={code} ms={ms} "
            f"stderr={err.strip()[:120]}"
        )

    idle_project = tmp_path / "idle" / "proj"
    _project(idle_project)
    _roadmap(idle_project, {"k1": None})
    idle_st = _state(idle_project)
    idle_samples: list[int] = []
    for _ in range(3):
        started = time.monotonic()
        assert conductor.tick(idle_project, idle_st) == "ok"
        idle_samples.append(int(round((time.monotonic() - started) * 1000)))
    idle_ms = sorted(idle_samples)[1]
    advance_ms = sorted(ms for _, ms in samples)
    median_ms = advance_ms[1]
    total_advance = sum(ms for _, ms in samples)
    window_share = total_advance / (total_advance + idle_ms * len(samples))
    ratio = median_ms / max(idle_ms, 1)

    print(f"[VERIFY] VC-109 advance_samples_ms={[ms for _, ms in samples]}")
    print(
        f"[VERIFY] VC-109 idle_tick_ms_samples={idle_samples} idle_tick_ms={idle_ms}"
    )
    print(
        f"[VERIFY] VC-109 window_share={total_advance}/"
        f"({total_advance}+{idle_ms * len(samples)})={window_share:.6f} "
        f"median_ms={median_ms} ratio={ratio:.2f}x"
    )
    _verify(
        "VC-109",
        advance_samples_ms=[ms for _, ms in samples],
        median_ms=median_ms,
        idle_tick_ms=idle_ms,
        window_share=f"{window_share:.6f}",
        ratio=f"{ratio:.2f}x",
        n_ge_4_tick_stall="advance is per-key-per-tick and ~2 orders above the idle tick",
    )

    assert all(code == 0 for code, _ in samples), samples
    assert median_ms >= idle_ms, (median_ms, idle_ms)
    assert window_share > 0.5, window_share


# ---------------------------------------------------------------------------
# AC-002: cross-tick top-up window (quantify only, never change the skip logic)
# ---------------------------------------------------------------------------


def test_ac002_topup_window_quantified(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fixture: one running key, 6 dep-free disjoint-face cards, bound 4.

    Tick 1 starts min(4, 6) = 4.  Three of the four then finish and the fourth
    becomes a straggler: any in-flight row still skips ``_advance_key`` for the
    WHOLE key, so the 3 freed slots are not refilled while the straggler runs.
    The test measures, in tick turns and idle slot-ticks, how long that window
    lasts and what the next batch does once the key drains.  Nothing in
    ``orchestrate`` / ``execute_loop`` is modified.
    """
    project = _project(tmp_path)
    _roadmap(project, {"k1": None})
    for index in range(6):
        _card(project, "k1", f"T-{index + 1}", faces=[f"src/mod{index}/**"])
    _set_bounds(project, max_parallel_keys=8, max_workers_per_key=4)
    _noop_advance(monkeypatch)
    st = _state(project)

    assert conductor.tick(project, st) == "ok"
    batch1 = sorted(_task_keys(project, "k1"))
    assert batch1 == [f"ap-k1-T-{index}" for index in range(1, 5)], batch1

    # Three of the four finish; T-4 stays in flight (straggler).
    for index in (1, 2, 3):
        _set_row(project, f"ap-k1-T-{index}", "done")

    free_slots = 3
    straggler_ticks = 0
    idle_slot_ticks = 0
    before = _task_keys(project, "k1")
    straggler_tick_ms: list[int] = []
    for _ in range(2):
        started = time.monotonic()
        assert conductor.tick(project, st) == "ok"
        straggler_tick_ms.append(int(round((time.monotonic() - started) * 1000)))
        new_rows = _task_keys(project, "k1") - before
        assert new_rows == set(), sorted(new_rows)  # no top-up while T-4 lives
        straggler_ticks += 1
        idle_slot_ticks += free_slots
        before = _task_keys(project, "k1")

    # The straggler finishes; the next tick must start the next batch in the
    # SAME tick (the batch boundary itself adds no extra idle tick).
    _set_row(project, "ap-k1-T-4", "done")
    started = time.monotonic()
    assert conductor.tick(project, st) == "ok"
    batch_boundary_tick_ms = int(round((time.monotonic() - started) * 1000))
    next_batch = sorted(_task_keys(project, "k1") - before)

    print(
        f"[VERIFY] AC-002 batch1_started={len(batch1)} batch1={batch1} "
        f"per_key_bound=4"
    )
    print(
        f"[VERIFY] AC-002 straggler_ticks={straggler_ticks} "
        f"free_slots={free_slots} idle_slot_ticks={idle_slot_ticks} "
        f"straggler_tick_ms={straggler_tick_ms} "
        f"batch_boundary_tick_ms={batch_boundary_tick_ms}"
    )
    print(
        f"[VERIFY] AC-002 next_batch_started={len(next_batch)} "
        f"next_batch={next_batch} ticks_after_all_terminal_to_next_batch=1"
    )
    _verify(
        "AC-002",
        batch1_started=len(batch1),
        topup_window_ticks=straggler_ticks,
        free_slots=free_slots,
        idle_slot_ticks=idle_slot_ticks,
        next_batch_started=len(next_batch),
        extra_idle_ticks_at_batch_boundary=0,
    )

    assert next_batch == ["ap-k1-T-5", "ap-k1-T-6"], next_batch
    assert _stalled_events(project) == []

"""
test_autopilot_conductor_exec.py — L1 tests for the EXECUTE task loop + L3
convergence + done transaction (T-12, AC-004/010/022/023 /
VC-012/024/025).

Worker behavior is injected through the queue (rows flipped to done/failed)
and worker output files; advance is monkeypatched with a gate-validating
fake so the done-transaction contract (三件套) is asserted against the same
checks the real advance_phase.py applies.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
from autopilot import config, conductor, dispatch, gates, roadmap, state, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def true_str(b: bool) -> str:
    return "true" if b else "false"


# ── fixtures ──────────────────────────────────────────────────────────────────

def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    ap = tmp_path / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp_path, cfg)
    return tmp_path


def _key_project(
    tmp_path: pathlib.Path,
    *,
    phases: dict[str, str],
    k1_status: str = "running",
) -> pathlib.Path:
    project = _project(tmp_path)
    key_status = ", ".join(f"{k}={k1_status}" for k in phases)
    table = "\n".join(f"| {k} | worker | - |" for k in phases)
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        "# Roadmap\n"
        "> generated_at: t\n"
        "> goal_mtime: 1\n"
        "\n"
        "## Stage 1: work\n"
        "> goal: deliver\n"
        "> status: running\n"
        f"> key-status: {key_status}\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        f"{table}\n",
        encoding="utf-8",
    )
    index = "\n".join(
        f"| {k} | active | {p} | — | - | d | 2026-09-10T00:00:00 |"
        for k, p in phases.items()
    )
    (project / ".agenticdoc" / "_index.parallel").write_text(index + "\n", encoding="utf-8")
    return project


def _state(project: pathlib.Path) -> conductor.ConductorState:
    tl = timeline.Timeline(timeline.timeline_path(project))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(project))


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _rows(project: pathlib.Path, prefix: str = "ap-") -> list[dict]:
    return [
        r for r in mw_common.parse_workers_file(mw_common.workers_path(project))
        if r["task_key"].startswith(prefix)
    ]


def _set_row(project: pathlib.Path, task_key: str, status: str) -> None:
    wpath = mw_common.workers_path(project)
    entries = mw_common.parse_workers_file(wpath)
    for e in entries:
        if e["task_key"] == task_key:
            e["status"] = status
    wpath.write_text(
        "\n".join(mw_common.serialize_entry(e) for e in entries) + "\n", encoding="utf-8"
    )


def _worker_output(project: pathlib.Path, key: str, task_key: str, text: str) -> None:
    out = project / ".agenticdoc" / key / "workers" / task_key / "output.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


def _tasks(project: pathlib.Path, key: str, stems: list[str], plan: str = "") -> None:
    tdir = project / ".agenticdoc" / key / "tasks"
    tdir.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (tdir / f"{stem}.md").write_text(f"# {stem}\n\nDo the thing.\n", encoding="utf-8")
    if plan:
        (project / ".agenticdoc" / key / "plan.md").write_text(plan, encoding="utf-8")


def _set_index_phase_file(project: pathlib.Path, key: str, phase: str) -> None:
    """Rewrite the key's index phase column (what update_index.py does)."""
    ipath = project / ".agenticdoc" / "_index.parallel"
    lines = []
    for line in ipath.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"| {key} |"):
            cols = [c.strip() for c in line.strip("|").split("|")]
            cols[2] = phase
            line = "| " + " | ".join(cols) + " |"
        lines.append(line)
    ipath.write_text("\n".join(lines) + "\n", encoding="utf-8")


_L3_MEETS = (
    "# L3 Report\n\n"
    "## Quality Gate Report\n\n"
    "| VC | verdict | evidence |\n"
    "|----|---------|----------|\n"
    "| VC-001 | PASS | evidence/runs/a.md |\n"
    "| VC-002 | PASS | evidence/runs/b.md |\n"
    "\n"
    "## Achieved\n\n"
    + ("达成摘要：本 key 完成了全部任务书列出的交付物，验证套件全绿，"
       "证据链闭合无缺口，目标收益如 spec 所述已经落地，遗留问题仅在文档层面。"
       * 3)
    + "\n"
)

_L3_BELOW = (
    "# L3 Report\n\n"
    "## Quality Gate Report\n\n"
    "| VC | verdict | evidence |\n"
    "|----|---------|----------|\n"
    "| VC-001 | PASS | evidence/runs/a.md |\n"
    "| VC-002 | FAIL | (missing) |\n"
    "\n"
    "## Achieved\n\n"
    + ("达成摘要：部分完成，但 VC-002 证据缺失需要修复。 " * 6)
    + "\n"
)


def _fake_advance_factory(project: pathlib.Path, *, update_index: bool = True):
    """Gate-validating advance fake: mirrors the done 三件套 checks and (when
    update_index) rewrites the index phase like the real script chain."""
    calls: list[tuple[str, str]] = []

    def fake_advance(key: str, phase: str, root, summary=None):
        calls.append((key, phase))
        if phase == "done":
            key_dir = pathlib.Path(root) / ".agenticdoc" / key
            achieved = key_dir / "achieved.md"
            pm_state = key_dir / "pm-state.md"
            qg = list((key_dir / "evidence").glob("quality-gate-report-*.md"))
            if (
                not achieved.is_file() or achieved.stat().st_size < 200
                or not pm_state.is_file() or "PASS" not in pm_state.read_text(encoding="utf-8")
                or not qg
            ):
                return 1, "", "done gate failed (三件套)"
            if update_index:
                _set_index_phase_file(project, key, "DONE")
        elif update_index:
            _set_index_phase_file(project, key, phase.upper())
        return 0, "advanced", ""

    return fake_advance, calls


# ── EXECUTE task loop (D-111) ─────────────────────────────────────────────────

def test_tasks_run_in_plan_order_then_advance(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE"})
    _tasks(
        project, "k1", ["T-02-second", "T-01-first"],
        plan="# Plan\n\n1. T-01-first 先做\n2. 然后 T-02-second\n",
    )
    fake_advance, calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    # task 1 (plan order, not stem order)
    assert conductor.tick(project, st) == "ok"
    assert [r["task_key"] for r in _rows(project, "ap-k1-")] == ["ap-k1-T-01-first"]
    assert _rows(project, "ap-k1-")[0]["status"] == "pending"
    # per-key serial: finishing T-01 releases T-02, not both at once
    _set_row(project, "ap-k1-T-01-first", "done")
    assert conductor.tick(project, st) == "ok"
    assert [r["task_key"] for r in _rows(project, "ap-k1-")] == [
        "ap-k1-T-01-first", "ap-k1-T-02-second",
    ]
    # all done → advance execute→verify
    _set_row(project, "ap-k1-T-02-second", "done")
    assert conductor.tick(project, st) == "ok"
    assert calls == [("k1", "verify")]
    assert len(_rows(project, "ap-k1-")) == 2  # both done rows, nothing new
    adv = [e for e in _events(project) if e["ev"] == "advance"]
    assert any("execute->verify exit=0" in e["detail"] for e in adv)


def test_exec_failure_retry_then_success(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE"})
    _tasks(project, "k1", ["T-01-first"])
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # a1 dispatched
    _set_row(project, "ap-k1-T-01-first", "failed")  # exit≠0 form (AC-023)
    assert conductor.tick(project, st) == "ok"
    fam = [r["task_key"] for r in _rows(project, "ap-k1-T-01")]
    assert fam == ["ap-k1-T-01-first", "ap-k1-T-01-first-a2"]  # retry round
    a2_md = (
        project / ".agenticdoc" / "k1" / "workers" / "ap-k1-T-01-first-a2" / "task.md"
    ).read_text(encoding="utf-8")
    assert "attempt: 2" in a2_md and "loop: exec:k1:T-01-first" in a2_md
    rounds = state.used_rounds(conductor._all_workers_dirs(project))
    assert rounds.get("exec:k1:T-01-first") == 2  # real attempt accounting
    _set_row(project, "ap-k1-T-01-first-a2", "done")
    assert conductor.tick(project, st) == "ok"
    adv = [e for e in _events(project) if e["ev"] == "advance"]
    assert any("execute->verify exit=0" in e["detail"] for e in adv)
    _verify("VC-025", failure_form="exit1", retry_rounds=2, recovered=true_str(True))


def test_exec_retry_exhausted_stalls_other_key_unblocked(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE", "k2": "EXECUTE"})
    _tasks(project, "k1", ["T-01-first"])
    _tasks(project, "k2", ["T-09-other"])
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # k1 a1 (parallel cap 2 → k2 too)
    _set_row(project, "ap-k1-T-01-first", "failed")
    conductor.tick(project, st)  # k1 a2
    _set_row(project, "ap-k1-T-01-first-a2", "failed")
    assert conductor.tick(project, st) == "ok"
    # budget (2) spent → k1 stalled (gate + key-status), no a3
    assert _rows(project, "ap-k1-T-01-first-a3") == []
    rm = roadmap.load_roadmap(
        project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    )
    assert rm.stages[0].key_status["k1"] == "stalled"
    stalled_gate = [
        g for g in gates.enumerate(conductor.gates_dir(project)) if g.kind == "stalled"
    ]
    assert stalled_gate and stalled_gate[0].key == "k1"
    # AC-023: the other key's dispatch is unaffected (≥1 row)
    assert len(_rows(project, "ap-k2-")) >= 1
    _verify(
        "VC-025", failure_form="spawn-watchdog", stalled_k1=true_str(True),
        other_key_rows=len(_rows(project, "ap-k2-")),
    )


def test_exec_budget_one_escalates_immediately(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-011/VC-013, task-retry loop at round_budget=1: the first failure
    spends the whole budget — no second-round dispatch, key stalls, other
    keys unaffected."""
    project = _key_project(tmp_path, phases={"k1": "EXECUTE", "k2": "EXECUTE"})
    _tasks(project, "k1", ["T-01-first"])
    _tasks(project, "k2", ["T-09-other"])
    cfg = config.load_config(project)
    cfg["round_budget"] = 1
    config.save_config(project, cfg)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # a1 for both keys
    _set_row(project, "ap-k1-T-01-first", "failed")
    assert conductor.tick(project, st) == "ok"
    # budget=1 spent by the failed attempt 1 → no a2, k1 stalled
    assert _rows(project, "ap-k1-T-01-first-a2") == []
    rm = roadmap.load_roadmap(
        project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    )
    assert rm.stages[0].key_status["k1"] == "stalled"
    # AC-023 still holds: the other key is not blocked
    assert len(_rows(project, "ap-k2-")) >= 1
    _verify(
        "VC-013", loop="task-retry", budget=1, second_round_rows=0,
        escalated="stalled", other_key_rows=len(_rows(project, "ap-k2-")),
    )


def test_exec_needs_clarification_counts_as_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE"})
    _tasks(project, "k1", ["T-01-first"])
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)
    _set_row(project, "ap-k1-T-01-first", "needs-clarification")
    assert conductor.tick(project, st) == "ok"
    assert "ap-k1-T-01-first-a2" in [r["task_key"] for r in _rows(project, "ap-k1-")]


def test_orphan_task_dispatched_with_note(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE"})
    _tasks(project, "k1", ["T-01-planned", "T-07-orphan"], plan="# Plan\n\n1. T-01-planned\n")
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"  # T-01-planned dispatched
    _set_row(project, "ap-k1-T-01-planned", "done")
    assert conductor.tick(project, st) == "ok"
    assert [r["task_key"] for r in _rows(project, "ap-k1-T-07")] == ["ap-k1-T-07-orphan"]
    notes = [e for e in _events(project) if e["ev"] == "config" and "orphan" in e["detail"]]
    assert notes and notes[0]["key"] == "k1"  # timeline 注记


def test_plan_missing_task_is_l1_gap(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "TASKS"})
    _tasks(project, "k1", ["T-01-there"], plan="# Plan\n\n1. T-01-there\n2. T-99-missing\n")
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    # plan-referenced T-99-missing → synthetic blocking gap → L2 verifier
    verifiers = [r for r in _rows(project, "ap-k1-") if "l2-" in r["task_key"]]
    assert verifiers, "expected an L2 verifier for the missing plan task"
    vmd = (
        project / ".agenticdoc" / "k1" / "workers" / verifiers[0]["task_key"] / "task.md"
    ).read_text(encoding="utf-8")
    assert "T-99-missing" in vmd


# ── L3 convergence + done transaction (D-108/D-112) ──────────────────────────

def _verify_key_project(tmp_path: pathlib.Path) -> pathlib.Path:
    project = _key_project(tmp_path, phases={"k1": "VERIFY"})
    key_dir = project / ".agenticdoc" / "k1"
    key_dir.mkdir(parents=True, exist_ok=True)
    for name, text in (
        ("spec.md", "# Spec\n" + "x" * 600),
        ("design.md", "# Design\n" + "x" * 600),
        ("plan.md", "# Plan\n" + "x" * 400),
        ("achieved.md", "# interim\n"),
    ):
        (key_dir / name).write_text(text, encoding="utf-8")
    _tasks(project, "k1", ["T-01-first"])
    return project


def test_meets_done_transaction(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _verify_key_project(tmp_path)
    fake_advance, calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    # round 1: L3 review dispatched (reviewer type, read-scoped)
    assert conductor.tick(project, st) == "ok"
    l3_rows = _rows(project, "ap-k1-l3-")
    assert [r["task_key"] for r in l3_rows] == ["ap-k1-l3-a1"]
    l3_md = (
        project / ".agenticdoc" / "k1" / "workers" / "ap-k1-l3-a1" / "task.md"
    ).read_text(encoding="utf-8")
    assert "type: reviewer" in l3_md and "read_scope:" in l3_md
    assert "loop: l3:k1" in l3_md and "attempt: 1" in l3_md
    # worker wrote a meets report
    _worker_output(project, "k1", "ap-k1-l3-a1", _L3_MEETS)
    _set_row(project, "ap-k1-l3-a1", "done")
    assert conductor.tick(project, st) == "ok"
    # done transaction: QG report + achieved draft + pm-state PASS + advance
    key_dir = project / ".agenticdoc" / "k1"
    qg = list((key_dir / "evidence").glob("quality-gate-report-*.md"))
    assert len(qg) == 1 and "## Quality Gate Report" in qg[0].read_text(encoding="utf-8")
    achieved = (key_dir / "achieved.md").read_text(encoding="utf-8")
    assert "## Achieved" in achieved and (key_dir / "achieved.md").stat().st_size >= 200
    pm_state = (key_dir / "pm-state.md").read_text(encoding="utf-8")
    assert "PASS" in pm_state and "quality-gate-report" in pm_state
    assert calls == [("k1", "done")]
    ks = state.read_key_states(project)["k1"]
    assert ks.phase == "DONE"  # advance post-check index
    adv = [e for e in _events(project) if e["ev"] == "advance"]
    assert any("verify->done exit=0" in e["detail"] for e in adv)
    # key marked done in the roadmap (next tick: phase DONE → _mark_key_done)
    assert conductor.tick(project, st) == "ok"
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "done"
    # idempotent: a later tick does not redo the transaction
    assert conductor.tick(project, st) == "ok"
    assert len(list((key_dir / "evidence").glob("quality-gate-report-*.md"))) == 1
    # L3 verdict persisted for the closure dossier (AC-003): meets + report
    assert (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip() == "meets"
    l3_report = (key_dir / "l3-report.md").read_text(encoding="utf-8")
    assert "## Quality Gate Report" in l3_report
    # all keys terminal → closure dossier carries the per-key verdict row
    dossier = (
        project / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
    )
    assert dossier.is_file(), "closure dossier not written"
    row = [
        l for l in dossier.read_text(encoding="utf-8").splitlines()
        if l.startswith("| k1 |")
    ]
    assert row and "| meets |" in row[0] and "l3-report.md" in row[0], row
    _verify(
        "VC-005", dossier_verdict="meets", report="l3-report.md",
        verdict_file=true_str(True),
    )
    _verify(
        "VC-012", verdict="meets", qg_reports=1, achieved_bytes=(
            key_dir / "achieved.md").stat().st_size, advance_exit=0,
    )


def test_below_repair_reeval_then_stalled(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _verify_key_project(tmp_path)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # l3-a1
    _worker_output(project, "k1", "ap-k1-l3-a1", _L3_BELOW)
    _set_row(project, "ap-k1-l3-a1", "done")
    # below → repair dispatched (coding set)
    assert conductor.tick(project, st) == "ok"
    assert [r["task_key"] for r in _rows(project, "ap-k1-repair-")] == [
        "ap-k1-repair-a1"
    ]
    rmd = (
        project / ".agenticdoc" / "k1" / "workers" / "ap-k1-repair-a1" / "task.md"
    ).read_text(encoding="utf-8")
    assert "type: repair" in rmd and "loop: repair:k1" in rmd
    # repair done → L3 round 2
    _set_row(project, "ap-k1-repair-a1", "done")
    assert conductor.tick(project, st) == "ok"
    assert [r["task_key"] for r in _rows(project, "ap-k1-l3-")] == [
        "ap-k1-l3-a1", "ap-k1-l3-a2",
    ]
    # round 2 also below → stalled (2-round cap, no repair-a2)
    _worker_output(project, "k1", "ap-k1-l3-a2", _L3_BELOW)
    _set_row(project, "ap-k1-l3-a2", "done")
    assert conductor.tick(project, st) == "ok"
    assert _rows(project, "ap-k1-repair-a2") == []
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    _verify("VC-012", verdict="below-twice", repair_rounds=1, stalled=true_str(True))


def test_l3_budget_one_escalates_after_one_round(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-011/VC-013, L3 convergence loop at round_budget=1: one below
    round spends the budget — no second review round, no repair dispatch,
    key stalls with the verdict persisted for the closure dossier."""
    project = _verify_key_project(tmp_path)
    cfg = config.load_config(project)
    cfg["round_budget"] = 1
    config.save_config(project, cfg)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # l3-a1
    _worker_output(project, "k1", "ap-k1-l3-a1", _L3_BELOW)
    _set_row(project, "ap-k1-l3-a1", "done")
    assert conductor.tick(project, st) == "ok"
    # 1 轮后升级：no l3-a2, no repair, stalled
    assert _rows(project, "ap-k1-l3-a2") == []
    assert _rows(project, "ap-k1-repair-") == []
    rm = roadmap.load_roadmap(
        project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    )
    assert rm.stages[0].key_status["k1"] == "stalled"
    # verdict persisted (AC-003 dossier input)
    key_dir = project / ".agenticdoc" / "k1"
    assert (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip() == "below"
    assert "## Quality Gate Report" in (key_dir / "l3-report.md").read_text(encoding="utf-8")
    _verify(
        "VC-013", loop="l3", budget=1, second_round_rows=0, escalated="stalled",
        verdict_persisted=true_str(True),
    )


def test_missing_sections_and_short_achieved_are_below(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _verify_key_project(tmp_path)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # l3-a1
    # missing ## Achieved section → below
    _worker_output(
        project, "k1", "ap-k1-l3-a1",
        "# L3\n\n## Quality Gate Report\n\nall good\n",
    )
    _set_row(project, "ap-k1-l3-a1", "done")
    assert conductor.tick(project, st) == "ok"
    assert [r["task_key"] for r in _rows(project, "ap-k1-repair-")] == [
        "ap-k1-repair-a1"
    ]
    _set_row(project, "ap-k1-repair-a1", "done")
    assert conductor.tick(project, st) == "ok"  # l3-a2 dispatched
    # meets verdict but a short ## Achieved (<200B) → below path (no padding)
    short = _L3_MEETS.replace(
        _L3_MEETS[_L3_MEETS.find("## Achieved"):], "## Achieved\n\ntoo short\n"
    )
    _worker_output(project, "k1", "ap-k1-l3-a2", short)
    _set_row(project, "ap-k1-l3-a2", "done")
    assert conductor.tick(project, st) == "ok"
    key_dir = project / ".agenticdoc" / "k1"
    # D-108 order: the QG report is written BEFORE the 200B post-check, so it
    # legitimately exists — the contract is no advance + stalled escalation
    assert list((key_dir / "evidence").glob("quality-gate-report-*.md"))
    assert "ap-k1-repair-a2" not in [r["task_key"] for r in _rows(project)]
    assert state.read_key_states(project)["k1"].phase == "VERIFY"  # no advance
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"  # 2 rounds spent
    cfg_events = [e for e in _events(project) if e["ev"] == "config" and "200B" in e["detail"]]
    assert cfg_events  # 后验留痕


def test_advance_index_mismatch_set_phase_retry(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _verify_key_project(tmp_path)
    # advance succeeds but "forgets" the index — the post-check must repair
    fake_advance, _calls = _fake_advance_factory(project, update_index=False)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)

    def fake_set_phase(root, key, phase):
        _set_index_phase_file(project, key, phase)
        return 0, ""

    monkeypatch.setattr(conductor, "_set_index_phase", fake_set_phase)
    st = _state(project)
    conductor.tick(project, st)  # l3-a1
    _worker_output(project, "k1", "ap-k1-l3-a1", _L3_MEETS)
    _set_row(project, "ap-k1-l3-a1", "done")
    assert conductor.tick(project, st) == "ok"
    ks = state.read_key_states(project)["k1"]
    assert ks.phase == "DONE"  # repaired via set-phase rerun
    cfg_events = [
        e for e in _events(project) if e["ev"] == "config" and "mismatch" in e["detail"]
    ]
    assert cfg_events  # timeline 留痕


def test_advance_index_mismatch_persists_human_gate(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _verify_key_project(tmp_path)
    fake_advance, _calls = _fake_advance_factory(project, update_index=False)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    monkeypatch.setattr(
        conductor, "_set_index_phase", lambda root, key, phase: (1, "boom")
    )
    st = _state(project)
    conductor.tick(project, st)  # l3-a1
    _worker_output(project, "k1", "ap-k1-l3-a1", _L3_MEETS)
    _set_row(project, "ap-k1-l3-a1", "done")
    assert conductor.tick(project, st) == "ok"
    # set-phase rerun failed → stalled (human gate) + timeline records
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    assert any(
        g.kind == "stalled" and g.key == "k1"
        for g in gates.enumerate(conductor.gates_dir(project))
    )
    assert any(
        e["ev"] == "config" and "mismatch" in e["detail"] for e in _events(project)
    )


# ── crash-recovery invariants (AC-022/VC-024) ────────────────────────────────

def test_kill_restart_invariants(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE", "k2": "EXECUTE"})
    _tasks(project, "k1", ["T-01-first"])
    _tasks(project, "k2", ["T-05-five"])
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)
    # the k1 worker started (one [START] pid line, D-115 shape)
    trace = (
        project / ".agenticdoc" / "k1" / "workers" / "ap-k1-T-01-first" / "trace.log"
    )
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text("[START] pid=4242\n", encoding="utf-8")
    budgets_before = state.used_rounds(conductor._all_workers_dirs(project))
    mtime_before = trace.stat().st_mtime_ns
    # kill + restart: a fresh ConductorState re-derives everything from files
    st2 = _state(project)
    assert conductor.tick(project, st2) == "ok"
    assert conductor.tick(project, st2) == "ok"
    # in-flight guard: no duplicate dispatch of the same task
    k1_fam = [r for r in _rows(project, "ap-k1-T-01")]
    assert len(k1_fam) == 1  # still the single a1 row
    assert trace.read_text(encoding="utf-8").count("[START]") == 1
    assert trace.stat().st_mtime_ns == mtime_before  # untouched
    assert state.used_rounds(conductor._all_workers_dirs(project)) == budgets_before
    # progress continues within 2 ticks: k2's task still advancing
    assert len(_rows(project, "ap-k2-")) == 1
    _set_row(project, "ap-k1-T-01-first", "done")
    assert conductor.tick(project, st2) == "ok"
    assert any(
        e["ev"] == "advance" and "execute->verify" in e["detail"]
        for e in _events(project)
    )
    _verify(
        "VC-024", start_lines=1, budgets_unchanged=true_str(True),
        mtime_unchanged=true_str(True), resumed_in_ticks=2,
    )

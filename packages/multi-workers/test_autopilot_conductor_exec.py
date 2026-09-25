"""
test_autopilot_conductor_exec.py — L1 tests for the EXECUTE task loop + L3
convergence + done transaction (T-12, AC-004/010/022/023 /
VC-012/024/025).

Worker behavior is injected through the queue (rows flipped to done/failed)
and worker output files; advance is monkeypatched with a gate-validating
fake so the done-transaction contract (三件套) is asserted against the same
checks the real advance_phase.py applies.
"""
import hashlib
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
from autopilot import closure, config, conductor, dispatch, gates, roadmap, state, timeline  # noqa: E402


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


def test_plan_task_id_mapped_to_prefix_stripped_filename_closes_gap(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan may document the id→file mapping as a prefix strip (plan §3:
    `T-001-board-params-config-errors` → `tasks/001-board-params-config-errors.md`).
    When the file exists under that mapped stem the plan id is NOT a missing
    task, so the key advances instead of burning an L2 round on a phantom gap."""
    project = _key_project(tmp_path, phases={"k1": "TASKS"})
    key_dir = project / ".agenticdoc" / "k1"
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "spec.md").write_text(
        "# Spec\n\n| AC | desc |\n|----|------|\n| AC-001 | todo |\n", encoding="utf-8"
    )
    (key_dir / "design.md").write_text("# Design\n\n### D-001 choice\n", encoding="utf-8")
    _tasks(
        project, "k1", ["001-board-params-config-errors"],
        plan=(
            "# Plan\n\n## 3 任务清单\n\n| 任务 | 目标 |\n|------|------|\n"
            "| `T-001-board-params-config-errors` | 骨架 |\n\n"
            "映射：`tasks/001-board-params-config-errors.md`（去掉 `T-NNN-` 前缀）\n"
        ),
    )
    fake_advance, calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    assert calls == [("k1", "execute")]
    assert [r for r in _rows(project, "ap-k1-") if "l2-" in r["task_key"]] == []


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


# ── done-closure repair L2 (key mw-done-closure-repair, T-06/T-07/T-08) ──────
# Tick-driven coverage for the achieved.md vocabulary closure loop:
# gate-blocked (advance verify->done exit 1) -> bad-draft marker -> L3
# reprompt -> three-condition overwrite -> advance exit 0 -> DONE.
#
# Naming convention (concurrency contract with the concurrent conductor
# change): every new fixture and test here carries a `_dcr_` / `test_dcr_`
# prefix, so the regression pass (`-k "not test_dcr"`) never picks them up.

_DCR_STANDARD_VOCAB = {
    "系统行为变化": "achieved.md 必含「系统行为变化」节（新增/修改功能与影响面）",
    "遗留": "achieved.md 必含「遗留问题」节（明确去留的 key / 能力补丁 / 兼容策略）",
}
_DCR_ALT_VOCAB = {
    "行为影响": "achieved.md 必含「行为影响」节（对既有行为的改动面）",
    "未了事项": "achieved.md 必含「未了事项」节（尚未闭合的事项与去处）",
}

_DCR_PADDING = (
    "达成摘要：本 key 完成了任务书列出的全部交付物，验证套件全绿，证据链闭合无缺口，"
    "目标收益如 spec 所述已经落地。"
) * 3


def _dcr_events(project: pathlib.Path, ev: str) -> list[dict]:
    return [e for e in _events(project) if e["ev"] == ev]


def _dcr_markers(project: pathlib.Path, key: str) -> list[pathlib.Path]:
    key_dir = project / ".agenticdoc" / key
    if not key_dir.is_dir():
        return []
    return [p for p in key_dir.iterdir() if p.name == closure.BAD_DRAFT_MARKER_NAME]


def _dcr_task_body(md_path: pathlib.Path) -> str:
    """The prompt body of a conductor task.md (frontmatter stripped).

    ``dispatch.render_task_md`` writes ``stripped_prompt``, so the inverse is
    the text after the closing frontmatter fence with the surrounding
    newlines removed."""
    text = md_path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    assert len(parts) == 3, f"unexpected task.md shape: {text[:200]!r}"
    return parts[2].strip("\n")


def _dcr_no_match(pattern: str, description: str) -> str:
    """The framework's content_match failure line, verbatim shape."""
    return f"NO MATCH: achieved.md missing pattern '{pattern}' — {description}"


def _dcr_gate_blocked_stderr(key: str, failures: list[str]) -> str:
    """Byte-exact replica of advance_phase.py's gate-blocked stderr.

    The real branch (framework ``scripts/advance_phase.py``) prints three
    lines to stderr and exits 1::

        GATE BLOCKED: <key> cannot advance to 'done'
           Current phase: <phase>
           - <failure>

    Each is a separate ``print(..., file=sys.stderr)``, so every line ends in
    a trailing newline. (The T-06 card paraphrases the header as
    ``GATE BLOCKED: <key> (current phase: ...)``; the installed script — the
    byte source this fixture must mirror — says ``cannot advance to`` with a
    three-space-indented ``   Current phase:`` line. Only the ``   - ``
    failure lines are parsed, so the header wording is behavior-neutral.)
    """
    lines = [
        f"GATE BLOCKED: {key} cannot advance to 'done'",
        "   Current phase: verify",
    ]
    lines += [f"   - {failure}" for failure in failures]
    return "\n".join(lines) + "\n"


def _dcr_l3_report(achieved: str, *, fail: bool = False) -> str:
    rows = "| VC-001 | PASS | evidence/runs/a.md |\n"
    if fail:
        rows += "| VC-002 | FAIL | (missing) |\n"
    return (
        "# L3 Report\n\n"
        "## Quality Gate Report\n\n"
        "| VC | verdict | evidence |\n"
        "|----|---------|----------|\n"
        + rows
        + "\n## Achieved\n\n"
        + achieved
        + "\n"
    )


def _dcr_achieved_noncompliant() -> str:
    """A >=200B ## Achieved body free of every vocabulary literal in play."""
    return "本 key 的交付物与证据链已经就绪，目标收益落地，无阻塞项。" * 6


def _dcr_achieved_compliant(vocab: dict[str, str]) -> str:
    """A compliant ## Achieved body: one ``###`` sub-section per rule.

    ``###`` (not ``##``) keeps the sub-sections inside conductor._md_section's
    ``## Achieved`` window (it stops at the next ``## `` line), so the verbatim
    transcription (AC-010) carries the literals the done gate matches."""
    parts = [_DCR_PADDING, ""]
    for pattern, description in vocab.items():
        parts += [f"### {pattern}", "", f"按门禁要求补齐：{description}。", ""]
    return "\n".join(parts).rstrip() + "\n"


def _dcr_advance_factory(
    project: pathlib.Path,
    *,
    vocab: dict[str, str] | None = None,
    forced_failures: list[str] | None = None,
    update_index: bool = True,
):
    """Gate-validating advance fake with a done-gate-blocked mode.

    ``vocab`` maps each required achieved.md literal to its rule description:
    a done advance whose achieved.md lacks any literal returns exit 1 with the
    byte-exact gate-blocked stderr (injected vocabulary — the literals live in
    this package-root test file, never in ``autopilot/`` sources).
    ``forced_failures`` bypasses the vocab check (AC-006: a gate failure whose
    lines do not name achieved.md). Non-done phases succeed and (by default)
    rewrite the index like the real script chain.

    Returns ``(fake, calls, stderrs)``; ``stderrs`` collects every non-empty
    stderr payload returned, in call order.
    """
    calls: list[tuple[str, str]] = []
    stderrs: list[str] = []

    def fake_advance(key: str, phase: str, root, summary=None):
        calls.append((key, phase))
        if phase != "done":
            if update_index:
                _set_index_phase_file(project, key, phase.upper())
            return 0, "advanced", ""
        achieved = pathlib.Path(root) / ".agenticdoc" / key / "achieved.md"
        content = achieved.read_text(encoding="utf-8") if achieved.is_file() else ""
        if forced_failures is not None:
            failures = list(forced_failures)
        else:
            failures = [
                _dcr_no_match(pattern, description)
                for pattern, description in (vocab or {}).items()
                if pattern not in content
            ]
        if failures:
            stderr = _dcr_gate_blocked_stderr(key, failures)
            stderrs.append(stderr)
            return 1, "", stderr
        if update_index:
            _set_index_phase_file(project, key, "DONE")
        return 0, "advanced", ""

    return fake_advance, calls, stderrs


def _dcr_setup_gate_blocked(
    project: pathlib.Path, st: conductor.ConductorState
) -> None:
    """tick 1-2: dispatch l3-a1, mark it meets with a non-compliant draft,
    then force the done gate to block -> marker + l3-a2 reprompt dispatch."""
    assert conductor.tick(project, st) == "ok"
    _worker_output(
        project, "k1", "ap-k1-l3-a1",
        _dcr_l3_report(_dcr_achieved_noncompliant()),
    )
    _set_row(project, "ap-k1-l3-a1", "done")
    assert conductor.tick(project, st) == "ok"


def _dcr_finish_reprompt(
    project: pathlib.Path, st: conductor.ConductorState, vocab: dict[str, str]
) -> str:
    """Mark the in-flight l3-a2 with a compliant draft and tick it through to
    DONE. Returns the l3-a2 output text (the deciding source)."""
    text = _dcr_l3_report(_dcr_achieved_compliant(vocab))
    _worker_output(project, "k1", "ap-k1-l3-a2", text)
    _set_row(project, "ap-k1-l3-a2", "done")
    assert conductor.tick(project, st) == "ok"
    return text


def _dcr_answer_gate(project: pathlib.Path, gate_path: pathlib.Path, status: str) -> None:
    text = gate_path.read_text(encoding="utf-8")
    assert "status: pending" in text
    gate_path.write_text(
        text.replace("status: pending", f"status: {status}", 1),
        encoding="utf-8", newline="\n",
    )


def _dcr_gate_by_key(project: pathlib.Path) -> dict[str, pathlib.Path]:
    out: dict[str, pathlib.Path] = {}
    for path in sorted(conductor.gates_dir(project).iterdir()):
        if not path.name.startswith("gate-"):
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("key:"):
                out[line.split(":", 1)[1].strip().strip("'")] = path
                break
    return out


def test_dcr_fake_advance_stderr_shape() -> None:
    """Fixture format lock: the gate-blocked stderr bytes the fake returns."""
    stderr = _dcr_gate_blocked_stderr(
        "k1", [_dcr_no_match("系统行为变化", "规则一"), _dcr_no_match("遗留", "规则二")]
    )
    assert stderr == (
        "GATE BLOCKED: k1 cannot advance to 'done'\n"
        "   Current phase: verify\n"
        "   - NO MATCH: achieved.md missing pattern '系统行为变化' — 规则一\n"
        "   - NO MATCH: achieved.md missing pattern '遗留' — 规则二\n"
    )
    assert closure.failure_lines(stderr) == [
        "NO MATCH: achieved.md missing pattern '系统行为变化' — 规则一",
        "NO MATCH: achieved.md missing pattern '遗留' — 规则二",
    ]
    _verify("VC-002", stderr_shape="advance_phase.py", failure_lines=2)


def test_dcr_scenario_a_standard_vocab_closes_done(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-001/VC-001: standard vocabulary, L3 meets, non-compliant achieved
    -> gate-blocked -> reprompt -> compliant -> overwrite -> DONE, with no
    stalled gate and no gate-answered event."""
    project = _verify_key_project(tmp_path)
    fake, _calls, stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)

    _dcr_setup_gate_blocked(project, st)
    # the rejection declared the bad draft and dispatched the reprompt
    assert len(stderrs) == 1
    assert closure.has_achieved_failure(closure.failure_lines(stderrs[0]))
    assert len(_dcr_markers(project, "k1")) == 1
    assert [r["task_key"] for r in _rows(project, "ap-k1-l3-a2")] == ["ap-k1-l3-a2"]

    _dcr_finish_reprompt(project, st, _DCR_STANDARD_VOCAB)

    assert state.read_key_states(project)["k1"].phase == "DONE"
    assert [g for g in gates.enumerate(conductor.gates_dir(project)) if g.kind == "stalled"] == []
    assert _dcr_events(project, "gate-answered") == []
    assert _dcr_markers(project, "k1") == []

    # event sequence: advance exit=1 -> l3-reprompt -> dispatch -> advance exit=0
    adv = _dcr_events(project, "advance")
    assert [e["detail"] for e in adv] == [
        "verify->done exit=1 class=gate-blocked",
        "verify->done exit=0",
    ]
    reprompt = _dcr_events(project, "l3-reprompt")
    assert len(reprompt) == 1 and reprompt[0]["key"] == "k1"
    dispatched = [
        e for e in _dcr_events(project, "dispatch") if "ap-k1-l3-a2" in e["detail"]
    ]
    assert len(dispatched) == 1
    assert adv[0]["seq"] < reprompt[0]["seq"] < dispatched[0]["seq"] < adv[-1]["seq"]
    _verify("VC-001", phase="DONE", stalled_gates=0, gate_answered=0)


def test_dcr_reprompt_prompt_byte_exact(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-002/VC-002: the dispatched reprompt task.md body is byte-equal to
    the fixed base (_l3_prompt + REPROMPT_INSTRUCTION) plus the verbatim
    failure lines, recomposed with closure.compose_reprompt_prompt."""
    project = _verify_key_project(tmp_path)
    fake, _calls, stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)

    flines = closure.failure_lines(stderrs[0])
    expected = closure.compose_reprompt_prompt(conductor._l3_prompt("k1", 2), flines)
    body = _dcr_task_body(
        project / ".agenticdoc" / "k1" / "workers" / "ap-k1-l3-a2" / "task.md"
    )
    assert body == expected.strip()
    for line in flines:
        assert line in body
    assert body.startswith(conductor._l3_prompt("k1", 2))
    assert "## Quality Gate Report" in body  # the reviewer instructions survive
    _verify(
        "VC-002", prompt_contains_failure_lines=true_str(True),
        prompt_equals_fixed_base_plus_lines=true_str(body == expected.strip()),
    )


def test_dcr_second_vocab_portable(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-008/VC-010: a different vocabulary literal set drives the same
    closure loop — the mechanism hardcodes no engineering vocabulary."""
    project = _verify_key_project(tmp_path)
    fake, _calls, stderrs = _dcr_advance_factory(project, vocab=_DCR_ALT_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)
    flines = closure.failure_lines(stderrs[0])
    assert any("行为影响" in line for line in flines)
    assert any("未了事项" in line for line in flines)

    _dcr_finish_reprompt(project, st, _DCR_ALT_VOCAB)

    assert state.read_key_states(project)["k1"].phase == "DONE"
    assert [g for g in gates.enumerate(conductor.gates_dir(project)) if g.kind == "stalled"] == []
    assert _dcr_events(project, "gate-answered") == []
    _verify("VC-010", stalled_gates=0, gate_answered=0, phase="DONE")


def test_dcr_achieved_verbatim_transcript(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-010/VC-012: achieved.md is the deciding L3 output's ## Achieved
    section, transcribed verbatim (at most one trailing-newline difference)."""
    project = _verify_key_project(tmp_path)
    fake, _calls, _stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)
    source = _dcr_finish_reprompt(project, st, _DCR_STANDARD_VOCAB)

    section = conductor._md_section(source, "## Achieved")
    assert section is not None
    achieved = (project / ".agenticdoc" / "k1" / "achieved.md").read_text(
        encoding="utf-8"
    )
    assert achieved == section.rstrip() + "\n"
    _verify("VC-012", verdict="meets", byte_equal=true_str(True))


def test_dcr_human_repair_protected(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-004/VC-006: after a gate-blocked failure an external, vocabulary-
    compliant rewrite of achieved.md is never overwritten — not while the
    reprompt is in flight, not when it converges — and the converged round
    still advances exit=0."""
    project = _verify_key_project(tmp_path)
    fake, _calls, _stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)
    assert _dcr_events(project, "l3-reprompt")

    achieved_path = project / ".agenticdoc" / "k1" / "achieved.md"
    human = (
        "# 人工修稿\n\n## 系统行为变化\n\n"
        + "见 evidence/runs/a.md。 " * 12
        + "\n\n## 遗留问题\n\n无。\n"
    )
    achieved_path.write_text(human, encoding="utf-8", newline="\n")
    before = achieved_path.read_bytes()

    for _ in range(3):  # reprompt in flight: no transaction, bytes frozen
        assert conductor.tick(project, st) == "ok"
    assert achieved_path.read_bytes() == before

    _dcr_finish_reprompt(project, st, _DCR_STANDARD_VOCAB)
    assert achieved_path.read_bytes() == before  # sha mismatch -> no overwrite
    assert state.read_key_states(project)["k1"].phase == "DONE"
    assert _dcr_markers(project, "k1") == []  # lazy cleanup on advance exit=0
    assert any(
        e["detail"] == "verify->done exit=0" for e in _dcr_events(project, "advance")
    )
    _verify("VC-006", bytes_unchanged=true_str(True), advance_exit=0)


def test_dcr_reprompt_budget_exhausted_stalls_keeps_meets(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-005/VC-007: with round_budget=1 the first gate-blocked round spends
    the whole L3 budget — no l3-a2, key stalls, and the persisted L3 verdict
    stays `meets` (the quality verdict and the gate failure are orthogonal)."""
    project = _verify_key_project(tmp_path)
    cfg = config.load_config(project)
    cfg["round_budget"] = 1
    config.save_config(project, cfg)
    fake, _calls, _stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)

    key_dir = project / ".agenticdoc" / "k1"
    l3_rows = [r for r in _rows(project, "ap-k1-") if "-l3-" in r["task_key"]]
    assert len(l3_rows) == 1  # l3_limit spent by l3-a1; no reprompt
    assert _rows(project, "ap-k1-l3-a2") == []
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    stalled = [g for g in gates.enumerate(conductor.gates_dir(project)) if g.kind == "stalled"]
    assert len(stalled) == 1 and stalled[0].key == "k1"
    assert (key_dir / "l3-verdict.txt").read_text(encoding="utf-8").strip() == "meets"
    reason = _dcr_events(project, "stalled")[0]["detail"]
    assert "gate" in reason.lower() or "achieved.md" in reason.lower()
    _verify(
        "VC-007", stalled=true_str(True), l3_dispatches=len(l3_rows), verdict="meets"
    )


def test_dcr_non_achieved_failure_no_reprompt_streak_stall(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-006/VC-008: gate failure lines that do not mention achieved.md do
    not burn an L3 round — the existing advance_stall_ticks streak owns the
    escalation."""
    project = _verify_key_project(tmp_path)
    non_achieved = [
        "MISSING: evidence/quality-gate-report-*.md (0 matches) — 需先执行 /quality-gate"
    ]
    fake, _calls, _stderrs = _dcr_advance_factory(project, forced_failures=non_achieved)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    _worker_output(
        project, "k1", "ap-k1-l3-a1",
        _dcr_l3_report(_dcr_achieved_noncompliant()),
    )
    _set_row(project, "ap-k1-l3-a1", "done")
    for _ in range(5):  # advance_stall_ticks default = 5
        assert conductor.tick(project, st) == "ok"

    l3_rows = [r for r in _rows(project, "ap-k1-") if "-l3-" in r["task_key"]]
    assert len(l3_rows) == 1  # no reprompt dispatch
    assert _dcr_events(project, "l3-reprompt") == []
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    failures = [e for e in _dcr_events(project, "advance") if "exit=1" in e["detail"]]
    assert len(failures) == 5
    _verify("VC-008", l3_dispatch_delta=0, streak_stall=true_str(True))


def test_dcr_inflight_reprompt_blocks_advance(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-007/VC-009: while the l3 reprompt row is in flight, later ticks add
    no advance events (the in-flight guard is not bypassed)."""
    project = _verify_key_project(tmp_path)
    fake, _calls, _stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)
    before = len(_dcr_events(project, "advance"))
    a2_before = [r["task_key"] for r in _rows(project, "ap-k1-l3-a2")]
    assert a2_before == ["ap-k1-l3-a2"]

    for _ in range(5):
        assert conductor.tick(project, st) == "ok"

    assert len(_dcr_events(project, "advance")) == before
    assert [r["task_key"] for r in _rows(project, "ap-k1-l3-a2")] == a2_before
    _verify("VC-009", advance_events_delta=0)


def test_dcr_gate_flood_regression_30_ticks(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-009/VC-011 (4e874f5cc regression lock): 30 mixed ticks with an
    approved resume (reprompt in flight) and a rejected closed-legacy key
    consume every gate answer exactly once and grow no gate files."""
    project = _key_project(tmp_path, phases={"k1": "VERIFY", "k2": "VERIFY"})
    cfg = config.load_config(project)
    cfg["round_budget"] = 1
    config.save_config(project, cfg)
    fake, _calls, _stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)

    assert conductor.tick(project, st) == "ok"  # l3-a1 for both keys
    for key in ("k1", "k2"):
        _worker_output(
            project, key, f"ap-{key}-l3-a1",
            _dcr_l3_report(_dcr_achieved_noncompliant()),
        )
        _set_row(project, f"ap-{key}-l3-a1", "done")
    assert conductor.tick(project, st) == "ok"  # both gate-block -> both stall
    gate_files = _dcr_gate_by_key(project)
    assert set(gate_files) == {"k1", "k2"}

    _dcr_answer_gate(project, gate_files["k1"], "approved")  # resume + 1 credit
    _dcr_answer_gate(project, gate_files["k2"], "rejected")  # closed-legacy
    assert conductor.tick(project, st) == "ok"
    assert _rows(project, "ap-k1-l3-a2")  # reprompt in flight
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k2"] == "closed-legacy"

    gates_before = len([p for p in conductor.gates_dir(project).iterdir() if p.name.startswith("gate-")])
    for _ in range(30):
        assert conductor.tick(project, st) == "ok"
    gates_after = len([p for p in conductor.gates_dir(project).iterdir() if p.name.startswith("gate-")])

    answered: dict[str, int] = {}
    for event in _dcr_events(project, "gate-answered"):
        gid = event["detail"].split()[0]
        answered[gid] = answered.get(gid, 0) + 1
    assert answered, "expected consumed gate answers"
    assert max(answered.values()) == 1
    assert gates_after - gates_before <= 2
    _verify(
        "VC-011", max_answered_per_gate=max(answered.values()),
        gates_growth=gates_after - gates_before,
    )


def test_dcr_marker_lifecycle_after_success(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-011/VC-013(a): a successful three-condition overwrite leaves no
    marker behind, and the key reaches DONE."""
    project = _verify_key_project(tmp_path)
    fake, _calls, _stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)
    assert len(_dcr_markers(project, "k1")) == 1
    _dcr_finish_reprompt(project, st, _DCR_STANDARD_VOCAB)
    assert _dcr_markers(project, "k1") == []
    assert state.read_key_states(project)["k1"].phase == "DONE"
    _verify("VC-013", marker_absent=true_str(True), marker_count=0)


def test_dcr_marker_single_file_on_repeat_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-011/VC-013(c): two gate-blocked rounds over byte-identical rejected
    drafts keep one marker file (in-place update, no multiplication)."""
    project = _verify_key_project(tmp_path)
    fake, _calls, _stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)
    assert len(_dcr_markers(project, "k1")) == 1

    same = _dcr_l3_report(_dcr_achieved_noncompliant())
    _worker_output(project, "k1", "ap-k1-l3-a2", same)
    _set_row(project, "ap-k1-l3-a2", "done")
    assert conductor.tick(project, st) == "ok"  # second gate-block -> stall
    markers = _dcr_markers(project, "k1")
    assert len(markers) == 1
    assert markers[0].name == closure.BAD_DRAFT_MARKER_NAME
    _verify("VC-013", marker_absent=true_str(False), marker_count=len(markers))


def test_dcr_marker_absent_after_closed_legacy(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-011/VC-013(d): rejecting the stalled gate closes the key as
    closed-legacy and sweeps the residual bad-draft marker."""
    project = _verify_key_project(tmp_path)
    cfg = config.load_config(project)
    cfg["round_budget"] = 1
    config.save_config(project, cfg)
    fake, _calls, _stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)  # budget=1 -> stalled, marker present
    assert _dcr_markers(project, "k1")

    _dcr_answer_gate(project, _dcr_gate_by_key(project)["k1"], "rejected")
    assert conductor.tick(project, st) == "ok"
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "closed-legacy"
    assert _dcr_markers(project, "k1") == []
    _verify("VC-013", marker_absent=true_str(True), marker_count=0)


def test_dcr_stall_draft_sha_mismatch_blocks_overwrite(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-07 附 (T-04 note closure): mark_stalled appends the 「遗留问题（stalled
    草稿）」section, which changes achieved.md bytes and invalidates the
    marker's sha. After the stalled gate is approved, the rerun transaction
    must keep that draft (sha mismatch -> no overwrite) and spend the resume
    credit on a fresh L3 reprompt."""
    project = _verify_key_project(tmp_path)
    cfg = config.load_config(project)
    cfg["round_budget"] = 1
    config.save_config(project, cfg)
    fake, _calls, _stderrs = _dcr_advance_factory(project, vocab=_DCR_STANDARD_VOCAB)
    monkeypatch.setattr(conductor.advance, "advance", fake)
    st = _state(project)
    _dcr_setup_gate_blocked(project, st)  # stalls and appends the legacy draft

    key_dir = project / ".agenticdoc" / "k1"
    achieved_path = key_dir / "achieved.md"
    stalled_text = achieved_path.read_text(encoding="utf-8")
    assert "## 遗留问题（stalled 草稿）" in stalled_text
    marker = closure.read_bad_draft_marker(key_dir)
    assert marker is not None
    assert marker["sha256"] != hashlib.sha256(stalled_text.encode("utf-8")).hexdigest()

    _dcr_answer_gate(project, _dcr_gate_by_key(project)["k1"], "approved")
    assert conductor.tick(project, st) == "ok"
    # the L3 section did not clobber the stall draft; the credit funded l3-a2
    assert "## 遗留问题（stalled 草稿）" in achieved_path.read_text(encoding="utf-8")
    assert [r["task_key"] for r in _rows(project, "ap-k1-l3-a2")] == ["ap-k1-l3-a2"]
    _verify(
        "VC-006", sha_mismatch_no_overwrite=true_str(True),
        draft_preserved=true_str(True), resume_credit_used=true_str(True),
    )

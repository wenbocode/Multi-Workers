"""
test_autopilot_gate_guards.py — T-01 conductor guard pack (AC-022 / AC-028,
VC-029 / VC-030 / VC-031 / VC-042).

Three guard-only fixes, no decision-semantics change:

- D1: ``_consumed_gate_ids`` consumption regex must match 5+ digit gate ids
  (``gate-10000``); the old ``\\d{4}\\b`` silently missed them.
- D2: ``_apply_stalled_rejections`` needs the same consumption guard as
  ``_apply_stalled_approvals``; reachable because ``mark_stalled`` only
  short-circuits ``== "stalled"`` (``closed-legacy → stalled`` is allowed).
- D4: ``_set_stage_status`` gains a pure monotonic predicate; terminal
  stages may not regress / cross-convert / be downgraded, and the refusal
  leaves one deduplicated ``stage-reopen-refused`` event.

All assertions are on file truth (roadmap status lines / timeline events),
driven against tmp_path projects.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import config, conductor, gates, roadmap, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


# ── fixtures ──────────────────────────────────────────────────────────────────

def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    ap = tmp_path / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text(
        "# Goal\n\nShip it.\n", encoding="utf-8"
    )
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp_path, cfg)
    return tmp_path


def _state(project: pathlib.Path) -> conductor.ConductorState:
    tl = timeline.Timeline(timeline.timeline_path(project))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(project))


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _write_roadmap(project: pathlib.Path, text: str) -> pathlib.Path:
    path = project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    path.write_text(text, encoding="utf-8")
    return path


def _one_stage_roadmap(stage_status: str, key_status: str = "done") -> str:
    return (
        "# Roadmap\n"
        "> generated_at: t\n"
        "> goal_mtime: 1\n"
        "\n"
        "## Stage 1: work\n"
        "> goal: deliver\n"
        f"> status: {stage_status}\n"
        f"> key-status: k1={key_status}\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        "| k1 | worker | - |\n"
    )


def _stage_status(project: pathlib.Path, number: int) -> str:
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    stage = roadmap.stage_by_number(rm, number)
    assert stage is not None
    return stage.status


def _answer_gate(path: pathlib.Path, status: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert "status: pending" in text
    text = text.replace("status: pending", f"status: {status}", 1)
    text = text.replace(
        "answered_at:", "answered_at: 2026-09-22T00:00:00+00:00", 1
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def _set_key_status(project: pathlib.Path, key: str, number: int, value: str) -> None:
    """Rewrite one key-status value by hand (what mark_stalled would write)."""
    path = roadmap.roadmap_path(project)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        roadmap.update_key_status(text, number, key, value),
        encoding="utf-8",
        newline="\n",
    )


def _refused(project: pathlib.Path) -> list[dict]:
    return [e for e in _events(project) if e["ev"] == "stage-reopen-refused"]


# ── D1: consumption regex must match 5+ digit gate ids (VC-029) ──────────────

def test_gate_consumption_matches_five_digit_ids(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    st = _state(project)
    st.timeline.append(
        "gate-answered", stage=1, detail="gate-10000 approved → stage 1 running"
    )
    assert conductor._consumed_gate_ids(project) == {"gate-10000"}
    # a 4-digit id still matches, and the token is not truncated
    st.timeline.append(
        "gate-answered", stage=1, detail="gate-6687 rejected → k1 closed-legacy"
    )
    assert conductor._consumed_gate_ids(project) == {"gate-10000", "gate-6687"}
    _verify("VC-029", five_digit_consumed="true")


def test_gate_consumption_ignores_non_boundary_ids(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    st = _state(project)
    st.timeline.append("gate-answered", stage=1, detail="gate-10000x approved (typo)")
    st.timeline.append("gate-answered", stage=1, detail="context gate-10000 approved")
    assert conductor._consumed_gate_ids(project) == set()


# ── D2: stalled-reject consumption guard (VC-030) ────────────────────────────

def _rejected_stalled_gate(project: pathlib.Path, key: str = "k1") -> gates.Gate:
    path = gates.create(
        conductor.gates_dir(project), "stalled",
        f"key {key} 已 stalled——遗留关闭（closed-legacy），还是人工介入后重试？",
        context_refs=[f".agenticdoc/{key}"], key=key,
    )
    _answer_gate(path, "rejected")
    found = [g for g in gates.enumerate(conductor.gates_dir(project)) if g.key == key]
    assert len(found) == 1
    return found[0]


def test_rejected_stalled_gate_is_consumed_once(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("running", "stalled"))
    st = _state(project)
    gate = _rejected_stalled_gate(project)

    conductor._apply_stalled_rejections(project, st, {"k1": "stalled"}, {"k1": 1})
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    assert rm.stages[0].key_status["k1"] == "closed-legacy"
    first = [
        e for e in _events(project)
        if e["ev"] == "gate-answered" and gate.id in str(e.get("detail", ""))
    ]
    assert len(first) == 1

    # Reachability (VC-030): mark_stalled only short-circuits == "stalled",
    # so a closed-legacy key can re-stall and the same rejected gate is seen
    # again. A replay must NOT rewrite key-status a second time.
    _set_key_status(project, "k1", 1, "stalled")
    conductor._apply_stalled_rejections(project, st, {"k1": "stalled"}, {"k1": 1})
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    assert rm.stages[0].key_status["k1"] == "stalled"  # replay was refused
    replayed = [
        e for e in _events(project)
        if e["ev"] == "gate-answered" and gate.id in str(e.get("detail", ""))
    ]
    assert len(replayed) == 1  # exactly one consumption record
    _verify(
        "VC-030", gate=gate.id, key_status_writes=1,
        key_status=rm.stages[0].key_status["k1"],
    )


# ── D4: stage-status monotonicity + deduplicated refusal (VC-042) ────────────

def test_stage_transition_predicate_is_monotone() -> None:
    allowed = conductor._stage_transition_allowed
    # forward progression
    assert allowed("pending", "running")
    assert allowed("approved", "running")
    assert allowed("running", "closed")
    assert allowed("running", "closed-human")
    assert allowed("running", "halted")
    # non-terminal downgrade refused
    assert not allowed("running", "pending")
    assert not allowed("running", "approved")
    # terminal family: no regress / cross-convert / downgrade
    for terminal in ("closed", "closed-human", "halted"):
        for other in ("pending", "approved", "running", "closed", "closed-human", "halted"):
            assert not allowed(terminal, other), (terminal, other)
    # unknown statuses fail closed
    assert not allowed("pending", "banana")
    assert not allowed("banana", "running")


def test_closed_stage_reopen_refused_and_deduped(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("closed"))
    st = _state(project)
    rm_path = roadmap.roadmap_path(project)

    assert conductor._set_stage_status(project, st, rm_path, 1, "running") is False
    assert _stage_status(project, 1) == "closed"
    assert conductor._set_stage_status(project, st, rm_path, 1, "running") is False
    refused = _refused(project)
    assert len(refused) == 1  # deduplicated across the replay
    assert refused[0]["stage"] == 1
    assert "closed → running" in refused[0]["detail"]
    _verify(
        "VC-042", refused=len(refused), dedup="true",
        stage_status=_stage_status(project, 1),
    )


def test_terminal_family_cross_convert_refused(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("halted"))
    st = _state(project)
    rm_path = roadmap.roadmap_path(project)

    assert conductor._set_stage_status(project, st, rm_path, 1, "closed") is False
    assert conductor._set_stage_status(project, st, rm_path, 1, "running") is False
    assert _stage_status(project, 1) == "halted"
    details = sorted(str(e["detail"]) for e in _refused(project))
    assert any("halted → closed" in d for d in details)
    assert any("halted → running" in d for d in details)


def test_legal_stage_transitions_still_write(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("pending"))
    st = _state(project)
    rm_path = roadmap.roadmap_path(project)

    assert conductor._set_stage_status(project, st, rm_path, 1, "running") is True
    assert _stage_status(project, 1) == "running"
    assert conductor._set_stage_status(project, st, rm_path, 1, "closed") is True
    assert _stage_status(project, 1) == "closed"
    assert conductor._set_stage_status(project, st, rm_path, 1, "closed") is False
    assert _refused(project) == []  # legal writes never leave a refusal


def test_stage_confirm_replay_cannot_reopen_closed_stage(
    tmp_path: pathlib.Path,
) -> None:
    """JC gate-0001 shape: an approved stage-confirm gate replays while the
    stage is already closed — the write is refused and the gate is never
    consumed (no second gate-answered)."""
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("closed"))
    st = _state(project)
    cfg = config.default_config()
    gate_path = gates.create(
        conductor.gates_dir(project), "stage-confirm",
        "Stage 1 已就绪——确认启动该 stage？", stage=1,
    )
    _answer_gate(gate_path, "approved")

    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert _stage_status(project, 1) == "closed"
    assert [e for e in _events(project) if e["ev"] == "gate-answered"] == []
    assert len(_refused(project)) == 1

    # restart / next tick replays the same gate → still one refusal record
    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert _stage_status(project, 1) == "closed"
    assert len(_refused(project)) == 1
    _verify("VC-042", replay_refused=1, gate_answered=0, stage_status="closed")

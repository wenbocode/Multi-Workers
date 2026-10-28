"""
test_mwds_t09_gate_stage_terminal.py — T-09 (mw-dispatch-settle-gates, AC-002).

L1 tests for the fourth condition of the pending-gate reminder judgment in
`autopilot/conductor.py`: a gate that provably belongs to a terminal autopilot
stage is not reminded about, while every unresolvable case stays fail-open.

VC-004 reminder judgment consumes `_STAGE_TERMINAL_RANK` (single truth source)
VC-005 gates created without `stage` resolve through `roadmap.stage_of_key`
VC-006 no `_roadmap.md` -> byte-identical reminders (fail-open, existing 12)
VC-007 `halted` stage gate -> zero reminders; the TS panel keeps it current
VC-008 an active stage + a pending gate still reminds (no over-suppression)

Reverse cases (a)-(g) are named per the task card; the module is self-contained
(gate/timeline/roadmap fixtures are local, no other test file is imported).
"""
import ast
import datetime
import inspect
import pathlib
import re
import sys
import textwrap

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import config, conductor, gates, roadmap, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _true(value: bool) -> str:
    return "true" if value else "false"


# ── fixtures ──────────────────────────────────────────────────────────────────

def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    ap = tmp_path / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text("# Goal\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp_path, cfg)
    return tmp_path


def _state(project: pathlib.Path) -> conductor.ConductorState:
    tl = timeline.Timeline(timeline.timeline_path(project))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(project))


def _events(project: pathlib.Path, ev: str | None = None) -> list[dict]:
    events = timeline.query_events(timeline.timeline_path(project)).events
    return [e for e in events if ev is None or e.get("ev") == ev]


def _remind_rows(project: pathlib.Path) -> list[dict]:
    return [
        row for row in conductor.auto_decision_rows(project)
        if row.get("phase") == "remind"
    ]


def _roadmap_text(stages: list[tuple[int, str, list[str]]]) -> str:
    """One roadmap: `(number, status, keys)` per stage. Every declared key
    also gets a `> key-status:` line (roadmap.py requires the two key sets to
    match bidirectionally)."""
    lines = [
        "# Roadmap",
        "> generated_at: 2026-09-10T00:00:00+00:00",
        "> goal_mtime: 1789000000000",
        "",
    ]
    for number, status, keys in stages:
        lines += [
            f"## Stage {number}: stage-{number}",
            f"> goal: deliver stage {number}",
            f"> status: {status}",
            "> key-status: " + ", ".join(f"{k}=running" for k in keys),
            "### Keys",
            "| key | role | depends_on |",
            "|-----|------|-----------|",
            *[f"| {k} | worker | - |" for k in keys],
            "",
        ]
    return "\n".join(lines)


def _roadmap(project: pathlib.Path, text: str) -> None:
    path = project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    path.write_text(text, encoding="utf-8", newline="\n")


def _create_gate(
    project: pathlib.Path,
    *,
    kind: str = "stalled",
    key: str | None = "k1",
    stage: int | None = None,
) -> pathlib.Path:
    return gates.create(
        conductor.gates_dir(project), kind, "test gate", stage=stage, key=key
    )


def _age_gate(gate_file: pathlib.Path, minutes: float) -> None:
    """Rewrite `created_at` so the gate looks `minutes` old (the reminder
    anchor is the gate's own `created_at`; gates.create always stamps now)."""
    stamp = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(minutes=minutes)
    ).isoformat(timespec="seconds")
    text = gate_file.read_text(encoding="utf-8")
    rewritten = re.sub(
        r"^created_at:.*$", f"created_at: {stamp}", text, count=1, flags=re.MULTILINE
    )
    assert rewritten != text, "gate file has no created_at line"
    gate_file.write_text(rewritten, encoding="utf-8", newline="\n")


def _remind(project: pathlib.Path) -> None:
    """Run the one per-tick reminder step (tick's step 2b) in isolation."""
    conductor._remind_pending_gates(  # noqa: SLF001 — the unit under test
        project, _state(project), config.default_config()
    )


# ── (a)(b) terminal stage via the gate's own `stage` snapshot ────────────────

@pytest.mark.parametrize("status", ["closed", "closed-human", "halted"])
def test_gate_stage_terminal_suppresses_reminder(
    tmp_path: pathlib.Path, status: str
) -> None:
    """(a) `closed` / (b) `halted` (and `closed-human`) + a leaked pending gate
    -> zero reminders: the gate's own `stage=` snapshot resolves to a terminal
    stage. The gate file itself is untouched (no new state)."""
    project = _project(tmp_path)
    _roadmap(project, _roadmap_text([(1, status, ["k1"])]))
    gate_file = _create_gate(project, kind="stage-confirm", key="k1", stage=1)
    _age_gate(gate_file, 31)
    before = gate_file.read_bytes()
    _remind(project)
    assert _remind_rows(project) == [], status
    assert _events(project, "gate-reminder") == [], status
    assert gates.parse(gate_file).status == "pending"  # suppressed, not answered
    assert gate_file.read_bytes() == before  # no residual write
    _verify(
        f"VC-007_{status}",
        gate_stage_terminal="1/1",
        reminders=0,
        gate_file_untouched=_true(gate_file.read_bytes() == before),
    )


# ── (c) two-level resolution: gate.stage absent, key->stage map used ─────────

def test_gate_without_stage_resolves_through_key(tmp_path: pathlib.Path) -> None:
    """(c) the gate carries no `stage`, but its `key` is declared by a terminal
    stage in the roadmap -> `stage_of_key` resolves it and it is suppressed."""
    project = _project(tmp_path)
    _roadmap(project, _roadmap_text([(1, "closed", ["k1"]), (2, "running", ["k2"])]))
    gate_file = _create_gate(project, kind="stalled", key="k1", stage=None)
    _age_gate(gate_file, 31)
    _remind(project)
    assert gates.parse(gate_file).stage is None
    assert _remind_rows(project) == []
    assert _events(project, "gate-reminder") == []
    _verify("VC-005", no_gate_stage_resolved="1/1", resolution="key->stage=1", reminders=0)


# ── (d) fail-open: no roadmap at all (the shape of the existing 12 tests) ────

def test_no_roadmap_fails_open_and_reminds(tmp_path: pathlib.Path) -> None:
    """(d) the pre-AC-002 fixture shape: no `_roadmap.md`. The stage facts are
    absent, so condition 4 never fires and the reminder is emitted exactly as
    before (verbatim behavior lock; VC-006 rides the existing 12-test file)."""
    project = _project(tmp_path)
    assert not (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").exists()
    gate_file = _create_gate(project, kind="stalled", key="k1")
    _age_gate(gate_file, 31)
    _remind(project)
    rows = _remind_rows(project)
    events = _events(project, "gate-reminder")
    assert len(rows) == 1 and rows[0]["reminder_n"] == 1 and rows[0]["gate_key"] == "k1"
    assert len(events) == 1 and events[0]["data"]["gate_kind"] == "stalled"
    _verify("VC-006", no_roadmap_reminders="1/1", fail_open=_true(True))


# ── (e) an active stage does not suppress a pending gate ─────────────────────

def test_running_stage_still_reminds(tmp_path: pathlib.Path) -> None:
    """(e) stage `running` (rank 1 < terminal rank 2) -> the pending gate still
    reminds: no over-suppression of the active stage."""
    project = _project(tmp_path)
    _roadmap(project, _roadmap_text([(1, "running", ["k1"])]))
    gate_file = _create_gate(project, kind="stalled", key="k1", stage=None)
    _age_gate(gate_file, 31)
    _remind(project)
    rows = _remind_rows(project)
    events = _events(project, "gate-reminder")
    assert len(rows) == 1 and rows[0]["reminder_n"] == 1
    assert len(events) == 1
    _verify("VC-008", running_stage_reminders=len(rows), events=len(events))


# ── (f) corrupt roadmap -> fail-open + one conductor.log diagnostic ──────────

def test_corrupt_roadmap_fails_open_and_logs(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(f) an unparseable roadmap raises RoadmapError, which is caught: the
    judgment degrades to no-suppression (reminder still fires) and one
    diagnostic line reaches stderr (= `.mw/conductor.log` under `mw serve`).

    Note: the roadmap is markdown, so "invalid JSON" is realized as a
    structurally invalid roadmap — both arrive as `RoadmapError` from
    `roadmap.load_roadmap`, which is the only contract this card relies on."""
    project = _project(tmp_path)
    _roadmap(project, "# Roadmap\n\n## Stage 1: broken\n> status: not-a-status\n")
    gate_file = _create_gate(project, kind="stalled", key="k1")
    _age_gate(gate_file, 31)
    _remind(project)
    captured = capsys.readouterr()
    diagnostics = [ln for ln in captured.err.splitlines() if "roadmap unavailable" in ln]
    rows = _remind_rows(project)
    assert len(rows) == 1
    assert len(diagnostics) == 1, captured.err
    assert "stage-terminal suppression disabled" in diagnostics[0]
    _verify(
        "VC-006",
        corrupt_roadmap_reminders=len(rows),
        diagnostics=len(diagnostics),
        fail_open=_true(True),
    )


# ── (g) exactly one roadmap read per tick ────────────────────────────────────

def test_one_roadmap_read_per_tick(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(g) each reminder pass reads the roadmap exactly once, however many
    pending gates there are (the facts are injected, never re-read per gate)."""
    project = _project(tmp_path)
    _roadmap(project, _roadmap_text([(1, "running", ["k1", "k2"])]))
    for key in ("k1", "k2"):
        _age_gate(_create_gate(project, kind="stalled", key=key), 31)
    reads: list[pathlib.Path] = []
    real_load = roadmap.load_roadmap

    def counting(path: pathlib.Path) -> roadmap.Roadmap:
        reads.append(pathlib.Path(path))
        return real_load(path)

    monkeypatch.setattr(roadmap, "load_roadmap", counting)
    _remind(project)
    assert len(reads) == 1, reads
    assert len(_remind_rows(project)) == 2  # both gates judged from that one read
    _verify("VC-004", roadmap_reads_per_tick=len(reads), pending_gates=2)


# ── VC-004 source contract: single truth source, no inlined family ───────────

def test_judgment_consumes_terminal_rank_not_an_inline_copy() -> None:
    """VC-004 as a source assertion: the judgment references
    `_STAGE_TERMINAL_RANK` and does not inline the terminal family names."""
    src = textwrap.dedent(inspect.getsource(conductor.pending_gate_reminders))
    tree = ast.parse(src)
    string_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    inline_family = string_constants & {"closed", "closed-human", "halted"}
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert inline_family == set(), inline_family
    assert "_STAGE_TERMINAL_RANK" in names
    assert conductor._STAGE_STATUS_RANK["closed"] == conductor._STAGE_TERMINAL_RANK
    assert conductor._STAGE_STATUS_RANK["closed-human"] == conductor._STAGE_TERMINAL_RANK
    assert conductor._STAGE_STATUS_RANK["halted"] == conductor._STAGE_TERMINAL_RANK
    _verify(
        "VC-004",
        consumes="_STAGE_TERMINAL_RANK",
        inline_copy=0,
        terminal_rank=conductor._STAGE_TERMINAL_RANK,
    )


# ── VC-005: 3 of the 4 stage-less gate creation sites resolve via key ────────

def test_stage_less_call_sites_resolve_via_key(tmp_path: pathlib.Path) -> None:
    """The 4 production gate creation sites that pass no `stage=`
    (budget-exhausted, xkey-authorize, stalled carry a `key`; goal-change
    carries neither). The 3 key-bearing sites resolve through `stage_of_key`
    and are suppressed by a terminal stage; the global one keeps reminding.

    This is the machine form of `[VERIFY] VC-005: no_gate_stage_resolved=3/4`."""
    project = _project(tmp_path)
    _roadmap(
        project,
        _roadmap_text([(1, "closed", ["k-budget", "k-xkey", "k-stalled"])]),
    )
    key_level = [
        ("budget-exhausted", "k-budget"),
        ("xkey-authorize", "k-xkey"),
        ("stalled", "k-stalled"),
    ]
    for kind, key in key_level:
        _age_gate(_create_gate(project, kind=kind, key=key, stage=None), 31)
    _age_gate(_create_gate(project, kind="goal-change", key=None, stage=None), 31)
    _remind(project)

    reminded = {row["gate_kind"] for row in _remind_rows(project)}
    assert reminded == {"goal-change"}
    resolved = sum(1 for _, key in key_level if key in roadmap.stage_of_key(
        roadmap.load_roadmap(roadmap.roadmap_path(project))
    ))
    assert resolved == 3
    _verify(
        "VC-005",
        no_gate_stage_resolved=f"{resolved}/4 call_sites",
        suppressed=len(key_level),
        global_gate_reminded=len(_remind_rows(project)),
    )


# ── integration: the same judgment through tick(), and the panel口径 ─────────

def test_tick_suppresses_terminal_stage_gate(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end through `tick` (step 2b), with orchestrate stubbed so only
    the reminder step can act: a terminal stage yields zero reminders."""
    project = _project(tmp_path)
    monkeypatch.setattr(conductor, "orchestrate", lambda root, st: None)
    _roadmap(project, _roadmap_text([(1, "closed", ["k1"])]))
    gate_file = _create_gate(project, kind="stage-close", key="k1", stage=1)
    _age_gate(gate_file, 31)
    assert conductor.tick(project, _state(project)) in ("ok", "halted-goal-change")
    assert _remind_rows(project) == []
    assert _events(project, "gate-reminder") == []
    _verify("VC-007", tick_terminal_reminders=0)


def test_panel_still_treats_halted_as_current() -> None:
    """VC-007's panel half: this card is conductor-side only. The TS status
    model still treats `halted` as the current (not closed) stage, so the
    deliberate口径 split — conductor suppresses the reminder, the panel keeps
    showing the stage — is locked here without touching any TS file."""
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    ts = (
        repo_root
        / "packages"
        / "coding-agent"
        / "src"
        / "extensions"
        / "agent-team-loop"
        / "autopilot"
        / "status-model.ts"
    )
    text = ts.read_text(encoding="utf-8")
    assert 's.status !== "closed" && s.status !== "closed-human"' in text
    _verify("VC-007", halted_reminders=0, panel_unchanged=_true(True))

"""
test_mwds_t20_roadmap_table.py — T-20 (mw-dispatch-card-gate): conductor
roadmap keys-table parse robustness + degradation localization + fail-loud.

The incident (`H:\\git\\E2Feature`): one unescaped ``|`` inside a role cell split
a 3-column keys-table row into 4; `roadmap.load_roadmap` raised; the conductor
declared the whole roadmap "unavailable"; and that single row disabled
stage-terminal suppression AND every dispatch for two days — with the only
trace a repeated stderr line in `.mw/conductor.log`.

Locked here (machine form of the card's requirements 1/2/3/4/5):

  VC-T20-01  M > N cells  -> the row is RECOVERED (key/role/depends_on) and a
             `RoadmapWarning` records the unescaped pipe
  VC-T20-02  M < N cells  -> the row is SKIPPED with a warning while the other
             rows stay usable; `strict=True` still raises (pre-T-20 behaviour)
  VC-T20-03  missing header / no stage sections -> still `RoadmapError`
  VC-T20-04  degradation localized: stage-terminal suppression still fires on a
             '|'-damaged roadmap (counterfactual: the injected pre-T-20
             `RoadmapError` DOES disable it)
  VC-T20-05  the alarm is operator-visible (timeline `config` + stderr) and is
             deduplicated per (file, line, kind) per session

The module is self-contained: gate/timeline/roadmap fixtures are local (the
same shapes as `test_mwds_t09_gate_stage_terminal.py`), no other test file is
imported, and nothing touches a real project.
"""
import datetime
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import config, conductor, gates, roadmap, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _true(value: bool) -> str:
    return "true" if value else "false"


# ── roadmap fixtures ─────────────────────────────────────────────────────────

def _roadmap_text(*, key_rows: list[str], header: bool = True) -> str:
    """One stage (running) with the given raw table rows. `key_rows` are the
    literal '| ... |' lines so a damaged row can be pinned verbatim."""
    lines = [
        "# Roadmap",
        "> generated_at: 2026-09-10T00:00:00+00:00",
        "> goal_mtime: 1789000000000",
        "",
        "## Stage 1: stage-1",
        "> goal: deliver stage 1",
        "> status: running",
        "> key-status: k1=done, k2=done",
        "### Keys",
    ]
    if header:
        lines += ["| key | role | depends_on |", "|-----|------|-----------|"]
    lines += key_rows
    lines.append("")
    return "\n".join(lines)


#: The verbatim pre-fix row recovered from `H:\git\E2Feature\.mw\conductor.log`
#: (GBK-decoded; the live `_roadmap.md` was repaired on 2026-10-13 00:49 and no
#: longer carries the inner pipe). The role contains an unescaped `|` inside
#: `` `view=feature | module` `` which split the row into 4 cells.
REAL_OFFENDING_ROLE_A = (
    "**批次 2 我的线（L3 Feature 卡 + `/mine`）**：一个 owner 进 `/mine`，3 分钟内知道"
    "今天有没有他的事——①新增 N8 `GET /mine/summary`（三源并集计数 + 今日待办条）"
    "/ N9 `GET /features/{id}/deps?view=shared`（本批只上共担视图，`view=feature"
)
REAL_OFFENDING_ROLE_B = "module` 返回 `53`）/ N11 `GET /features/{id}/interfaces`（挂接点 / API）"
REAL_OFFENDING_ROW = f"| feature-mine-line | {REAL_OFFENDING_ROLE_A} | {REAL_OFFENDING_ROLE_B} | feature-planning-cockpit |"


# ── conductor fixtures (same shapes as T-09) ─────────────────────────────────

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


def _write_roadmap(project: pathlib.Path, text: str) -> pathlib.Path:
    path = roadmap.roadmap_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _events(project: pathlib.Path, ev: str | None = None) -> list[dict]:
    events = timeline.query_events(timeline.timeline_path(project)).events
    return [e for e in events if ev is None or e.get("ev") == ev]


def _config_events(project: pathlib.Path, needle: str) -> list[dict]:
    return [
        event for event in _events(project, "config")
        if needle in str(event.get("detail", ""))
    ]


def _remind_rows(project: pathlib.Path) -> list[dict]:
    return [
        row for row in conductor.auto_decision_rows(project)
        if row.get("phase") == "remind"
    ]


def _create_gate(
    project: pathlib.Path, *, kind: str = "stalled", key: str | None = "k1"
) -> pathlib.Path:
    return gates.create(conductor.gates_dir(project), kind, "test gate", key=key)


def _age_gate(gate_file: pathlib.Path, minutes: float) -> None:
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
    conductor._remind_pending_gates(  # noqa: SLF001 — the unit under test
        project, _state(project), config.default_config()
    )


@pytest.fixture(autouse=True)
def _fresh_alarm_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts a fresh alarm-dedup session (the production registry
    is per conductor process; a test process would otherwise leak state)."""
    monkeypatch.setattr(conductor, "_ROADMAP_ALARM_SEEN", set())


# ── VC-T20-01: M > N cells -> recovered row + warning fact ───────────────────

def test_pipe_in_cell_is_recovered_with_warning(tmp_path: pathlib.Path) -> None:
    text = _roadmap_text(key_rows=["| k1 | use a | b choice | - |"])
    parsed = roadmap.parse_roadmap(text)  # strict default: the row is not illegal
    stage = roadmap.stage_by_number(parsed, 1)
    assert stage is not None
    assert [(k.key, k.role, k.depends_on) for k in stage.keys] == [
        ("k1", "use a | b choice", ())
    ]
    assert len(parsed.warnings) == 1
    warning = parsed.warnings[0]
    assert warning.kind == "recovered-pipe"
    assert warning.stage == 1
    assert "unescaped '|'" in warning.reason
    # fail-loud: the recovered row is never silent
    assert any("roadmap parse warning" in p for p in roadmap.validate_roadmap(parsed))

    project = _project(tmp_path)
    _write_roadmap(project, text)
    loaded = roadmap.load_roadmap(roadmap.roadmap_path(project))
    assert loaded.stages[0].keys[0].role == "use a | b choice"  # roadmap available
    assert loaded.warnings[0].path == str(roadmap.roadmap_path(project))
    _verify(
        "VC-T20-01",
        available=_true(True),
        recovered_key=loaded.stages[0].keys[0].key,
        recovered_depends_on=str(loaded.stages[0].keys[0].depends_on),
        warnings=len(loaded.warnings),
    )


def test_real_incident_row_is_recovered(tmp_path: pathlib.Path) -> None:
    """The exact row from the E2Feature conductor.log: the role is rebuilt by
    the fixed rule and the trailing dependency key is preserved."""
    project = _project(tmp_path)
    _write_roadmap(
        project, _roadmap_text(key_rows=[REAL_OFFENDING_ROW, "| k2 | plain | - |"])
    )
    loaded = roadmap.load_roadmap(roadmap.roadmap_path(project))
    stage = roadmap.stage_by_number(loaded, 1)
    assert stage is not None
    by_key = {k.key: k for k in stage.keys}
    assert set(by_key) == {"feature-mine-line", "k2"}
    assert by_key["feature-mine-line"].depends_on == ("feature-planning-cockpit",)
    assert by_key["feature-mine-line"].role.endswith(REAL_OFFENDING_ROLE_B)
    assert "view=feature | module" in by_key["feature-mine-line"].role
    assert len(loaded.warnings) == 1
    _verify(
        "VC-T20-01",
        incident_row_recovered=_true(True),
        recovered_keys="feature-mine-line,k2",
        depends_on="feature-planning-cockpit",
    )


# ── VC-T20-02: M < N cells -> skipped row + warning, other rows usable ───────

def test_truncated_row_skipped_others_usable(tmp_path: pathlib.Path) -> None:
    text = _roadmap_text(key_rows=["| k1 | only-two |", "| k2 | plain | - |"])
    # strict (pre-T-20) still raises: the back-compat assertion is never weakened
    with pytest.raises(roadmap.RoadmapError):
        roadmap.parse_roadmap(text)
    parsed = roadmap.parse_roadmap(text, strict=False)
    assert [k.key for k in parsed.stages[0].keys] == ["k2"]  # k1 skipped, k2 usable
    assert [w.kind for w in parsed.warnings] == ["skipped-row"]
    assert parsed.warnings[0].lineno == 12
    assert any("roadmap parse warning" in p for p in roadmap.validate_roadmap(parsed))

    project = _project(tmp_path)
    _write_roadmap(project, text)
    loaded = roadmap.load_roadmap(roadmap.roadmap_path(project))  # production default
    assert [k.key for k in loaded.stages[0].keys] == ["k2"]
    assert loaded.warnings[0].kind == "skipped-row"
    _verify(
        "VC-T20-02",
        strict_raises=_true(True),
        lenient_keys="k2",
        skipped=len(loaded.warnings),
    )


def test_escaped_pipe_is_literal_and_needs_no_recovery() -> None:
    """The recommended fix is real: a backslash-escaped pipe inside a cell is
    a literal character, so the row is exactly 3 columns and no warning fires."""
    text = _roadmap_text(key_rows=[r"| k1 | use a \| b choice | - |"])
    parsed = roadmap.parse_roadmap(text)
    assert [(k.key, k.role, k.depends_on) for k in parsed.stages[0].keys] == [
        ("k1", "use a | b choice", ())
    ]
    assert parsed.warnings == ()


def test_empty_and_duplicate_rows_localize() -> None:
    """The other unrecoverable rows localize the same way under strict=False:
    skip + warning, document stays usable."""
    text = _roadmap_text(
        key_rows=["| | r | - |", "| k1 | r | - |", "| k1 | r2 | - |", "| k2 | r | - |"]
    )
    parsed = roadmap.parse_roadmap(text, strict=False)
    assert [k.key for k in parsed.stages[0].keys] == ["k1", "k2"]
    assert [w.kind for w in parsed.warnings] == ["skipped-row", "skipped-row"]
    with pytest.raises(roadmap.RoadmapError):
        roadmap.parse_roadmap(text)  # strict keeps the historical contract


# ── VC-T20-03: structural damage is still "roadmap unavailable" ──────────────

def test_missing_header_stays_unavailable(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, _roadmap_text(header=False, key_rows=["| k1 | r | - |"]))
    with pytest.raises(roadmap.RoadmapError, match="no header"):
        roadmap.load_roadmap(roadmap.roadmap_path(project))


def test_no_stage_sections_stays_unavailable(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, "# Roadmap\n> generated_at: x\nnothing else\n")
    with pytest.raises(roadmap.RoadmapError, match="no '## Stage"):
        roadmap.load_roadmap(roadmap.roadmap_path(project))


# ── VC-T20-04: degradation localized (stage-terminal suppression still fires) ─

def test_damaged_row_does_not_disable_stage_terminal_suppression(
    tmp_path: pathlib.Path,
) -> None:
    """Counterfactual: the pre-T-20 parse failure DID disable suppression; the
    recovered parse keeps it working (the two projects differ only in which
    parse path the conductor takes)."""
    # (A) pre-T-20 behaviour: inject the exact RoadmapError the old parser
    # raised for the incident row -> facts unavailable -> reminder fires.
    pre = _project(tmp_path / "pre")
    _write_roadmap(
        pre,
        _roadmap_text(key_rows=["| k1 | use a | b choice | - |"]).replace(
            "> status: running", "> status: closed"
        ),
    )
    _age_gate(_create_gate(pre, kind="stalled", key="k1"), 31)
    old_message = (
        "line 7 (stage 1): keys table row must have 3 columns "
        "(key | role | depends_on), got 4: ['k1', 'use a', 'b choice', '-']"
    )

    def _pre_fix_loader(path: pathlib.Path, **kwargs: object) -> roadmap.Roadmap:
        raise roadmap.RoadmapError(old_message)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(roadmap, "load_roadmap", _pre_fix_loader)
        _remind(pre)
    pre_reminders = _remind_rows(pre)
    assert len(pre_reminders) == 1, "pre-fix: suppression disabled -> reminder fires"

    # (B) post-T-20 behaviour: the recovered roadmap yields the terminal stage
    # facts -> suppression works, exactly zero reminders.
    post = _project(tmp_path / "post")
    _write_roadmap(
        post,
        _roadmap_text(key_rows=["| k1 | use a | b choice | - |"]).replace(
            "> status: running", "> status: closed"
        ),
    )
    _age_gate(_create_gate(post, kind="stalled", key="k1"), 31)
    stage_status, stage_of_key = conductor._gate_stage_context(  # noqa: SLF001
        post, _state(post)
    )
    assert stage_status == {1: "closed"} and stage_of_key == {"k1": 1}
    _remind(post)
    post_reminders = _remind_rows(post)
    assert post_reminders == [], "post-fix: suppression still works"
    assert _events(post, "gate-reminder") == []
    _verify(
        "VC-T20-04",
        pre_fix_reminders=len(pre_reminders),
        post_fix_reminders=len(post_reminders),
        stage_status=str(stage_status),
        localized=_true(len(post_reminders) == 0),
    )


# ── VC-T20-05: operator-visible, deduplicated alarms ─────────────────────────

def test_warning_alarm_visible_and_deduplicated(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path)
    rm_path = _write_roadmap(project, _roadmap_text(key_rows=["| k1 | use a | b choice | - |"]))
    st = _state(project)
    loaded = roadmap.load_roadmap(rm_path)
    # first sight alarms once (stderr + timeline); repeats stay silent
    assert conductor._emit_roadmap_warnings(project, st, loaded) == 1  # noqa: SLF001
    assert conductor._emit_roadmap_warnings(project, st, loaded) == 0  # noqa: SLF001
    captured = capsys.readouterr()
    lines = [ln for ln in captured.err.splitlines() if "roadmap parse warning" in ln]
    assert len(lines) == 1, captured.err
    # content is actionable: file path + line + reason + fix
    assert str(rm_path) in lines[0] and f"{rm_path}:12" in lines[0]
    assert "unescaped '|'" in lines[0] and "fix:" in lines[0]
    events = _config_events(project, "roadmap parse warning")
    assert len(events) == 1, events  # operator-visible via /autopilot timeline
    _verify(
        "VC-T20-05",
        alarms=len(lines),
        timeline_events=len(events),
        actionable=_true("fix:" in lines[0]),
    )


def test_reminder_tick_emits_one_alarm_across_ticks(tmp_path: pathlib.Path) -> None:
    """The integration shape: two reminder ticks over the same damaged file
    emit exactly one alarm (no per-tick repetition)."""
    project = _project(tmp_path)
    _write_roadmap(project, _roadmap_text(key_rows=["| k1 | use a | b choice | - |"]))
    _create_gate(project, kind="stalled", key="k1")  # pending, not yet due
    _remind(project)
    _remind(project)
    assert len(_config_events(project, "roadmap parse warning")) == 1
    _verify("VC-T20-05", ticks=2, alarms=1)


def test_structural_failure_alarm_is_deduplicated(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, "# Roadmap\n\n## Stage 1: broken\n> status: not-a-status\n")
    _create_gate(project, kind="stalled", key="k1")
    _remind(project)
    _remind(project)
    captured = capsys.readouterr()
    lines = [
        ln for ln in captured.err.splitlines()
        if "roadmap unavailable" in ln and "stage-terminal suppression disabled" in ln
    ]
    assert len(lines) == 1, captured.err
    assert "fix:" in lines[0]
    assert len(_config_events(project, "roadmap unavailable")) == 1
    _verify("VC-T20-05", structural_alarms=len(lines), deduplicated=_true(True))

"""
test_autopilot_gate_consumption.py — T-05 consumption carrier (AC-022 /
AC-023 / AC-028, VC-031 / VC-032 / VC-043).

The fact "this gate was consumed" moves out of the timeline — which keeps
only 2 rotated generations and therefore loses history — into the gate file
itself (`consumed_at` / `consumed_seq`, parsed by T-03). The timeline
`gate-answered` events stay a READ-ONLY fallback for gates answered before
the field existed, matched on the composite `(id, created_at)` so an id
reused across archival cannot swallow a new answer.

Non-vacuous counterfactuals (each one goes red on the pre-T-05 behaviour):
(a) rotate the whole timeline away → consumption still resolves (field);
(b) reused id with a newer `created_at` → not judged consumed (composite);
(c) consume the same gate twice → no second field write, no second event.
"""
import json
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


def _stage_confirm_gate(project: pathlib.Path) -> pathlib.Path:
    return gates.create(
        conductor.gates_dir(project), "stage-confirm",
        "Stage 1 已就绪——确认启动该 stage？", stage=1,
    )


def _rotate_timeline_away(project: pathlib.Path) -> None:
    """Simulate the 2-generation rotation dropping every retained file."""
    path = timeline.timeline_path(project)
    for candidate in [path, *sorted(path.parent.glob("timeline.jsonl.*"))]:
        candidate.unlink()


def _answered(project: pathlib.Path) -> list[dict]:
    return [e for e in _events(project) if e["ev"] == "gate-answered"]


def _gate_files(project: pathlib.Path) -> list[str]:
    return sorted(p.name for p in conductor.gates_dir(project).glob("gate-*.md"))


# ── (a) the carrier survives timeline rotation (VC-043) ──────────────────────

def test_consumed_field_carries_across_timeline_rotation(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("pending"))
    st = _state(project)
    cfg = config.default_config()
    gate_path = _stage_confirm_gate(project)
    _answer_gate(gate_path, "approved")

    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert _stage_status(project, 1) == "running"
    gate = gates.parse(gate_path)
    assert gate.consumed_at is not None  # the durable carrier
    first = _answered(project)
    assert len(first) == 1
    assert gate.consumed_seq == first[0]["seq"]  # monotone seq of the event

    # (a) move the timeline history away — the 2-generation rotation
    _rotate_timeline_away(project)
    assert _events(project) == []

    # gate-field-first: consumption still resolves with no timeline at all
    assert conductor._consumed_gate_ids(project) == {gate.id}
    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert _stage_status(project, 1) == "running"
    assert _answered(project) == []  # no replay, no second event
    assert gates.parse(gate_path).consumed_at == gate.consumed_at
    _verify(
        "VC-043", stage="running", replay_events=0,
        carrier="consumed_at/consumed_seq",
    )


def test_replayed_answered_gate_keeps_closed_stage_closed(
    tmp_path: pathlib.Path,
) -> None:
    """JC gate-0008 shape: replay after the timeline was rotated away must be
    stopped by the gate field, leaving the closed stage closed and creating
    no new gate."""
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("pending"))
    st = _state(project)
    cfg = config.default_config()
    gate_path = _stage_confirm_gate(project)
    _answer_gate(gate_path, "approved")
    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert _stage_status(project, 1) == "running"

    rm_path = roadmap.roadmap_path(project)
    rm_path.write_text(
        rm_path.read_text(encoding="utf-8").replace(
            "status: running", "status: closed", 1
        ),
        encoding="utf-8", newline="\n",
    )
    _rotate_timeline_away(project)
    before = _gate_files(project)

    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert _stage_status(project, 1) == "closed"
    assert _gate_files(project) == before  # no stage-close gate re-created
    assert _answered(project) == []
    _verify("VC-043", stage="closed", new_gates=0)


# ── (b) reused id must not be judged consumed (VC-031) ───────────────────────

def test_reused_id_with_later_created_at_is_not_consumed(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("pending"))
    gate_path = _stage_confirm_gate(project)  # gate-0001, created_at = now
    gate_id = gates.parse(gate_path).id

    # An archived generation consumed the same id long before this file
    # existed: the stale timeline record must not leak onto the new gate.
    stale = {
        "ts": "2000-01-01T00:00:00Z", "seq": 1, "ev": "gate-answered",
        "key": "1", "stage": 1,
        "detail": f"{gate_id} approved → stage 1 running",
    }
    timeline.timeline_path(project).write_text(
        json.dumps(stale) + "\n", encoding="utf-8"
    )

    # composite (id, created_at): event.ts < file.created_at -> NOT consumed.
    # The old single-key reader (id only) returns {gate_id} here.
    assert conductor._consumed_gate_ids(project) == set()

    # ... and the fresh answer is therefore applied, not swallowed.
    st = _state(project)
    cfg = config.default_config()
    _answer_gate(gate_path, "approved")
    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert _stage_status(project, 1) == "running"
    assert len(_answered(project)) == 2  # stale archived + the fresh one
    assert gates.parse(gate_path).consumed_at is not None
    _verify("VC-031", reuse_safe="true", gate=gate_id)


def test_timeline_fallback_still_resolves_legacy_history_read_only(
    tmp_path: pathlib.Path,
) -> None:
    """The fallback is not dead code: a legacy record (event after the file's
    created_at, no consumed_at field) is still honoured — and reading it must
    never rewrite the gate file (history stays immutable)."""
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("pending"))
    gate_path = _stage_confirm_gate(project)
    gate_id = gates.parse(gate_path).id
    legacy = {
        "ts": "2099-01-01T00:00:00Z", "seq": 1, "ev": "gate-answered",
        "key": "1", "stage": 1,
        "detail": f"{gate_id} approved → stage 1 running",
    }
    timeline.timeline_path(project).write_text(
        json.dumps(legacy) + "\n", encoding="utf-8"
    )

    before = gate_path.read_bytes()
    assert conductor._consumed_gate_ids(project) == {gate_id}
    assert gate_path.read_bytes() == before  # read-only fallback

    st = _state(project)
    cfg = config.default_config()
    _answer_gate(gate_path, "approved")
    before_events = len(_answered(project))  # the legacy record itself
    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert _stage_status(project, 1) == "pending"  # already consumed -> skipped
    assert len(_answered(project)) == before_events  # no new consumption event
    assert gates.parse(gate_path).consumed_at is None


# ── (c) idempotent double consumption (VC-032) ───────────────────────────────

def test_double_consumption_does_not_rewrite_or_reappend(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, _one_stage_roadmap("pending"))
    st = _state(project)
    cfg = config.default_config()
    gate_path = _stage_confirm_gate(project)
    _answer_gate(gate_path, "approved")

    writes: list[tuple] = []
    real = conductor._rewrite_gate_consumed

    def _counting(path, consumed_at, seq):
        writes.append((path, consumed_at, seq))
        return real(path, consumed_at, seq)

    monkeypatch.setattr(conductor, "_rewrite_gate_consumed", _counting)

    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert len(writes) == 1
    after_first = gate_path.read_bytes()
    assert len(_answered(project)) == 1

    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert len(writes) == 1  # no second field write
    assert gate_path.read_bytes() == after_first  # byte-identical
    assert len(_answered(project)) == 1  # no second event
    text = gate_path.read_text(encoding="utf-8")
    assert text.count("consumed_at:") == 1
    assert text.count("consumed_seq:") == 1
    print("[VERIFY] VC-032: dedup=file_id flood_handled=true second_write=0")


def test_timeline_flood_dedupes_by_gate_id(tmp_path: pathlib.Path) -> None:
    """The FM flood shape: thousands of gate-answered events for one id must
    collapse to one consumed id (no hallucinated per-event distribution)."""
    project = _project(tmp_path)
    st = _state(project)
    for _ in range(5):
        st.timeline.append(
            "gate-answered", stage=1,
            detail="gate-0001 approved → stage 1 running",
        )
    assert conductor._consumed_gate_ids(project) == {"gate-0001"}
    print("[VERIFY] VC-032: dedup=file_id flood_handled=true")


# ── carrier write contract ───────────────────────────────────────────────────

def test_rewrite_gate_consumed_preserves_body_and_line_endings(
    tmp_path: pathlib.Path,
) -> None:
    """The consumed mark is a two-line frontmatter edit: everything else in
    the file — including CRLF endings a hand edit may have introduced — is
    preserved byte-for-byte (the same contract gate-writer.ts answers with)."""
    path = tmp_path / "gate-0001.md"
    original = (
        "---\r\n"
        "id: gate-0001\r\n"
        "kind: stalled\r\n"
        "stage:\r\n"
        "key: k1\r\n"
        "created_at: 2026-09-22T00:00:00Z\r\n"
        "created_by: conductor\r\n"
        "question: retry?\r\n"
        "context_refs: []\r\n"
        "status: approved\r\n"
        "answered_at: 2026-09-22T00:00:00Z\r\n"
        "answered_by: human\r\n"
        "note:\r\n"
        "---\r\n"
        "\r\n"
        "# Gate gate-0001 (stalled)\r\n"
    )
    path.write_bytes(original.encode("utf-8"))
    conductor._rewrite_gate_consumed(path, "2026-09-26T06:00:00Z", 7)
    raw = path.read_bytes().decode("utf-8")
    assert "consumed_at: 2026-09-26T06:00:00Z" in raw
    assert "consumed_seq: 7" in raw
    assert "\r\n" in raw  # line endings untouched
    assert "# Gate gate-0001 (stalled)\r\n" in raw
    gate = gates.parse(path)
    assert gate.consumed_at == "2026-09-26T06:00:00Z"
    assert gate.consumed_seq == 7

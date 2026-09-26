"""
test_autopilot_gates.py - human gate file protocol tests (goal-autopilot T-05,
D-105).

Protocol layer only: create/seq allocation (max+1 with restart rescan),
frontmatter round-trip for all schema fields, enumerate + pending filter,
explicit exceptions on corrupt frontmatter, and 5-kind rendering. The
flow-level VC-005/VC-026 assertions (dossier, dispatch rows) live in the
T-11 conductor tests; here they are verified at the file-protocol layer via
[VERIFY] lines printed after each assertion group.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import gates

# Hand-authored gate file in the documented wire format (also doubles as the
# golden-format reference: anything create() writes must stay parseable by
# the same rules a human or the TS gate-writer would follow).
HAND_AUTHORED_FM = [
    "id: gate-0003",
    "kind: stage-confirm",
    "stage: 2",
    "key:",
    "created_at: 2026-09-10T08:00:00+00:00",
    "created_by: conductor",
    "question: Proceed to Stage 3 (integration)?",
    "context_refs:",
    "  - evidence/x.md",
    "  - 'a ref with spaces.md'",
    "status: pending",
    "answered_at:",
    "answered_by:",
    "note:",
]

# Machine-valid frontmatter used as the base for corruption tests.
VALID_FM = [
    "id: gate-0001",
    "kind: stalled",
    "stage: 2",
    "key: k3",
    "created_at: 2026-09-10T08:00:00+00:00",
    "created_by: conductor",
    "question: Is this gate valid?",
    "context_refs: []",
    "status: pending",
    "answered_at:",
    "answered_by:",
    "note:",
]


def _write_gate_file(
    tmp_path: pathlib.Path,
    fm_lines: list[str],
    name: str = "gate-0001.md",
    body: str = "body prose",
) -> pathlib.Path:
    d = tmp_path / "gates"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(
        "---\n" + "\n".join(fm_lines) + "\n---\n\n" + body + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return p


def _preset_gate(
    path: pathlib.Path,
    gate_id: str,
    *,
    kind: str = "stage-confirm",
    status: str = "pending",
) -> pathlib.Path:
    """Hand-author a gate file (id/kind/status override the golden format)."""
    lines = list(HAND_AUTHORED_FM)
    lines[0] = f"id: {gate_id}"
    lines = [
        f"status: {status}" if ln.startswith("status:") else
        f"kind: {kind}" if ln.startswith("kind:") else
        ln
        for ln in lines
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n" + "\n".join(lines) + "\n---\n\nbody\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _answer(
    path: pathlib.Path,
    *,
    status: str,
    answered_by: str,
    note: str,
    answered_at: str = "2026-09-10T09:30:00+00:00",
) -> None:
    """Answer a gate by hand-editing the file (file is the source of truth)."""
    text = path.read_text(encoding="utf-8")
    text = text.replace("status: pending", f"status: {status}")
    text = text.replace("answered_at:", f"answered_at: {answered_at}")
    text = text.replace("answered_by:", f"answered_by: {answered_by}")
    text = text.replace("note:", f"note: {note}")
    path.write_text(text, encoding="utf-8", newline="\n")


# --- create: seq = max+1 with restart rescan ----------------------------------


class TestCreateSeqAllocation:
    def test_first_gate_is_0001(self, tmp_path):
        d = tmp_path / "gates"
        p = gates.create(d, "stage-confirm", "Start Stage 1?", [".agenticdoc/goal.md"])
        assert p == d / "gate-0001.md"
        assert p.exists()
        assert gates.parse(p).id == "gate-0001"
        print("[VERIFY] VC-005: first_seq=1")

    def test_seq_increments_per_create(self, tmp_path):
        d = tmp_path / "gates"
        names = [gates.create(d, "stalled", f"q{i}", []).name for i in range(3)]
        assert names == ["gate-0001.md", "gate-0002.md", "gate-0003.md"]

    def test_seq_is_max_plus_one_not_count(self, tmp_path):
        d = tmp_path / "gates"
        gates.create(d, "stalled", "q1", [])
        gates.create(d, "stalled", "q2", [])
        (d / "gate-0001.md").unlink()
        # only gate-0002 remains: count+1 would collide, max+1 must give 0003
        assert gates.create(d, "stalled", "q3", []).name == "gate-0003.md"

    def test_restart_rescan_after_preset_0003(self, tmp_path):
        # A gate-0003 written before "restart" (hand-authored, not created by
        # this process): rescan must take max and continue at 0004.
        d = tmp_path / "gates"
        _preset_gate(d / "gate-0003.md", "gate-0003")
        p = gates.create(d, "stage-close", "Close Stage 2?", [], stage=2)
        assert p.name == "gate-0004.md"
        assert gates.parse(p).id == "gate-0004"
        # and the next create continues from the new max
        assert gates.create(d, "stalled", "q", [], key="k3").name == "gate-0005.md"
        print("[VERIFY] VC-005: seq=max_plus_one=true restart_rescan=true preset_0003_next=0004")

    def test_create_validates_arguments(self, tmp_path):
        d = tmp_path / "gates"
        with pytest.raises(gates.GateFormatError, match="kind"):
            gates.create(d, "mystery", "q", [])
        with pytest.raises(gates.GateFormatError):
            gates.create(d, "stalled", "", [])
        with pytest.raises(gates.GateFormatError):
            gates.create(d, "stalled", "line1\nline2", [])
        with pytest.raises(gates.GateFormatError):
            gates.create(d, "stalled", "q", [""])
        with pytest.raises(gates.GateFormatError):
            gates.create(d, "stalled", "q", [], stage="2")
        with pytest.raises(gates.GateFormatError):
            gates.create(d, "stalled", "q", [], stage=True)
        with pytest.raises(gates.GateFormatError):
            gates.create(d, "stalled", "q", [], key="")
        assert gates.enumerate(d) == []  # nothing was written on failure


# --- parse: frontmatter round-trip ---------------------------------------------


class TestParseRoundTrip:
    def test_all_fields_round_trip(self, tmp_path):
        d = tmp_path / "gates"
        question = (
            "Close `k3` as legacy? L3 verdict: below (round 2/2) - workers' output"
        )
        refs = [
            ".agenticdoc/_autopilot/stages/stage-2-close.md",
            "evidence/research/design-gate-l2-worker-protocol-2026-09-08.md",
            "a path with spaces and 'quote'.md",
        ]
        p = gates.create(d, "stalled", question, refs, stage=2, key="k3")
        gate = gates.parse(p)
        assert gate.id == "gate-0001"
        assert gate.kind == "stalled"
        assert gate.stage == 2
        assert gate.key == "k3"
        assert "T" in gate.created_at  # ISO timestamp (validated on parse)
        assert gate.created_by == "conductor"
        assert gate.question == question
        assert gate.context_refs == refs
        assert gate.status == "pending"
        assert gate.answered_at is None
        assert gate.answered_by is None
        assert gate.note is None
        assert gate.path == p
        print(
            f"[VERIFY] VC-005: roundtrip_fields={len(gates.FRONTMATTER_FIELDS)} "
            "context_refs=3"
        )

    def test_empty_optionals_round_trip(self, tmp_path):
        p = gates.create(tmp_path / "gates", "goal-change", "goal.md changed?", [])
        gate = gates.parse(p)
        assert gate.stage is None
        assert gate.key is None
        assert gate.context_refs == []

    def test_frontmatter_has_all_schema_fields_in_canonical_order(self, tmp_path):
        p = gates.create(tmp_path / "gates", "goal-change", "q?", [])
        lines = p.read_text(encoding="utf-8").splitlines()
        end = lines.index("---", 1)
        keys = [
            ln.split(":", 1)[0] for ln in lines[1:end] if not ln.startswith(" ")
        ]
        assert keys == list(gates.FRONTMATTER_FIELDS)
        assert len(keys) == 12

    def test_files_are_utf8_lf_only(self, tmp_path):
        p = gates.create(tmp_path / "gates", "stalled", "q?", ["x.md"], stage=1)
        raw = p.read_bytes().decode("utf-8")
        assert "\r" not in raw
        assert raw.endswith("\n")
        print("[VERIFY] VC-005: encoding=utf8 lf_only=true")

    def test_hand_authored_golden_format_parses(self, tmp_path):
        p = _write_gate_file(tmp_path, list(HAND_AUTHORED_FM))
        gate = gates.parse(p)
        assert gate.id == "gate-0003"
        assert gate.kind == "stage-confirm"
        assert gate.stage == 2
        assert gate.key is None
        assert gate.context_refs == ["evidence/x.md", "a ref with spaces.md"]

    def test_crlf_hand_edit_parses(self, tmp_path):
        d = tmp_path / "gates"
        p = gates.create(d, "stalled", "q", [])
        text = p.read_text(encoding="utf-8").replace("\n", "\r\n")
        p.write_bytes(text.encode("utf-8"))
        gate = gates.parse(p)
        assert gate.status == "pending"
        assert gate.question == "q"


# --- enumerate + pending filter -------------------------------------------------


class TestEnumerateAndPending:
    def test_missing_dir_is_empty_queue(self, tmp_path):
        assert gates.enumerate(tmp_path / "nope") == []
        assert gates.pending_gates(tmp_path / "nope") == []

    def test_enumerate_sorted_and_pending_filter(self, tmp_path):
        d = tmp_path / "gates"
        for i in range(3):
            gates.create(d, "stalled", f"q{i}", [], key=f"k{i + 1}")
        _answer(
            d / "gate-0002.md",
            status="approved",
            answered_by="ws-1:4242:1694332800",
            note="approved in window",
        )
        all_gates = gates.enumerate(d)
        assert [g.id for g in all_gates] == ["gate-0001", "gate-0002", "gate-0003"]
        pend = gates.pending_gates(d)
        assert [g.id for g in pend] == ["gate-0001", "gate-0003"]
        answered = all_gates[1]
        assert answered.status == "approved"
        assert answered.answered_by == "ws-1:4242:1694332800"  # window claimId audit
        assert answered.note == "approved in window"
        assert answered.answered_at is not None
        print("[VERIFY] VC-005: enumerate=3 pending=2 answered_by_audit=true")

    def test_non_gate_files_ignored(self, tmp_path):
        d = tmp_path / "gates"
        gates.create(d, "stalled", "q", [])
        (d / "readme.txt").write_text("noise", encoding="utf-8")
        (d / "gate-0001.md.bak").write_text("noise", encoding="utf-8")
        (d / "gate-0009.md").mkdir()  # a directory with a gate-like name
        assert [g.id for g in gates.enumerate(d)] == ["gate-0001"]


# --- corrupt frontmatter -> explicit exception ----------------------------------


class TestCorruptFrontmatter:
    def test_valid_base_parses(self, tmp_path):
        gate = gates.parse(_write_gate_file(tmp_path, list(VALID_FM)))
        assert gate.id == "gate-0001" and gate.status == "pending"

    def test_missing_opening_delimiter(self, tmp_path):
        p = _write_gate_file(tmp_path, list(VALID_FM))
        text = p.read_text(encoding="utf-8")
        p.write_text(text[len("---\n"):], encoding="utf-8", newline="\n")
        with pytest.raises(gates.GateFormatError, match="---"):
            gates.parse(p)

    def test_missing_closing_delimiter(self, tmp_path):
        lines = list(VALID_FM)
        p = _write_gate_file(tmp_path, lines)
        p.write_text("---\n" + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        with pytest.raises(gates.GateFormatError, match="closes"):
            gates.parse(p)

    def test_unknown_kind(self, tmp_path):
        lines = [ln if not ln.startswith("kind:") else "kind: mystery" for ln in VALID_FM]
        with pytest.raises(gates.GateFormatError, match="kind"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_unknown_status(self, tmp_path):
        lines = [ln if not ln.startswith("status:") else "status: maybe" for ln in VALID_FM]
        with pytest.raises(gates.GateFormatError, match="status"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_stage_not_an_integer(self, tmp_path):
        lines = [ln if not ln.startswith("stage:") else "stage: two" for ln in VALID_FM]
        with pytest.raises(gates.GateFormatError, match="stage"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_unknown_field_rejected(self, tmp_path):
        lines = list(VALID_FM) + ["priority: high"]
        with pytest.raises(gates.GateFormatError, match="unknown frontmatter field"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_duplicate_field_rejected(self, tmp_path):
        lines = list(VALID_FM) + ["status: pending"]
        with pytest.raises(gates.GateFormatError, match="duplicate"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_missing_required_field(self, tmp_path):
        lines = [ln for ln in VALID_FM if not ln.startswith("question:")]
        with pytest.raises(gates.GateFormatError, match="missing"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_garbage_line(self, tmp_path):
        lines = list(VALID_FM)
        lines.insert(4, "just some words")
        with pytest.raises(gates.GateFormatError, match="invalid frontmatter line"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_unterminated_single_quote(self, tmp_path):
        lines = [ln if not ln.startswith("question:") else "question: 'oops" for ln in VALID_FM]
        with pytest.raises(gates.GateFormatError, match="unterminated"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_double_quoted_scalar_unsupported(self, tmp_path):
        lines = [ln if not ln.startswith("question:") else 'question: "oops"' for ln in VALID_FM]
        with pytest.raises(gates.GateFormatError, match="double-quoted"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_inline_flow_list_unsupported(self, tmp_path):
        lines = [ln if not ln.startswith("context_refs:") else "context_refs: [a, b]" for ln in VALID_FM]
        with pytest.raises(gates.GateFormatError, match="context_refs"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_empty_list_item(self, tmp_path):
        lines = [
            ln if not ln.startswith("context_refs:") else "context_refs:" for ln in VALID_FM
        ]
        lines.insert(lines.index("context_refs:") + 1, "  - ")
        with pytest.raises(gates.GateFormatError, match="empty context_refs item"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_bad_created_at(self, tmp_path):
        lines = [ln if not ln.startswith("created_at:") else "created_at: yesterday" for ln in VALID_FM]
        with pytest.raises(gates.GateFormatError, match="ISO-8601"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_bad_id(self, tmp_path):
        lines = [ln if not ln.startswith("id:") else "id: 7" for ln in VALID_FM]
        with pytest.raises(gates.GateFormatError, match="id"):
            gates.parse(_write_gate_file(tmp_path, lines))

    def test_non_utf8_file(self, tmp_path):
        d = tmp_path / "gates"
        d.mkdir(parents=True)
        p = d / "gate-0001.md"
        p.write_bytes(b"\xff\xfe---\nid: gate-0001\n")
        with pytest.raises(gates.GateFormatError, match="UTF-8"):
            gates.parse(p)

    def test_error_is_explicit_valueerror(self, tmp_path):
        lines = [ln if not ln.startswith("kind:") else "kind: nope" for ln in VALID_FM]
        with pytest.raises(gates.GateFormatError) as excinfo:
            gates.parse(_write_gate_file(tmp_path, lines))
        assert isinstance(excinfo.value, ValueError)
        assert "gate-0001" in str(excinfo.value)

    def test_enumerate_raises_on_corrupt_file(self, tmp_path):
        d = tmp_path / "gates"
        gates.create(d, "stalled", "q1", [])
        gates.create(d, "stalled", "q2", [])
        (d / "gate-0002.md").write_text("---\nkind: stalled\n", encoding="utf-8")
        with pytest.raises(gates.GateFormatError, match="gate-0002"):
            gates.enumerate(d)
        print("[VERIFY] VC-005: corrupt_frontmatter=explicit_exception=true")

    def test_enumerate_raises_on_id_filename_mismatch(self, tmp_path):
        d = tmp_path / "gates"
        gates.create(d, "stalled", "q1", [])
        text = (d / "gate-0001.md").read_text(encoding="utf-8")
        # same frontmatter id, wrong file name -> queue identity corruption
        (d / "gate-0007.md").write_text(text, encoding="utf-8", newline="\n")
        with pytest.raises(gates.GateFormatError, match="gate-0007"):
            gates.enumerate(d)


# --- kinds + 3 statuses ---------------------------------------------------------


class TestKindAndStatusEnumeration:
    def test_all_kinds_render_and_round_trip(self, tmp_path):
        d = tmp_path / "gates"
        for kind in gates.GATE_KINDS:
            p = gates.create(d, kind, f"Proceed with {kind}?", [f"refs/{kind}.md"])
            text = p.read_text(encoding="utf-8")
            assert f"kind: {kind}" in text
            assert f"# Gate gate-" in text
            assert gates.parse(p).kind == kind
        count = len(gates.GATE_KINDS)
        ids = [g.id for g in gates.enumerate(d)]
        assert ids == [f"gate-{i:04d}" for i in range(1, count + 1)]
        assert {g.kind for g in gates.enumerate(d)} == set(gates.GATE_KINDS)
        print(f"[VERIFY] VC-005: kinds={count} rendered={count} roundtrip={count}")

    def test_status_lifecycle_three_values(self, tmp_path):
        d = tmp_path / "gates"
        for i, status in enumerate(gates.GATE_STATUSES):
            _preset_gate(d / f"gate-{i + 1:04d}.md", f"gate-{i + 1:04d}", status=status)
            assert gates.parse(d / f"gate-{i + 1:04d}.md").status == status
        assert [g.id for g in gates.pending_gates(d)] == ["gate-0001"]
        print("[VERIFY] VC-026: statuses=pending,approved,rejected parse=true")

    def test_rejected_gate_keeps_audit_fields(self, tmp_path):
        d = tmp_path / "gates"
        gates.create(d, "stage-close", "Close Stage 1?", [], stage=1)
        _answer(
            d / "gate-0001.md",
            status="rejected",
            answered_by="ws-2:8080:1694336400",
            note="dossier incomplete",
        )
        gate = gates.parse(d / "gate-0001.md")
        assert gate.status == "rejected"
        assert gate.answered_by == "ws-2:8080:1694336400"
        assert gate.note == "dossier incomplete"
        assert gates.pending_gates(d) == []
        print("[VERIFY] VC-026: reject_audit=answered_by+note preserved=true")

    def test_rejected_stalled_gate_parses_for_legacy_close(self, tmp_path):
        # VC-026 protocol precondition: a rejected stalled gate is consumable
        # by the conductor for the legacy-close path (T-11 does the flow).
        d = tmp_path / "gates"
        gates.create(d, "stalled", "Close k3 as legacy?", ["k3/output.md"], key="k3")
        _answer(
            d / "gate-0001.md",
            status="rejected",
            answered_by="ws-3:9090:1694337000",
            note="user chose legacy close",
        )
        gate = gates.parse(d / "gate-0001.md")
        assert (gate.kind, gate.key, gate.status) == ("stalled", "k3", "rejected")
        print("[VERIFY] VC-026: stalled_reject=parseable kind=stalled key=k3")

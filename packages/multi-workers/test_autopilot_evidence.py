"""test_autopilot_evidence.py - T-06 / AC-029 evidence snapshot + provenance.

Covers the T-06 deliverables against the frozen design names
(``evidence/research/design-evidence-provenance-20260926.md`` section F3.3 and
``design-gate-schema-presentation-20260926.md`` section D1.1):

  * ``snapshot(paths)`` pure ``(path, sha256, mtime_ns, bytes)`` records;
  * ``changed(before, after)`` by sha256 difference;
  * ``<gates>/gate-NNNN.evidence.json`` (schema exactly ``gate-evidence/1``)
    with a ``created`` and a ``consumed`` snapshot;
  * fail-closed provenance: verdict-producing sources take the minimum, a
    correction is a one-way dispute, and ``bound`` = value ``meets`` AND
    binding present-and-matching (missing binding => ``not bound``).

Counterfactuals (each must actually turn red under a wrong implementation):
  (a) rewriting an evidence file inside the answer window => ``changed[] != []``;
  (b) a source with no provenance / no sha binding => ``not bound`` (a
      default-bound implementation goes red);
  (c) correction ``corrected_value="below"`` while the verdict says ``meets``
      => the resolved value is ``below``; anchored on the real E2 key
      ``feature-l3-readcap-injection`` (verdict ``meets``, correction ``below``
      + ``counted_as_done: false`` + ``dispositions: ["pending-authorization"]``
      + ``original_sha256``, roadmap ``=done``, stage ``closed``).
"""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import evidence, gates  # noqa: E402

# --- Real E2 anchor (verbatim from the 2026-09-26T08:32Z design snapshot) ------

# H:\git\E2Feature\.agenticdoc\feature-l3-readcap-injection\l3-verdict.txt
E2_VERDICT_BYTES = b"meets\n"
E2_VERDICT_SHA = "1e01e3da4a54438288d5e205b7aa535dd8e34c3eb6c3e0e9b2d1ff829f1417d2"

# .../l3-verdict-correction-fm-136c65a70b2b.json (verbatim field values)
E2_CORRECTION = {
    "fv_version": "1.0.0",
    "fv_schema_version": "1.0",
    "run_id": "fm-136c65a70b2b",
    "generated_at": "2026-09-25T00:00:00Z",
    "key": "feature-l3-readcap-injection",
    "ledger_items": ["VC-006"],
    "dispositions": ["pending-authorization"],
    "counted_as_done": False,
    "kind": "verdict-value-correction",
    "correction": "value",
    "original_value": "meets",
    "original_sha256": E2_VERDICT_SHA,
    "corrected_value": "below",
    "recorded_path": ".agenticdoc/feature-l3-readcap-injection/l3-verdict.txt",
    "corrected_basis": "landed recompute verdict (same run_id)",
    "evidence_source": {
        "path": ".agenticdoc/feature-l3-readcap-injection/l3-report.md",
        "sha256": "6d07d711822f73465cbf59a38adda9c2d10f060eef29ca7abede9dc32c2908b2",
        "exists": True,
    },
    "evidence_source_path": ".agenticdoc/feature-l3-readcap-injection/l3-report.md",
    "evidence_source_sha256": "6d07d711822f73465cbf59a38adda9c2d10f060eef29ca7abede9dc32c2908b2",
    "owner": "用户/PM",
    "unlock_condition": "授权补一轮 L3 复评（底层修复已落地，尚未复评）",
}

# H:\git\E2Feature\.agenticdoc\_autopilot\_roadmap.md (Stage 2 header + key row)
E2_ROADMAP_KEY_STATUS_LINE = (
    "> key-status: feature-trend-two-points=done, feature-tier-a-closeout=done, "
    "feature-completeness-four-dim=done, feature-phaseb-handoff=done, "
    "feature-l3-readcap-injection=done, feature-mvp-closeout=done"
)
E2_STAGE_STATUS_LINE = "> status: closed"


def _write(path: pathlib.Path, text: str) -> pathlib.Path:
    path.write_text(text, encoding="utf-8")
    return path


# --- snapshot + changed --------------------------------------------------------


def test_snapshot_shape_purity_and_missing(tmp_path):
    a = _write(tmp_path / "a.md", "alpha")
    b = _write(tmp_path / "b.md", "beta")
    missing = tmp_path / "nope.md"

    first = evidence.snapshot([a, b])
    assert [record["path"] for record in first] == [
        evidence.norm_path(a),
        evidence.norm_path(b),
    ]
    for record, text in zip(first, ("alpha", "beta")):
        assert set(record) == {"path", "sha256", "mtime_ns", "bytes"}
        assert record["sha256"] == hashlib.sha256(text.encode()).hexdigest()
        assert record["bytes"] == len(text)
        assert isinstance(record["mtime_ns"], int)

    second = evidence.snapshot([a, b])
    assert first == second  # pure: identical input -> identical output

    absent = evidence.snapshot([missing])[0]
    assert absent == {
        "path": evidence.norm_path(missing),
        "sha256": None,
        "mtime_ns": None,
        "bytes": None,
    }

    deduped = evidence.snapshot([a, pathlib.Path(str(a))])
    assert len(deduped) == 1  # duplicate normalized path

    # No global state leaked into the module.
    assert not hasattr(evidence, "_CACHE")


def test_counterfactual_a_rewrite_inside_answer_window_is_detected(tmp_path):
    verdict = _write(tmp_path / "l3-verdict.txt", "meets\n")
    created = evidence.snapshot([verdict])

    # Control: no rewrite inside the window -> no drift (must not false-positive).
    assert evidence.changed(created, evidence.snapshot([verdict])) == []

    # Out-of-band rewrite inside the answer window -> machine-detectable.
    _write(verdict, "below\n")
    consumed = evidence.snapshot([verdict])
    assert evidence.changed(created, consumed) == [evidence.norm_path(verdict)]


def test_changed_covers_new_and_deleted_paths():
    before = [
        {"path": "p/same.md", "sha256": "aa"},
        {"path": "p/edited.md", "sha256": "bb"},
        {"path": "p/deleted.md", "sha256": "cc"},
    ]
    after = [
        {"path": "p/same.md", "sha256": "aa"},
        {"path": "p/edited.md", "sha256": "dd"},
        {"path": "p/deleted.md", "sha256": None},
        {"path": "p/added.md", "sha256": "ee"},
    ]
    assert evidence.changed(before, after) == [
        "p/added.md",
        "p/deleted.md",
        "p/edited.md",
    ]
    assert evidence.changed(before, before) == []


def test_evidence_digest_is_order_independent_and_sensitive():
    one = [{"path": "b.md", "role": "l3-report", "sha256": "bb", "bytes": 1, "mtime_ns": 1}]
    two = [{"path": "a.md", "role": "l3-verdict", "sha256": "aa", "bytes": 1, "mtime_ns": 1}]
    assert evidence.evidence_digest(one + two) == evidence.evidence_digest(two + one)
    mutated = copy.deepcopy(two)
    mutated[0]["sha256"] = "zz"
    assert evidence.evidence_digest(one + mutated) != evidence.evidence_digest(one + two)


# --- sidecar read / write ------------------------------------------------------


def _seed_gate(gates_dir: pathlib.Path, gate_id: str = "gate-0001") -> dict:
    report = _write(gates_dir.parent / "l3-report.md", "report-v1")
    gate_file = _write(gates_dir.parent / f"{gate_id}.md", "---\nstatus: pending\n---\n")
    assert evidence.record_snapshot(
        gates_dir,
        gate_id,
        reason="created",
        kind="stage-close",
        scope={"stage": 2, "key": None},
        gate_file=evidence.gate_file_record(gate_file, status="pending"),
        evidence=evidence.snapshot([report]),
    )
    return {"report": report, "gate_file": gate_file}


def test_sidecar_schema_and_field_contract(tmp_path):
    gates_dir = tmp_path / "gates"
    seed = _seed_gate(gates_dir)
    assert evidence.record_snapshot(
        gates_dir,
        "gate-0001",
        reason="consumed",
        kind="stage-close",
        scope={"stage": 2, "key": None},
        gate_file=evidence.gate_file_record(seed["gate_file"], status="approved"),
        evidence=evidence.snapshot([seed["report"]]),
    )

    path = evidence.sidecar_path(gates_dir, "gate-0001")
    assert path.name == "gate-0001.evidence.json"
    assert path.parent == gates_dir

    document = evidence.read_sidecar(gates_dir, "gate-0001")
    assert document is not None
    assert document["schema"] == "gate-evidence/1"
    assert evidence.EVIDENCE_SCHEMA == "gate-evidence/1"
    assert set(document) == {"schema", "gate_id", "kind", "scope", "snapshots"}
    assert document["gate_id"] == "gate-0001"
    assert document["kind"] in gates.GATE_KINDS
    assert document["scope"] == {"stage": 2, "key": None}

    assert [snap["reason"] for snap in document["snapshots"]] == ["created", "consumed"]
    for snap in document["snapshots"]:
        assert set(snap) == {
            "reason",
            "taken_at",
            "taken_by",
            "gate_file",
            "evidence",
            "evidence_digest",
            "unresolved",
            "changed",
            "roster_digest",
        }
        assert snap["taken_by"] == "conductor"
        assert snap["taken_by"] in {evidence.TAKEN_BY}
        assert list(snap["evidence"][0]) == [
            "path",
            "role",
            "exists",
            "bytes",
            "sha256",
            "mtime_ns",
        ]
        assert snap["evidence_digest"] == evidence.evidence_digest(snap["evidence"])
    assert document["snapshots"][1]["changed"] == []


def test_counterfactual_a_sidecar_records_consumed_changed(tmp_path):
    gates_dir = tmp_path / "gates"
    seed = _seed_gate(gates_dir)
    _write(seed["report"], "report-v2-rewritten-inside-the-window")
    evidence.record_snapshot(
        gates_dir,
        "gate-0001",
        reason="consumed",
        kind="stage-close",
        scope={"stage": 2, "key": None},
        gate_file=evidence.gate_file_record(seed["gate_file"], status="approved"),
        evidence=evidence.snapshot([seed["report"]]),
    )
    document = evidence.read_sidecar(gates_dir, "gate-0001")
    assert document["snapshots"][1]["changed"] == [evidence.norm_path(seed["report"])]
    assert evidence.sidecar_changed(document) == [evidence.norm_path(seed["report"])]


def test_record_snapshot_is_idempotent_by_reason(tmp_path):
    gates_dir = tmp_path / "gates"
    seed = _seed_gate(gates_dir)
    path = evidence.sidecar_path(gates_dir, "gate-0001")
    before = path.read_bytes()
    assert (
        evidence.record_snapshot(
            gates_dir,
            "gate-0001",
            reason="created",
            kind="stage-close",
            evidence=evidence.snapshot([seed["report"]]),
        )
        is False
    )
    assert path.read_bytes() == before  # zero-write


def test_writes_stay_inside_gates_dir(tmp_path):
    project = tmp_path / "project"
    gates_dir = project / "gates"
    report = _write(tmp_path / "l3-report.md", "x")  # outside the project root
    assert evidence.record_snapshot(
        gates_dir,
        "gate-0001",
        reason="created",
        kind="stalled",
        evidence=evidence.snapshot([report]),
        unresolved=["some/missing/pointer"],
    )
    assert sorted(entry.name for entry in project.iterdir()) == ["gates"]
    assert sorted(entry.name for entry in gates_dir.iterdir()) == [
        "gate-0001.evidence.json"
    ]


def test_read_sidecar_is_read_only_and_corrupt_is_never_overwritten(tmp_path):
    missing_dir = tmp_path / "not-yet"
    assert evidence.read_sidecar(missing_dir, "gate-0001") is None
    assert not missing_dir.exists()  # read cannot create a directory

    gates_dir = tmp_path / "gates"
    gates_dir.mkdir()
    corrupt = gates_dir / "gate-0001.evidence.json"
    corrupt.write_text("{ this is not json", encoding="utf-8")
    before = corrupt.read_bytes()
    assert evidence.read_sidecar(gates_dir, "gate-0001") is None
    assert (
        evidence.record_snapshot(
            gates_dir, "gate-0001", reason="created", kind="stalled", evidence=[]
        )
        is False
    )
    assert corrupt.read_bytes() == before


def test_gate_id_traversal_rejected(tmp_path):
    gates_dir = tmp_path / "gates"
    for bad in ("../../evil", "gate-1/../../x", "gate-01/../x", "evil", "gate-"):
        with pytest.raises(ValueError):
            evidence.sidecar_path(gates_dir, bad)
    with pytest.raises(ValueError):
        evidence.record_snapshot(
            gates_dir, "../escape", reason="created", kind="stalled"
        )
    assert not gates_dir.exists()


def test_record_snapshot_rejects_unknown_reason_and_kind(tmp_path):
    gates_dir = tmp_path / "gates"
    with pytest.raises(ValueError):
        evidence.record_snapshot(gates_dir, "gate-0001", reason="wat", kind="stalled")
    with pytest.raises(ValueError):
        evidence.record_snapshot(gates_dir, "gate-0001", reason="created", kind="wat")
    assert not gates_dir.exists()


# --- provenance resolution -----------------------------------------------------


def test_resolution_min_is_fail_closed():
    meets = [{"role": "l3-verdict", "value": "meets"}]
    below = [{"role": "recompute", "value": "below"}]
    assert evidence.resolve_value(meets).value == "meets"
    assert evidence.resolve_value(meets + below).value == "below"
    assert evidence.resolve_value(meets + [{"role": "x", "value": "garbage"}]).value == (
        evidence.INDETERMINATE
    )
    assert evidence.resolve_value([]).value == evidence.INDETERMINATE
    # An unavailable source is skipped, not treated as a dissent.
    assert (
        evidence.resolve_value(meets + [{"role": "provenance", "value": None}]).value
        == "meets"
    )


def test_counterfactual_b_no_binding_is_not_bound(tmp_path):
    """A meeting verdict with no provenance / no sha binding must be
    ``not bound``; a default-bound implementation goes red here."""
    missing = tmp_path / "l3-verdict.txt"  # never created -> no sha binding
    records = evidence.snapshot([missing])
    assert records[0]["sha256"] is None

    result = evidence.resolve(
        sources=[{"role": "l3-verdict", "value": "meets"}], evidence=records
    )
    assert result.value == "meets"
    assert result.binding == evidence.BINDING_UNBOUND
    assert result.status == evidence.STATUS_NOT_BOUND == "not bound"
    assert result.auto_release is False

    # No evidence at all is also not bound.
    bare = evidence.resolve(sources=[{"role": "l3-verdict", "value": "meets"}])
    assert bare.binding == evidence.BINDING_UNBOUND
    assert bare.status == "not bound"

    # Non-vacuous control: the binding layer itself refuses to say "bound".
    assert evidence.binding_of(records)[0] != evidence.BINDING_BOUND

    # A partial binding (one pinned pointer, one gap) is also not bound.
    pinned = _write(tmp_path / "l3-report.md", "pinned")
    partial = evidence.snapshot([pinned, missing])
    result_partial = evidence.resolve(
        sources=[{"role": "l3-verdict", "value": "meets"}], evidence=partial
    )
    assert result_partial.binding == evidence.BINDING_PARTIAL
    assert result_partial.status == "not bound"


def test_counterfactual_c_e2_correction_below_wins_over_verdict_meets(tmp_path):
    # The real E2 sha anchor: the correction binds the bytes of `meets\n`.
    assert hashlib.sha256(E2_VERDICT_BYTES).hexdigest() == E2_VERDICT_SHA
    assert E2_CORRECTION["original_sha256"] == E2_VERDICT_SHA
    assert E2_CORRECTION["corrected_value"] == "below"
    assert E2_CORRECTION["counted_as_done"] is False
    assert E2_CORRECTION["dispositions"] == ["pending-authorization"]
    assert "feature-l3-readcap-injection=done" in E2_ROADMAP_KEY_STATUS_LINE
    assert E2_STAGE_STATUS_LINE == "> status: closed"

    verdict = tmp_path / "l3-verdict.txt"
    verdict.write_bytes(E2_VERDICT_BYTES)
    records = evidence.snapshot([verdict])
    assert records[0]["sha256"] == E2_VERDICT_SHA

    result = evidence.resolve(
        sources=[{"role": "l3-verdict", "value": "meets"}],
        correction=E2_CORRECTION,
        evidence=records,
        claimed="done",
    )
    assert result.value == "below", "one-way correction must override the verdict"
    assert result.status == "not bound"
    assert result.auto_release is False
    assert "correction" in result.disputes
    assert "claimed-done-without-bound-meets" in result.disputes


def test_correction_is_one_way_and_stale_is_fail_closed(tmp_path):
    verdict = tmp_path / "l3-verdict.txt"
    verdict.write_bytes(b"below\n")
    records = evidence.snapshot([verdict])
    sha = records[0]["sha256"]

    # Upward correction: recorded, never applied (no below -> meets upgrade).
    upward = {
        "original_value": "below",
        "original_sha256": sha,
        "corrected_value": "meets",
        "counted_as_done": True,
    }
    result = evidence.resolve(
        sources=[{"role": "l3-verdict", "value": "below"}],
        correction=upward,
        evidence=records,
    )
    assert result.value == "below"
    assert "correction-upward-ignored" in result.disputes

    # Stale correction (record refreshed): fail-closed, never a silent meets.
    verdict.write_bytes(b"meets\n")
    refreshed = evidence.snapshot([verdict])
    stale = dict(E2_CORRECTION)
    stale["original_sha256"] = "0" * 64
    result_stale = evidence.resolve(
        sources=[{"role": "l3-verdict", "value": "meets"}],
        correction=stale,
        evidence=refreshed,
    )
    assert result_stale.value == evidence.INDETERMINATE
    assert result_stale.status == evidence.STATUS_INDETERMINATE
    assert result_stale.auto_release is False
    assert "correction-stale" in result_stale.disputes


def test_bound_requires_value_meets_and_matching_binding(tmp_path):
    gates_dir = tmp_path / "gates"
    report = _write(tmp_path / "l3-report.md", "stable")
    gate_file = _write(tmp_path / "gate-0007.md", "---\nstatus: pending\n---\n")
    created = evidence.snapshot([report])
    assert evidence.record_snapshot(
        gates_dir,
        "gate-0007",
        reason="created",
        kind="stalled",
        scope={"stage": None, "key": "feature-x"},
        gate_file=evidence.gate_file_record(gate_file, status="pending"),
        evidence=created,
    )
    assert evidence.record_snapshot(
        gates_dir,
        "gate-0007",
        reason="consumed",
        kind="stalled",
        scope={"stage": None, "key": "feature-x"},
        gate_file=evidence.gate_file_record(gate_file, status="approved"),
        evidence=evidence.snapshot([report]),
    )
    document = evidence.read_sidecar(gates_dir, "gate-0007")

    bound = evidence.resolve(
        sources=[{"role": "l3-verdict", "value": "meets"}],
        sidecar=document,
        expected_paths=[report],
    )
    assert bound.binding == evidence.BINDING_BOUND
    assert bound.value == "meets"
    assert bound.status == evidence.STATUS_BOUND
    assert bound.auto_release is True
    assert bound.drift is False

    # A below verdict with a perfect binding is still not allowed to auto-release.
    below = evidence.resolve(
        sources=[{"role": "l3-verdict", "value": "below"}],
        sidecar=document,
        expected_paths=[report],
    )
    assert below.binding == evidence.BINDING_BOUND
    assert below.status == "not bound"

    # A missing expected pointer breaks the binding even though value is meets.
    uncovered = evidence.resolve(
        sources=[{"role": "l3-verdict", "value": "meets"}],
        sidecar=document,
        expected_paths=[report, tmp_path / "l3-verdict.txt"],
    )
    assert uncovered.binding == evidence.BINDING_PARTIAL
    assert uncovered.status == "not bound"


def test_drift_blocks_auto_release(tmp_path):
    gates_dir = tmp_path / "gates"
    report = _write(tmp_path / "l3-report.md", "v1")
    gate_file = _write(tmp_path / "gate-0008.md", "gate")
    evidence.record_snapshot(
        gates_dir,
        "gate-0008",
        reason="created",
        kind="stalled",
        gate_file=evidence.gate_file_record(gate_file, status="pending"),
        evidence=evidence.snapshot([report]),
    )
    _write(report, "v2-rewritten")  # out-of-band change inside the answer window
    evidence.record_snapshot(
        gates_dir,
        "gate-0008",
        reason="consumed",
        kind="stalled",
        gate_file=evidence.gate_file_record(gate_file, status="approved"),
        evidence=evidence.snapshot([report]),
    )
    document = evidence.read_sidecar(gates_dir, "gate-0008")
    assert document["snapshots"][1]["changed"] == [evidence.norm_path(report)]

    result = evidence.resolve(
        sources=[{"role": "l3-verdict", "value": "meets"}],
        sidecar=document,
        expected_paths=[report],
    )
    assert result.binding == evidence.BINDING_BOUND  # the consumed hash is self-consistent
    assert result.drift is True
    assert result.status == evidence.STATUS_INDETERMINATE
    assert result.auto_release is False
    assert "drift" in result.disputes


def test_sidecar_digest_mismatch_is_not_bound(tmp_path):
    gates_dir = tmp_path / "gates"
    seed = _seed_gate(gates_dir)
    evidence.record_snapshot(
        gates_dir,
        "gate-0001",
        reason="consumed",
        kind="stage-close",
        evidence=evidence.snapshot([seed["report"]]),
    )
    document = evidence.read_sidecar(gates_dir, "gate-0001")
    document["snapshots"][0]["evidence"][0]["sha256"] = "tampered"
    binding, reasons = evidence.binding_of(
        sidecar=document, expected_paths=[seed["report"]]
    )
    assert binding == evidence.BINDING_PARTIAL
    assert "digest-mismatch" in reasons


def test_module_docstring_states_the_three_propositions():
    doc = evidence.__doc__ or ""
    assert (
        "no single linear precedence, the sources answer three different propositions"
        in doc
    )


def test_sidecar_json_roundtrip_is_utf8_and_lf(tmp_path):
    gates_dir = tmp_path / "gates"
    _seed_gate(gates_dir)
    raw = evidence.sidecar_path(gates_dir, "gate-0001").read_bytes()
    assert b"\r\n" not in raw
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["schema"] == evidence.EVIDENCE_SCHEMA

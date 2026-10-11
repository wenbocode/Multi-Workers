"""test_autopilot_contract_guard.py - G3 contract identity + authorization.

Key mw-gate-verdict-hardening, task T-04 (AC-009 / AC-011 / AC-013,
VC-012 / VC-015). The full ten-case matrix is closed out by T-11; this file is
the minimal self-contained set that also backs T-10's done-gate use.

Covered:
  - VC-012: `authorizes` is a JSON-list field with the closed set
    ``{retry, contract-change}``; out-of-set members and non-arrays are
    rejected at parse time (fail-closed); absent/empty means unauthorized.
  - VC-015: approval lookup reads only the machine field - a prose `note` that
    mentions `contract-change` is not an authorization source.
  - AC-013: the frozen 40-name frontmatter order and the 6 required fields are
    untouched, and `create()` never renders `authorizes`.
  - parsing / canonical sha / freeze sidecar / change detection / composed
    verdict.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import contract_guard, gates

SPEC_TEXT = """# Spec

## 3. Acceptance Criteria

| AC ID | 判据 |
|---|---|
| AC-001 | first contract text, locked |
| AC-002 | second contract text, locked |
| AC-003 | third contract text, locked |

prose rows are ignored: | not an AC |
"""

DESIGN_TEXT = """# Design

## §7 Verification Contract

VC-001: first assertion text
       Layer: L0   Output: [VERIFY] VC-001: one=true   Source: AC-001
VC-002: second assertion text
       Layer: L1   Output: [VERIFY] VC-002: two=true   Source: AC-002
"""


def _gate_file(
    gates_dir: pathlib.Path,
    gate_id: str,
    *,
    key: str,
    status: str,
    authorizes: list[str] | None = None,
    note: str | None = None,
) -> pathlib.Path:
    """Hand-author a schema-valid gate file (the wire format a human/TS writes)."""
    lines = [
        "---",
        f"id: {gate_id}",
        "kind: stalled",
        "stage: 2",
        f"key: {key}",
        "created_at: 2026-09-10T08:00:00+00:00",
        "created_by: conductor",
        "question: proceed?",
        "context_refs: []",
        f"status: {status}",
        "answered_at:",
        "answered_by:",
        "note:",
    ]
    if note is not None:
        lines[-1] = f"note: '{note}'"
    if authorizes is not None:
        lines.append("authorizes: '" + json.dumps(authorizes) + "'")
    lines.append("---")
    gates_dir.mkdir(parents=True, exist_ok=True)
    path = gates_dir / f"{gate_id}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _key_dir(tmp_path: pathlib.Path, spec: str = SPEC_TEXT, design: str = DESIGN_TEXT) -> pathlib.Path:
    key_dir = tmp_path / "key"
    key_dir.mkdir()
    (key_dir / "spec.md").write_text(spec, encoding="utf-8", newline="\n")
    (key_dir / "design.md").write_text(design, encoding="utf-8", newline="\n")
    return key_dir


# --- VC-012: closed set, JSON array, fail-closed ------------------------------


def test_vc012_authorizes_is_closed_set_json_list(tmp_path: pathlib.Path) -> None:
    assert "authorizes" in gates._JSON_LIST_FIELDS
    assert gates.AUTHORIZES_ACTIONS == frozenset({"retry", "contract-change"})
    assert "install" not in gates.AUTHORIZES_ACTIONS

    gdir = tmp_path / "gates"
    good = _gate_file(
        gdir, "gate-0001", key="k", status="approved",
        authorizes=["retry", "contract-change"],
    )
    assert gates.parse(good).authorizes == ["retry", "contract-change"]
    assert gates.parse(_gate_file(gdir, "gate-0002", key="k", status="pending", authorizes=[])).authorizes == []
    assert gates.parse(_gate_file(gdir, "gate-0003", key="k", status="pending")).authorizes is None

    for gate_id, action in (("gate-0004", "install"), ("gate-0005", "whatever")):
        bad = _gate_file(gdir, gate_id, key="k", status="approved", authorizes=[action])
        with pytest.raises(gates.GateFormatError):
            gates.parse(bad)

    scalar = _gate_file(gdir, "gate-0006", key="k", status="approved")
    scalar.write_text(
        scalar.read_text(encoding="utf-8").replace(
            "note:\n", 'note:\nauthorizes: \'"contract-change"\'\n'
        ),
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(gates.GateFormatError):
        gates.parse(scalar)
    print("[VERIFY] VC-012: closed_set=2 listed_only=true")


def test_vc012_array_value_requires_json_list_registration(tmp_path: pathlib.Path) -> None:
    """Counterfactual anchor: the array form only parses because the field is a
    declared JSON-list field (removing it from _JSON_LIST_FIELDS turns this red)."""
    assert "authorizes" in gates._JSON_LIST_FIELDS
    gdir = tmp_path / "gates"
    p = _gate_file(gdir, "gate-0001", key="k", status="approved", authorizes=["contract-change"])
    assert gates.parse(p).authorizes == ["contract-change"]


# --- VC-015: prose note is not an authorization source ------------------------


def test_vc015_note_prose_is_not_an_authorization_source(tmp_path: pathlib.Path) -> None:
    gdir = tmp_path / "gates"
    carrier = gates.parse(
        _gate_file(
            gdir,
            "gate-0001",
            key="k",
            status="approved",
            note="放宽的是验证方式与文档同步，contract-change 属可修范围",
        )
    )
    assert contract_guard.gate_authorizes_contract_change(carrier) is False
    assert contract_guard.find_authorizing_gate([carrier], "k") is None
    print("[VERIFY] VC-015: authorized=false")


def test_vc015_approval_requires_approved_machine_field_and_key(tmp_path: pathlib.Path) -> None:
    gdir = tmp_path / "gates"
    machine = gates.parse(
        _gate_file(gdir, "gate-0001", key="k", status="approved", authorizes=["contract-change"])
    )
    wrong_key = gates.parse(
        _gate_file(gdir, "gate-0002", key="other", status="approved", authorizes=["contract-change"])
    )
    pending = gates.parse(
        _gate_file(gdir, "gate-0003", key="k", status="pending", authorizes=["contract-change"])
    )
    empty = gates.parse(_gate_file(gdir, "gate-0004", key="k", status="approved", authorizes=[]))
    retry_only = gates.parse(
        _gate_file(gdir, "gate-0005", key="k", status="approved", authorizes=["retry"])
    )
    pool = [wrong_key, pending, empty, retry_only, machine]
    assert contract_guard.find_authorizing_gate(pool, "k") is machine
    assert contract_guard.authorizing_gates(pool, "k") == [machine]
    assert contract_guard.find_authorizing_gate(pool, "missing") is None


# --- AC-013: frozen schema shape untouched, create() renders no authorizes ----


def test_ac013_frozen_schema_and_create_render(tmp_path: pathlib.Path) -> None:
    assert len(gates._REQUIRED_FIELDS) == 6
    assert len(gates.FRONTMATTER_FIELDS) == 40
    assert "authorizes" not in gates.FRONTMATTER_FIELDS

    p = gates.create(tmp_path / "gates", "stalled", "q?", [], stage=1, key="k")
    lines = p.read_text(encoding="utf-8").splitlines()
    end = lines.index("---", 1)
    keys = [ln.split(":", 1)[0] for ln in lines[1:end] if not ln.startswith(" ")]
    assert len(keys) == 13  # base 12 + gate_schema
    assert "authorizes" not in keys
    assert gates.parse(p).authorizes is None
    print("[VERIFY] VC-016: required_fields=6 create_keys=13 authorizes_rendered=false")


# --- parsing ------------------------------------------------------------------


def test_ac_line_parser_scans_spec_table() -> None:
    acs = contract_guard.parse_acs(SPEC_TEXT)
    assert acs == {
        "AC-001": "first contract text, locked",
        "AC-002": "second contract text, locked",
        "AC-003": "third contract text, locked",
    }


def test_vc_block_parser_reuses_generator_regex_semantics() -> None:
    vcs = contract_guard.parse_vcs(DESIGN_TEXT)
    assert set(vcs) == {"VC-001", "VC-002"}
    parts = vcs["VC-001"].split("\x1f")
    assert parts == [
        "first assertion text",
        "L0",
        "[VERIFY] VC-001: one=true",
        "AC-001",
    ]


def test_canonical_sha_is_stable_and_body_sensitive() -> None:
    a = {"AC-001": "text one", "AC-002": "text two"}
    b = {"AC-002": "text two", "AC-001": "text one"}
    assert contract_guard.family_sha(a) == contract_guard.family_sha(b)
    changed = {"AC-001": "text one changed", "AC-002": "text two"}
    assert contract_guard.family_sha(a) != contract_guard.family_sha(changed)
    assert contract_guard.canonical_sha("AC-001", "text one") == contract_guard.canonical_sha(
        "AC-001", "text one"
    )
    assert contract_guard.extract_contract(SPEC_TEXT, DESIGN_TEXT).acs["AC-001"] == (
        contract_guard.canonical_sha("AC-001", "first contract text, locked")
    )


def test_trailing_cell_whitespace_does_not_move_identity() -> None:
    padded = SPEC_TEXT.replace(
        "| AC-001 | first contract text, locked |",
        "| AC-001 |   first contract text, locked   |",
    )
    assert contract_guard.parse_acs(padded)["AC-001"] == "first contract text, locked"
    assert contract_guard.family_sha(contract_guard.parse_acs(padded)) == contract_guard.family_sha(
        contract_guard.parse_acs(SPEC_TEXT)
    )


# --- freeze sidecar -----------------------------------------------------------


def test_freeze_roundtrip_shape(tmp_path: pathlib.Path) -> None:
    key_dir = tmp_path / "key"
    key_dir.mkdir()
    freeze = contract_guard.build_freeze(
        "k", SPEC_TEXT, DESIGN_TEXT, frozen_at="2026-10-10T00:00:00+00:00"
    )
    assert freeze["schema"] == 1
    assert freeze["key"] == "k"
    assert freeze["frozen_at"] == "2026-10-10T00:00:00+00:00"
    assert freeze["generator"] == contract_guard.FREEZE_GENERATOR
    assert set(freeze["spec"]) == {"AC-001", "AC-002", "AC-003"}
    assert set(freeze["design"]) == {"VC-001", "VC-002"}

    path = contract_guard.write_freeze(key_dir, freeze)
    assert path == key_dir / "evidence" / "contract-freeze.json"
    assert contract_guard.read_freeze(key_dir) == freeze
    assert "authorizes" not in path.name
    print("[VERIFY] VC-012: freeze_schema=1 spec_ids=3 design_ids=2")


def test_read_freeze_missing_or_unusable_returns_none(tmp_path: pathlib.Path) -> None:
    key_dir = tmp_path / "key"
    key_dir.mkdir()
    assert contract_guard.read_freeze(key_dir) is None

    path = contract_guard.freeze_path(key_dir)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert contract_guard.read_freeze(key_dir) is None

    path.write_text(json.dumps({"schema": 99, "spec": {}, "design": {}}), encoding="utf-8")
    assert contract_guard.read_freeze(key_dir) is None

    path.write_text(json.dumps({"schema": 1, "spec": [], "design": {}}), encoding="utf-8")
    assert contract_guard.read_freeze(key_dir) is None


def test_diff_contract_detects_added_removed_changed() -> None:
    freeze = contract_guard.build_freeze("k", SPEC_TEXT, DESIGN_TEXT)
    changed_spec = SPEC_TEXT.replace(
        "| AC-001 | first contract text, locked |", "| AC-001 | rewritten text |"
    ).replace("| AC-003 | third contract text, locked |\n", "")
    changed_spec += "| AC-004 | brand new |\n"
    changed_design = DESIGN_TEXT.replace("two=true", "two=false")
    diff = contract_guard.diff_contract(
        contract_guard.extract_contract(changed_spec, changed_design), freeze
    )
    assert diff.changed == ("AC-001", "VC-002")
    assert diff.removed == ("AC-003",)
    assert diff.added == ("AC-004",)
    assert diff.changed_ids == ("AC-001", "AC-003", "AC-004", "VC-002")
    assert diff.has_changes is True


# --- composed verdict ---------------------------------------------------------


def test_evaluate_without_freeze_is_no_anchor(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(tmp_path)
    verdict = contract_guard.evaluate(key_dir, tmp_path / "gates")
    assert verdict.ok is True
    assert verdict.no_anchor is True
    assert verdict.changed_ids == ()
    assert verdict.reasons == ("no-freeze",)


def test_evaluate_refuses_unauthorized_change_and_accepts_with_carrier(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(tmp_path)
    contract_guard.freeze_contract(key_dir, "k", SPEC_TEXT, DESIGN_TEXT)
    (key_dir / "spec.md").write_text(
        SPEC_TEXT.replace("first contract text, locked", "first contract text, rewritten"),
        encoding="utf-8",
        newline="\n",
    )
    gdir = tmp_path / "gates"

    # A pending gate and a prose note do not authorize (VC-015).
    _gate_file(gdir, "gate-0001", key="k", status="pending", authorizes=["contract-change"])
    _gate_file(gdir, "gate-0002", key="k", status="approved",
               note="contract-change was discussed")
    refused = contract_guard.evaluate(key_dir, gdir)
    assert refused.ok is False
    assert refused.no_anchor is False
    assert refused.changed_ids == ("AC-001",)
    assert refused.reasons == ("contract-unauthorized",)

    # The approved machine field authorizes it.
    _gate_file(gdir, "gate-0003", key="k", status="approved", authorizes=["contract-change"])
    allowed = contract_guard.evaluate(key_dir, gdir)
    assert allowed.ok is True
    assert allowed.changed_ids == ("AC-001",)
    assert allowed.carrier == "gate-0003"
    assert allowed.reasons == ("authorized",)
    print("[VERIFY] VC-014: refused=true changed_ids=1 classified=true")


def test_contract_guard_never_imports_conductor() -> None:
    source = pathlib.Path(contract_guard.__file__).read_text(encoding="utf-8")
    assert "import conductor" not in source
    assert "from autopilot import conductor" not in source

"""
test_autopilot_gate_schema_v2.py - T-03: gate schema v2 (28 additive optional
fields) + the `auto_gate_mode` config key.

Non-vacuous counterfactuals (each actually runs):
  (a) a real historical v1 gate file (no v2 field at all) still parses;
  (b) an unknown frontmatter field fails closed, naming the field;
  (c) malformed JSON in evidence_refs fails closed (never a silent []);
  (d) gates._REQUIRED_FIELDS is unchanged (exact set and length).

Every fixture builds its own gates dir under tmp_path; nothing touches a real
project.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import config as cfg
from autopilot import effective_config as ec
from autopilot import gates

BASE_FIELDS = (
    "id",
    "kind",
    "stage",
    "key",
    "created_at",
    "created_by",
    "question",
    "context_refs",
    "status",
    "answered_at",
    "answered_by",
    "note",
)
V2_FIELDS = (
    "reason_code",
    "evidence_refs",
    "loop",
    "used_rounds",
    "round_limit",
    "credits_used",
    "observed_at",
    "verdicts_final",
    "open_items",
    "subject_sha256",
    "roadmap_validation",
    "proposal_sha256",
    "goal_sha256",
    "constraints",
    "goal_sha256_before",
    "goal_sha256_after",
    "goal_diff",
    "write_scope",
    "blast_radius",
    "answer_source",
    "auto_policy_id",
    "expires_at",
    "evidence_anchor_mtime_ns",
    "default_action",
    "out_of_band_actions",
    "gate_schema",
)
CONSUMED_FIELDS = ("consumed_at", "consumed_seq")

# Verbatim JC gate-0008 frontmatter (2026-09-26 snapshot): a real historical
# v1 gate file, no v2 field anywhere.
LEGACY_GATE = (
    "---\n"
    "id: gate-0008\n"
    "kind: stage-close\n"
    "stage: 1\n"
    "key:\n"
    "created_at: 2026-09-26T04:37:27+00:00\n"
    "created_by: conductor\n"
    "question: 'Stage 1 全部 key 已终态，闭环 dossier 已写入 "
    ".agenticdoc/_autopilot/stages/stage-1-close.md——确认闭环？"
    "approve=标记 closed 并开放下一 stage；reject=halt 等待人工处理'\n"
    "context_refs:\n"
    "  - stage-1\n"
    "status: pending\n"
    "answered_at:\n"
    "answered_by:\n"
    "note:\n"
    "---\n"
    "\n"
    "# Gate gate-0008 (stage-close)\n"
    "\n"
    "body prose\n"
)


def _write(tmp_path: pathlib.Path, lines: list[str], name: str = "gate-0001.md") -> pathlib.Path:
    d = tmp_path / "gates"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(
        "---\n" + "\n".join(lines) + "\n---\n\nbody\n",
        encoding="utf-8",
        newline="\n",
    )
    return p


def _base_lines(
    *,
    kind: str = "stalled",
    extra: list[str] | None = None,
    name_id: str = "gate-0001",
) -> list[str]:
    lines = [
        f"id: {name_id}",
        f"kind: {kind}",
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
    if extra:
        lines.extend(extra)
    return lines


# --- schema shape --------------------------------------------------------------


def test_field_list_is_base_plus_28_in_frozen_order() -> None:
    fields = gates.FRONTMATTER_FIELDS
    assert list(fields[:12]) == list(BASE_FIELDS), "base 12 must not be reordered"
    assert list(fields[12:38]) == list(V2_FIELDS), "v2 order = D1.1 1..26"
    assert list(fields[38:40]) == list(CONSUMED_FIELDS)
    assert len(fields) == 40
    assert len(set(fields)) == 40  # no duplicate names
    print(
        "[VERIFY] VC-011: frontmatter_fields=40 base=12 v2=26 consumed=2 "
        f"list_fields={len(gates._LIST_FIELDS)}"
    )


def test_list_fields_is_the_two_named_fields() -> None:
    assert gates._LIST_FIELDS == {"context_refs", "evidence_refs"}


def test_required_fields_unchanged_exact_set_and_length() -> None:
    """Counterfactual (d): adding any required v2 field turns this red."""
    expected = frozenset(
        {"id", "kind", "created_at", "created_by", "question", "status"}
    )
    assert gates._REQUIRED_FIELDS == expected
    assert len(gates._REQUIRED_FIELDS) == 6
    assert gates._REQUIRED_FIELDS.isdisjoint(V2_FIELDS)
    print("[VERIFY] VC-038: required_unchanged=6 v2_optional=true")


# --- counterfactual (a): legacy v1 file ---------------------------------------


def test_real_historical_v1_gate_file_still_parses(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "gates"
    p.mkdir()
    gate_file = p / "gate-0008.md"
    gate_file.write_text(LEGACY_GATE, encoding="utf-8", newline="\n")
    gate = gates.parse(gate_file)
    assert gate.id == "gate-0008"
    assert gate.kind == "stage-close"
    assert gate.stage == 1
    assert gate.context_refs == ["stage-1"]
    # Absent v2 fields -> legacy defaults, never an error.
    assert gate.gate_schema == gates.GATE_SCHEMA_LEGACY == 1
    assert gate.reason_code is None
    assert gate.evidence_refs == []
    assert gate.verdicts_final is None
    assert gate.open_items is None
    assert gate.expires_at is None
    assert gate.default_action is None
    assert gate.answer_source is None
    assert gate.consumed_at is None
    assert gate.consumed_seq is None
    print("[VERIFY] VC-024: legacy_v1_parses=true gate_schema_default=1")


# --- renderer: new gates are schema 2 -----------------------------------------


def test_renderer_writes_gate_schema_2(tmp_path: pathlib.Path) -> None:
    p = gates.create(tmp_path / "gates", "goal-change", "goal.md changed?", [])
    text = p.read_text(encoding="utf-8")
    assert "gate_schema: 2" in text
    assert gates.parse(p).gate_schema == 2


def test_renderer_keeps_base_field_block_then_marker(tmp_path: pathlib.Path) -> None:
    p = gates.create(tmp_path / "gates", "stalled", "q", [], key="k1")
    lines = p.read_text(encoding="utf-8").splitlines()
    end = lines.index("---", 1)
    keys = [ln.split(":", 1)[0] for ln in lines[1:end] if not ln.startswith(" ")]
    assert keys[0] == "id"
    assert keys[1] == "gate_schema"
    assert set(BASE_FIELDS).issubset(set(keys))
    assert len(keys) == 13  # base 12 + gate_schema


# --- v2 fields round-trip -----------------------------------------------------


def test_all_v2_fields_round_trip(tmp_path: pathlib.Path) -> None:
    extra = [
        "reason_code: stage:all-keys-terminal",
        "evidence_refs:",
        "  - gate-dossier:_autopilot/stages/stage-1-close.md#18e3fec0133f",
        "  - l3-verdict:crash-analysis/l3-verdict.txt",
        "loop: l2:k1:spec-to-design",
        "used_rounds: 2",
        "round_limit: 3",
        "credits_used: 1",
        "observed_at: 2026-09-26T04:37:27+00:00",
        "verdicts_final: '[{\"key\":\"crash-analysis\",\"verdict\":\"meets\"}]'",
        "open_items: '[{\"kind\":\"verdict-none\",\"key\":\"llm-router\"}]'",
        "subject_sha256: 18e3fec0133f",
        "roadmap_validation: '[]'",
        "proposal_sha256: proposal-sha",
        "goal_sha256: goal-sha",
        "constraints: '[\"do not widen scope\"]'",
        "goal_sha256_before: before-sha",
        "goal_sha256_after: after-sha",
        "goal_diff: '{\"sections_added\":1,\"sections_removed\":0}'",
        "write_scope: '[\"packages/multi-workers\"]'",
        "blast_radius: '{\"files\":[\"a.py\"]}'",
        "answer_source: human",
        "auto_policy_id:",
        "expires_at: 2026-09-27T04:37:27+00:00",
        "evidence_anchor_mtime_ns: 1790126702018359200",
        "default_action: escalate-to-human",
        "out_of_band_actions: '[\"restart@2026-09-26T05:00:00+00:00\"]'",
        "gate_schema: 2",
        "consumed_at: 2026-09-26T06:00:00+00:00",
        "consumed_seq: 7",
    ]
    p = _write(tmp_path, _base_lines(extra=extra))
    gate = gates.parse(p)
    assert gate.reason_code == "stage:all-keys-terminal"
    assert gate.evidence_refs == [
        "gate-dossier:_autopilot/stages/stage-1-close.md#18e3fec0133f",
        "l3-verdict:crash-analysis/l3-verdict.txt",
    ]
    assert gate.loop == "l2:k1:spec-to-design"
    assert (gate.used_rounds, gate.round_limit, gate.credits_used) == (2, 3, 1)
    assert gate.observed_at == "2026-09-26T04:37:27+00:00"
    assert gate.verdicts_final == [{"key": "crash-analysis", "verdict": "meets"}]
    assert gate.open_items == [{"kind": "verdict-none", "key": "llm-router"}]
    assert gate.subject_sha256 == "18e3fec0133f"
    assert gate.roadmap_validation == []
    assert (gate.proposal_sha256, gate.goal_sha256) == ("proposal-sha", "goal-sha")
    assert gate.constraints == ["do not widen scope"]
    assert (gate.goal_sha256_before, gate.goal_sha256_after) == (
        "before-sha",
        "after-sha",
    )
    assert gate.goal_diff == {"sections_added": 1, "sections_removed": 0}
    assert gate.write_scope == ["packages/multi-workers"]
    assert gate.blast_radius == {"files": ["a.py"]}
    assert gate.answer_source == "human"
    assert gate.auto_policy_id is None
    assert gate.expires_at == "2026-09-27T04:37:27+00:00"
    assert gate.evidence_anchor_mtime_ns == 1790126702018359200
    assert gate.default_action == "escalate-to-human"
    assert gate.out_of_band_actions == ["restart@2026-09-26T05:00:00+00:00"]
    assert gate.gate_schema == 2
    assert gate.consumed_at == "2026-09-26T06:00:00+00:00"
    assert gate.consumed_seq == 7


def test_evidence_refs_accepts_single_line_json_array(tmp_path: pathlib.Path) -> None:
    """design D2.3 after-example: the same list may be a JSON array scalar."""
    p = _write(
        tmp_path,
        _base_lines(extra=["evidence_refs: '[\"a.md#abc\", \"b.txt\"]'"]),
    )
    assert gates.parse(p).evidence_refs == ["a.md#abc", "b.txt"]


# --- counterfactual (b): unknown field ----------------------------------------


def test_unknown_field_fails_closed_naming_the_field(tmp_path: pathlib.Path) -> None:
    p = _write(tmp_path, _base_lines(extra=["bogus_field: x"]))
    with pytest.raises(gates.GateFormatError) as excinfo:
        gates.parse(p)
    message = str(excinfo.value)
    assert "unknown frontmatter field" in message
    assert "bogus_field" in message


# --- counterfactual (c): malformed JSON is fail-closed ------------------------


def test_bad_json_evidence_refs_fails_closed(tmp_path: pathlib.Path) -> None:
    p = _write(tmp_path, _base_lines(extra=["evidence_refs: '[\"a\", \"b\"'"]))
    with pytest.raises(gates.GateFormatError) as excinfo:
        gates.parse(p)
    assert "evidence_refs" in str(excinfo.value)


def test_bad_json_structured_field_fails_closed(tmp_path: pathlib.Path) -> None:
    p = _write(tmp_path, _base_lines(extra=["verdicts_final: '{oops'"]))
    with pytest.raises(gates.GateFormatError) as excinfo:
        gates.parse(p)
    assert "verdicts_final" in str(excinfo.value)


def test_json_object_field_rejects_array(tmp_path: pathlib.Path) -> None:
    p = _write(tmp_path, _base_lines(extra=["goal_diff: '[1, 2]'"]))
    with pytest.raises(gates.GateFormatError) as excinfo:
        gates.parse(p)
    assert "goal_diff" in str(excinfo.value)


def test_json_list_field_rejects_object(tmp_path: pathlib.Path) -> None:
    p = _write(tmp_path, _base_lines(extra=["open_items: '{\"kind\":\"x\"}'"]))
    with pytest.raises(gates.GateFormatError) as excinfo:
        gates.parse(p)
    assert "open_items" in str(excinfo.value)


def test_gate_schema_rejects_unknown_version(tmp_path: pathlib.Path) -> None:
    p = _write(tmp_path, _base_lines(extra=["gate_schema: 3"]))
    with pytest.raises(gates.GateFormatError) as excinfo:
        gates.parse(p)
    assert "gate_schema" in str(excinfo.value)


# --- config: auto_gate_mode ----------------------------------------------------


def test_auto_gate_mode_defaults_to_off() -> None:
    assert cfg.DEFAULT_CONFIG["auto_gate_mode"] == "off"
    assert cfg.default_config()["auto_gate_mode"] == "off"
    assert list(cfg.DEFAULT_CONFIG)[-1] == "auto_gate_mode"


@pytest.mark.parametrize("value", ["off", "shadow", "live"])
def test_auto_gate_mode_valid_values_round_trip(
    tmp_path: pathlib.Path, value: str
) -> None:
    cfg.save_config(tmp_path, {**cfg.default_config(), "auto_gate_mode": value})
    assert cfg.load_config(tmp_path)["auto_gate_mode"] == value


@pytest.mark.parametrize("bad", ["on", "OFF", "auto", True, 1, None, ["live"]])
def test_auto_gate_mode_invalid_fails_closed(bad: object) -> None:
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.validate_config({**cfg.default_config(), "auto_gate_mode": bad})
    assert "auto_gate_mode" in str(excinfo.value)


def test_auto_gate_mode_invalid_file_does_not_fall_back(
    tmp_path: pathlib.Path,
) -> None:
    """A present-but-invalid value must raise, never run on the 'off' default."""
    path = cfg.config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"auto_gate_mode": "sneaky"}', encoding="utf-8")
    with pytest.raises(cfg.ConfigError):
        cfg.load_config(tmp_path)


def test_auto_gate_mode_is_not_machine_overridable() -> None:
    assert "auto_gate_mode" in cfg.DEFAULT_CONFIG
    assert "auto_gate_mode" not in ec.EFFECTIVE_KEYS

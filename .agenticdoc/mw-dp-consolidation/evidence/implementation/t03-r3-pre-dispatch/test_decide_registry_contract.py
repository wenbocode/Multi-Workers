"""test_decide_registry_contract.py — self-describing registry snapshot contract.

T03 (key ``mw-dp-consolidation``) replaced the 25 numbered dps with the eight
active entries of spec §1.1 and moved the old ids into a read-only retired
directory. This module keeps the snapshot side of the contract honest:

1. ``decide_registry.json`` holds exactly the eight active entries, and the
   retired directory is a separate top-level section (never mixed into points);
2. :data:`decision_points.STATE_FIELD_DESCRIPTIONS` covers every required path of
   every active entry *and* every path of the read-only retired explanation, with
   a legal JSON type and a non-empty description;
3. every exported point carries its protocol identity (``kind`` /
   ``role_scope`` / ``candidate_source`` / ``candidate_bounds`` /
   ``target_entries``) plus the four wiring keys, and a wiring claim is backed
   by the call site it cites (the eight entries are unwired until T04/T11 land);
4. the snapshot has no parallel top-level ``wiring`` section and
   ``schema == 4``;
5. every point has a non-empty question set whose frozen enum comes from the one
   Python table (``ENTRY_CHOICES`` / ``ROUTE_TARGETS``);
6. the cross-layer debt is explicit and stage-aware: ``triage-client.ts`` keeps
   the documented legacy rows for retired ids only (plus, after T04, rows of the
   active entries), and the generated TS registry is asserted to be *either* the
   frozen pre-T03 artifact *or* the eight-entry projection T04 regenerates. A
   one-sided rename must turn red here, and no test claims the field-level
   parity T04 owes.

Hermetic: read-only, no network, no ``.mw`` writes.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
EXPORT_PATH = PACKAGE_DIR / mw._DP_EXPORT_NAME
TRIAGE_CLIENT = (
    REPO_ROOT
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "pm"
    / "triage-client.ts"
)
GENERATED_TS = (
    REPO_ROOT
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "shared"
    / "decide-registry.generated.ts"
)

TARGET_EIGHT = (
    "dp-w-type",
    "dp-pm-steer",
    "dp-w-check-task",
    "dp-QG",
    "dp-gate-approve",
    "dp-sign-key",
    "dp-auto",
    "dp-route",
)
#: JSON-native types a ``required_state_fields`` entry may declare.
VALID_FIELD_TYPES = frozenset({"object", "string", "integer", "number", "boolean", "array"})
#: ``triage-client.ts`` rows that remain on the pre-T01 structured vocabulary.
#: They are explicit legacy debt for retired ids only; no active entry may grow a
#: row there (its material contract is the generated registry, owned by T04).
LEGACY_TS_ROWS: dict[str, list[str]] = {
    "dp4-failure-handling": ["failure.kind"],
    "dp5-test-triage": ["failure.kind", "failure.test_name", "failure.baseline_known"],
    "dp6-qg-verdict": ["closure"],
    "dp13-commit-release": ["closure"],
}
#: The four per-point wiring keys (no legacy ``note`` alias may survive).
WIRING_KEYS = ("wired", "trigger", "adopted_at", "wiring_note")
#: Top-level keys of the generated snapshot (the retired directory is its own
#: section; there is no parallel ``wiring`` section any more).
SNAPSHOT_KEYS = {"schema", "generated_from", "question_types", "preparation", "points", "retired"}
#: Per-point key set: the frozen export plus the T03 protocol identity.
POINT_KEYS = {
    "id",
    "tier",
    "default_enabled",
    "default_mode",
    "description",
    "kind",
    "role_scope",
    "candidate_source",
    "candidate_bounds",
    "target_entries",
    "questions_version",
    "p0_consequences",
    "wired",
    "trigger",
    "adopted_at",
    "wiring_note",
    "executor",
    "required_state_fields",
    "optional_state_fields",
    "model_state_fields",
    "questions",
}


def _export_doc() -> dict:
    return json.loads(EXPORT_PATH.read_text(encoding="utf-8"))


def _points() -> list[dict]:
    """Snapshot + the hand-written wiring merged per point (what `--json` prints)."""
    return mw._dp_export_doc()[0]["points"]


def _points_by_id() -> dict[str, dict]:
    return {point["id"]: point for point in _points()}


def _split_location(location: str) -> tuple[str, int]:
    path, separator, line = location.rpartition(":")
    assert separator == ":" and path and line.isdigit(), f"not <path>:<line>: {location!r}"
    return path, int(line)


def _line_count(path: pathlib.Path) -> int:
    return len(path.read_bytes().splitlines())


# ---------------------------------------------------------------------------
# 1. Snapshot identity
# ---------------------------------------------------------------------------


def test_snapshot_holds_exactly_the_eight_active_entries() -> None:
    doc = _export_doc()
    assert tuple(point["id"] for point in doc["points"]) == TARGET_EIGHT
    assert tuple(entry.id for entry in dpts.DP_REGISTRY) == TARGET_EIGHT
    assert len(doc["points"]) == dpts.EXPECTED_DP_COUNT == 8


def test_retired_directory_is_its_own_section() -> None:
    doc = _export_doc()
    assert [record["id"] for record in doc["retired"]] == [
        record.id for record in dpts.RETIRED_DP_REGISTRY
    ]
    assert len(doc["retired"]) == 25
    point_ids = {point["id"] for point in doc["points"]}
    assert not point_ids & {record["id"] for record in doc["retired"]}
    for record in doc["retired"]:
        assert set(record) == {
            "id",
            "tier",
            "description",
            "disposition",
            "migrated_to",
            "note",
        }
        assert record["disposition"] in ("migrated", "retired")


# ---------------------------------------------------------------------------
# 2. The field-semantics table (active material + retired explanation)
# ---------------------------------------------------------------------------


def test_state_field_descriptions_cover_every_required_path() -> None:
    required = {path for paths in dpts.REQUIRED_STATE_FIELDS.values() for path in paths}
    assert required, "REQUIRED_STATE_FIELDS is empty"
    missing = sorted(required - set(dpts.STATE_FIELD_DESCRIPTIONS))
    assert missing == [], f"required paths with no semantics: {missing}"


def test_state_field_descriptions_cover_the_retired_explanation() -> None:
    retired = {
        path for paths in dpts.RETIRED_STATE_FIELDS.values() for path in paths
    }
    assert retired, "RETIRED_STATE_FIELDS is empty"
    missing = sorted(retired - set(dpts.STATE_FIELD_DESCRIPTIONS))
    assert missing == [], f"retired explained paths with no semantics: {missing}"


def test_state_field_descriptions_have_a_legal_type_and_text() -> None:
    covered = {path for paths in dpts.REQUIRED_STATE_FIELDS.values() for path in paths}
    covered |= {path for paths in dpts.RETIRED_STATE_FIELDS.values() for path in paths}
    allowed_keys = {"type", "description"} | set(dpts.STATE_FIELD_CONSTRAINT_KEYS)
    for path in sorted(covered):
        spec = dpts.STATE_FIELD_DESCRIPTIONS[path]
        assert {"type", "description"} <= set(spec) <= allowed_keys, (
            f"{path}: unexpected keys {sorted(set(spec) - allowed_keys)}"
        )
        assert spec["type"] in VALID_FIELD_TYPES, f"{path}: {spec['type']!r}"
        assert isinstance(spec["description"], str) and spec["description"].strip(), (
            f"{path}: empty description"
        )
        if "enum" in spec:
            options = spec["enum"]
            assert spec["type"] == "string" and options, path
            assert all(isinstance(option, str) and option for option in options), path
            assert len(set(options)) == len(options), f"{path}: duplicate enum values"
        if "max_items" in spec:
            assert spec["type"] == "array", path
            assert isinstance(spec["max_items"], int) and spec["max_items"] > 0, path
        if "item_type" in spec:
            assert spec["type"] == "array" and spec["item_type"] in VALID_FIELD_TYPES, path
        for key in ("max_bytes", "item_max_bytes"):
            if key in spec:
                assert isinstance(spec[key], int) and spec[key] > 0, f"{path}: bad {key}"
        if "signed" in spec:
            assert spec["type"] == "integer" and spec["signed"] is True, path
        if "min_value" in spec:
            assert spec["type"] == "integer", f"{path}: min_value on {spec['type']}"
            assert isinstance(spec["min_value"], int), f"{path}: min_value must be an integer"


def test_exported_required_state_fields_render_the_semantics_table() -> None:
    for point in _points():
        expected = []
        for path in dpts.REQUIRED_STATE_FIELDS.get(point["id"], ()):
            spec = dpts.STATE_FIELD_DESCRIPTIONS[path]
            field = {
                "name": path,
                "type": spec["type"],
                "description": spec["description"],
            }
            for key in dpts.STATE_FIELD_CONSTRAINT_KEYS:
                if key not in spec:
                    continue
                # The export is JSON-shaped: an enum tuple becomes an array.
                field[key] = list(spec[key]) if key == "enum" else spec[key]
            expected.append(field)
        assert point["required_state_fields"] == expected, (
            f"{point['id']}: required_state_fields drifted from the semantics table"
        )
        assert point["optional_state_fields"] == [
            {
                "name": path,
                "type": dpts.STATE_FIELD_DESCRIPTIONS[path]["type"],
                "description": dpts.STATE_FIELD_DESCRIPTIONS[path]["description"],
                **({
                    key: (
                        list(dpts.STATE_FIELD_DESCRIPTIONS[path][key])
                        if key == "enum"
                        else dpts.STATE_FIELD_DESCRIPTIONS[path][key]
                    )
                    for key in dpts.STATE_FIELD_CONSTRAINT_KEYS
                    if key in dpts.STATE_FIELD_DESCRIPTIONS[path]
                }),
            }
            for path in dpts.OPTIONAL_STATE_FIELDS.get(point["id"], ())
        ], f"{point['id']}: optional_state_fields drifted"


def test_model_state_fields_are_declared_for_every_active_entry() -> None:
    for entry in dpts.DP_REGISTRY:
        paths = dpts.MODEL_STATE_FIELDS.get(entry.id)
        assert paths, f"{entry.id}: no model allowlist"
        declared = set(dpts.REQUIRED_STATE_FIELDS[entry.id]) | set(
            dpts.OPTIONAL_STATE_FIELDS.get(entry.id, ())
        )
        assert set(paths) == declared, f"{entry.id}: model allowlist != declared material"
    sign = dpts.MODEL_STATE_FIELDS["dp-sign-key"]
    for path in (
        "delivery_goal",
        "actual_completion",
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    ):
        assert path in sign
    assert "delivery_goal" in dpts.REQUIRED_STATE_FIELDS["dp-sign-key"]


# ---------------------------------------------------------------------------
# 3. Per-point protocol identity and wiring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_point", dpts.DP_REGISTRY, ids=lambda point: point.id)
def test_point_carries_its_protocol_identity(dp_point: dpts.DecisionPoint) -> None:
    point = _points_by_id()[dp_point.id]
    assert set(point) <= POINT_KEYS, f"{dp_point.id}: unexpected export keys"
    assert point["kind"] in dpts.ENTRY_KINDS
    assert point["role_scope"] == dpts.ENTRY_ROLES[dp_point.id]
    assert point["candidate_source"] == dpts.ENTRY_CANDIDATE_SOURCE[dp_point.id]
    assert point["target_entries"] == list(dp_point.target_entries)
    if dp_point.kind == "dynamic-candidates":
        assert point["candidate_bounds"], f"{dp_point.id}: dynamic entry needs bounds"


@pytest.mark.parametrize("dp_point", dpts.DP_REGISTRY, ids=lambda point: point.id)
def test_wiring_is_self_described_and_resolvable(dp_point: dpts.DecisionPoint) -> None:
    point = _points_by_id()[dp_point.id]
    for key in WIRING_KEYS:
        assert key in point, f"{dp_point.id}: missing wiring key {key!r}"
    assert "note" not in point, f"{dp_point.id}: legacy wiring key 'note' survived"
    assert isinstance(point["wired"], bool), f"{dp_point.id}: wired must be a boolean"
    assert isinstance(point["wiring_note"], str) and point["wiring_note"].strip(), (
        f"{dp_point.id}: wiring_note must be a non-empty string"
    )
    if point["wired"]:
        for field in ("trigger", "adopted_at"):
            location = point[field]
            assert isinstance(location, str), f"{dp_point.id}: {field} must be <path>:<line>"
            relative, line = _split_location(location)
            target = (REPO_ROOT / relative).resolve()
            assert target.is_relative_to(REPO_ROOT), f"{dp_point.id}: {field} escapes the repo"
            assert target.is_file(), f"{dp_point.id}: {field} names a missing file: {relative}"
            assert 1 <= line <= _line_count(target), (
                f"{dp_point.id}: {field} line {line} is outside {relative} "
                f"({_line_count(target)} lines)"
            )
    else:
        assert point["trigger"] is None, f"{dp_point.id}: an unwired dp must not claim a trigger"
        assert point["adopted_at"] is None, f"{dp_point.id}: an unwired dp must not claim a call site"


def test_wiring_claims_are_backed_by_the_call_site_they_cite() -> None:
    """T03 is protocol only, but the invariant is not "always unwired".

    T04/T11 own the wiring: forcing all eight to stay ``wired: false`` here would
    make every later caller card edit this test outside its own write face. The
    real contract is that a claim is backed: an unwired entry must not claim a
    trigger/adoption location, and a wired entry must cite a repo file that really
    names the entry (so a wired flag is never a placeholder).
    """
    points = _points()
    assert [point["id"] for point in points] == list(TARGET_EIGHT)
    for point in points:
        if not point["wired"]:
            assert point["trigger"] is None, point["id"]
            assert point["adopted_at"] is None, point["id"]
            continue
        relative, line = _split_location(point["trigger"])
        target = (REPO_ROOT / relative).resolve()
        assert target.is_file(), f"{point['id']}: missing wired file {relative}"
        text = target.read_text(encoding="utf-8", errors="replace")
        assert point["id"] in text, (
            f"{point['id']}: wiring cites {relative}:{line} but that file never "
            "names the entry"
        )
        assert isinstance(point["adopted_at"], str) and point["adopted_at"].strip()


# ---------------------------------------------------------------------------
# 4. One snapshot shape
# ---------------------------------------------------------------------------


def test_snapshot_has_no_top_level_wiring_section() -> None:
    doc = _export_doc()
    assert "wiring" not in doc, "the parallel top-level wiring section must be gone"
    assert set(doc) == SNAPSHOT_KEYS


def test_snapshot_schema_is_four() -> None:
    assert dpts.SNAPSHOT_SCHEMA == 4
    assert _export_doc()["schema"] == 4
    # Schema 4 = the eight-entry protocol: per-point kind/role/candidate identity
    # plus the separate preparation and retired sections.
    for point in _export_doc()["points"]:
        assert "kind" in point and "role_scope" in point, point["id"]
        assert "candidate_source" in point and "target_entries" in point, point["id"]
        for field in point["required_state_fields"] + point["optional_state_fields"]:
            assert set(field) <= {
                "name",
                "type",
                "description",
                *dpts.STATE_FIELD_CONSTRAINT_KEYS,
            }, f"{point['id']}/{field['name']}: unknown export key"


# ---------------------------------------------------------------------------
# 5. Question sets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("point", _points(), ids=[point["id"] for point in _points()])
def test_every_point_has_a_well_formed_question_set(point: dict) -> None:
    questions = point["questions"]
    assert questions, f"{point['id']}: no questions"
    ids = [str(question["id"]) for question in questions]
    assert len(ids) == len(set(ids)), f"{point['id']}: duplicate question ids {ids}"
    for question in questions:
        assert question["type"] in decision.QUESTION_TYPES, (
            f"{point['id']}/{question['id']}: illegal type {question['type']!r}"
        )
        if question["type"] == decision.QUESTION_CHOICE and question.get("dynamic_choices") is None:
            expected = (
                list(dpts.ROUTE_TARGETS)
                if point["id"] == "dp-route"
                else list(dpts.ENTRY_CHOICES[point["id"]])
            )
            assert question["choices"] == expected, (
                f"{point['id']}: choices drifted from the one Python table"
            )
    if point["id"] in ("dp-route",):
        assert point["questions"][0]["choices"] == list(dpts.ROUTE_TARGETS)


# ---------------------------------------------------------------------------
# 6. Cross-layer debt (T04 owns regeneration; this file must not fake it)
# ---------------------------------------------------------------------------


def _ts_required_fields() -> tuple[list[str], dict[str, list[str]]]:
    """Extract ``UNIVERSAL_REQUIRED_FIELDS`` + the per-dp matrix from the TS peer.

    TS composes the two blocks at validation time (``universal + by_dp[dpId]``),
    so a dp's *effective* list is the union; the names themselves must match the
    Python side once T04 regenerates the TS contract.
    """
    text = TRIAGE_CLIENT.read_text(encoding="utf-8")

    universal_start = text.index("const UNIVERSAL_REQUIRED_FIELDS = [")
    universal_open = text.index("[", universal_start)
    universal_close = text.index("];", universal_open)
    universal = re.findall(r'"([^"]+)"', text[universal_open:universal_close])
    assert universal, "UNIVERSAL_REQUIRED_FIELDS parsed empty"

    table_start = text.index("export const REQUIRED_FIELDS_BY_DP")
    table_open = text.index("{", table_start)
    table_close = text.index("\n};", table_open)
    body = text[table_open + 1 : table_close]

    dp1_match = re.search(r'export const DP1_ID = "([^"]+)";', text)
    assert dp1_match is not None, "DP1_ID declaration not found"
    dp1_id = dp1_match.group(1)

    by_dp: dict[str, list[str]] = {}
    for key, inner in re.findall(r'(\[DP1_ID\]|"[^"]+")\s*:\s*\[([^\]]*)\]', body, re.S):
        dp_id = dp1_id if key == "[DP1_ID]" else key.strip('"')
        by_dp[dp_id] = re.findall(r'"([^"]+)"', inner)
    assert {"dp4-failure-handling"} <= set(by_dp), (
        f"the required_if matrix was not parsed: {sorted(by_dp)}"
    )
    return universal, by_dp


def _generated_ts_entry_ids() -> tuple[str, ...]:
    """Ids declared as top-level keys of ``DECIDE_REGISTRY`` (one tab deep)."""
    text = GENERATED_TS.read_text(encoding="utf-8")
    return tuple(re.findall(r'^\t"([^"]+)": \{', text, re.M))


def _generated_ts_stage() -> str:
    """Which registry generation the checked-in TS module represents.

    ``pre-t04``: the frozen pre-T03 artifact (the 25 retired ids).
    ``post-t04``: the eight-entry projection T04 regenerates.
    Anything else (a partial/one-sided rename) is a hard failure. The stage is
    derived from the artifact, never hand-flipped, so the card that regenerates
    the module does not have to edit this test to unblock itself.
    """
    ids = _generated_ts_entry_ids()
    assert len(ids) == len(set(ids)), f"duplicate entry ids in the generated TS: {ids}"
    if set(ids) == set(dpts.RETIRED_DP_IDS):
        return "pre-t04"
    assert set(ids) == set(TARGET_EIGHT), (
        "the generated TS registry is neither the frozen pre-T03 artifact nor the "
        f"eight-entry projection: {sorted(ids)}"
    )
    return "post-t04"


def test_ts_required_rows_follow_the_registry_stage() -> None:
    """The required_if matrix may only move together with the registry stage.

    Retired ids keep exactly the four documented legacy rows (read-only history);
    unknown ids never appear; and an *active* entry may only own a row once the
    generated TS was regenerated for the eight entries (post-T04). Before that,
    such a row means the pair was edited one-sidedly by hand.
    """
    _universal, by_dp = _ts_required_fields()
    stage = _generated_ts_stage()
    known = set(dpts.ACTIVE_DP_IDS) | set(dpts.RETIRED_DP_IDS)
    assert set(by_dp) <= known, (
        f"unknown ids in REQUIRED_FIELDS_BY_DP: {sorted(set(by_dp) - known)}"
    )
    retired_rows = {key: row for key, row in by_dp.items() if dpts.is_retired_dp(key)}
    assert retired_rows == LEGACY_TS_ROWS, (
        "the documented legacy rows of retired ids changed; only those retired ids "
        f"may keep a row: {sorted(set(retired_rows) - set(LEGACY_TS_ROWS))}"
    )
    for entry_id, fields in by_dp.items():
        assert fields and all(isinstance(name, str) and name.strip() for name in fields), (
            f"{entry_id}: empty or non-string required field name"
        )
    active_rows = sorted(set(by_dp) & set(dpts.ACTIVE_DP_IDS))
    if stage == "pre-t04":
        assert active_rows == [], (
            "an active entry grew a legacy TS row before T04 regenerated the pair: "
            f"{active_rows}"
        )


def test_universal_required_fields_stay_the_frozen_identity_block() -> None:
    universal, _by_dp = _ts_required_fields()
    assert universal == [
        "schema_version",
        "decision_point",
        "key",
        "phase",
        "task_type",
        "risk",
        "risk_source",
        "authority_tier",
        "questions_version",
    ]


def test_generated_ts_registry_is_the_frozen_legacy_or_the_t04_projection() -> None:
    """A real, evolvable contract on the generated TS peer.

    T04 owns ``gen_decide_registry_ts.py`` + ``decide-registry.generated.ts``; T03
    must not hand-edit or pre-generate them. This test therefore accepts exactly
    two stages and rejects a one-sided rename:

    * pre-T04: the module is the frozen old artifact, declaring exactly the 25
      retired ids (no active id, no mix);
    * post-T04: it declares exactly the eight active entries, each with its
      ``requiredStateFields`` block.

    The header/interface shape is pinned in both stages. Field-level parity
    between the TS module and the Python snapshot remains T04's own check and is
    deliberately not claimed here.
    """
    text = GENERATED_TS.read_text(encoding="utf-8")
    stage = _generated_ts_stage()
    assert text.startswith(
        "// @generated by packages/multi-workers/scripts/gen_decide_registry_ts.py "
    ), "the generated header was replaced"
    assert "export const DECIDE_REGISTRY: Record<string, DecideRegistryEntry> = {" in text
    assert "export interface DecideRegistryEntry {" in text
    assert "\n\t\trequiredStateFields: [\n" in text
    ids = _generated_ts_entry_ids()
    if stage == "pre-t04":
        assert sorted(ids) == sorted(record.id for record in dpts.RETIRED_DP_REGISTRY)
        assert '"dp1-dispatch-type": {' in text, (
            "the frozen pre-T03 artifact no longer carries its first entry"
        )
    else:
        assert ids == TARGET_EIGHT

"""test_decide_registry_contract.py — self-describing config + per-dp probe.

Card W4 (mw-decision-substitution). ``decide_registry.json`` used to keep the
wiring facts in a parallel top-level section and to list ``required_state_fields``
as bare path strings, so a reader could not see whether a dp was wired or what a
field meant, and nothing proved that a configured dp actually reaches ``decide``.
This module locks the replacement contract:

1. every one of the 25 dps passes the offline contract probe
   (:func:`mw._dp_verify_point`): the minimal state built from its own
   ``required_state_fields`` reaches ``DecisionClient.decide`` without a
   ``DecisionInputError``, comes back ``available=true`` with one answer per
   question, and renders the documented ``{model, state, questions}`` body;
2. :data:`decision_points.STATE_FIELD_DESCRIPTIONS` covers every required path
   (union over all dps) with a legal JSON type and a non-empty description;
3. every exported point carries ``wired``/``trigger``/``adopted_at``/
   ``wiring_note``, and a ``wired=true`` location resolves to a real file line;
4. the snapshot has no top-level ``wiring`` section and ``schema == 2``;
5. every point has a non-empty question set with unique ids and legal types;
6. the TS required-field matrix (``pm/triage-client.ts``) agrees with Python's
   :data:`decision_points.REQUIRED_STATE_FIELDS` dp by dp — the field names are
   a cross-layer contract, so a one-sided rename must turn red here.

Hermetic: read-only, no network, no ``.mw`` writes; the probe uses
``decision.FakeBackend`` and a project-less ``DecisionConfig`` (no evidence file).
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

#: JSON-native types a ``required_state_fields`` entry may declare.
VALID_FIELD_TYPES = frozenset({"object", "string", "integer", "number", "boolean", "array"})
#: dps whose state has no TS producer (W9: dp25 is built by `mw decide sign`
#: from `decide_signoff.collect()` facts), so the cross-layer parity check above
#: skips them by design instead of demanding a `triage-client.ts` row nobody owns.
PYTHON_ONLY_DP_IDS = frozenset({"dp25-signoff-conclusion"})
#: Pre-card ``triage-client.ts`` rows that still name a field vocabulary the T04
#: registry does not declare (dp5/dp6/dp13). Frozen so a *new* one-sided drift is
#: still red; aligning them with the typed contract is TS-owner work (T09) —
#: reported to the PM instead of edited outside this card's write face.
TS_STALE_ROWS: dict[str, list[str]] = {
    "dp4-failure-handling": ["failure.kind"],
    "dp5-test-triage": ["failure.kind", "failure.test_name", "failure.baseline_known"],
    "dp6-qg-verdict": ["closure"],
    "dp13-commit-release": ["closure"],
}
#: The four per-point wiring keys (no legacy ``note`` alias may survive).
WIRING_KEYS = ("wired", "trigger", "adopted_at", "wiring_note")


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


def _flatten_paths(state: object, prefix: str = "") -> list[str]:
    """Dotted leaf paths of a nested dict (lists are leaves — they are values)."""
    if not isinstance(state, dict):
        return [prefix]
    out: list[str] = []
    for key, value in state.items():
        out.extend(_flatten_paths(value, f"{prefix}.{key}" if prefix else str(key)))
    return out


# ---------------------------------------------------------------------------
# 1. Every dp's config resolves and renders (offline; 25/25)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("point", _points(), ids=[point["id"] for point in _points()])
def test_every_dp_passes_the_offline_contract_probe(point: dict) -> None:
    row = mw._dp_verify_point(point)
    assert row["failures"] == [], f"{point['id']}: {row['failures']}"
    assert row["ok"] is True
    assert row["available"] is True
    assert row["questions"] >= 1
    assert row["answer_ids"], f"{point['id']}: no normalized answers"


@pytest.mark.parametrize("point", _points(), ids=[point["id"] for point in _points()])
def test_probe_state_carries_only_the_declared_required_paths(point: dict) -> None:
    """The probe must not pass by padding the state with unlisted fields."""
    state = mw._dp_verify_state(point)
    declared = [field["name"] for field in point["required_state_fields"]]
    assert sorted(_flatten_paths(state)) == sorted(declared)


def test_probe_verdict_is_repeatable() -> None:
    """No clock/network/state: the same dp gives the same verdict twice."""
    for point in _points():
        first = mw._dp_verify_point(point)
        second = mw._dp_verify_point(point)
        assert first["ok"] and second["ok"], point["id"]
        assert first["answer_ids"] == second["answer_ids"]


# ---------------------------------------------------------------------------
# 2. The field-semantics table
# ---------------------------------------------------------------------------


def test_state_field_descriptions_cover_every_required_path() -> None:
    required = {path for paths in dpts.REQUIRED_STATE_FIELDS.values() for path in paths}
    assert required, "REQUIRED_STATE_FIELDS is empty"
    missing = sorted(required - set(dpts.STATE_FIELD_DESCRIPTIONS))
    assert missing == [], f"required paths with no semantics: {missing}"


def test_state_field_descriptions_have_a_legal_type_and_text() -> None:
    required = {path for paths in dpts.REQUIRED_STATE_FIELDS.values() for path in paths}
    allowed_keys = {"type", "description"} | set(dpts.STATE_FIELD_CONSTRAINT_KEYS)
    for path in sorted(required):
        spec = dpts.STATE_FIELD_DESCRIPTIONS[path]
        assert {"type", "description"} <= set(spec) <= allowed_keys, (
            f"{path}: unexpected keys {sorted(set(spec) - allowed_keys)}"
        )
        assert spec["type"] in VALID_FIELD_TYPES, f"{path}: {spec['type']!r}"
        assert isinstance(spec["description"], str) and spec["description"].strip(), (
            f"{path}: empty description"
        )
        # T04: a declared constraint must be well-formed, never a stray value.
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


# ---------------------------------------------------------------------------
# 3. Per-point wiring
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 4. One shape: no parallel top-level section
# ---------------------------------------------------------------------------


def test_snapshot_has_no_top_level_wiring_section() -> None:
    doc = _export_doc()
    assert "wiring" not in doc, "the parallel top-level wiring section must be gone"
    assert set(doc) == {"schema", "generated_from", "question_types", "points"}


def test_snapshot_schema_is_three() -> None:
    assert dpts.SNAPSHOT_SCHEMA == 3
    assert _export_doc()["schema"] == 3
    # Schema 3 = the typed business contract: optional fields + declared
    # constraints ride every point, not just the required path names.
    for point in _export_doc()["points"]:
        assert "optional_state_fields" in point, point["id"]
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


# ---------------------------------------------------------------------------
# 6. Python <-> TS required-field parity (cross-layer contract)
# ---------------------------------------------------------------------------


def _ts_required_fields() -> tuple[list[str], dict[str, list[str]]]:
    """Extract ``UNIVERSAL_REQUIRED_FIELDS`` + the per-dp matrix from the TS peer.

    TS composes the two blocks at validation time (``universal + by_dp[dpId]``),
    so a dp's *effective* list is the union; the names themselves must match
    Python literally.
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
    assert {"dp1-dispatch-type", "dp2-checkpoint-split", "dp3-worker-clarify"} <= set(by_dp), (
        f"the required_if matrix was not parsed: {sorted(by_dp)}"
    )
    return universal, by_dp


def test_python_and_ts_required_fields_agree_per_dp() -> None:
    """Cross-layer lock, scoped to the dps a TS producer actually mirrors.

    T04 gave dp4..dp24 a registry-owned business contract. ``triage-client.ts``
    is not a producer for those dps (they are ``wired=false``), so the lock is:

    * every dp with a TS producer (dp1/dp2/dp3) mirrors Python exactly;
    * a pre-existing TS row may only *narrow* the registry set (dp4's
      ``failure.kind``); a row naming a pre-card vocabulary is frozen in
      :data:`TS_STALE_ROWS` so a new one-sided drift still turns red;
    * a Python-only dp (dp25) must not grow a TS row.
    """
    universal, by_dp = _ts_required_fields()
    ts_producers = ("dp1-dispatch-type", "dp2-checkpoint-split", "dp3-worker-clarify")
    for dp_id in ts_producers:
        assert dp_id in by_dp, f"{dp_id}: no TS required_if row"
        ts_fields = set(universal) | set(by_dp[dp_id])
        python_fields = set(dpts.REQUIRED_STATE_FIELDS[dp_id])
        missing = sorted(python_fields - ts_fields)
        extra = sorted(ts_fields - python_fields)
        assert missing == [], f"{dp_id}: TS is missing {missing}"
        assert extra == [], f"{dp_id}: TS requires fields Python does not: {extra}"
        # The composition premise: every universal field really is required by
        # this dp on the Python side too, so the union is not papering over a gap.
        assert set(universal) <= python_fields, (
            f"{dp_id}: universal fields outside the Python required set: "
            f"{sorted(set(universal) - python_fields)}"
        )
    assert set(TS_STALE_ROWS["dp4-failure-handling"]) <= set(
        dpts.REQUIRED_STATE_FIELDS["dp4-failure-handling"]
    ), "dp4: TS now requires a field the registry does not declare"
    for dp_id, frozen in TS_STALE_ROWS.items():
        assert by_dp.get(dp_id) == frozen, (
            f"{dp_id}: TS required_if row changed; align it with the registry "
            "instead of re-freezing it"
        )
    assert set(by_dp) == {"dp4-failure-handling", *TS_STALE_ROWS, *ts_producers}
    for dp_id in PYTHON_ONLY_DP_IDS:
        assert dp_id not in by_dp, f"{dp_id}: TS grew a row for a Python-only dp"


def test_ts_dp3_requires_local_candidates() -> None:
    """W3's concrete gap: the dynamic-choice enum is fed by local_candidates."""
    _universal, by_dp = _ts_required_fields()
    assert "local_candidates" in by_dp["dp3-worker-clarify"]

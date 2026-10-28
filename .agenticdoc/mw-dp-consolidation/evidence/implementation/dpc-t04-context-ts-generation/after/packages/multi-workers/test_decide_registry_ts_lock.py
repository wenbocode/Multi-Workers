"""Drift lock: the checked-in TS registry must equal a fresh render, byte for byte.

T04 (key ``mw-dp-consolidation``) regenerates the module from the Python side:
``decision_points.registry_snapshot`` is the single authority for the eight
active entry contracts (questions version, kind, role, required/optional field
constraints, model allowlist), ``decision_context.CONTEXT_SLOTS`` for the
``context`` slots an entry may emit, and the snapshot's ``preparation`` /
``retired`` sections for the basis layering and the read-only retirement
directory. The TS producers may not keep a second hand-written copy, so this
module proves the checked-in artifact really is that one source:

* the file is a byte-for-byte ``render()`` (write path == checked-in path) and
  ``--check``/``--stdout`` write nothing at all;
* exactly the eight active ids are entry keys, in the registry's own order, with
  their questions version, ``kind`` and ``roleScope`` (eligibility, not a grant);
* every declared field constraint (type, enum, caps, ``emptyIsValue``) round
  trips field by field, in the source order;
* the model whitelist and the PM-prepared basis contract are separate layers:
  ``basis_catalog`` is *not* material and never rides in the trimmable
  ``context`` block, so ``fit_context`` cannot delete core evidence;
* the 25 retired ids are a read-only projection with no field contract, i.e.
  zero callable aliases and no second menu.

Hermetic: read-only plus a temp-free ``--stdout``/``--check`` subprocess; no
network, no provider, no ``.mw`` writes.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

MW_ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(MW_ROOT))
sys.path.insert(0, str(MW_ROOT / "scripts"))  # noqa: E402

import decision_context  # noqa: E402
import decision_points as dpts  # noqa: E402
import gen_decide_registry_ts as gen  # noqa: E402

#: The generated const declarations this module parses (the only TS it trusts).
ENTRY_ANCHOR = "export const DECIDE_REGISTRY: Record<string, DecideRegistryEntry> = "
PREPARATION_ANCHOR = (
    "export const DECIDE_REGISTRY_PREPARATION: DecideRegistryPreparation = "
)
RETIRED_ANCHOR = (
    "export const DECIDE_REGISTRY_RETIRED: DecideRegistryRetiredEntry[] = "
)

#: Constraint key -> generated TS property (the one naming table).
CONSTRAINT_KEYS = {
    "max_items": "maxItems",
    "item_type": "itemType",
    "max_bytes": "maxBytes",
    "item_max_bytes": "itemMaxBytes",
    "signed": "signed",
    "min_value": "minValue",
    "empty_is_value": "emptyIsValue",
}
#: Order the generator emits a field's properties in (``enum`` first).
FIELD_PROPERTY_ORDER = (
    "name",
    "type",
    "description",
    "enum",
    "maxItems",
    "itemType",
    "maxBytes",
    "itemMaxBytes",
    "signed",
    "minValue",
    "emptyIsValue",
)


# ---------------------------------------------------------------------------
# A tiny TS literal parser: the assertions below read the checked-in artifact
# itself (not ``render()``), so a stale or hand-edited module cannot pass.
# ---------------------------------------------------------------------------


class _Reference:
    """An identifier used as a value (``DECIDE_REGISTRY_PREPARATION``)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Reference) and other.name == self.name

    def __repr__(self) -> str:  # pragma: no cover - assertion helper
        return f"_Reference({self.name!r})"


class _LiteralParser:
    """Parse one JSON-compatible TS literal (objects/arrays/strings/numbers)."""

    _IDENT = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")

    def __init__(self, text: str, index: int) -> None:
        self.text = text
        self.index = index

    def _skip(self) -> None:
        while self.index < len(self.text) and self.text[self.index] in " \t\r\n":
            self.index += 1

    def _expect(self, char: str) -> None:
        self._skip()
        assert self.text[self.index] == char, (
            f"expected {char!r} at offset {self.index}: {self.text[self.index:self.index + 24]!r}"
        )
        self.index += 1

    def parse(self) -> object:
        self._skip()
        char = self.text[self.index]
        if char == "{":
            return self._object()
        if char == "[":
            return self._array()
        if char in "\"'":
            return self._string()
        if char == "-" or char.isdigit():
            return self._number()
        return self._identifier()

    def _object(self) -> dict:
        self._expect("{")
        result: dict = {}
        while True:
            self._skip()
            if self.text[self.index] == "}":
                self.index += 1
                return result
            key = self._string() if self.text[self.index] in "\"'" else self._ident_word()
            assert isinstance(key, str) and key, "object key must be a string"
            assert key not in result, f"duplicate literal key: {key}"
            self._expect(":")
            result[key] = self.parse()
            self._skip()
            if self.text[self.index] == ",":
                self.index += 1

    def _array(self) -> list:
        self._expect("[")
        items: list = []
        while True:
            self._skip()
            if self.text[self.index] == "]":
                self.index += 1
                return items
            items.append(self.parse())
            self._skip()
            if self.text[self.index] == ",":
                self.index += 1

    def _string(self) -> str:
        quote = self.text[self.index]
        self.index += 1
        chars: list[str] = []
        while True:
            char = self.text[self.index]
            if char == "\\":
                chars.append(self.text[self.index + 1])
                self.index += 2
                continue
            if char == quote:
                self.index += 1
                return "".join(chars)
            chars.append(char)
            self.index += 1

    def _number(self) -> int | float:
        start = self.index
        if self.text[self.index] == "-":
            self.index += 1
        while self.index < len(self.text) and (
            self.text[self.index].isdigit() or self.text[self.index] == "."
        ):
            self.index += 1
        raw = self.text[start : self.index]
        return float(raw) if "." in raw else int(raw)

    def _ident_word(self) -> str:
        start = self.index
        while self.index < len(self.text) and self.text[self.index] in self._IDENT:
            self.index += 1
        word = self.text[start : self.index]
        assert word, f"unparsed token at offset {start}"
        return word

    def _identifier(self) -> object:
        word = self._ident_word()
        if word == "true":
            return True
        if word == "false":
            return False
        if word in ("null", "undefined"):
            return None
        return _Reference(word)


def _generated_text() -> str:
    return gen.output_path().read_text(encoding="utf-8")


def _literal_after(anchor: str) -> object:
    text = _generated_text()
    start = text.index(anchor)
    parser = _LiteralParser(text, start + len(anchor))
    value = parser.parse()
    parser._skip()
    assert text[parser.index] == ";", f"{anchor!r}: the literal is not terminated"
    return value


def _generated_entries() -> dict[str, dict]:
    entries = _literal_after(ENTRY_ANCHOR)
    assert isinstance(entries, dict), "DECIDE_REGISTRY must be an object literal"
    return entries


def _snapshot_points() -> dict[str, dict]:
    return {point["id"]: point for point in dpts.registry_snapshot()["points"]}


def _expected_field(field_spec: dict) -> dict:
    """The exact generated property set/order for one declared field."""
    field: dict = {
        "name": field_spec["name"],
        "type": field_spec["type"],
        "description": field_spec["description"],
    }
    if field_spec.get("enum"):
        field["enum"] = list(field_spec["enum"])
    for key, ts_key in CONSTRAINT_KEYS.items():
        if key in field_spec:
            field[ts_key] = field_spec[key]
    return field


def _declared_material_paths() -> set[str]:
    return {
        path
        for dp_id in dpts.ACTIVE_DP_IDS
        for path in (
            set(dpts.REQUIRED_STATE_FIELDS[dp_id])
            | set(dpts.OPTIONAL_STATE_FIELDS.get(dp_id, ()))
        )
    }


# ---------------------------------------------------------------------------
# 1. Byte lock: the checked-in artifact is the generator output
# ---------------------------------------------------------------------------


def test_generated_registry_matches_a_fresh_render() -> None:
    path = gen.output_path()
    assert path.exists(), f"missing generated module: {gen.OUTPUT_RELATIVE_PATH}"
    on_disk = path.read_text(encoding="utf-8")
    assert on_disk == gen.render(), (
        "decide-registry.generated.ts is stale; run "
        "`cd packages/multi-workers && python scripts/gen_decide_registry_ts.py`"
    )


def test_generator_check_mode_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/gen_decide_registry_ts.py", "--check"],
        cwd=MW_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_check_and_stdout_modes_write_nothing() -> None:
    """The pure-generation modes must not touch the module or any other file."""
    path = gen.output_path()
    before = path.read_bytes()
    cases = MW_ROOT / "decide_cases"
    legacy_cases = {
        case.name: hashlib.sha256(case.read_bytes()).hexdigest()
        for case in sorted(cases.glob("dp*.json"))
    }
    assert len(legacy_cases) == 4, f"the four read-only legacy cases moved: {legacy_cases}"
    registry_before = (MW_ROOT / "decide_registry.json").read_bytes()

    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    checked = subprocess.run(
        [sys.executable, "scripts/gen_decide_registry_ts.py", "--check"],
        cwd=MW_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert checked.returncode == 0, checked.stderr
    assert checked.stdout == ""
    printed = subprocess.run(
        [sys.executable, "scripts/gen_decide_registry_ts.py", "--stdout"],
        cwd=MW_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert printed.returncode == 0, printed.stderr
    assert printed.stdout == before.decode("utf-8"), "--stdout must print the write path"

    assert path.read_bytes() == before, "--check/--stdout rewrote the generated module"
    assert (MW_ROOT / "decide_registry.json").read_bytes() == registry_before
    assert (
        {
            case.name: hashlib.sha256(case.read_bytes()).hexdigest()
            for case in sorted(cases.glob("dp*.json"))
        }
        == legacy_cases
    ), "a pure generation command wrote one of the four legacy cases"


def test_generated_header_and_shape_are_pinned() -> None:
    text = _generated_text()
    assert text.startswith(
        "// @generated by packages/multi-workers/scripts/gen_decide_registry_ts.py — do not edit\n"
    )
    assert ENTRY_ANCHOR.strip() + " {" in text
    assert "export interface DecideRegistryEntry {" in text
    assert "export interface DecideRegistryPreparation {" in text
    assert "export interface DecideRegistryRetiredEntry {" in text
    assert "\n\t\trequiredStateFields: [\n" in text


def test_checked_in_registry_json_is_the_same_source_snapshot() -> None:
    """T04 takes the T03 registry over verbatim: it must stay the live snapshot."""
    on_disk = (MW_ROOT / "decide_registry.json").read_text(encoding="utf-8")
    assert on_disk == dpts.registry_snapshot_text(), (
        "decide_registry.json drifted from decision_points.registry_snapshot(); "
        "regenerate it from the Python registry instead of editing it"
    )


# ---------------------------------------------------------------------------
# 2. The eight active entry contracts
# ---------------------------------------------------------------------------


def test_generated_registry_declares_the_eight_active_entries_in_order() -> None:
    entries = _generated_entries()
    assert tuple(entries) == dpts.ACTIVE_DP_IDS
    assert len(entries) == dpts.EXPECTED_DP_COUNT == 8
    assert set(entries).isdisjoint(dpts.RETIRED_DP_IDS), "a retired id became a callable entry"


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_generated_entry_matches_the_python_field_contract(dp_id: str) -> None:
    entry = _generated_entries()[dp_id]
    point = _snapshot_points()[dp_id]
    assert entry["questionsVersion"] == point["questions_version"]
    for key, source in (
        ("requiredStateFields", "required_state_fields"),
        ("optionalStateFields", "optional_state_fields"),
    ):
        rendered = entry[key]
        expected = [_expected_field(spec) for spec in point.get(source) or []]
        assert rendered == expected, f"{dp_id}/{key}: generated field contract drifted"
        for field in rendered:
            assert list(field) == [
                name
                for name in FIELD_PROPERTY_ORDER
                if name in field
            ], f"{dp_id}/{key}: field property order drifted"


def test_generated_model_whitelist_matches_the_python_allowlist() -> None:
    entries = _generated_entries()
    for dp_id in dpts.ACTIVE_DP_IDS:
        assert entries[dp_id]["modelStateFields"] == list(dpts.MODEL_STATE_FIELDS[dp_id]), (
            f"{dp_id}: the model allowlist is a second hand-kept table"
        )


def test_generated_empty_is_value_flags_survive_the_rendering() -> None:
    """``[]`` is a real value, not a missing one: the flag must reach TS."""
    entries = _generated_entries()
    flagged: dict[str, set[str]] = {}
    for dp_id, entry in entries.items():
        names = {
            field["name"]
            for field in entry["requiredStateFields"] + entry["optionalStateFields"]
            if field.get("emptyIsValue") is True
        }
        if names:
            flagged[dp_id] = names
    assert flagged["dp-QG"] == {"review_evidence"}
    assert flagged["dp-sign-key"] == {
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    }
    for dp_id, entry in entries.items():
        for field in entry["requiredStateFields"] + entry["optionalStateFields"]:
            expected = dpts.STATE_FIELD_DESCRIPTIONS[field["name"]].get("empty_is_value")
            assert field.get("emptyIsValue") == expected, (
                f"{dp_id}/{field['name']}: empty_is_value lost in generation"
            )


def test_generated_entries_declare_kind_and_role_without_granting_them() -> None:
    entries = _generated_entries()
    points = _snapshot_points()
    for dp_id, entry in entries.items():
        assert entry["kind"] == points[dp_id]["kind"], dp_id
        assert entry["roleScope"] == dpts.ENTRY_ROLES[dp_id], dp_id
    assert [dp for dp, entry in entries.items() if entry["roleScope"] == "worker"] == [
        "dp-w-check-task"
    ]
    for dp_id, entry in entries.items():
        assert not {"grants", "permissions", "authority", "allowedTools"} & set(entry), (
            f"{dp_id}: the generated contract must describe eligibility, not grant it"
        )


def test_generated_module_carries_no_hand_written_choice_menu() -> None:
    text = _generated_text()
    for marker in ("choices:", "labels:", "instructions:", "targetEntries:"):
        assert marker not in text, f"the generated module grew a second menu: {marker}"
    assert "undefined" not in text


# ---------------------------------------------------------------------------
# 3. Preparation layering: the basis is neither material nor trimmable context
# ---------------------------------------------------------------------------


def test_generated_preparation_contract_is_separate_from_material() -> None:
    preparation = _literal_after(PREPARATION_ANCHOR)
    section = dpts.registry_snapshot()["preparation"]
    assert preparation == {
        "keys": list(section["keys"]),
        "basisItemKeys": list(section["basis_item_keys"]),
        "basisSource": section["basis_source"],
        "independentOf": section["independent_of"],
        "basisStateField": "preparation.basis_catalog",
        "contextTrimmable": False,
    }
    assert preparation["basisStateField"] == "preparation." + section["keys"][0]
    assert preparation["basisStateField"] not in _declared_material_paths()
    for dp_id in dpts.ACTIVE_DP_IDS:
        assert preparation["basisStateField"] not in dpts.MODEL_STATE_FIELDS[dp_id], dp_id


def test_every_generated_entry_references_the_one_preparation_contract() -> None:
    text = _generated_text()
    for dp_id in dpts.ACTIVE_DP_IDS:
        start = text.index(f'\t"{dp_id}": {{')
        block = text[start : text.index("\n\t},", start)]
        assert block.endswith("\n\t\tpreparation: DECIDE_REGISTRY_PREPARATION,"), dp_id


def test_a_preparation_field_cannot_ride_in_the_trimmable_context() -> None:
    assert decision_context.validate_context(
        {"preparation.basis_catalog": "x"}, "dp-sign-key"
    ) == ["context.preparation.basis_catalog: unknown slot"]
    assert decision_context.validate_context({"prepared_at": "2026-10-26"}, "dp-QG") == [
        "context.prepared_at: unknown slot"
    ]


# ---------------------------------------------------------------------------
# 4. Context slots: real provenance, no core evidence, no retired producer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_generated_context_slots_match_the_slot_table(dp_id: str) -> None:
    entry = _generated_entries()[dp_id]
    expected = list(decision_context.slot_names_for(dp_id))
    assert entry["contextSlots"] == expected, (
        f"{dp_id}: the generated slots are a second hand-kept table"
    )
    rendered = ", ".join(f'"{slot}"' for slot in expected)
    assert f"contextSlots: [{rendered}]" in _generated_text()


def test_context_slot_provenance_names_only_active_entries() -> None:
    producers = {
        producer
        for slot in decision_context.SLOT_ORDER
        for producer in decision_context.CONTEXT_SLOTS[slot].get("producers", ())
    }
    assert producers <= set(dpts.ACTIVE_DP_IDS), sorted(producers - set(dpts.ACTIVE_DP_IDS))
    assert producers == {"dp-QG", "dp-auto"}
    assert decision_context.slot_names_for("dp-QG") == ("error_excerpt",)
    assert decision_context.slot_names_for("dp-auto") == ("error_excerpt",)
    for dp_id in ("dp-sign-key", "dp-route", "dp-w-type", "dp-gate-approve"):
        assert decision_context.slot_names_for(dp_id) == (), dp_id
    for retired_id in dpts.RETIRED_DP_IDS:
        assert decision_context.slot_names_for(retired_id) == (), retired_id


def test_no_context_slot_is_core_material_or_preparation() -> None:
    declared = _declared_material_paths()
    assert decision_context.trimmable_slot_conflicts(declared) == ()
    assert set(decision_context.SLOT_ORDER).isdisjoint(declared)
    assert set(decision_context.SLOT_ORDER).isdisjoint(
        {"preparation", *(f"preparation.{key}" for key in dpts.PREPARATION_KEYS)}
    )
    # The sign-key four-part material and the auto candidates are evidence, not
    # context: a fit_context cut must never be able to drop them.
    for path in (
        "delivery_goal",
        "actual_completion",
        "verification_evidence.verified",
        "unfinished_impact",
        "handling_options",
        "pm_note.subject",
    ):
        assert path not in decision_context.SLOT_ORDER, path


def test_generator_refuses_a_slot_that_collides_with_core_material() -> None:
    snapshot = json.loads(json.dumps(dpts.registry_snapshot()))
    sign = next(point for point in snapshot["points"] if point["id"] == "dp-sign-key")
    sign["required_state_fields"][0]["name"] = "change_summary"
    with pytest.raises(ValueError, match="collide with core decision material"):
        gen.render(snapshot)


def test_generator_refuses_context_provenance_of_a_retired_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = {
        name: {**dict(spec), "producers": tuple(spec.get("producers", ()))}
        for name, spec in decision_context.CONTEXT_SLOTS.items()
    }
    slots["error_excerpt"]["producers"] = ("dp-QG", "dp4-failure-handling")
    monkeypatch.setattr(decision_context, "CONTEXT_SLOTS", slots)
    with pytest.raises(ValueError, match="provenance"):
        gen.render(dpts.registry_snapshot())


# ---------------------------------------------------------------------------
# 5. The retired directory: read-only, 25 ids, zero aliases
# ---------------------------------------------------------------------------


def test_retired_projection_keeps_the_twentyfive_ids_read_only() -> None:
    retired = _literal_after(RETIRED_ANCHOR)
    assert isinstance(retired, list)
    assert [record["id"] for record in retired] == [
        record.id for record in dpts.RETIRED_DP_REGISTRY
    ]
    assert len(retired) == 25
    dispositions = [record["disposition"] for record in retired]
    assert dispositions.count("migrated") == 6
    assert dispositions.count("retired") == 19
    for record in retired:
        assert list(record) == [
            "id",
            "tier",
            "description",
            "disposition",
            "migratedTo",
            "note",
        ], record["id"]
        assert record["disposition"] in dpts.RETIRED_DISPOSITIONS
        if record["disposition"] == "migrated":
            assert record["migratedTo"] in dpts.ACTIVE_DP_IDS, record["id"]
        else:
            assert record["migratedTo"] is None, record["id"]
        for key in ("tier", "description", "note"):
            assert isinstance(record[key], str) and record[key].strip(), record["id"]


def test_retired_projection_is_not_a_callable_alias_or_a_second_menu() -> None:
    entries = _generated_entries()
    retired = _literal_after(RETIRED_ANCHOR)
    text = _generated_text()
    retired_ids = [record["id"] for record in retired]
    assert set(entries).isdisjoint(retired_ids)
    for record in retired:
        assert not {
            "requiredStateFields",
            "optionalStateFields",
            "modelStateFields",
            "contextSlots",
        } & set(record), f"{record['id']}: a retired id kept a callable field contract"
        assert f'\t"{record["id"]}": {{' not in text, (
            f"{record['id']}: rendered as an entry-shaped key (would read as an alias)"
        )

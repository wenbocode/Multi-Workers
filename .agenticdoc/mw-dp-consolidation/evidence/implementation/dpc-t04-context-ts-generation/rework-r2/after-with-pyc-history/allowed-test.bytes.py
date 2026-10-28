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
# 0. The case-directory boundary: four legacy files + the eight T05 cases
# ---------------------------------------------------------------------------

#: The four pre-T05 case files, by exact name. "However many ``dp*.json`` files
#: happen to exist" is *not* the contract: T05 adds the eight active cases next
#: to these four read-only ones, so a count (or a glob that also matches
#: ``dp-QG.json``) would refuse the legal coexistence instead of locking the
#: legacy bytes.
LEGACY_CASE_FILES: tuple[str, ...] = ("dp1.json", "dp2.json", "dp3.json", "dp25.json")
#: The eight active case file names T05 writes. Names only: this task claims no
#: business validity for their content.
ACTIVE_CASE_FILES: tuple[str, ...] = tuple(f"{dp_id}.json" for dp_id in dpts.ACTIVE_DP_IDS)


def _case_dir() -> pathlib.Path:
    """The product case directory (the coexistence regression points it elsewhere)."""
    return MW_ROOT / "decide_cases"


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case_snapshot(case_dir: pathlib.Path) -> dict[str, str]:
    """``{file name: sha256}`` of every file of one case directory.

    The four legacy files are required *by name*: a deleted or renamed one is a
    real defect, while an extra active case is a legal state T05 introduces.
    """
    present = sorted(entry.name for entry in case_dir.iterdir() if entry.is_file())
    missing = [name for name in LEGACY_CASE_FILES if name not in present]
    assert not missing, (
        f"the four read-only legacy cases moved: {missing} missing from {case_dir}"
    )
    return {name: _sha256_file(case_dir / name) for name in present}


def _assert_case_dir_unchanged(before: dict[str, str], after: dict[str, str]) -> None:
    """Refuse any add / delete / rewrite in a case directory (every file)."""
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(name for name in before if name in after and before[name] != after[name])
    assert not (added or removed or changed), (
        "a pure generation command wrote the case directory: "
        f"added={added} removed={removed} changed={changed}"
    )


def _assert_bytes_unchanged(path: pathlib.Path, before: bytes, label: str) -> None:
    """Byte witness of one generated artifact (``--check``/``--stdout`` may not write)."""
    after = path.read_bytes()
    assert after == before, f"a pure generation command rewrote {label}"


def _build_case_fixture(
    root: pathlib.Path,
    *,
    legacy: tuple[str, ...] = LEGACY_CASE_FILES,
    active: tuple[str, ...] = ACTIVE_CASE_FILES,
) -> pathlib.Path:
    """A private case directory: real legacy bytes + synthetic active cases.

    The legacy files are byte copies of the checked-in ones, so the fixture is
    the four real read-only cases; the active ones carry a synthetic marker
    because T05 has not produced them yet. Nothing here proves their business
    content - only the directory boundary.
    """
    root.mkdir(parents=True, exist_ok=True)
    product = MW_ROOT / "decide_cases"
    for name in legacy:
        (root / name).write_bytes((product / name).read_bytes())
    for name in active:
        (root / name).write_text(
            json.dumps({"_synthetic": True, "case": name}, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return root


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
    """The pure-generation modes must not touch the module, the JSON or any case file.

    The case directory is protected as a whole: the four read-only legacy cases
    are required by name, and the run may neither add, delete nor rewrite *any*
    file there - so the four-legacy + eight-active coexistence T05 introduces is
    a legal state, while a write of either group is refused.
    """
    path = gen.output_path()
    before = path.read_bytes()
    cases = _case_dir()
    cases_before = _case_snapshot(cases)
    legacy_before = {name: cases_before[name] for name in LEGACY_CASE_FILES}
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

    _assert_bytes_unchanged(path, before, "the generated module")
    _assert_bytes_unchanged(
        MW_ROOT / "decide_registry.json", registry_before, "decide_registry.json"
    )
    cases_after = _case_snapshot(cases)
    assert {name: cases_after[name] for name in LEGACY_CASE_FILES} == legacy_before, (
        "a pure generation command wrote one of the four legacy cases"
    )
    _assert_case_dir_unchanged(cases_before, cases_after)


def test_case_dir_boundary_accepts_legacy_and_active_cases_together(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """T04's four legacy cases and T05's eight active cases are a legal state.

    Runs the *real* ``--check``/``--stdout`` write-nothing check (the same
    function body the product run executes, with the same assertions) against a
    private case directory; the generated module, ``decide_registry.json`` and
    the checked-in cases stay the real, read-only ones.
    """
    fixture = _build_case_fixture(tmp_path / "decide_cases")
    assert sorted(entry.name for entry in fixture.iterdir()) == sorted(
        LEGACY_CASE_FILES + ACTIVE_CASE_FILES
    )
    product_cases = _case_dir()
    product_before = _case_snapshot(product_cases)
    monkeypatch.setattr(sys.modules[__name__], "_case_dir", lambda: fixture)
    test_check_and_stdout_modes_write_nothing()
    _assert_case_dir_unchanged(product_before, _case_snapshot(product_cases))


def test_case_dir_snapshot_requires_every_legacy_file(tmp_path: pathlib.Path) -> None:
    """A missing legacy case is refused *by name*, not by a file count."""
    fixture = _build_case_fixture(
        tmp_path / "decide_cases", legacy=("dp1.json", "dp2.json", "dp3.json")
    )
    with pytest.raises(
        AssertionError, match=r"legacy cases moved: \['dp25\.json'\] missing"
    ):
        _case_snapshot(fixture)

@pytest.mark.parametrize(
    ("mutation", "detail"),
    [
        ("add-active", r"added=\['dp-extra\.json'\]"),
        ("add-foreign", r"added=\['notes\.txt'\]"),
        ("rewrite-active", r"changed=\['dp-QG\.json'\]"),
        ("delete-active", r"removed=\['dp-QG\.json'\]"),
        ("rewrite-legacy", r"changed=\['dp1\.json'\]"),
    ],
)
def test_case_dir_boundary_refuses_a_changed_case_set(
    tmp_path: pathlib.Path, mutation: str, detail: str
) -> None:
    """Add / rewrite / delete inside the case directory is refused, active or legacy."""
    fixture = _build_case_fixture(tmp_path / "decide_cases")
    before = _case_snapshot(fixture)
    if mutation == "add-active":
        (fixture / "dp-extra.json").write_bytes(b'{"added": true}\n')
    elif mutation == "add-foreign":
        (fixture / "notes.txt").write_bytes(b"scratch\n")
    elif mutation == "rewrite-active":
        (fixture / "dp-QG.json").write_bytes(b'{"rewritten": true}\n')
    elif mutation == "delete-active":
        (fixture / "dp-QG.json").unlink()
    else:
        (fixture / "dp1.json").write_bytes(b'{"rewritten": true}\n')
    with pytest.raises(AssertionError, match=detail):
        _assert_case_dir_unchanged(before, _case_snapshot(fixture))


def test_case_dir_boundary_refuses_a_deleted_legacy_case(tmp_path: pathlib.Path) -> None:
    """Deleting a legacy case is refused by the existence check, not the diff."""
    fixture = _build_case_fixture(tmp_path / "decide_cases")
    _case_snapshot(fixture)
    (fixture / "dp25.json").unlink()
    with pytest.raises(AssertionError, match=r"\['dp25\.json'\] missing"):
        _case_snapshot(fixture)


def _assert_a_writing_command_is_refused(
    monkeypatch: pytest.MonkeyPatch, fixture: pathlib.Path, mutate, expected: str
) -> None:
    """Run the real boundary with a *simulated* writer that mutates the fixture.

    The simulator only proves that the fixture/guard is not gullible: it returns
    rc=0 and the real artifact text, so the case-directory witness is the only
    failing signal. The real ``--check``/``--stdout`` runs are executed (not
    faked) by ``test_check_and_stdout_modes_write_nothing`` and its coexistence
    regression above.
    """
    artifact = gen.output_path().read_text(encoding="utf-8")
    state = {"mutated": False}

    def simulated_run(argv, **kwargs):  # noqa: ANN001, ANN003 - mirrors subprocess.run
        if not state["mutated"]:
            # The two modes are one command's two invocations; the writer touches
            # the directory once (a repeated unlink would just raise ENOENT).
            mutate(fixture)
            state["mutated"] = True
        # ``--check`` prints nothing, ``--stdout`` prints the write path's text:
        # the simulated run must satisfy the body's own mode contract so the only
        # failing signal left is the case-directory witness.
        printed = "" if "--check" in argv else artifact
        return subprocess.CompletedProcess(argv, 0, stdout=printed, stderr="")

    monkeypatch.setattr(sys.modules[__name__], "_case_dir", lambda: fixture)
    monkeypatch.setattr(subprocess, "run", simulated_run)
    with pytest.raises(AssertionError, match=expected):
        test_check_and_stdout_modes_write_nothing()


def test_boundary_refuses_a_command_that_writes_active_cases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """A writer that adds / rewrites / deletes active cases is refused."""
    fixture = _build_case_fixture(tmp_path / "decide_cases")
    product_cases = _case_dir()
    product_before = _case_snapshot(product_cases)

    def mutate(root: pathlib.Path) -> None:
        (root / "dp-QG.json").write_bytes(b'{"rewritten": true}\n')
        (root / "dp-extra.json").write_bytes(b'{"added": true}\n')
        (root / "dp-route.json").unlink()

    _assert_a_writing_command_is_refused(
        monkeypatch,
        fixture,
        mutate,
        r"wrote the case directory: added=\['dp-extra\.json'\] "
        r"removed=\['dp-route\.json'\] changed=\['dp-QG\.json'\]",
    )
    _assert_case_dir_unchanged(product_before, _case_snapshot(product_cases))


def test_boundary_refuses_a_command_that_rewrites_a_legacy_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """A writer that rewrites one of the four legacy cases is refused by name."""
    fixture = _build_case_fixture(tmp_path / "decide_cases")

    def mutate(root: pathlib.Path) -> None:
        (root / "dp1.json").write_bytes(b'{"rewritten": true}\n')

    _assert_a_writing_command_is_refused(
        monkeypatch, fixture, mutate, r"wrote one of the four legacy cases"
    )


def test_boundary_refuses_a_command_that_deletes_a_legacy_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """A writer that deletes a legacy case is refused (the required file is gone)."""
    fixture = _build_case_fixture(tmp_path / "decide_cases")

    def mutate(root: pathlib.Path) -> None:
        (root / "dp25.json").unlink()

    _assert_a_writing_command_is_refused(
        monkeypatch, fixture, mutate, r"legacy cases moved: \['dp25\.json'\] missing"
    )

def test_artifact_byte_guard_refuses_ts_and_json_drift(tmp_path: pathlib.Path) -> None:
    """The byte witness refuses a rewritten generated module or registry JSON.

    Fixture-level: copies of the real artifact/JSON bytes are rewritten and the
    same guard the production run applies must reject them. Production parity on
    the real paths is asserted (not simulated) by the two tests above.
    """
    module = tmp_path / "decide-registry.generated.ts"
    registry = tmp_path / "decide_registry.json"
    module.write_bytes(gen.output_path().read_bytes())
    registry.write_bytes((MW_ROOT / "decide_registry.json").read_bytes())
    module_before = module.read_bytes()
    registry_before = registry.read_bytes()
    _assert_bytes_unchanged(module, module_before, "the generated module")
    _assert_bytes_unchanged(registry, registry_before, "decide_registry.json")
    module.write_bytes(module_before + b"// drift\n")
    drifted = registry_before.replace(b'"schema": 4', b'"schema": 5', 1)
    assert drifted != registry_before, "the JSON fixture mutation must really change bytes"
    registry.write_bytes(drifted)
    with pytest.raises(AssertionError, match=r"rewrote the generated module"):
        _assert_bytes_unchanged(module, module_before, "the generated module")
    with pytest.raises(AssertionError, match=r"rewrote decide_registry\.json"):
        _assert_bytes_unchanged(registry, registry_before, "decide_registry.json")


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

"""test_decide_registry_export.py — drift guard for the exported dp registry.

Card D-CFG + W4: ``packages/multi-workers/decide_registry.json`` is the
framework-readable form of :data:`decision_points.DP_REGISTRY` (25 points,
generated) with the hand-maintained wiring carried on each point (``wired`` /
``trigger`` / ``adopted_at`` / ``wiring_note``, TS call sites as ``path:line``).
Everything generated must stay byte-identical to ``registry_snapshot()``, and
everything hand-written must stay resolvable, so this module fails the moment
one side drifts:

1. the on-disk file equals a fresh ``mw decide dp export --write`` render
   (byte for byte, including the preserved per-point wiring);
2. all 25 registered ids are present, in registry order, and every point owns
   its four wiring keys (no parallel top-level ``wiring`` section);
3. a ``wired=true`` point names an existing repo file and a line inside it, a
   ``wired=false`` point carries no location;
4. ``questions_version`` / ``required_state_fields`` / the question set match
   the live registry (no hand-edited registry facts);
5. ``executor`` keeps the three-way runtime reading (``_unwired_executor`` is
   ``unwired``, not ``wired``).

Hermetic: read-only against the package files, no network, no ``.mw`` writes.
The authorization table ``.mw/decide-points.json`` is never touched (it is the
human authority source, design D-001).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
EXPORT_PATH = PACKAGE_DIR / mw._DP_EXPORT_NAME

#: Frozen per-point wiring keys (generated snapshot + hand edit sections).
WIRING_KEYS = dpts.SNAPSHOT_WIRING_KEYS
#: The call sites the evidence files (dp-inventory-A-20261021.md) confirm.
WIRED_DP_IDS = frozenset({"dp1-dispatch-type", "dp2-checkpoint-split", "dp3-worker-clarify"})


def _export_doc() -> dict:
    return json.loads(EXPORT_PATH.read_text(encoding="utf-8"))


def _points_by_id(doc: dict | None = None) -> dict[str, dict]:
    return {point["id"]: point for point in (doc or _export_doc())["points"]}


def _split_location(location: str) -> tuple[str, int]:
    """``"<repo-relative path>:<line>"`` -> ``(path, line)``."""
    path, separator, line = location.rpartition(":")
    assert separator == ":" and path and line.isdigit(), f"not <path>:<line>: {location!r}"
    return path, int(line)


def _line_count(path: pathlib.Path) -> int:
    return len(path.read_bytes().splitlines())


def _export_args(**kw) -> argparse.Namespace:
    base = {"subcommand": "decide", "decide_action": "dp", "dp_action": "export",
            "project": ".", "json": False, "write": False}
    base.update(kw)
    return argparse.Namespace(**base)


def test_export_is_byte_identical_to_a_regeneration() -> None:
    expected = dpts.registry_snapshot_text(mw._dp_export_doc()[0]).encode("utf-8")
    actual = EXPORT_PATH.read_bytes()
    if actual != expected:
        pytest.fail(
            f"{EXPORT_PATH.name} drifted from decision_points.DP_REGISTRY "
            f"(on disk {len(actual)} B, regenerated {len(expected)} B); "
            f"run `python mw.py decide dp export --write`"
        )
    assert b"\r" not in actual, "decide_registry.json must use bare '\\n' newlines"


def test_export_holds_all_25_points_in_registry_order() -> None:
    doc = _export_doc()
    assert doc["schema"] == dpts.SNAPSHOT_SCHEMA
    assert doc["generated_from"] == "decision_points.DP_REGISTRY"
    assert doc["question_types"] == sorted(decision.QUESTION_TYPES)
    assert len(doc["points"]) == len(dpts.DP_REGISTRY) == dpts.EXPECTED_DP_COUNT
    assert [point["id"] for point in doc["points"]] == [point.id for point in dpts.DP_REGISTRY]
    assert "wiring" not in doc, "the parallel top-level wiring section must be gone"


@pytest.mark.parametrize("dp_point", dpts.DP_REGISTRY, ids=lambda point: point.id)
def test_wiring_entry_points_at_a_real_line(dp_point: dpts.DecisionPoint) -> None:
    entry = _points_by_id()[dp_point.id]
    for key in WIRING_KEYS:
        assert key in entry, f"{dp_point.id}: wiring key {key!r} drifted off the point"
    assert "note" not in entry, f"{dp_point.id}: legacy wiring key 'note' survived"
    assert isinstance(entry["wiring_note"], str) and entry["wiring_note"].strip(), (
        f"{dp_point.id}: empty wiring_note"
    )
    if entry["wired"] is True:
        for field in ("trigger", "adopted_at"):
            location = entry[field]
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
        assert entry["wired"] is False, f"{dp_point.id}: wired must be a boolean"
        assert entry["trigger"] is None and entry["adopted_at"] is None, (
            f"{dp_point.id}: an unwired dp must not claim a call site"
        )


def test_wired_set_is_the_three_documented_call_sites() -> None:
    wired = {
        point["id"] for point in _export_doc()["points"] if point["wired"] is True
    }
    assert wired == WIRED_DP_IDS, (
        "the wired set is hand-maintained evidence; a wiring change must be deliberate "
        f"and recorded in the card (got {sorted(wired)})"
    )


def test_questions_version_and_required_state_fields_follow_the_registry() -> None:
    by_id = _points_by_id()
    for point in dpts.DP_REGISTRY:
        exported = by_id[point.id]
        # Tier + default flag are registry facts too: the export must not keep a
        # stale tier after a re-tier (W11: dp25 P1 -> P2, default on).
        assert exported["tier"] == point.tier, f"{point.id}: tier drifted; regenerate the export"
        assert exported["default_enabled"] is point.default_enabled, (
            f"{point.id}: default_enabled drifted; regenerate the export"
        )
        assert exported["questions_version"] == point.questions_version, (
            f"{point.id}: questions_version drifted; regenerate the export"
        )
        assert exported["required_state_fields"] == [
            {
                "name": path,
                "type": dpts.STATE_FIELD_DESCRIPTIONS[path]["type"],
                "description": dpts.STATE_FIELD_DESCRIPTIONS[path]["description"],
            }
            for path in dpts.REQUIRED_STATE_FIELDS.get(point.id, ())
        ], f"{point.id}: required_state_fields drifted from REQUIRED_STATE_FIELDS"
        assert [question["id"] for question in exported["questions"]] == [
            str(question["id"]) for question in point.questions
        ], f"{point.id}: the exported question set drifted"
        assert [question["type"] for question in exported["questions"]] == [
            str(question["type"]) for question in point.questions
        ], f"{point.id}: an exported question type drifted"


def test_executor_kind_matches_the_runtime_three_way_reading() -> None:
    assert dpts._executor_kind(None) == "none"
    assert dpts._executor_kind(lambda answers, trigger: "acted") == "wired"
    placeholder = dpts._unwired_executor("dp-test")
    assert dpts._executor_kind(placeholder) == "unwired"
    with pytest.raises(NotImplementedError):
        placeholder({}, dpts.Trigger())

    by_id = _points_by_id()
    for point in dpts.DP_REGISTRY:
        assert by_id[point.id]["executor"] == dpts._executor_kind(point.executor), (
            f"{point.id}: executor kind drifted from the registry"
        )
    assert {point["executor"] for point in by_id.values()} <= {"wired", "unwired", "none"}
    unwired = {point.id for point in dpts.DP_REGISTRY if getattr(point.executor, "unwired", False)}
    assert unwired, "_unwired_executor placeholders disappeared from the registry"
    assert {by_id[dp_id]["executor"] for dp_id in unwired} == {"unwired"}, (
        "a registered placeholder must not be reported as wired"
    )


def test_write_regenerates_without_losing_wiring(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    target = tmp_path / mw._DP_EXPORT_NAME
    target.write_bytes(EXPORT_PATH.read_bytes())
    monkeypatch.setattr(mw, "_dp_export_path", lambda: target)

    assert mw._dp_export(_export_args(write=True), tmp_path) == 0
    assert target.read_bytes() == EXPORT_PATH.read_bytes()
    assert f"wrote {target} (25 points, 3 wired)" in capsys.readouterr().out

    # `--json` is the same document, wiring included.
    assert mw._dp_export(_export_args(json=True), tmp_path) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["points"]) == 25
    assert set(payload) == {"schema", "generated_from", "question_types", "points"}
    assert payload["schema"] == 2
    assert sum(1 for point in payload["points"] if point["wired"]) == 3


def test_write_migrates_a_legacy_top_level_wiring_section(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The pre-W4 shape migrates once: top-level `wiring` + `note` -> per point.

    A legacy file must not cost the hand-written call sites, and the rewritten
    file must be byte-identical to the current export (i.e. no top-level section
    survives the migration).
    """
    current = _export_doc()
    legacy = {
        "schema": 1,
        "generated_from": current["generated_from"],
        "question_types": current["question_types"],
        "points": [
            {key: value for key, value in point.items() if key not in WIRING_KEYS}
            for point in current["points"]
        ],
        "wiring": {
            point["id"]: {
                "wired": point["wired"],
                "trigger": point["trigger"],
                "adopted_at": point["adopted_at"],
                "note": point["wiring_note"],
            }
            for point in current["points"]
        },
    }
    target = tmp_path / mw._DP_EXPORT_NAME
    target.write_text(
        json.dumps(legacy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    monkeypatch.setattr(mw, "_dp_export_path", lambda: target)

    assert mw._dp_export(_export_args(write=True), tmp_path) == 0
    capsys.readouterr()
    migrated = json.loads(target.read_text(encoding="utf-8"))
    assert "wiring" not in migrated
    assert migrated["schema"] == 2
    assert migrated == current, "the migration lost a hand-written wiring entry"
    assert target.read_bytes() == EXPORT_PATH.read_bytes()


def test_write_refuses_to_clobber_unreadable_wiring(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    target = tmp_path / mw._DP_EXPORT_NAME
    target.write_text("{ not json", encoding="utf-8")
    before = target.read_bytes()
    monkeypatch.setattr(mw, "_dp_export_path", lambda: target)

    assert mw._dp_export(_export_args(write=True), tmp_path) == 2
    assert "nothing was written" in capsys.readouterr().err
    assert target.read_bytes() == before, "a typo in the hand-maintained file must not cost the wiring"

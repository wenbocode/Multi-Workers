"""test_dp_consolidation_signoff.py - T22 typed key-signoff validator.

Card T22 (``dpc-t22-signoff-validator``) / spec section 1.2 dp-sign-key and
design D-007:

* only an *active, valid* ``finalize`` plus its matching evidence satisfies a
  required key sign-off; ``continue`` / ``user-confirm`` stay legal menu words
  but write no sign-off file and never validate as one;
* a legacy file with no ``logical_id`` or the retired ``dp25-signoff-conclusion``
  id is read-only history, not a successful legacy pass;
* key-signoff and ``authority-change`` are typed, separate products: a
  consumer of one refuses the other, and ``finalize`` is never an
  authority-change / promote / demote word;
* the four business parts and the three arrays stay the material contract:
  ``[]`` is a real "none", a missing/``null`` array is not valid material;
* a sign-off is not a phase done, a stage close or a second PM approval.

Everything runs under ``tmp_path`` with the production writers; no network,
no provider, no credential. Fixtures are isolated per test.
"""

from __future__ import annotations

import dataclasses
import datetime
import io
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
import decision  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_signoff_result as signoff_result  # noqa: E402
import decision_wire as wire  # noqa: E402
from autopilot import contract_guard  # noqa: E402

KEY = "k-t22-signoff"
OTHER_KEY = "k-t22-other"
QP = "q-0123abcd"
LOGICAL = "logical-t22-001"


def _project(tmp_path: pathlib.Path, *, key: str = KEY) -> tuple[pathlib.Path, pathlib.Path]:
    project = tmp_path / "proj"
    key_dir = project / ".agenticdoc" / key
    (key_dir / "evidence" / "review").mkdir(parents=True)
    return project, key_dir


def _material(**overrides: object) -> dict:
    material = {
        "delivery_goal": "deliver the typed key-signoff validator for T22",
        "actual_completion": "typed validator, writer integration and tests landed",
        "verification_evidence": {
            "verified": ["pytest test_dp_consolidation_signoff.py"],
            "unverified": ["real provider end to end"],
        },
        "unfinished_impact": ["phase/stage closure stays a separate gate"],
    }
    material.update(overrides)
    return material


def _facts(project: pathlib.Path, *, key: str = KEY, trigger: str = "t22-1"):
    decide_archive.append_decide(
        decide_signoff.archive_path(project),
        dp="dp-QG",
        key=key,
        task_key="task-t22",
        trigger_id=trigger,
        state={"schema_version": 2, "decision_point": "dp-QG"},
        questions_version=QP,
        available=True,
        answer={"q-verdict": {"value": "pass", "confidence": 0.9}},
        authority="binding",
        acted=True,
        actual_action="record the QG pass verdict",
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    return decide_signoff.collect(project, key)


def _record(
    project: pathlib.Path,
    key_dir: pathlib.Path,
    material: dict,
    *,
    key: str = KEY,
    logical_id: str = LOGICAL,
    conclusion: str = "finalize",
):
    facts = _facts(project, key=key)
    record = signoff_result.build_result(
        key_dir,
        key=key,
        logical_id=logical_id,
        decision_id=f"{signoff_result.DP_ID}:{logical_id}",
        conclusion=conclusion,
        material=material,
        facts=facts,
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
        task_key="task-t22",
        initiator_role="pm",
        snapshot_material=material,
    )
    signoff_result.write_result(key_dir, record, redact=decision.known_secret_redactor())
    return facts, record


def _sign(
    project: pathlib.Path,
    key_dir: pathlib.Path,
    material: dict,
    *,
    key: str = KEY,
    logical_id: str = LOGICAL,
):
    facts, record = _record(
        project, key_dir, material, key=key, logical_id=logical_id
    )
    text = decide_signoff.render(facts, "finalize", None, key, "-", result=record)
    decide_signoff.write_signoff(project, key, text)
    return facts, record


def _validate(
    key_dir: pathlib.Path,
    material: dict,
    *,
    key: str = KEY,
    current_evidence: object | None = "from-material",
    **kwargs: object,
):
    evidence = (
        material["verification_evidence"]
        if current_evidence == "from-material"
        else current_evidence
    )
    return signoff_result.validate_key_signoff(
        key_dir, key, material, evidence, **kwargs
    )


# ---------------------------------------------------------------------------
# The active typed vocabulary
# ---------------------------------------------------------------------------


def test_active_signoff_point_is_dp_sign_key_with_typed_product() -> None:
    assert signoff_result.DP_ID == "dp-sign-key"
    assert signoff_result.PRODUCT_TYPE == "key-signoff"
    assert signoff_result.AUTHORITY_CHANGE_PRODUCT_TYPE == "authority-change"
    assert signoff_result.CONCLUSIONS == ("finalize", "continue", "user-confirm")
    assert signoff_result.SIGNING_CONCLUSIONS == ("finalize",)
    assert signoff_result.LEGACY_DP_IDS == ("dp25-signoff-conclusion",)
    assert decide_signoff.SIGNOFF_DP_ID == "dp-sign-key"
    assert decide_signoff.SIGNOFF_CONCLUSIONS == signoff_result.CONCLUSIONS


# ---------------------------------------------------------------------------
# VC-004 / VC-051: four business parts and three arrays
# ---------------------------------------------------------------------------


def test_valid_finalize_is_the_only_successful_key_signoff(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)

    result = _validate(key_dir, material)
    assert result.valid is True, result.problems
    assert result.product_type == "key-signoff"
    assert result.conclusion == "finalize"
    assert result.signs_key is True
    assert result.writes_signoff is True
    assert result.closes_stage is False
    assert result.second_approval == 0
    assert result.key == KEY
    assert result.logical_id == LOGICAL
    assert result.decision_id == f"dp-sign-key:{LOGICAL}"
    assert result.dp == "dp-sign-key"
    text = (key_dir / "evidence" / "review" / "sign-final.md").read_text(encoding="utf-8")
    assert "product_type: key-signoff" in text.splitlines()
    assert "conclusion: finalize" in text.splitlines()


@pytest.mark.parametrize("conclusion", ["continue", "user-confirm"])
def test_continue_and_user_confirm_write_no_signoff_file(
    tmp_path: pathlib.Path, conclusion: str
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    facts, record = _record(
        project, key_dir, material, logical_id=f"logical-{conclusion}", conclusion=conclusion
    )
    assert record.conclusion == conclusion
    with pytest.raises(decide_signoff.SignoffError):
        decide_signoff.render(facts, conclusion, None, KEY, "-", result=record)
    assert not decide_signoff.signoff_path(project, KEY).exists()

    invalid = _validate(key_dir, material)
    assert invalid.valid is False
    assert invalid.signs_key is False
    assert "missing sign-off file" in invalid.reason


@pytest.mark.parametrize(
    "material",
    [
        _material(verification_evidence={"unverified": []}),
        _material(verification_evidence={"verified": [], "unverified": None}),
        _material(verification_evidence={"verified": None, "unverified": []}),
        _material(unfinished_impact=None),
        {"delivery_goal": "x", "actual_completion": "y", "verification_evidence": {"verified": [], "unverified": []}},
        _material(delivery_goal=""),
        _material(actual_completion=""),
    ],
)
def test_missing_or_null_sign_arrays_are_invalid(
    tmp_path: pathlib.Path, material: dict
) -> None:
    project, key_dir = _project(tmp_path)
    _sign(project, key_dir, _material())
    result = _validate(key_dir, material)
    assert result.valid is False
    assert result.signs_key is False


def test_empty_arrays_are_a_real_none_and_remain_distinct_from_null(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    empty = _material(
        verification_evidence={"verified": [], "unverified": []},
        unfinished_impact=[],
    )
    _sign(project, key_dir, empty)
    assert _validate(key_dir, empty).valid is True

    # The persisted audit copy keeps `[]` as a list and `None` as null: a
    # projection must not collapse the two.
    stored = signoff_result.read_result(key_dir, LOGICAL)
    assert stored is not None
    assert stored.material["verification_evidence"]["verified"] == []
    assert stored.material["unfinished_impact"] == []
    null_material = _material(unfinished_impact=None)
    record = signoff_result.build_result(
        key_dir,
        key=KEY,
        logical_id="logical-null",
        decision_id=f"dp-sign-key:logical-null",
        conclusion="finalize",
        material=null_material,
        facts=decide_signoff.collect(project, KEY),
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
        snapshot_material=null_material,
    )
    assert record.material["unfinished_impact"] is None
    assert record.material["unfinished_impact"] != []


def test_material_change_after_signoff_is_not_reused(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    _sign(project, key_dir, _material())
    stale = _material(actual_completion="a different completion after the model call")
    result = _validate(key_dir, stale)
    assert result.valid is False
    assert result.signs_key is False
    assert "material" in result.reason


def test_current_evidence_must_match_the_signed_evidence(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)

    changed = {
        "verified": ["a later, different verification run"],
        "unverified": ["real provider end to end"],
    }
    result = _validate(key_dir, material, current_evidence=changed)
    assert result.valid is False
    assert "evidence" in result.reason

    missing = _validate(key_dir, material, current_evidence=None)
    assert missing.valid is False
    assert "evidence" in missing.reason


def test_render_refuses_a_file_word_that_disagrees_with_the_record(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    facts, record = _record(project, key_dir, material, conclusion="continue")
    with pytest.raises(decide_signoff.SignoffError):
        decide_signoff.render(facts, "finalize", None, KEY, "-", result=record)
    assert not decide_signoff.signoff_path(project, KEY).exists()


def test_missing_expected_matter_is_not_a_valid_signoff(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    _sign(project, key_dir, _material())
    result = signoff_result.validate_key_signoff(key_dir, KEY, None, {"verified": [], "unverified": []})
    assert result.valid is False
    assert result.signs_key is False


def test_signoff_is_bound_to_its_key_and_not_reusable_across_keys(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    other = signoff_result.validate_key_signoff(
        key_dir, OTHER_KEY, material, material["verification_evidence"]
    )
    assert other.valid is False
    assert other.signs_key is False
    assert other.key == OTHER_KEY


# ---------------------------------------------------------------------------
# VC-038 / VC-039: finalize vocabulary, no legacy / no stale reuse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["narrow", "revoke", "approve", "signed", "pass"])
def test_legacy_words_are_not_a_successful_signoff(
    tmp_path: pathlib.Path, word: str
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    path = decide_signoff.signoff_path(project, KEY)
    text = path.read_text(encoding="utf-8")
    tampered = text.replace("conclusion: finalize", f"conclusion: {word}")
    assert tampered != text
    signoff_result.write_signoff_text(key_dir, tampered)
    before = path.read_bytes()

    result = _validate(key_dir, material)
    assert result.valid is False
    assert result.signs_key is False
    assert path.read_bytes() == before  # read-only validation, no rewrite


def test_missing_logical_id_legacy_file_does_not_pass(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    path = decide_signoff.signoff_path(project, KEY)
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = "conclusion: finalize\ncounted_rows: 0\n"
    path.write_text(legacy, encoding="utf-8", newline="\n")
    before = path.read_bytes()

    validation = signoff_result.validate_signoff(key_dir, KEY)
    assert validation.valid is False
    assert "logical_id" in validation.reason
    assert _validate(key_dir, _material()).valid is False
    assert path.read_bytes() == before


def test_retired_dp25_history_is_read_only_not_a_current_signoff(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    path = decide_signoff.signoff_path(project, KEY)
    retired = path.read_text(encoding="utf-8").replace(
        "dp: dp-sign-key", "dp: dp25-signoff-conclusion"
    )
    signoff_result.write_signoff_text(key_dir, retired)
    before = path.read_bytes()

    result = _validate(key_dir, material)
    assert result.valid is False
    assert result.signs_key is False
    assert path.read_bytes() == before
    # The retired number is not callable again (history stays read-only).
    with pytest.raises(decision.DecisionInputError):
        dpts.get_decision_point("dp25-signoff-conclusion")


def test_writer_refuses_a_typed_non_finalize_signoff_text(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    path = decide_signoff.signoff_path(project, KEY)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "product_type: key-signoff\nconclusion: continue\n"
    with pytest.raises(decide_signoff.SignoffError):
        decide_signoff.write_signoff(project, KEY, text)
    assert not path.exists()


def test_signoff_requires_the_persisted_result_record(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    record_path = signoff_result.result_path(key_dir, LOGICAL)
    record_path.unlink()
    path = decide_signoff.signoff_path(project, KEY)
    before = path.read_bytes()

    result = _validate(key_dir, material)
    assert result.valid is False
    assert result.signs_key is False
    assert result.reason  # a locatable reason, never a silent pass
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# VC-005 / VC-006 / VC-053: QG products are not sign-offs
# ---------------------------------------------------------------------------


def test_a_qg_pass_artifact_is_not_a_key_signoff(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    qg_file = key_dir / "evidence" / "review" / "qg-pass.md"
    qg_file.parent.mkdir(parents=True, exist_ok=True)
    qg_file.write_text("conclusion: pass\ndp: dp-QG\n", encoding="utf-8", newline="\n")
    usable_pass = 0
    releases = 0

    result = _validate(key_dir, _material())
    assert result.valid is False
    assert result.signs_key is False
    assert "missing sign-off file" in result.reason
    assert usable_pass == 0 and releases == 0
    # An archive authority-change consumer refuses the key-signoff QG product.
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.require_authority_change({"kind": "decide", "dp": "dp-QG"})


def test_missing_quality_evidence_cannot_be_turned_into_a_signoff(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material(
        verification_evidence={"verified": [], "unverified": ["no quality evidence"]}
    )
    _sign(project, key_dir, material)
    result = _validate(key_dir, material)
    # The arrays are legal, but the unverified gap stays exactly as reported and
    # is never converted into a verified item by the validator.
    assert result.valid is True
    stored = signoff_result.read_result(key_dir, LOGICAL)
    assert stored is not None
    assert stored.material["verification_evidence"] == {
        "verified": [],
        "unverified": ["no quality evidence"],
    }


# ---------------------------------------------------------------------------
# VC-010 / VC-038: no stage close, no second approval, no QG substitution
# ---------------------------------------------------------------------------


def test_signoff_does_not_close_stage_or_add_a_second_approval(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    first = _validate(key_dir, material)
    second = _validate(key_dir, material)
    assert first.valid and second.valid
    assert first.second_approval == 0 and second.second_approval == 0
    assert first.closes_stage is False and second.closes_stage is False
    payload = first.as_dict()
    assert not {"stage_close", "phase_done", "done"} & set(payload)
    # A read-only validation writes nothing: no authority-change row appears.
    rows = [row for _lineno, row in decide_archive.iter_rows(decide_signoff.archive_path(project))]
    assert not any(row.get("kind") == "authority-change" for row in rows)


def test_validation_is_read_only(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    sign = decide_signoff.signoff_path(project, KEY)
    record = signoff_result.result_path(key_dir, LOGICAL)
    sign_sha = sign.read_bytes()
    record_sha = record.read_bytes()
    assert _validate(key_dir, material).valid is True
    assert sign.read_bytes() == sign_sha
    assert record.read_bytes() == record_sha


# ---------------------------------------------------------------------------
# Typed isolation: key-signoff vs authority-change
# ---------------------------------------------------------------------------


def test_tampered_product_type_is_not_a_key_signoff(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    path = decide_signoff.signoff_path(project, KEY)
    text = path.read_text(encoding="utf-8").replace(
        "product_type: key-signoff", "product_type: authority-change"
    )
    signoff_result.write_signoff_text(key_dir, text)
    result = _validate(key_dir, material)
    assert result.valid is False
    assert result.signs_key is False
    assert "product_type" in result.reason


def test_tampered_result_product_type_is_refused(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    record_path = signoff_result.result_path(key_dir, LOGICAL)
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    raw["product_type"] = "authority-change"
    record_path.write_text(json.dumps(raw), encoding="utf-8", newline="\n")

    result = _validate(key_dir, material)
    assert result.valid is False
    assert result.signs_key is False
    assert "record" in result.reason


def test_authority_change_product_is_accepted_only_by_its_own_consumer(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    record = signoff_result.read_result(key_dir, LOGICAL)
    assert record is not None
    # The key-signoff record is not an authority-change row.
    with pytest.raises(decide_archive.DecisionArchiveError):
        decide_archive.require_authority_change(record.as_dict())
    row = decide_archive.append_authority_change(
        decide_signoff.archive_path(project),
        dp="dp-QG",
        key=KEY,
        by="human",
        change="qg enabled=false",
    )
    assert decide_archive.require_authority_change(row)["kind"] == "authority-change"
    # ... and that row is not a key-signoff result either.
    assert record.product_type == "key-signoff"


# ---------------------------------------------------------------------------
# VC-050: association and no fabricated execution
# ---------------------------------------------------------------------------


def test_result_association_is_explicit_and_non_decreasing(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _, record = _sign(project, key_dir, material)
    result = _validate(
        key_dir,
        material,
        expected_logical_id=record.logical_id,
        expected_snapshot=record.snapshot_sha256,
    )
    assert result.valid is True
    assert result.logical_id == record.logical_id
    assert result.decision_id == record.decision_id
    assert result.snapshot_sha256 == record.snapshot_sha256
    assert result.material_sha256 == record.material_sha256
    assert result.evidence_sha256 == record.evidence_sha256
    assert result.observed_ts == record.ts
    # A different expected logical id is refused, never silently relinked.
    wrong = _validate(key_dir, material, expected_logical_id="logical-other")
    assert wrong.valid is False and wrong.signs_key is False


def test_failed_write_leaves_no_signoff_or_fabricated_execution(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    facts, record = _record(project, key_dir, material)
    # The record's archive snapshot no longer matches the facts it describes:
    # render must refuse instead of writing a stale sign-off.
    stale = dataclasses.replace(record, rows_sha256="0" * 64)
    with pytest.raises(decide_signoff.SignoffError):
        text = decide_signoff.render(facts, "finalize", None, KEY, "-", result=stale)
        decide_signoff.write_signoff(project, KEY, text)
    assert not decide_signoff.signoff_path(project, KEY).exists()
    result = _validate(key_dir, material)
    assert result.valid is False and result.signs_key is False


# ---------------------------------------------------------------------------
# VC-051: secrets never reach the persisted audit copy
# ---------------------------------------------------------------------------


def test_secret_in_material_is_redacted_in_the_result_record(
    tmp_path: pathlib.Path,
) -> None:
    secret = "sk-t22-should-never-be-persisted"
    project, key_dir = _project(tmp_path)
    material = _material(actual_completion=f"pasted {secret} into the completion")
    _sign(project, key_dir, material)
    record_text = signoff_result.result_path(key_dir, LOGICAL).read_text(encoding="utf-8")
    sign_text = decide_signoff.signoff_path(project, KEY).read_text(encoding="utf-8")
    assert secret not in record_text
    assert secret not in sign_text
    # The comparison source stays the *sent* material digest, so redaction did
    # not weaken the change check.
    assert _validate(key_dir, material).valid is True


# ---------------------------------------------------------------------------
# AC-039 / AC-052: the native contract/goal basis of a current finalize
# ---------------------------------------------------------------------------

SPEC_TEXT = "# spec\n\n| AC 编号 | 可判定描述 |\n|---|---|\n| AC-001 | first contract text, locked |\n"
DESIGN_TEXT = (
    "# design\n\nVC-001: the first condition\n"
    "       Layer: L2\n"
    "       Output: [VERIFY] VC-001: first=1\n"
    "       Source: AC-001\n"
)
GOAL_TEXT = "# Project Goal\n\n## Goal\n\nship the first goal\n\n## Context\n\ncontext one\n"


def _write_native_sources(
    key_dir: pathlib.Path,
    *,
    spec: str = SPEC_TEXT,
    design: str = DESIGN_TEXT,
    goal: str | None = GOAL_TEXT,
    newline: str = "\n",
) -> None:
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "spec.md").write_text(spec, encoding="utf-8", newline=newline)
    (key_dir / "design.md").write_text(design, encoding="utf-8", newline=newline)
    if goal is not None:
        (key_dir.parent / "goal.md").write_text(goal, encoding="utf-8", newline=newline)


def test_native_contract_basis_is_bound_and_rechecked(tmp_path: pathlib.Path) -> None:
    project, key_dir = _project(tmp_path)
    _write_native_sources(key_dir)
    material = _material()
    _sign(project, key_dir, material)

    validation = signoff_result.validate_signoff(key_dir, KEY)
    assert validation.valid is True, validation.reason
    assert validation.native_basis_verified is True
    assert validation.basis_sha256
    assert _validate(key_dir, material).signs_key is True
    record = signoff_result.read_result(key_dir, LOGICAL)
    assert record is not None and record.native_basis is not None
    assert record.native_basis["contract"]["items"]["AC-001"]

    # A substantive AC rewrite invalidates the old finalize and names the item.
    (key_dir / "spec.md").write_text(
        SPEC_TEXT.replace("first contract text, locked", "second contract text"),
        encoding="utf-8",
        newline="\n",
    )
    stale = signoff_result.validate_signoff(key_dir, KEY)
    assert stale.valid is False
    assert "AC-001" in stale.reason
    assert _validate(key_dir, material).signs_key is False

    # Restoring the exact same semantic text makes the same identity current
    # again: no new approval was minted or consumed here.
    (key_dir / "spec.md").write_text(SPEC_TEXT, encoding="utf-8", newline="\n")
    assert signoff_result.validate_signoff(key_dir, KEY).valid is True


def test_native_goal_basis_change_invalidates_the_finalize(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    _write_native_sources(key_dir)
    material = _material()
    _sign(project, key_dir, material)
    assert _validate(key_dir, material).signs_key is True

    (key_dir.parent / "goal.md").write_text(
        GOAL_TEXT.replace("first goal", "a different goal"),
        encoding="utf-8",
        newline="\n",
    )
    validation = signoff_result.validate_signoff(key_dir, KEY)
    assert validation.valid is False
    assert "goal" in validation.reason
    assert _validate(key_dir, material).signs_key is False


def test_formatting_only_unrelated_and_same_content_refreeze_reuse_the_finalize(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    _write_native_sources(key_dir)
    material = _material()
    _sign(project, key_dir, material)
    assert _validate(key_dir, material).signs_key is True

    # Formatting-only: CRLF, extra blank lines and trailing line whitespace in
    # the goal prose never enter the canonical identity.
    _write_native_sources(
        key_dir,
        spec=SPEC_TEXT.replace("\n", "\r\n") + "\r\n",
        design=DESIGN_TEXT.replace("\n", "\r\n"),
        goal="\n" + GOAL_TEXT.replace("\n", "   \n").replace("first goal", "first  goal") + "\n\n",
        newline="",
    )
    # An unrelated material and a same-content re-freeze move bytes/time only.
    (key_dir / "evidence" / "review" / "unrelated.txt").write_text(
        "not part of the contract\n", encoding="utf-8", newline="\n"
    )
    first = contract_guard.read_freeze(key_dir)
    assert first is None  # nothing was frozen before the unrelated edit
    contract_guard.freeze_contract(
        key_dir, KEY, SPEC_TEXT, DESIGN_TEXT, frozen_at="2026-01-01T00:00:00+00:00"
    )
    first = contract_guard.read_freeze(key_dir)
    contract_guard.freeze_contract(
        key_dir, KEY, SPEC_TEXT, DESIGN_TEXT, frozen_at="2026-01-02T00:00:00+00:00"
    )
    second = contract_guard.read_freeze(key_dir)
    assert first is not None and second is not None
    assert first.get("frozen_at") != second.get("frozen_at")

    validation = signoff_result.validate_signoff(key_dir, KEY)
    assert validation.valid is True, validation.reason
    assert _validate(key_dir, material).signs_key is True


def test_bound_native_source_loss_or_damage_invalidates_the_finalize(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    _write_native_sources(key_dir)
    material = _material()
    _sign(project, key_dir, material)
    assert _validate(key_dir, material).signs_key is True

    (key_dir / "spec.md").unlink()
    missing = signoff_result.validate_signoff(key_dir, KEY)
    assert missing.valid is False
    assert "missing" in missing.reason

    (key_dir / "spec.md").write_bytes(b"\xff\xfe not utf-8\n")
    damaged = signoff_result.validate_signoff(key_dir, KEY)
    assert damaged.valid is False
    assert "unreadable" in damaged.reason


def test_tampered_native_basis_machine_or_record_is_not_current(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    _write_native_sources(key_dir)
    material = _material()
    _sign(project, key_dir, material)
    path = decide_signoff.signoff_path(project, KEY)
    original = path.read_text(encoding="utf-8")

    path.write_text(
        original.replace("basis_sha256: ", "basis_sha256: 0"),
        encoding="utf-8",
        newline="\n",
    )
    assert signoff_result.validate_signoff(key_dir, KEY).valid is False
    path.write_text(original, encoding="utf-8", newline="\n")

    record_path = signoff_result.result_path(key_dir, LOGICAL)
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    raw["native_basis"]["contract"]["items"]["AC-001"] = "0" * 64
    record_path.write_text(json.dumps(raw), encoding="utf-8", newline="\n")
    validation = signoff_result.validate_signoff(key_dir, KEY)
    assert validation.valid is False
    assert "record" in validation.reason or "basis" in validation.reason


def test_pre_native_basis_record_is_history_not_current_proof(
    tmp_path: pathlib.Path,
) -> None:
    project, key_dir = _project(tmp_path)
    material = _material()
    _sign(project, key_dir, material)
    path = decide_signoff.signoff_path(project, KEY)
    record_path = signoff_result.result_path(key_dir, LOGICAL)
    raw = json.loads(record_path.read_text(encoding="utf-8"))
    # Reproduce an old-format record/file pair: no basis lines and the original
    # snapshot formula. Its bytes are history and are not rewritten.
    raw.pop("native_basis", None)
    raw.pop("basis_sha256", None)
    raw.pop("basis_version", None)
    raw["snapshot_sha256"] = signoff_result.snapshot_digest(
        key=KEY,
        material_sha256=raw["material_sha256"],
        evidence_sha256=raw["evidence_sha256"],
        rows_sha256=raw["rows_sha256"],
    )
    record_path.write_text(json.dumps(raw), encoding="utf-8", newline="\n")
    text = path.read_text(encoding="utf-8")
    text = "\n".join(
        line
        for line in text.splitlines()
        if not line.startswith(("basis_version:", "basis_sha256:"))
    ) + "\n"
    text = text.replace(
        f"snapshot_sha256: {signoff_result.parse_machine_lines(text)['snapshot_sha256']}",
        f"snapshot_sha256: {raw['snapshot_sha256']}",
    )
    path.write_text(text, encoding="utf-8", newline="\n")
    before = path.read_bytes()

    validation = signoff_result.validate_signoff(key_dir, KEY)
    assert validation.valid is True  # internally consistent history
    assert validation.native_basis_verified is False
    assert _validate(key_dir, material).signs_key is False
    assert path.read_bytes() == before


def test_real_family_contract_refreeze_invalidates_the_old_finalize(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The production family refreeze consumer proves the AC-001 change.

    This reuses the real T26 fixture (live PM claim, protected policy/authority,
    real gate/lifecycle consumer and writer) and only the model transport is
    the existing faux client. No helper bypasses the actor/writer/consumer.
    """
    import mw as mw_cli
    import test_dp_consolidation_gate_effects as ge

    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    root, owner, _claim, _state, _target = ge._conductor_h_fixture(
        tmp_path / "family-refreeze"
    )
    ge._family_policy(root)
    ge._family_rounds(root, owner, 1)
    key_dir = root / ".agenticdoc" / owner
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "spec.md").write_text(ge.T20_SPEC, encoding="utf-8", newline="\n")
    (key_dir / "design.md").write_text(ge.T20_DESIGN, encoding="utf-8", newline="\n")
    contract_guard.freeze_contract(key_dir, owner, ge.T20_SPEC, ge.T20_DESIGN)
    original = contract_guard.extract_contract(ge.T20_SPEC, ge.T20_DESIGN)
    before_versions = {**original.acs, **original.vcs}

    decide_archive.append_decide(
        decide_signoff.archive_path(root),
        dp="dp-QG",
        key=owner,
        task_key="T22-native",
        trigger_id="native-1",
        state={"schema_version": 2, "decision_point": "dp-QG"},
        questions_version=QP,
        available=True,
        answer={"q-verdict": {"value": "pass", "confidence": 0.9}},
        authority="binding",
        acted=True,
        actual_action="record the QG pass verdict",
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    material = _material()
    facts = decide_signoff.collect(root, owner)
    record = signoff_result.build_result(
        key_dir,
        key=owner,
        logical_id="native-family-1",
        decision_id=f"{signoff_result.DP_ID}:native-family-1",
        conclusion="finalize",
        material=material,
        facts=facts,
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
        task_key="T22-native",
        initiator_role="pm",
        snapshot_material=material,
    )
    signoff_result.write_result(
        key_dir, record, redact=decision.known_secret_redactor()
    )
    text = decide_signoff.render(facts, "finalize", None, owner, "-", result=record)
    decide_signoff.write_signoff(root, owner, text)
    assert signoff_result.validate_signoff(key_dir, owner).valid is True

    changed_spec = ge.T20_SPEC.replace(
        "first contract text, locked", "first contract text, rewritten"
    )
    (key_dir / "spec.md").write_text(changed_spec, encoding="utf-8", newline="\n")
    after = contract_guard.extract_contract(changed_spec, ge.T20_DESIGN)
    after_versions = {**after.acs, **after.vcs}
    request = {
        "key": owner,
        "items": ["AC-001"],
        "before_versions": {"AC-001": before_versions["AC-001"]},
        "after_versions": {"AC-001": after_versions["AC-001"]},
        "reason": "the acceptance condition missed the duplicate action count",
        "commitment_impact": "no commitment reduction",
        "evidence_impact": "AC-001 must be re-verified",
        "authority_ref": "signed-scope",
        "reverification_plan": "re-run the AC-001 fixture cases",
        "acceptance_reductions": [],
    }
    note = " | ".join(
        (
            request["key"],
            request["reason"],
            request["commitment_impact"],
            request["evidence_impact"],
            request["reverification_plan"],
            "AC-001",
        )
    )
    payload = {
        "request": request,
        "note": note,
        "approval": {
            "approval_ref": "change-approval-native",
            "key": owner,
            "items": ["AC-001"],
            "before_versions": request["before_versions"],
            "after_versions": request["after_versions"],
            "reverification_plan": request["reverification_plan"],
            "authority_source": "signed-scope",
            "authority_ref": "signed-scope",
            "acceptance_reductions": [],
        },
    }
    book = ge._family_book("contract-refreeze", payload, key=owner, logical_id="family-native-1")
    book_path = ge._family_book_path(root, book)
    ge._family_deploy_authority(
        monkeypatch, root, [f"contract-change:{owner}", "contract-item:AC-001"]
    )
    client = ge._pm_fake_client(root, book["book"]["preparation"], "approve")
    freeze_before = contract_guard.read_freeze(key_dir)
    signoff_before = decide_signoff.signoff_path(root, owner).read_bytes()
    archive_before = decide_signoff.archive_path(root).read_bytes()

    rc = mw_cli._ap_family_run(
        ge._family_args("contract-refreeze", owner, book_path), root, client=client
    )
    assert rc == 0, capsys.readouterr().err
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "applied", result
    freeze_after = contract_guard.read_freeze(key_dir)
    assert freeze_after is not None and freeze_before is not None
    assert freeze_after["spec"]["AC-001"] != freeze_before["spec"]["AC-001"]
    # The old bytes stay as history; the old finalize is no longer current.
    assert decide_signoff.signoff_path(root, owner).read_bytes() == signoff_before
    assert decide_signoff.archive_path(root).read_bytes() == archive_before
    validation = signoff_result.validate_signoff(key_dir, owner)
    assert validation.valid is False
    assert "AC-001" in validation.reason
    assert signoff_result.validate_key_signoff(
        key_dir, owner, material, material["verification_evidence"]
    ).signs_key is False


# ---------------------------------------------------------------------------
# AC-039 / AC-052 (H06 adopted goal): the actually adopted goal version
# baseline is part of the native identity of a current finalize.
# ---------------------------------------------------------------------------


def _family_signoff(root: pathlib.Path, owner: str, *, logical_id: str):
    """Write a real finalize for the family fixture key (production writers)."""
    key_dir = root / ".agenticdoc" / owner
    material = _material()
    facts = _facts(root, key=owner)
    record = signoff_result.build_result(
        key_dir,
        key=owner,
        logical_id=logical_id,
        decision_id=f"{signoff_result.DP_ID}:{logical_id}",
        conclusion="finalize",
        material=material,
        facts=facts,
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
        task_key="T22-adopted-goal",
        initiator_role="pm",
        snapshot_material=material,
    )
    signoff_result.write_result(key_dir, record, redact=decision.known_secret_redactor())
    text = decide_signoff.render(facts, "finalize", None, owner, "-", result=record)
    decide_signoff.write_signoff(root, owner, text)
    return key_dir, material, record


def _family_goal_setup(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    import test_dp_consolidation_gate_effects as ge

    root, owner, _claim, _state, _target = ge._conductor_h_fixture(tmp_path / "family-goal")
    ge._family_policy(root)
    ge._family_rounds(root, owner, 1)
    payload = ge._family_goal_payload(root)
    book = ge._family_book("goal-adoption", payload, key=owner, logical_id="family-goal")
    book_path = ge._family_book_path(root, book)
    ge._family_deploy_authority(
        monkeypatch, root, ["goal-adopt:owner", "goal-version:goal-v2"]
    )
    return ge, root, owner, payload, book, book_path


def _run_family_goal(ge, root, owner, book_path, book):
    import mw as mw_cli

    client = ge._pm_fake_client(root, book["book"]["preparation"], "approve")
    rc = mw_cli._ap_family_run(
        ge._family_args("goal-adoption", owner, book_path), root, client=client
    )
    return rc


def _family_effect_path(root: pathlib.Path, gate_id: str) -> pathlib.Path:
    import test_dp_consolidation_gate_effects as ge

    gate = ge.conductor.gates.parse(
        ge.conductor.gates_dir(root) / (gate_id + ".md")
    )
    return contract_guard.family_effect_path(root, gate)


def test_real_family_goal_adoption_invalidates_the_old_finalize(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The normal H06 goal-adoption consumer proves the adopted goal version.

    Reuses the real T26 family fixture (live PM claim, protected policy, real
    gate/lifecycle consumer and protected baseline writer); only the model
    transport is the existing faux client. No helper bypasses the actor,
    writer or consumer.
    """
    import test_decide_signoff as tds

    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    ge, root, owner, payload, book, book_path = _family_goal_setup(tmp_path, monkeypatch)
    key_dir, material, _record = _family_signoff(root, owner, logical_id="dpc-t22-goal-1")
    assert signoff_result.validate_signoff(key_dir, owner).valid is True
    goal_doc = root / ".agenticdoc" / "goal.md"
    goal_before = goal_doc.read_bytes()
    sign_before = decide_signoff.signoff_path(root, owner).read_bytes()
    archive_before = decide_signoff.archive_path(root).read_bytes()

    rc = _run_family_goal(ge, root, owner, book_path, book)
    assert rc == 0, capsys.readouterr().err
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "applied", result
    baseline = pathlib.Path(payload["baseline_path"])
    assert json.loads(baseline.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"
    # The project goal document is unchanged; only the adopted baseline moved.
    assert goal_doc.read_bytes() == goal_before
    assert decide_signoff.signoff_path(root, owner).read_bytes() == sign_before
    assert decide_signoff.archive_path(root).read_bytes() == archive_before

    validation = signoff_result.validate_signoff(key_dir, owner)
    assert validation.valid is False
    assert "adopted goal" in validation.reason
    assert "goal-v2" in validation.reason
    assert signoff_result.validate_key_signoff(
        key_dir, owner, material, material["verification_evidence"]
    ).signs_key is False

    # The framework done gate consumes the same read-only validator.
    ap = tds._load_advance_phase()
    problems = ap._decision_signoff_problems(key_dir)
    assert problems and any("adopted goal" in p for p in problems), problems


def test_current_adopted_goal_can_be_signed_after_the_change(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import test_dp_consolidation_gate_effects as ge

    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    _ge, root, owner, _payload, book, book_path = _family_goal_setup(tmp_path, monkeypatch)
    rc = _run_family_goal(_ge, root, owner, book_path, book)
    assert rc == 0, capsys.readouterr().err
    assert json.loads(capsys.readouterr().out)["status"] == "applied"

    key_dir, material, record = _family_signoff(root, owner, logical_id="dpc-t22-goal-current")
    validation = signoff_result.validate_signoff(key_dir, owner)
    assert validation.valid is True, validation.reason
    assert validation.native_basis_verified is True
    assert record.native_basis is not None
    adopted = record.native_basis["adopted_goal"]
    assert adopted["state"] == "present"
    assert adopted["version"] == "goal-v2"
    assert signoff_result.validate_key_signoff(
        key_dir, owner, material, material["verification_evidence"]
    ).signs_key is True


def test_adoption_formatting_and_other_key_do_not_force_reapproval(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import test_dp_consolidation_gate_effects as ge

    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    _ge, root, owner, payload, book, book_path = _family_goal_setup(tmp_path, monkeypatch)
    rc = _run_family_goal(_ge, root, owner, book_path, book)
    assert rc == 0, capsys.readouterr().err
    assert json.loads(capsys.readouterr().out)["status"] == "applied"

    key_dir, material, _record = _family_signoff(root, owner, logical_id="dpc-t22-goal-format")
    assert signoff_result.validate_signoff(key_dir, owner).valid is True
    # Same semantic goal version, different JSON formatting/key order and an
    # unrelated evidence file: no new substantive approval is required.
    baseline = pathlib.Path(payload["baseline_path"])
    data = json.loads(baseline.read_text(encoding="utf-8"))
    baseline.write_text(
        json.dumps({"note": "reformatted", **data}, indent=4, ensure_ascii=False) + "\r\n",
        encoding="utf-8",
        newline="",
    )
    (key_dir / "evidence" / "review" / "unrelated.txt").write_text(
        "not part of the adopted goal\n", encoding="utf-8", newline="\n"
    )
    assert signoff_result.validate_signoff(key_dir, owner).valid is True
    assert signoff_result.validate_key_signoff(
        key_dir, owner, material, material["verification_evidence"]
    ).signs_key is True

    # A different key signed while this key has an adopted baseline is not
    # affected by that other key's adopted goal.
    other_dir = root / ".agenticdoc" / OTHER_KEY
    other_dir.mkdir(parents=True, exist_ok=True)
    other_material = _material()
    other_facts = _facts(root, key=OTHER_KEY, trigger="t22-other")
    other_record = signoff_result.build_result(
        other_dir,
        key=OTHER_KEY,
        logical_id="dpc-t22-goal-other",
        decision_id=f"{signoff_result.DP_ID}:dpc-t22-goal-other",
        conclusion="finalize",
        material=other_material,
        facts=other_facts,
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
        task_key="T22-adopted-goal",
        initiator_role="pm",
        snapshot_material=other_material,
    )
    signoff_result.write_result(
        other_dir, other_record, redact=decision.known_secret_redactor()
    )
    other_text = decide_signoff.render(
        other_facts, "finalize", None, OTHER_KEY, "-", result=other_record
    )
    decide_signoff.write_signoff(root, OTHER_KEY, other_text)
    other_validation = signoff_result.validate_signoff(other_dir, OTHER_KEY)
    assert other_validation.valid is True, other_validation.reason
    assert other_record.native_basis["adopted_goal"]["state"] == "absent"


@pytest.mark.parametrize(
    "damage",
    [
        "baseline_missing",
        "baseline_corrupt",
        "effect_missing",
        "effect_outside",
        "effect_unknown",
        "receipt_missing",
        "receipt_other_key",
        "object_tamper",
        "record_adopted_tamper",
    ],
)
def test_adopted_goal_binding_loss_damage_and_escape_are_not_current(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    damage: str,
) -> None:
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    _ge, root, owner, payload, book, book_path = _family_goal_setup(tmp_path, monkeypatch)
    rc = _run_family_goal(_ge, root, owner, book_path, book)
    assert rc == 0, capsys.readouterr().err
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "applied"
    key_dir, _material_, _record = _family_signoff(
        root, owner, logical_id="dpc-t22-goal-damage"
    )
    assert signoff_result.validate_signoff(key_dir, owner).valid is True
    baseline = pathlib.Path(payload["baseline_path"])
    effect = _family_effect_path(root, result["gate_id"])

    if damage == "baseline_missing":
        baseline.unlink()
    elif damage == "baseline_corrupt":
        baseline.write_bytes(b"\xff\xfe not utf-8\n")
    elif damage == "effect_missing":
        effect.unlink()
    elif damage == "effect_outside":
        raw = json.loads(effect.read_text(encoding="utf-8"))
        raw["target"] = str(tmp_path / "outside-goal.json")
        (tmp_path / "outside-goal.json").write_text(
            json.dumps({"goal_version": "goal-v2"}), encoding="utf-8"
        )
        effect.write_text(json.dumps(raw), encoding="utf-8", newline="\n")
    elif damage == "effect_unknown":
        raw = json.loads(effect.read_text(encoding="utf-8"))
        raw["status"] = "unknown"
        effect.write_text(json.dumps(raw), encoding="utf-8", newline="\n")
    elif damage == "receipt_missing":
        raw = json.loads(effect.read_text(encoding="utf-8"))
        raw.pop("receipt", None)
        effect.write_text(json.dumps(raw), encoding="utf-8", newline="\n")
    elif damage == "receipt_other_key":
        raw = json.loads(effect.read_text(encoding="utf-8"))
        raw["receipt"]["key"] = "someone-else"
        effect.write_text(json.dumps(raw), encoding="utf-8", newline="\n")
    elif damage == "object_tamper":
        baseline.write_text(
            json.dumps({"goal_version": "goal-v3"}), encoding="utf-8", newline="\n"
        )
    else:
        path = signoff_result.result_path(key_dir, "dpc-t22-goal-damage")
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["native_basis"]["adopted_goal"]["version"] = "goal-v9"
        path.write_text(json.dumps(raw), encoding="utf-8", newline="\n")

    validation = signoff_result.validate_signoff(key_dir, owner)
    assert validation.valid is False
    if damage == "record_adopted_tamper":
        assert "record" in validation.reason or "basis" in validation.reason
    else:
        assert "adopted goal" in validation.reason, validation.reason


def test_goal_adoption_during_the_model_request_is_not_signed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A goal version adopted while the model is answering is not bound."""
    import mw as mw_cli
    import test_decide_signoff as tds

    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    _ge, root, owner, _payload, book, book_path = _family_goal_setup(tmp_path, monkeypatch)
    (root / ".mw").mkdir(parents=True, exist_ok=True)
    (root / ".mw" / "decide.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8", newline="\n"
    )
    import test_dp_consolidation_cli as cli_fixtures

    family_client = _ge._pm_fake_client(root, book["book"]["preparation"], "approve")
    nested: list[int] = []

    def adopt_during(state, questions, cfg):
        business_id = cli_fixtures._business_question_id("dp-sign-key")
        assert set(questions) == {business_id, "basis_id"}
        assert state["preparation"] == envelope["preparation"]
        nested.append(
            mw_cli._ap_family_run(
                _ge._family_args("goal-adoption", owner, book_path),
                root,
                client=family_client,
            )
        )
        return decision.BackendOutcome(
            available=True,
            reason=None,
            retryable=False,
            answers={
                business_id: {"value": "finalize", "confidence": 0.9},
                "basis_id": {"value": "b-primary", "confidence": 0.9},
            },
            latency_ms=5,
            detail="",
        )

    backend = decision.FakeBackend(
        [adopt_during],
        name="timi-decisions",
        model="jev-latest",
        confidence_source=decision.CONFIDENCE_SOURCE_API,
    )
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)
    _facts(root, key=owner)
    envelope = {
        "material": _material(),
        "preparation": cli_fixtures._preparation("dp-sign-key", _material()),
        "meta": {
            "record_version": 2,
            "logical_id": "dpc-t22-goal-midcall",
            "key": owner,
            "task_key": "T22-adopted-goal",
            "initiator_role": "pm",
            "retry_of": None,
        },
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(envelope)))
    args = tds._sign_args(
        root,
        key=owner,
        key_pos=owner,
        stdin=True,
        request_file=None,
        retry_write=None,
        validate=None,
        json=True,
    )
    rc = mw_cli.cmd_decide(args)
    output = capsys.readouterr()
    assert nested == [0], output.err
    assert rc == 2
    assert "adopted goal" in (output.err + output.out)
    assert backend.calls, "the model really was called once"
    key_dir = root / ".agenticdoc" / owner
    assert not decide_signoff.signoff_path(root, owner).exists()
    assert not signoff_result.result_path(key_dir, "dpc-t22-goal-midcall").exists()
    assert json.loads(
        pathlib.Path(_payload["baseline_path"]).read_text(encoding="utf-8")
    )["goal_version"] == "goal-v2"


# ---------------------------------------------------------------------------
# The adopted-goal locator is itself cross-proven by the real family chain.
#
# Only the canonical effect file identity, the goal-change gate it was prepared
# for, its completion receipt and the executed/settled T10 rows may prove what a
# key adopted. A caller-supplied or tampered locator is never a permission, and
# the target bytes are read only after that proof holds.
# ---------------------------------------------------------------------------


class _TargetReadSpy:
    """Record every read of one of the given files; the real readers stay real."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, targets: list[pathlib.Path]
    ) -> None:
        self.targets = {
            os.path.normcase(os.path.abspath(str(item))) for item in targets
        }
        self.hits: list[str] = []
        for name in ("read_bytes", "read_text", "open"):
            monkeypatch.setattr(
                pathlib.Path, name, self._wrap(getattr(pathlib.Path, name))
            )

    def _wrap(self, original):
        def wrapper(path_self, *args, **kwargs):
            key = os.path.normcase(os.path.abspath(str(path_self)))
            if key in self.targets:
                self.hits.append(str(path_self))
            return original(path_self, *args, **kwargs)

        return wrapper


def _family_goal_applied(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> tuple[pathlib.Path, str, dict, dict, pathlib.Path]:
    """Run the real family goal-adoption chain once and return its artefacts."""

    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    _ge, root, owner, payload, book, book_path = _family_goal_setup(tmp_path, monkeypatch)
    rc = _run_family_goal(_ge, root, owner, book_path, book)
    assert rc == 0, capsys.readouterr().err
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "applied", result
    effect = _family_effect_path(root, result["gate_id"])
    assert effect.is_file(), effect
    return root, owner, payload, result, effect


def _rewrite_effect(effect: pathlib.Path, mutate) -> None:
    raw = json.loads(effect.read_text(encoding="utf-8"))
    mutate(raw)
    effect.write_text(json.dumps(raw), encoding="utf-8", newline="\n")


def _drop_or_change_lifecycle(
    root: pathlib.Path, stage: str, *, ref: str | None
) -> None:
    sink = wire.production_lifecycle_sink(root)
    rows = [
        json.loads(line)
        for line in sink.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kept: list[dict] = []
    for row in rows:
        if row.get("kind") == "lifecycle" and row.get("lifecycle") == stage:
            if ref is None:
                continue
            row = dict(row, decision_id=ref)
        kept.append(row)
    sink.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in kept)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


_RED_LOCATOR_DAMAGE = (
    "target_only_other_key",
    "target_and_receipt_unpermitted",
    "object_receipt_mismatch",
    "executed_missing",
    "executed_wrong_ref",
    "settled_missing",
    "effect_renamed",
    "gate_id_traversal",
)

_LOCATOR_REASON_KEYWORD = {
    "target_only_other_key": "does not match its completion receipt",
    "target_and_receipt_unpermitted": (
        "not the one the goal-change gate authorized"
    ),
    "object_receipt_mismatch": "object receipt does not match its completion receipt",
    "executed_missing": "no executed lifecycle receipt",
    "executed_wrong_ref": "no executed lifecycle receipt",
    "settled_missing": "no settled lifecycle receipt",
    "effect_renamed": "not stored at its gate-derived path",
    "gate_id_traversal": "not a canonical gate id",
}


@pytest.mark.parametrize("damage", _RED_LOCATOR_DAMAGE)
def test_adopted_goal_locator_is_cross_proven_before_any_target_read(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys, damage: str
) -> None:
    """A damaged locator is unproven and is never allowed to become new proof."""

    root, owner, payload, result, effect = _family_goal_applied(
        tmp_path, monkeypatch, capsys
    )
    key_dir = root / ".agenticdoc" / owner
    granted = pathlib.Path(payload["baseline_path"])
    other_target = root / ".agenticdoc" / OTHER_KEY / "private-goal.json"
    other_target.parent.mkdir(parents=True, exist_ok=True)
    other_target.write_text(
        json.dumps({"goal_version": "goal-v2", "secret": "fixture-only-secret"}),
        encoding="utf-8",
        newline="\n",
    )
    unpermitted = root / "unadopted-goal.json"
    unpermitted.write_text(
        json.dumps({"goal_version": "goal-v2"}), encoding="utf-8", newline="\n"
    )
    gate_file = (
        root / ".agenticdoc" / "_autopilot" / "gates" / (result["gate_id"] + ".md")
    )
    traversal = effect.with_name("traversal-gate.md")
    unauthorised = [other_target, unpermitted, traversal]

    if damage == "target_only_other_key":
        _rewrite_effect(effect, lambda raw: raw.update(target=str(other_target)))
    elif damage == "target_and_receipt_unpermitted":
        def _both(raw: dict) -> None:
            raw["target"] = str(unpermitted)
            raw["receipt"]["target"] = str(unpermitted)

        _rewrite_effect(effect, _both)
    elif damage == "object_receipt_mismatch":
        _rewrite_effect(
            effect, lambda raw: raw["receipt"].update(object_sha256="0" * 64)
        )
    elif damage == "executed_missing":
        _drop_or_change_lifecycle(root, "executed", ref=None)
    elif damage == "executed_wrong_ref":
        _drop_or_change_lifecycle(root, "executed", ref="dp-gate-approve:someone-else")
    elif damage == "settled_missing":
        _drop_or_change_lifecycle(root, "settled", ref=None)
    elif damage == "effect_renamed":
        effect.rename(effect.with_name("goal-change-" + "b" * 32 + ".json"))
    else:
        traversal.write_text(
            gate_file.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
        )
        _rewrite_effect(
            effect, lambda raw: raw.update(gate_id="../family-effects/traversal-gate")
        )

    spy = _TargetReadSpy(monkeypatch, unauthorised)
    binding = contract_guard.adopted_goal_binding(root, owner)
    assert binding.state == "unproven", binding
    assert binding.version is None and binding.target is None, binding
    keyword = _LOCATOR_REASON_KEYWORD[damage]
    assert keyword in binding.reason, binding.reason

    basis = signoff_result.capture_native_basis(key_dir)
    assert basis.adopted_goal_state == "unproven", basis
    problems = signoff_result.basis_usable_now(basis)
    assert problems and any("adopted goal" in problem for problem in problems), problems
    with pytest.raises(signoff_result.SignoffResultError) as refused:
        _family_signoff(root, owner, logical_id="dpc-t22-goal-locator")
    assert "adopted goal" in str(refused.value)
    assert not decide_signoff.signoff_path(root, owner).exists()
    assert spy.hits == [], spy.hits
    assert json.loads(granted.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"
    # The spy really observes reads, so the zero hits above is meaningful.
    other_target.read_bytes()
    assert spy.hits, "the target read spy is functional"


# ---------------------------------------------------------------------------
# The adopted-goal T10 chain must be one family round of the same key, task,
# logical decision, executor and successful settlement.
#
# The four originally proven gaps (a missing ``consumed`` receipt, an executed/
# settled row of another key, and a rollback settlement) are the first cases;
# the rest keep the same join strict for the neighbouring mutations. Every
# negative damages only the isolated fixture's own ledger after the real
# producer/writer/consumer ran; no gate, receipt or permission is hand-written.
# ---------------------------------------------------------------------------

_GOAL_CHAIN_DAMAGE = (
    "consumed_missing",
    "consumed_other_key",
    "executed_wrong_key",
    "executed_wrong_task",
    "executed_wrong_logical",
    "executed_wrong_executor",
    "executed_wrong_writer_action",
    "executed_object_member_renamed",
    "executed_duplicate",
    "settled_missing",
    "settled_wrong_key",
    "settled_rollback",
    "settled_rework",
    "settled_inconclusive",
    "settled_duplicate_conflict",
    "order_inverted",
)

_GOAL_CHAIN_REASON = {
    "consumed_missing": "no consumed lifecycle receipt",
    "consumed_other_key": "belongs to a different key/task/logical decision",
    "executed_wrong_key": "belongs to a different key/task/logical decision",
    "executed_wrong_task": "belongs to a different key/task/logical decision",
    "executed_wrong_logical": "belongs to a different key/task/logical decision",
    "executed_wrong_executor": "recorded by a different executor",
    "executed_wrong_writer_action": "not the original writer action",
    "executed_object_member_renamed": "does not carry this object receipt",
    "executed_duplicate": "more than one executed lifecycle receipt",
    "settled_missing": "no settled lifecycle receipt",
    "settled_wrong_key": "belongs to a different key/task/logical decision",
    "settled_rollback": "not a successful outcome",
    "settled_rework": "not a successful outcome",
    "settled_inconclusive": "not a successful outcome",
    "settled_duplicate_conflict": "more than one settled lifecycle receipt",
    "order_inverted": "not in recording order",
}


def _lifecycle_rows(root: pathlib.Path) -> list[dict]:
    sink = wire.production_lifecycle_sink(root)
    return [
        json.loads(line)
        for line in sink.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_lifecycle_rows(root: pathlib.Path, rows: list[dict]) -> None:
    sink = wire.production_lifecycle_sink(root)
    sink.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _mutate_lifecycle(
    root: pathlib.Path, stage: str, mutate
) -> None:
    rows = _lifecycle_rows(root)
    targets = [
        row
        for row in rows
        if row.get("kind") == "lifecycle" and row.get("lifecycle") == stage
    ]
    assert len(targets) == 1, (stage, len(targets))
    mutate(targets[0])
    _write_lifecycle_rows(root, rows)


def _duplicate_lifecycle(root: pathlib.Path, stage: str, **changes: object) -> None:
    rows = _lifecycle_rows(root)
    target = next(
        row
        for row in rows
        if row.get("kind") == "lifecycle" and row.get("lifecycle") == stage
    )
    duplicate = dict(target, **changes)
    duplicate.setdefault("event_id", "dup-" + stage)
    rows.append(duplicate)
    _write_lifecycle_rows(root, rows)


def _family_goal_chain(root: pathlib.Path) -> dict[str, dict]:
    return {
        row["lifecycle"]: row
        for row in _lifecycle_rows(root)
        if row.get("kind") == "lifecycle"
        and row.get("lifecycle") in ("consumed", "executed", "settled")
    }


@pytest.mark.parametrize("damage", _GOAL_CHAIN_DAMAGE)
def test_adopted_goal_chain_is_unproven_before_any_target_read(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys, damage: str
) -> None:
    """A damaged T10 chain is unproven and can never become a current proof."""

    root, owner, payload, _result, _effect = _family_goal_applied(
        tmp_path, monkeypatch, capsys
    )
    key_dir = root / ".agenticdoc" / owner
    granted = pathlib.Path(payload["baseline_path"])
    other_target = root / ".agenticdoc" / OTHER_KEY / "private-goal.json"
    other_target.parent.mkdir(parents=True, exist_ok=True)
    other_target.write_text(
        json.dumps({"goal_version": "goal-v2"}), encoding="utf-8", newline="\n"
    )
    unpermitted = root / "unadopted-goal.json"
    unpermitted.write_text(
        json.dumps({"goal_version": "goal-v2"}), encoding="utf-8", newline="\n"
    )

    if damage == "consumed_missing":
        rows = [
            row
            for row in _lifecycle_rows(root)
            if not (row.get("kind") == "lifecycle" and row.get("lifecycle") == "consumed")
        ]
        _write_lifecycle_rows(root, rows)
    elif damage == "consumed_other_key":
        _mutate_lifecycle(root, "consumed", lambda row: row.update(key=OTHER_KEY))
    elif damage == "executed_wrong_key":
        _mutate_lifecycle(root, "executed", lambda row: row.update(key=OTHER_KEY))
    elif damage == "executed_wrong_task":
        _mutate_lifecycle(root, "executed", lambda row: row.update(task_key="T26-other"))
    elif damage == "executed_wrong_logical":
        _mutate_lifecycle(
            root, "executed", lambda row: row.update(logical_id="family-other")
        )
    elif damage == "executed_wrong_executor":
        _mutate_lifecycle(
            root,
            "executed",
            lambda row: row.update(actor={"kind": "system", "id": "other-host:1"}),
        )
    elif damage == "executed_wrong_writer_action":
        _mutate_lifecycle(
            root,
            "executed",
            lambda row: row.update(action="type-read", reason="type-read"),
        )
    elif damage == "executed_object_member_renamed":
        _mutate_lifecycle(
            root,
            "executed",
            lambda row: row.update(
                result=str(row.get("result")).replace(
                    '"object_sha256"', '"object-digest"'
                )
            ),
        )
    elif damage == "executed_duplicate":
        _duplicate_lifecycle(root, "executed", event_id="dup-executed")
    elif damage == "settled_missing":
        rows = [
            row
            for row in _lifecycle_rows(root)
            if not (row.get("kind") == "lifecycle" and row.get("lifecycle") == "settled")
        ]
        _write_lifecycle_rows(root, rows)
    elif damage == "settled_wrong_key":
        _mutate_lifecycle(root, "settled", lambda row: row.update(key=OTHER_KEY))
    elif damage == "settled_rollback":
        _mutate_lifecycle(
            root,
            "settled",
            lambda row: row.update(outcome="rollback", result="rollback"),
        )
    elif damage == "settled_rework":
        _mutate_lifecycle(
            root, "settled", lambda row: row.update(outcome="rework", result="rework")
        )
    elif damage == "settled_inconclusive":
        _mutate_lifecycle(
            root,
            "settled",
            lambda row: row.update(outcome="inconclusive", result="inconclusive"),
        )
    elif damage == "settled_duplicate_conflict":
        _duplicate_lifecycle(
            root,
            "settled",
            event_id="dup-settled",
            outcome="rollback",
            result="rollback",
        )
    else:
        chain = _family_goal_chain(root)
        later = (
            datetime.datetime.fromisoformat(chain["settled"]["ts"])
            + datetime.timedelta(seconds=30)
        ).isoformat()
        _mutate_lifecycle(root, "executed", lambda row: row.update(ts=later))

    spy = _TargetReadSpy(monkeypatch, [granted, other_target, unpermitted])
    binding = contract_guard.adopted_goal_binding(root, owner)
    assert binding.state == "unproven", binding
    assert binding.version is None and binding.target is None, binding
    assert _GOAL_CHAIN_REASON[damage] in binding.reason, binding.reason

    basis = signoff_result.capture_native_basis(key_dir)
    assert basis.adopted_goal_state == "unproven", basis
    problems = signoff_result.basis_usable_now(basis)
    assert problems and any("adopted goal" in problem for problem in problems), problems
    with pytest.raises(signoff_result.SignoffResultError) as refused:
        _family_signoff(root, owner, logical_id="dpc-t22-goal-chain")
    assert "adopted goal" in str(refused.value)
    assert not decide_signoff.signoff_path(root, owner).exists()
    # The damaged target is never read, and the real object stays untouched.
    assert spy.hits == [], spy.hits
    assert json.loads(granted.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"
    other_target.read_bytes()
    assert spy.hits, "the target read spy is functional"


def test_real_adopted_goal_chain_joins_one_family_round(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The normal chain is present, joins every field and survives re-formatting."""

    root, owner, _payload, _result, _effect = _family_goal_applied(
        tmp_path, monkeypatch, capsys
    )
    key_dir = root / ".agenticdoc" / owner
    chain = _family_goal_chain(root)
    assert set(chain) == {"consumed", "executed", "settled"}
    assert [chain[stage]["ts"] for stage in ("consumed", "executed", "settled")] == sorted(
        chain[stage]["ts"] for stage in ("consumed", "executed", "settled")
    )
    assert {row["key"] for row in chain.values()} == {owner}
    assert {row["task_key"] for row in chain.values()} == {"T26-family"}
    assert {row["logical_id"] for row in chain.values()} == {"family-goal"}
    assert len({(row["actor"] or {}).get("id") for row in chain.values()}) == 1
    assert chain["executed"]["action"] == "direct-exec"
    assert chain["executed"]["reason"] == "goal-adoption"
    assert "\"object_sha256\": \"" in chain["executed"]["result"]
    assert chain["settled"]["outcome"] == "ok"

    binding = contract_guard.adopted_goal_binding(root, owner)
    assert binding.state == "present", binding
    assert binding.version == "goal-v2"

    # Pure ledger re-serialization (separator/key-order only) moves no fact.
    rows = _lifecycle_rows(root)
    sink = wire.production_lifecycle_sink(root)
    sink.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, separators=(" ,", " : ")) for row in rows
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    reformatted = contract_guard.adopted_goal_binding(root, owner)
    assert reformatted.state == "present", reformatted
    assert reformatted.target == binding.target
    assert reformatted.sha256 == binding.sha256

    # The same round makes a current finalize valid; another key stays absent.
    _family_signoff(root, owner, logical_id="dpc-t22-goal-chain-current")
    validation = signoff_result.validate_signoff(key_dir, owner)
    assert validation.valid is True, validation.reason
    assert contract_guard.adopted_goal_binding(root, OTHER_KEY).state == "absent"


def test_adopted_goal_chain_loss_invalidates_the_current_finalize(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The same chain is what keeps an already signed finalize current."""

    import test_decide_signoff as tds

    root, owner, _payload, _result, _effect = _family_goal_applied(
        tmp_path, monkeypatch, capsys
    )
    key_dir, material, _record = _family_signoff(
        root, owner, logical_id="dpc-t22-goal-chain-signed"
    )
    assert signoff_result.validate_signoff(key_dir, owner).valid is True

    _mutate_lifecycle(root, "executed", lambda row: row.update(key=OTHER_KEY))

    validation = signoff_result.validate_signoff(key_dir, owner)
    assert validation.valid is False
    assert "adopted goal" in validation.reason
    assert signoff_result.validate_key_signoff(
        key_dir, owner, material, material["verification_evidence"]
    ).signs_key is False
    framework = tds._load_advance_phase()
    problems = framework._decision_signoff_problems(key_dir)
    assert problems and any("adopted goal" in problem for problem in problems), problems

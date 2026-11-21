"""Field-reference hints stay distinct from evidence locations; no real service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import decision_book as book
import decision_points as dpts
from scripts.build_decide_cases import render_template


@pytest.mark.parametrize("dp_id", [point.id for point in dpts.DP_REGISTRY])
def test_scaffold_explains_field_references_and_stays_unready(dp_id: str) -> None:
    scaffold = book.scaffold_book(dp_id)
    basis = scaffold["preparation"]["basis_catalog"][0]
    hint = basis["material_refs"][0]
    assert hint != basis["text"]
    assert "字段路径" in hint
    assert "material." in hint
    assert "path:line" in hint
    assert book.is_placeholder(hint)
    assert book.check_book(scaffold)
    assert basis["text"] == book.BASIS_PLACEHOLDER
    for evidence in scaffold["notes"]["evidence"].values():
        assert evidence == book.EVIDENCE_PLACEHOLDER


def test_shipped_template_is_the_current_generator_output() -> None:
    template = Path(__file__).with_name("decide_book_template.json")
    assert template.read_text(encoding="utf-8") == render_template()
    assert set(json.loads(template.read_text(encoding="utf-8"))["books"]) == {point.id for point in dpts.DP_REGISTRY}


@pytest.mark.parametrize(
    "refs",
    [
        [],
        ["src/check.ts:42"],
        [r"E:\repo\src\check.ts:42"],
        ["material.review_evidence"],
        ["background.current_state"],
        ["review_evidence[0]"],
        [None],
        [42],
        [""],
        ["review_evidence", "src/check.ts:42"],
    ],
)
def test_qg_rejects_invalid_refs_without_changing_the_contract(refs: list[object]) -> None:
    material = {"review_evidence": ["src/check.ts:42"], "review_findings": "Needs repair"}
    catalog = [{"id": "basis", "text": "Review facts", "material_refs": refs, "applies_to": ["fix"]}]
    issues = dpts.basis_catalog_issues("dp-QG", catalog, material)
    assert issues
    assert all("material_refs" in field for field, _ in issues)


def test_even_an_existing_source_file_is_not_a_material_field(tmp_path: Path) -> None:
    source = tmp_path / "check.ts"
    source.write_text("export const check = true;\n", encoding="utf-8")
    location = f"{source}:1"
    material = {"review_evidence": [location]}
    catalog = [{"id": "basis", "text": "Read source", "material_refs": [location], "applies_to": ["fix"]}]
    assert source.is_file()
    assert dpts.basis_catalog_issues("dp-QG", catalog, material) == (
        ("basis_catalog[0].material_refs[0]", "does not reference a fact present in this material"),
    )
    catalog[0]["material_refs"] = ["review_evidence"]
    assert dpts.basis_catalog_issues("dp-QG", catalog, material) == ()
    assert material["review_evidence"] == [location]


@pytest.mark.parametrize("ref", ["background", "background.current_state", "background.constraints"])
def test_nested_refs_and_top_level_containers_still_work(ref: str) -> None:
    material = {
        "background": {"current_state": "src/check.ts:42", "constraints": "Read only"},
        "handling_options": [{"id": "inspect"}, {"id": "report"}],
    }
    catalog = [{"id": "basis", "text": "Inspect facts", "material_refs": [ref], "applies_to": ["inspect"]}]
    assert dpts.basis_catalog_issues("dp-auto", catalog, material) == ()

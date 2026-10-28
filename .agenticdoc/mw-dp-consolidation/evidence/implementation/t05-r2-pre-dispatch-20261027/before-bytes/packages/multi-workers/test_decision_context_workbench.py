"""test_decision_context_workbench.py - T07: offline cases, case route, workbench UI.

Scope of this file (card ``T07-workbench-cases`` plus the T05 eight-case
linkage):

* the eight complete synthetic decision books of the active entries are produced
  *offline* by ``scripts/build_decide_cases.py`` (no model, no credential, no
  network) and ship as ``decide_cases/dp-w-type.json``, ``dp-pm-steer.json``,
  ``dp-w-check-task.json``, ``dp-QG.json``, ``dp-gate-approve.json``,
  ``dp-sign-key.json``, ``dp-auto.json`` and ``dp-route.json`` under the design
  §2 layered schema-3 contract (``material`` + ``preparation`` + local
  ``meta``); the case shell (``title``/``note``) never leaks into the model
  state, and the four pre-consolidation cases stay byte-identical read-only
  history;
* ``GET /api/test/cases`` is a page-role, read-only route over a *fixed* table
  of ids (no caller-chosen path, no directory scan, no traversal, no symlink
  escape), and serving it makes zero model and zero credential calls;
* ``/api/history`` forwards the T06 ``workbench``/``facets`` projection
  verbatim (it is not re-derived here) and never invents a projection for a
  record that has none;
* the shipped dashboard renders a five-column workbench table, a ten-node
  single-decision DAG dialog for ``record_version == 2`` records, a log-only
  dialog for legacy records (no DAG entry, no guessed joins), the four closed
  processing states, the key/DP dropdowns from facets, the offline case
  selector with an offline local check, and preserves the DP
  edit/validate/observe/retry playground with its isolated test records.

The DOM run uses the same self-contained Node shim pattern as
``test_decision_dashboard_assets.py`` (no new dependency, no browser): the
shim parses the *shipped* HTML, runs the *shipped* JS, and is fed JSON that was
captured from a real loopback monitor instance in this test. Real visible
browser / real Jev acceptance stays a separate, unauthorized layer.

Deliberately *not* asserted here (dependency split, reported to the PM):
the retired four cases cannot pass the registry-typed ``check_book`` gate any
more, and the monitor's fixed case table still names them until the monitor
owner migrates its route to the eight entries. The eight-entry case files are
proven below against the production book gate with the in-copy repository root;
the real edit -> loopback HTTP body assertion for the new entries waits for
that route migration.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

import decide_archive
import decision
import decision_book
import decision_history
import decision_lifecycle
import decision_monitor
import decision_playground
import decision_points

import test_decision_monitor as monitor_suite

SECRET = monitor_suite.SECRET
REDACTOR = monitor_suite.REDACTOR
HOST = decision_monitor.HOST

ASSET_DIR = pathlib.Path(decision_monitor.__file__).resolve().parent
REPO_ROOT = ASSET_DIR.parents[1]
GENERATOR_PATH = ASSET_DIR / "scripts" / "build_decide_cases.py"
CASES_DIR = ASSET_DIR / "decide_cases"

#: The eight active entries and the case file the offline generator ships.
CASE_FILES = {
    "dp-w-type": "dp-w-type.json",
    "dp-pm-steer": "dp-pm-steer.json",
    "dp-w-check-task": "dp-w-check-task.json",
    "dp-QG": "dp-QG.json",
    "dp-gate-approve": "dp-gate-approve.json",
    "dp-sign-key": "dp-sign-key.json",
    "dp-auto": "dp-auto.json",
    "dp-route": "dp-route.json",
}

#: The four pre-consolidation cases: byte-locked read-only history. The monitor's
#: fixed case table still names them, so the route/loader/DOM assertions below
#: keep exercising that (unchanged) legacy surface; migrating the route to the
#: eight entries belongs to the monitor owner, not to this card.
LEGACY_CASE_FILES = {
    "dp1-dispatch-type": "dp1.json",
    "dp2-checkpoint-split": "dp2.json",
    "dp3-worker-clarify": "dp3.json",
    "dp25-signoff-conclusion": "dp25.json",
}

#: SHA256 of the four legacy case files: this card never generates or edits them.
LEGACY_CASE_SHA256 = {
    "dp1.json": "3131c02f4830b96994e3bea94efe1be8511fd7936f8c983cf579596218a6c9ff",
    "dp2.json": "a03e1a29540ba9636a0a37bf478598bb530c357fc65d54b5eaaf6326e16342ea",
    "dp3.json": "82ff47e50ab5f24cfd84c793c07e2d15484ea89c24a90c8595306c468f407f2d",
    "dp25.json": "bda25144a8c5cd73978603a3dc4c9b429d8d451485679d99ef46cfcc4c2cc7fd",
}

#: design §2 business fields (the only model-state vocabulary of T07).
DESIGN_STATE_FIELDS = {
    "dp-w-type": (
        "task_goal",
        "task_requirements",
        "task_deliverables",
        "images_required",
    ),
    "dp-pm-steer": (
        "task_goal",
        "task_requirements",
        "task_deliverables",
        "pm_decision_background",
        "worker_execution",
    ),
    "dp-w-check-task": (
        "task_goal",
        "reachability_facts",
        "completed",
        "remaining",
        "blockers",
        "constraints",
    ),
    "dp-QG": (
        "review_requirements",
        "review_evidence",
        "review_findings",
        "uncovered_scope",
    ),
    "dp-gate-approve": (
        "gate_background",
        "current_state",
        "condition_evidence",
        "pm_note",
    ),
    "dp-sign-key": (
        "delivery_goal",
        "actual_completion",
        "verification_evidence",
        "unfinished_impact",
    ),
    "dp-auto": ("question", "background", "handling_options"),
    "dp-route": ("decision_actor", "decision_object", "question"),
}

PLACEHOLDER_MARKERS = (
    "<string",
    "<integer",
    "<number",
    "<boolean",
    "<array",
    "<object",
    "EVIDENCE_PLACEHOLDER",
    "TODO",
    "TBD",
    "FIXME",
    "...",
    "\u2026",
)

#: The registry's own dp-pm-steer question vocabulary, kept verbatim (D003).
DP2_CHOICES = ["narrow", "split", "direct-exec", "escalate"]

#: The T06 projection is the authority for the workbench vocabulary: the UI
#: assertions import it instead of copying literals, so a projection change
#: cannot silently drift away from what the page claims to render.
STATES = decision_history.WORKBENCH_STATES
NODE_IDS = list(decision_history.WORKBENCH_NODE_IDS)
NODE_STATUSES = decision_history.NODE_STATUSES
STATE_LABELS = {
    "processing": "处理中",
    "completed": "处理完成",
    "failed": "失败",
    "legacy": "旧数据无状态",
}


# ---------------------------------------------------------------------------
# Isolation: tmp HOME, synthetic-only environment, no credential material
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_environment(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(home / "pi-agent"))
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "TIMI_API_KEY",
        "TIMI_BASE_URL",
        "MW_DECIDE_API_KEY",
        "MW_DECISION_API_KEY",
        "PI_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "PI_WORKER_TASK",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


# ---------------------------------------------------------------------------
# Offline generator / case files
# ---------------------------------------------------------------------------


def _generator_module():
    """Load the offline generator by path (a missing file fails as an assertion)."""
    assert GENERATOR_PATH.is_file(), f"missing offline case generator {GENERATOR_PATH}"
    spec = importlib.util.spec_from_file_location("build_decide_cases_under_test", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _iter_texts(node, path=""):
    """Every string leaf of a JSON value, with its dotted path."""
    if isinstance(node, str):
        yield path or "<root>", node
    elif isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _iter_texts(value, child)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from _iter_texts(value, f"{path}[{index}]")


def _assert_no_placeholders(value, where: str) -> None:
    for path, text in _iter_texts(value, where):
        assert text.strip(), f"{path} is empty: a complete case has no blank material"
        for marker in PLACEHOLDER_MARKERS:
            assert marker not in text, f"{path} still contains the placeholder marker {marker!r}"


def _lookup_material(material, dotted):
    """Value at a dotted material path, or ``_MISSING`` when it is absent."""
    current = material
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


_MISSING = object()


def _material_anchor(value):
    """First real prose leaf of a material value (candidate ids are keys, not text)."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "id":
                continue
            anchor = _material_anchor(item)
            if anchor:
                return anchor
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            anchor = _material_anchor(item)
            if anchor:
                return anchor
        return ""
    return ""


def _assert_case_materials(dp: str, material: dict) -> None:
    """The design §2 business facts of one entry, checked per entry."""
    for field in DESIGN_STATE_FIELDS[dp]:
        assert field in material, f"{dp}: design §2 field {field!r} is missing"
        value = material[field]
        assert value not in (None, "", [], {}), f"{dp}.{field} must carry real material"
    if dp == "dp-w-type":
        for field in ("task_goal", "task_requirements", "task_deliverables"):
            assert isinstance(material[field], str), f"{dp}.{field} is a verbatim string"
        # ``false`` is a real fact, and it is never an image-capability proof.
        assert material["images_required"] is False
    if dp == "dp-pm-steer":
        background = material["pm_decision_background"]
        assert isinstance(background, str) and len(background) > 40
        # The case keeps the registry questions: it never rewrites them and never
        # introduces a "continue" label (design D003 / §4.3).
        for forbidden in ("questions", "choices", "labels", "instructions", "checkpoint_action"):
            assert forbidden not in material, f"dp-pm-steer material must not redefine {forbidden!r}"
        assert "continue" not in json.dumps(material, ensure_ascii=False)
        worker_execution = material["worker_execution"]
        assert isinstance(worker_execution, str) and worker_execution
        assert "时间预算" in worker_execution
    if dp == "dp-w-check-task":
        investigation = material["investigation"]
        assert set(investigation) == {
            "unknown",
            "evidence_source",
            "budget",
            "stop_condition",
        }
        # fire-and-forget: the worker judgement never waits for a PM reply.
        assert "等待" not in json.dumps(material, ensure_ascii=False)
    if dp == "dp-QG":
        assert isinstance(material["review_evidence"], list) and material["review_evidence"]
        # reopen needs the substantive basis problem; this material carries none,
        # so the case can only exercise pass/fix (the branch gate below proves it).
        assert "basis_issue" not in material
    if dp == "dp-gate-approve":
        note = material["pm_note"]
        assert set(note) == {"subject", "planned_action", "basis"}
        assert set(note["basis"]) == {"goal", "evidence", "budget", "authority"}
        assert isinstance(material["condition_evidence"], list) and material["condition_evidence"]
    if dp == "dp-sign-key":
        evidence = material["verification_evidence"]
        assert isinstance(evidence, dict) and set(evidence) == {"verified", "unverified"}
        assert isinstance(evidence["verified"], list) and evidence["verified"]
        assert isinstance(evidence["unverified"], list) and evidence["unverified"]
        assert isinstance(material["unfinished_impact"], list) and material["unfinished_impact"]
    if dp == "dp-auto":
        background = material["background"]
        assert set(background) == {
            "task_goal",
            "current_state",
            "tried",
            "unknowns",
            "constraints",
        }
        options = material["handling_options"]
        assert isinstance(options, list) and len(options) >= 2, "dp-auto needs >= 2 candidates"
        ids = []
        labels = []
        for option in options:
            assert set(option) == {
                "id",
                "label",
                "description",
                "consequence",
                "risk",
                "conditions",
            }
            assert all(option[name].strip() for name in option)
            ids.append(option["id"])
            labels.append(option["label"])
        assert len(set(ids)) == len(ids), "dp-auto candidate ids must be distinguishable"
        assert len(set(labels)) == len(labels), "dp-auto candidate labels must be distinct"
        assert all(len(label) <= 80 for label in labels)
        # Free ids: the legacy contiguous cN scheme is history, not this contract.
        assert ids != [f"c{index}" for index in range(1, len(ids) + 1)]
        assert all(not re.fullmatch(r"c\d", candidate) for candidate in ids)
    if dp == "dp-route":
        assert set(material) == {"decision_actor", "decision_object", "question"}


def _assert_evidence_points_at_the_material(dp: str, material: dict, book: dict) -> None:
    """Every required material path has a ``path:line`` row inside the copy.

    The recorded line must really carry the material text, so the provenance is
    not a decorative reference: this test re-reads the generator source.
    """
    evidence = book["notes"]["evidence"]
    required = decision_book.required_state_paths(dp)
    optional = decision_book.optional_state_paths(dp)
    assert set(required) <= set(evidence), f"{dp}: required evidence rows are missing"
    assert set(evidence) <= set(required) | set(optional), f"{dp}: stray evidence rows"
    generator_rel = "packages/multi-workers/scripts/build_decide_cases.py"
    lines = GENERATOR_PATH.read_text(encoding="utf-8").splitlines()
    for path, reference in evidence.items():
        assert reference.startswith(generator_rel + ":"), (dp, path, reference)
        line_number = int(reference.rsplit(":", 1)[1])
        assert 1 <= line_number <= len(lines), reference
        anchor = _material_anchor(_lookup_material(material, path))
        assert anchor, f"{dp}.{path} has no text anchor"
        assert anchor[:8] in lines[line_number - 1], (
            f"{dp}.{path} evidence points at a line that does not carry the material"
        )


def test_eight_offline_cases_are_complete_schema3_and_contract_shaped():
    module = _generator_module()
    assert set(CASE_FILES) == set(module.CASE_IDS), "the generator owns exactly eight case ids"
    assert not set(module.CASE_IDS) & set(LEGACY_CASE_FILES), "no legacy id is generated"
    cases = module.build_cases()
    assert set(cases) == set(CASE_FILES)

    for dp, shell in cases.items():
        assert set(shell) == {"case_version", "dp", "title", "note", "book", "questions"}, (
            f"{dp}: the case includes the complete observation questions"
        )
        assert shell["questions"] == decision_points.questions_map(dp)
        _assert_no_placeholders(shell["questions"], dp + ".questions")
        assert shell["case_version"] == 1
        assert shell["dp"] == dp
        assert isinstance(shell["title"], str) and len(shell["title"]) > 8
        assert isinstance(shell["note"], str) and len(shell["note"]) > 20
        _assert_no_placeholders({"title": shell["title"], "note": shell["note"]}, dp)

        book = shell["book"]
        assert set(book) <= set(decision_book.BOOK_TOP_LEVEL_KEYS)
        assert book["schema_version"] == decision_book.BOOK_SCHEMA_VERSION == 3
        assert book["decision_point"] == dp
        assert "state" not in book, "a schema-3 book never carries the legacy state shape"
        material = book["material"]
        preparation = book["preparation"]
        meta = book["meta"]
        assert isinstance(material, dict) and isinstance(preparation, dict)
        _assert_case_materials(dp, material)
        _assert_no_placeholders(material, dp)
        _assert_no_placeholders(preparation, dp + ".preparation")

        # Local identity: exact closed key set and the entry's real initiator role.
        assert set(meta) == set(decision_book.META_KEYS)
        assert all(isinstance(value, str) and value.strip() for value in meta.values())
        assert not decision_points.role_issues(dp, meta["actor_role"]), dp

        # Complete: every string leaf is real prose, not a skeleton value
        # (candidate ids are keys, not material, so they are exempt).
        for path, text in _iter_texts(material, dp):
            if path.endswith(".id"):
                assert text.strip(), f"{path} must carry a candidate id"
                continue
            assert len(text.strip()) >= 8, f"{path} looks like a stub ({text!r})"

        # The title/note shell never enters the book.
        serialised = json.dumps(book, ensure_ascii=False)
        assert shell["title"] not in serialised
        assert shell["note"] not in serialised

        # The existing no-truncation budget gate applies to the send payload.
        payload = {
            "material": decision_points.model_state_for(dp, material),
            "preparation": preparation,
        }
        encoded = decision._encode_state(payload)
        assert len(encoded) <= decision_points.MAX_STATE_BYTES, (
            f"{dp}: send payload is {len(encoded)} bytes, the existing budget is "
            f"{decision_points.MAX_STATE_BYTES}; shorten the material instead of truncating"
        )

        _assert_evidence_points_at_the_material(dp, material, book)
        for field in DESIGN_STATE_FIELDS[dp]:
            assert any(
                path == field or path.startswith(field + ".") for path in book["notes"]["evidence"]
            ) or field in {"images_required"}, (
                f"{dp}: design §2 field {field!r} has no evidence entry"
            )


def test_dp_pm_steer_case_keeps_the_registry_question_vocabulary():
    point = decision_points.get_decision_point("dp-pm-steer")
    questions = point.questions
    assert [question["id"] for question in questions] == ["checkpoint_action"]
    choices = list(questions[0]["choices"])
    assert choices == DP2_CHOICES
    assert "continue" not in choices
    assert set(questions[0]["labels"]) == set(DP2_CHOICES)
    assert "继续" in questions[0]["instructions"]
    # The case material keeps the original goal/requirements instead of narrowing
    # them for the checkpoint decision.
    material = _generator_module().build_case("dp-pm-steer")["book"]["material"]
    assert material["task_goal"].startswith("给 mw decide monitor 增加旧记录只读筛选")
    assert "不改其余入口的既有契约" in material["task_requirements"]


def test_eight_cases_pass_the_offline_registry_typed_check():
    """Offline ``check_book`` (no credential, no model) accepts 8/8 cases.

    The gate runs with the *implementation copy* as its repository root, so the
    ``path:line`` evidence resolves inside the copy and never against the live
    tree. The real HTTP body/edit assertion still needs the monitor route
    migration and remains a separate integration step.
    """
    module = _generator_module()
    failures = {}
    for dp, case in module.build_cases().items():
        issues = decision_book.check_book(case["book"], repo_root=REPO_ROOT)
        if issues:
            failures[dp] = [(issue.code, issue.path, issue.detail) for issue in issues]
    assert failures == {}, failures


def test_case_evidence_is_really_checked_and_resolves_inside_the_copy(tmp_path):
    """The evidence gate is not vacuous: a wrong root really refuses the book."""
    module = _generator_module()
    cases = module.build_cases()
    for dp, case in cases.items():
        evidence = case["book"]["notes"]["evidence"]
        for reference in evidence.values():
            relative, _, line = reference.rpartition(":")
            resolved = (REPO_ROOT / relative).resolve()
            assert resolved.is_file(), reference
            assert REPO_ROOT in resolved.parents
            assert resolved == GENERATOR_PATH.resolve()
            int(line)

    empty_repo = tmp_path / "empty-repo"
    empty_repo.mkdir()
    issues = decision_book.check_book(
        cases["dp-sign-key"]["book"], repo_root=empty_repo
    )
    paths = {issue.path for issue in issues}
    assert "notes.evidence.delivery_goal" in paths, issues
    assert any(issue.code == "book-evidence" for issue in issues)


def test_each_case_prepares_a_real_basis_for_every_supported_choice():
    """Every choice the material supports has exactly one prepared reason (D012A).

    The model selects one of these items in the same call; the catalog is a
    preparation input, so a failure reason, a probability or the PM note can
    never impersonate it.
    """
    module = _generator_module()
    for dp, case in module.build_cases().items():
        book = case["book"]
        material = book["material"]
        preparation = book["preparation"]
        meta = book["meta"]
        assert set(preparation) == {"basis_catalog", "prepared_at"}
        assert preparation["prepared_at"].endswith("+00:00")

        legal = decision_points.resolve_entry_choices(dp, material)
        assert legal, dp
        supported = [
            choice
            for choice in legal
            if not decision_points.entry_choice_issues(dp, choice, material)
        ]
        covered = {
            choice for item in preparation["basis_catalog"] for choice in item["applies_to"]
        }
        assert covered == set(supported), dp
        for item in preparation["basis_catalog"]:
            assert set(item) == {"id", "text", "material_refs", "applies_to"}
            assert item["material_refs"], dp
            for choice in item["applies_to"]:
                issues = decision_points.prepared_request_issues(
                    dp,
                    material,
                    preparation,
                    actor_role=meta["actor_role"],
                    choice=choice,
                    basis_id=item["id"],
                )
                assert issues == (), (dp, choice, issues)


def test_dp_w_type_case_keeps_four_candidates_and_the_image_gate():
    module = _generator_module()
    case = module.build_case("dp-w-type")
    material = case["book"]["material"]
    point = decision_points.get_decision_point("dp-w-type")
    assert list(point.questions[0]["choices"]) == ["coding", "research", "review", "vision"]
    # The case states a real fact ("no image reading"); that is never a proof of
    # image capability, so a vision dispatch stays refused by the hard gate.
    assert material["images_required"] is False
    assert decision_points.vision_dispatch_issues(material, "coding", "proven") == ()
    vision = decision_points.vision_dispatch_issues(material, "vision", "proven")
    assert ("vision", "requires images_required=true on the real dispatch material") in vision


def test_dp_w_check_task_case_keeps_three_branches_and_needs_no_pm_wait():
    module = _generator_module()
    book = module.build_case("dp-w-check-task")["book"]
    material = dict(book["material"])
    point = decision_points.get_decision_point("dp-w-check-task")
    assert list(point.questions[0]["choices"]) == ["continue", "terminate", "investigate"]

    without_plan = dict(material)
    without_plan.pop("investigation")
    issues = decision_points.entry_choice_issues("dp-w-check-task", "investigate", without_plan)
    assert ("investigation.unknown", "required by the investigate branch (bounded evidence plan)") in issues
    for choice in ("continue", "terminate", "investigate"):
        assert decision_points.entry_choice_issues("dp-w-check-task", choice, material) == ()
    # fire-and-forget: no field asks the worker to block on a PM answer.
    assert "等待" not in json.dumps(material, ensure_ascii=False)


def test_dp_sigkey_qg_and_gate_entries_refuse_their_own_missing_branch_material():
    """Branch-conditional material is required, never defaulted (AC-043)."""
    module = _generator_module()
    qg = dict(module.build_case("dp-QG")["book"]["material"])
    reopen = decision_points.entry_choice_issues("dp-QG", "reopen", qg)
    assert ("basis_issue", "required by reopen: name the substantive basis problem") in reopen

    with_issue = dict(qg)
    with_issue["basis_issue"] = "验收要求与设计正文冲突，需要重新确认口径。"
    assert decision_points.entry_choice_issues("dp-QG", "reopen", with_issue) == ()
    pass_with_issue = decision_points.entry_choice_issues("dp-QG", "pass", with_issue)
    assert ("basis_issue", "pass cannot be combined with an unresolved basis problem") in pass_with_issue
    assert decision_points.entry_choice_issues("dp-QG", "pass", qg) == ()

    gate = dict(module.build_case("dp-gate-approve")["book"]["material"])
    no_authority = json.loads(json.dumps(gate, ensure_ascii=False))
    no_authority["pm_note"]["basis"].pop("authority")
    gate_issues = decision_points.entry_material_issues("dp-gate-approve", no_authority)
    assert ("pm_note.basis.authority", "must be a non-empty string") in gate_issues
    # No default gate answer: a missing selection is refused, not approve.
    assert decision_points.entry_choice_issues("dp-gate-approve", None, gate) == (
        ("choice", "missing selection: no default candidate is applied"),
    )


def test_dp_sign_key_case_keeps_the_four_parts_and_three_arrays():
    module = _generator_module()
    book = module.build_case("dp-sign-key")["book"]
    material = dict(book["material"])
    assert set(material) == {
        "delivery_goal",
        "actual_completion",
        "verification_evidence",
        "unfinished_impact",
    }
    for choice in ("finalize", "continue", "user-confirm"):
        assert decision_points.entry_choice_issues("dp-sign-key", choice, material) == ()

    # AC-051: [] is the real "none"; null/missing can never be upgraded to it.
    empty = json.loads(json.dumps(material, ensure_ascii=False))
    empty["verification_evidence"]["verified"] = []
    empty["verification_evidence"]["unverified"] = []
    empty["unfinished_impact"] = []
    assert decision_points.sign_key_material_issues(empty) == ()

    nulled = json.loads(json.dumps(material, ensure_ascii=False))
    nulled["verification_evidence"]["verified"] = None
    paths = {path for path, _detail in decision_points.sign_key_material_issues(nulled)}
    assert "verification_evidence.verified" in paths

    missing = json.loads(json.dumps(material, ensure_ascii=False))
    missing.pop("unfinished_impact")
    paths = {path for path, _detail in decision_points.sign_key_material_issues(missing)}
    assert "unfinished_impact" in paths


def test_dp_auto_case_uses_free_form_pm_candidates_and_invents_nothing():
    module = _generator_module()
    case = module.build_case("dp-auto")
    book = case["book"]
    material = book["material"]
    candidates = material["handling_options"]
    prepared = [candidate["id"] for candidate in candidates]

    # The registry-derived enum *is* the prepared set (no second candidate copy).
    assert decision_points.resolve_entry_choices("dp-auto", material) == tuple(prepared)
    assert "dynamic_choices" not in json.dumps(material, ensure_ascii=False)
    assert case["questions"] == decision_points.questions_map("dp-auto")

    for candidate in prepared:
        issues = decision_points.prepared_request_issues(
            "dp-auto",
            material,
            book["preparation"],
            actor_role=book["meta"]["actor_role"],
            choice=candidate,
            basis_id=next(
                item["id"]
                for item in book["preparation"]["basis_catalog"]
                if candidate in item["applies_to"]
            ),
        )
        assert issues == (), (candidate, issues)

    invented = decision_points.entry_choice_issues("dp-auto", "c1", material)
    assert ("choice", "must be one of the 3 legal ids of dp-auto; invented or retired ids are refused") in invented

    single = json.loads(json.dumps(material, ensure_ascii=False))
    single["handling_options"] = single["handling_options"][:1]
    assert decision_points.entry_choice_issues("dp-auto", prepared[0], single)


def test_dp_route_case_routes_to_the_other_seven_entries_without_authorising():
    module = _generator_module()
    book = module.build_case("dp-route")["book"]
    material = book["material"]
    point = decision_points.get_decision_point("dp-route")
    targets = list(point.questions[0]["choices"])
    assert targets == [
        "dp-w-type",
        "dp-pm-steer",
        "dp-w-check-task",
        "dp-QG",
        "dp-gate-approve",
        "dp-sign-key",
        "dp-auto",
    ]
    assert "dp-route" not in targets
    assert decision_points.resolve_entry_choices("dp-route", material) == tuple(targets)

    for target in targets:
        basis = next(
            item["id"] for item in book["preparation"]["basis_catalog"] if target in item["applies_to"]
        )
        issues = decision_points.prepared_request_issues(
            "dp-route",
            material,
            book["preparation"],
            actor_role=book["meta"]["actor_role"],
            choice=target,
            basis_id=basis,
        )
        assert issues == (), (target, issues)

    # Routing to itself is refused, and the material is only the routing fact:
    # it carries no business conclusion, no release and no action field.
    assert decision_points.entry_choice_issues("dp-route", "dp-route", material) == (
        ("choice", "must be one of the 7 legal ids of dp-route; invented or retired ids are refused"),
        ("choice", "dp-route may not route to itself"),
    )
    assert set(material) == {"decision_actor", "decision_object", "question"}


def test_generator_refuses_retired_ids_and_never_writes_legacy_cases(tmp_path, monkeypatch):
    module = _generator_module()
    assert set(module.LEGACY_CASE_IDS) == set(LEGACY_CASE_FILES)
    assert "dp1.json" not in set(module.CASE_IDS.values())
    for legacy_dp in LEGACY_CASE_FILES:
        with pytest.raises(SystemExit):
            module.build_case(legacy_dp)

    out = tmp_path / "cases"
    monkeypatch.setitem(module.CASE_IDS, "dp1-dispatch-type", "dp1.json")
    with pytest.raises(SystemExit) as excinfo:
        module.build_case("dp1-dispatch-type")
    assert "retired" in str(excinfo.value)
    with pytest.raises(SystemExit):
        module.write_cases(out)
    assert not (out / "dp1.json").exists(), "a legacy case file is never written"


def test_shipped_cases_match_the_offline_generator(tmp_path):
    module = _generator_module()
    out = tmp_path / "cases"
    written = module.write_cases(out)
    assert sorted(path.name for path in written) == sorted(CASE_FILES.values())
    assert not set(path.name for path in out.glob("*.json")) & set(LEGACY_CASE_FILES.values())
    for dp, name in CASE_FILES.items():
        shipped = CASES_DIR / name
        assert shipped.is_file(), f"missing shipped case {shipped}"
        generated = (out / name).read_text(encoding="utf-8")
        assert shipped.read_text(encoding="utf-8") == generated, (
            f"{name} drifted from the offline generator; regenerate with "
            "'python scripts/build_decide_cases.py' (offline, no model, no credential)"
        )
        assert json.loads(shipped.read_text(encoding="utf-8"))["dp"] == dp


def test_each_entry_refuses_missing_material_without_defaulting():
    """All eight entries block on missing/wrong material and on a wrong basis.

    The case layer proves the failure side of AC-043 without a live service:
    a missing required fact, a wrong type and a basis that does not apply are
    each refused, and a missing selection is never defaulted to the first
    candidate or to approve.
    """
    module = _generator_module()
    for dp in CASE_FILES:
        case = module.build_case(dp)
        material = json.loads(json.dumps(case["book"]["material"], ensure_ascii=False))
        required = decision_book.required_state_paths(dp)
        first = required[0]
        parts = first.split(".")
        holder = material
        for part in parts[:-1]:
            holder = holder[part]
        holder.pop(parts[-1])
        issues = decision_points.entry_material_issues(dp, material)
        assert (first, "missing or blank (input-incomplete)") in issues, (dp, issues)
        assert decision_points.entry_choice_issues(dp, None, material) == (
            ("choice", "missing selection: no default candidate is applied"),
        ), dp

        wrong_type = json.loads(json.dumps(case["book"]["material"], ensure_ascii=False))
        holder = wrong_type
        for part in parts[:-1]:
            holder = holder[part]
        holder[parts[-1]] = 5
        type_issues = dict(decision_points.entry_material_issues(dp, wrong_type))
        assert type_issues.get(first) == "expected string, got int", (dp, type_issues)

        preparation = case["book"]["preparation"]
        item = preparation["basis_catalog"][0]
        legal = decision_points.resolve_entry_choices(dp, case["book"]["material"])
        other = [choice for choice in legal if choice not in item["applies_to"]]
        if other:
            selection = decision_points.basis_selection_issues(
                item["id"], preparation["basis_catalog"], other[0]
            )
            assert ("basis_id", "does not apply to the selected choice") in selection, dp


def test_legacy_cases_stay_byte_identical_read_only_history():
    # The 25 retired ids are refused at this face too: no generation, no alias.
    retired_ids = [entry["id"] for entry in decision_points.registry_snapshot()["retired"]]
    assert len(retired_ids) == 25
    module = _generator_module()
    for retired_id in retired_ids:
        assert retired_id not in module.CASE_IDS
        with pytest.raises(SystemExit):
            module.build_case(retired_id)

    for name, sha256 in LEGACY_CASE_SHA256.items():
        shipped = CASES_DIR / name
        assert shipped.is_file(), f"missing legacy case {shipped}"
        assert hashlib.sha256(shipped.read_bytes()).hexdigest() == sha256, (
            f"{name} is read-only history and must never change; the eight-case "
            "generator writes only the eight active entries"
        )
        # The legacy book is refused by the schema-3 gate before any material is
        # parsed: the old ``state`` shape and the retired id are both hard stops.
        book = json.loads(shipped.read_text(encoding="utf-8"))["book"]
        issues = decision_book.check_book(book, repo_root=REPO_ROOT)
        assert issues, name
        assert any(issue.code == "book-schema" for issue in issues), name
        detail = " ".join(issue.detail for issue in issues)
        assert "retired" in detail or "legacy book contract" in detail, name


# ---------------------------------------------------------------------------
# /api/test/cases - fixed, page-authenticated, read-only
# ---------------------------------------------------------------------------


def _get(instance, path, **kwargs):
    return monitor_suite._http(instance.port, "GET", path, **kwargs)


def _post(instance, path, **kwargs):
    return monitor_suite._http(instance.port, "POST", path, **kwargs)


def test_case_route_is_page_authenticated_and_serves_only_fixed_ids(tmp_path):
    root = monitor_suite._root(tmp_path)
    spy = monitor_suite._SpyPlayground()
    with monitor_suite._running(
        root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR, playground=spy)
    ) as instance:
        status, _headers, payload, _raw = _get(instance, "/api/test/cases")
        assert status == 401, payload
        assert monitor_suite._envelope_error(payload)["code"] == "missing-token"

        status, _headers, payload, _raw = _get(
            instance, "/api/test/cases", token=instance.control_token
        )
        assert status == 403, payload
        assert monitor_suite._envelope_error(payload)["code"] == "wrong-role"

        token = monitor_suite._page_token(instance)
        status, _headers, payload, raw = _get(instance, "/api/test/cases", token=token)
        assert status == 200, payload
        cases = payload["data"]["cases"]
        assert [case["dp"] for case in cases] == list(LEGACY_CASE_FILES)
        assert payload["data"]["case_version"] == 1
        assert payload["data"]["source"] == "offline"
        for case in cases:
            assert set(case) == {"dp", "title", "note", "book", "questions", "sha256", "bytes"}
            shipped = json.loads((CASES_DIR / LEGACY_CASE_FILES[case["dp"]]).read_text(encoding="utf-8"))
            assert case["book"] == shipped["book"]
            assert case["questions"] == shipped["questions"]
            assert case["title"] == shipped["title"]
            assert case["note"] == shipped["note"]
            canonical = json.dumps(
                case["book"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            assert case["sha256"] == hashlib.sha256(canonical).hexdigest()
            assert case["bytes"] == len(canonical)
            assert case["title"] not in json.dumps(case["book"], ensure_ascii=False)
            assert case["note"] not in json.dumps(case["book"], ensure_ascii=False)

        status, _headers, payload, _raw = _get(
            instance, "/api/test/cases?dp=dp3-worker-clarify", token=token
        )
        assert status == 200, payload
        assert [case["dp"] for case in payload["data"]["cases"]] == ["dp3-worker-clarify"]

        for bad in (
            "/api/test/cases?dp=dp4-failure-handling",
            "/api/test/cases?dp=../dp1.json",
            "/api/test/cases?dp=" + SECRET,
            "/api/test/cases?path=dp1.json",
            "/api/test/cases?case_file=/etc/passwd",
        ):
            status, _headers, payload, _raw = _get(instance, bad, token=token)
            assert status == 400, (bad, payload)

        for bad_path in (
            "/api/test/cases/",
            "/api/test/cases/dp1.json",
            "/api/test/cases/../../dp1.json",
            "/api/test/cases/%2e%2e/dp1.json",
        ):
            status, _headers, payload, _raw = _get(instance, bad_path, token=token)
            assert status == 404, (bad_path, payload)

        status, _headers, payload, _raw = _post(
            instance, "/api/test/cases", token=token, origin=instance.origin, body={}
        )
        assert status == 405, payload

        # Read-only and zero-send: the provider seam is never touched.
        assert spy.calls == []


def test_case_route_makes_zero_credential_and_model_calls(tmp_path, monkeypatch):
    root = monitor_suite._root(tmp_path)
    spy = monitor_suite._SpyPlayground()
    resolved: list[str] = []

    def _redactor_factory(_root):
        resolved.append("redactor")
        return REDACTOR

    def _playground_factory(_root):
        resolved.append("playground")
        return spy

    def _credential_snapshot(*_args, **_kwargs):
        raise AssertionError("reading the case files must not resolve credentials")

    monkeypatch.setattr(decision, "credential_snapshot", _credential_snapshot)
    with monitor_suite._running(
        root,
        deps=decision_monitor.MonitorDeps(
            playground_factory=_playground_factory,
            redactor_factory=_redactor_factory,
        ),
    ) as instance:
        token = monitor_suite._page_token(instance)
        for path in ("/api/test/cases", "/api/test/cases?dp=dp1-dispatch-type"):
            status, _headers, payload, _raw = _get(instance, path, token=token)
            assert status == 200, payload
        assert resolved == [], f"the case route resolved {resolved!r}"
        assert spy.calls == []


def _synthetic_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A temp repo mirror whose evidence paths resolve, with no credentials.

    The four cases name ``packages/multi-workers/scripts/build_decide_cases.py``
    lines as evidence. Copying the generator (plus the registry/book authority)
    into a temp repo with a ``.git`` marker lets the *real* typed gate resolve
    that evidence without touching the developer's working tree or any
    credential file (tmp HOME, cleared env, no ``.mw/decide.json``).
    """
    root = tmp_path / "synthetic-repo"
    (root / ".git").mkdir(parents=True)
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    for relative in (
        "packages/multi-workers/scripts/build_decide_cases.py",
        "packages/multi-workers/decide_registry.json",
        "packages/multi-workers/decision_book.py",
    ):
        source = REPO_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return root


EDITS = {
    "dp1-dispatch-type": ("task_goal", "给 mw decide monitor 增加旧记录只读筛选，并保留现有写入链路不动。"),
    "dp2-checkpoint-split": (
        "pm_decision_background",
        "T06 投影未交付，T07 先完成表结构与弹窗；现在只够做一块，需要判断收窄、拆分、直执还是上抛人。",
    ),
    "dp3-worker-clarify": (
        "question",
        "旧记录详情里能否只读展示该 key 已存在的 signoff 行与时间？",
    ),
    "dp25-signoff-conclusion": (
        "actual_completion",
        "已完成五列表、四状态、DAG 与日志弹窗；观察提交未执行任何业务动作，测试记录保持独立 scope。",
    ),
}


def test_edited_cases_reach_the_real_loopback_typed_validate(tmp_path):
    """Load a case, edit it, and prove the *edited* body is what was validated.

    The review runs through the shipped ``DecisionPlayground`` (typed
    ``check_book`` + registry gate) inside a real loopback monitor; no model is
    called and the transport backend is never constructed.
    """
    repo = _synthetic_repo(tmp_path)
    playground = decision_playground.DecisionPlayground(
        repo,
        backend_factory=lambda _cfg: (_ for _ in ()).throw(
            AssertionError("validate must never build a transport backend")
        ),
    )
    monitor_root = monitor_suite._root(tmp_path, "monitor-root")
    with monitor_suite._running(
        monitor_root,
        deps=decision_monitor.MonitorDeps(redactor=REDACTOR, playground=playground),
    ) as instance:
        token = monitor_suite._page_token(instance)
        status, _headers, listing, _raw = _get(instance, "/api/test/cases", token=token)
        assert status == 200, listing
        cases = {case["dp"]: case for case in listing["data"]["cases"]}
        assert set(cases) == set(LEGACY_CASE_FILES)

        for dp, (field, edited_value) in EDITS.items():
            case = json.loads(json.dumps(cases[dp], ensure_ascii=False))
            book = case["book"]
            original = book["state"][field]
            assert isinstance(original, str) and original != edited_value
            book["state"][field] = edited_value
            # The shell never travels with the book.
            assert "title" not in book and "note" not in book
            assert case["title"] not in json.dumps(book, ensure_ascii=False)

            status, _headers, payload, _raw = _post(
                instance,
                "/api/test/validate",
                token=token,
                origin=instance.origin,
                body={"dp": dp, "book": book},
            )
            assert status == 200, (dp, payload)
            data = payload["data"]
            assert data["ok"] is True, (dp, data["issues"])
            assert data["issues"] == []
            assert data["observe_only"] is True
            assert data["context_sent"] is False

            # The reviewed object is exactly the edited state, not the shipped one.
            trigger = decision_points.Trigger.from_mapping(dict(book["state"]))
            sent_state = decision_points.get_decision_point(dp).build_state(trigger)
            assert sent_state[field] == edited_value
            assert data["state_digest"] == decision_book.state_digest(sent_state)
            assert data["state_bytes"] == len(decision._encode_state(sent_state))
            assert data["state_digest"] != decision_book.state_digest(
                decision_points.get_decision_point(dp).build_state(
                    decision_points.Trigger.from_mapping(
                        dict(json.loads((CASES_DIR / LEGACY_CASE_FILES[dp]).read_text(encoding="utf-8"))["book"]["state"])
                    )
                )
            ), "the edited field must change the reviewed digest"
            rendered = json.dumps(payload, ensure_ascii=False)
            assert case["title"] not in rendered and case["note"] not in rendered


def test_case_loader_refuses_unknown_ids_traversal_and_symlinks(tmp_path):
    assert set(decision_monitor.CASE_IDS) == set(LEGACY_CASE_FILES)
    assert pathlib.Path(decision_monitor.DECIDE_CASES_DIR).resolve() == CASES_DIR.resolve()
    for dp, name in LEGACY_CASE_FILES.items():
        assert decision_monitor.CASE_IDS[dp] == name

    for bad in ("dp4-failure-handling", "", "../dp1-dispatch-type", "dp1-dispatch-type/../../x", SECRET):
        with pytest.raises(decision_monitor.CaseError) as excinfo:
            decision_monitor.load_case(bad)
        assert excinfo.value.kind in ("case-unknown", "case-unsafe"), excinfo.value

    # A fixed-name copy in an injected directory is served (containment proof).
    good = tmp_path / "cases"
    good.mkdir()
    shutil.copyfile(CASES_DIR / "dp1.json", good / "dp1.json")
    loaded = decision_monitor.load_case("dp1-dispatch-type", cases_dir=good)
    assert loaded["dp"] == "dp1-dispatch-type"
    assert loaded["book"]["decision_point"] == "dp1-dispatch-type"

    # A symlinked case file is refused (no escape to a caller-chosen target).
    linked = tmp_path / "linked"
    linked.mkdir()
    target = tmp_path / "outside.json"
    shutil.copyfile(CASES_DIR / "dp1.json", target)
    try:
        os.symlink(target, linked / "dp1.json")
    except (OSError, NotImplementedError):
        pytest.skip("this platform/user cannot create symlinks")
    with pytest.raises(decision_monitor.CaseError) as excinfo:
        decision_monitor.load_case("dp1-dispatch-type", cases_dir=linked)
    assert excinfo.value.kind == "case-unsafe"

    # A malformed/foreign document in the fixed slot is refused, never echoed.
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "dp1.json").write_text('{"case_version": 2, "dp": "x"}', encoding="utf-8")
    with pytest.raises(decision_monitor.CaseError) as excinfo:
        decision_monitor.load_case("dp1-dispatch-type", cases_dir=broken)
    assert excinfo.value.kind == "case-invalid"
    assert SECRET not in str(excinfo.value)


# ---------------------------------------------------------------------------
# /api/history: forward the T06 workbench/facets projection verbatim
# ---------------------------------------------------------------------------


def _seed_workbench_records(tmp_path: pathlib.Path) -> pathlib.Path:
    """A real production tree with four v2/legacy records (managed writers only).

    Rows are written through ``decision_lifecycle`` (the T02 creation fact and
    the feedback words) and ``decide_archive`` (the decision fact), so the T06
    fold, the monitor route and the DOM all read one real chain. No payload is
    hand-built in this fixture.
    """
    root = monitor_suite._root(tmp_path, "workbench-root")
    store = decision_lifecycle.LifecycleStore.production(root, redact=REDACTOR)
    archive = root / ".agenticdoc" / "_autopilot" / "decisions.jsonl"

    def decide(key: str, dp: str, trigger: str, answer: dict | None, note: str) -> str:
        decide_archive.append_decide(
            archive,
            dp=dp,
            key=key,
            task_key="T07-workbench-cases",
            trigger_id=trigger,
            state={"task_goal": "the archive state is not the workbench input"},
            questions_version="q-1234abcd",
            available=answer is not None,
            reason=None if answer is not None else "entry-unavailable",
            authority="advisory",
            answer=answer,
            mode="auto",
            transport="timi-decisions",
            model="jev",
            attempts=1,
            latency_ms=10,
            confidence=0.9,
            confidence_source="api",
            note=note,
        )
        return f"{dp}:{trigger}"

    def start(key: str) -> decision_lifecycle.DecisionMeta:
        meta = decision_lifecycle.DecisionMeta.create(
            key=key, task_key="T07-workbench-cases", initiator_role="pm"
        )
        result = decision_lifecycle.record_start(store, meta)
        assert result.status == "written", result
        return meta

    # completed: consumed + settled ok, with a recorded selection (dp2)
    meta = start("mw-alpha")
    decision_id = decide(
        "mw-alpha",
        "dp2-checkpoint-split",
        "ckpt-a",
        {"checkpoint_action": {"value": "narrow"}},
        "narrow now",
    )
    assert decision_lifecycle.record_lifecycle(
        store, meta, stage="consumed", decision_id=decision_id, dp="dp2-checkpoint-split"
    ).status == "written"
    assert decision_lifecycle.record_lifecycle(
        store, meta, stage="settled", decision_id=decision_id, outcome="ok"
    ).status == "written"

    # failed: a recorded settled rework (dp1)
    meta = start("mw-beta")
    decision_id = decide(
        "mw-beta", "dp1-dispatch-type", "ckpt-b", {"triage_type": {"value": "coding"}}, "rework"
    )
    assert decision_lifecycle.record_lifecycle(
        store, meta, stage="settled", decision_id=decision_id, outcome="rework"
    ).status == "written"

    # processing: consumed only, no settlement yet (dp3)
    meta = start("mw-gamma")
    decision_id = decide(
        "mw-gamma", "dp3-worker-clarify", "ckpt-c", {"handling": {"value": "c1"}}, "open"
    )
    assert decision_lifecycle.record_lifecycle(
        store, meta, stage="consumed", decision_id=decision_id, dp="dp3-worker-clarify"
    ).status == "written"

    # legacy: an archive row without the v2 creation fact (dp25)
    decide("mw-delta", "dp25-signoff-conclusion", "ckpt-d", None, "legacy row")
    return root


def test_history_forwards_the_real_workbench_and_facets(tmp_path):
    root = _seed_workbench_records(tmp_path)
    with monitor_suite._running(
        root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)
    ) as instance:
        token = monitor_suite._page_token(instance)
        status, _headers, payload, _raw = _get(instance, "/api/history", token=token)
        assert status == 200, payload
        data = payload["data"]

        # facets: the whole snapshot universe, forwarded from the T06 object.
        assert set(data["facets"]) == {"keys", "dps"}
        assert set(data["facets"]["keys"]) == {"mw-alpha", "mw-beta", "mw-gamma", "mw-delta"}
        assert set(data["facets"]["dps"]) == set(LEGACY_CASE_FILES)

        workbench_keys = {
            "record_version",
            "processing_state",
            "key",
            "task_key",
            "question_summary",
            "dp_id",
            "selection",
            "initiator_role",
            "nodes",
        }
        expected_states = {
            "mw-alpha": "completed",
            "mw-beta": "failed",
            "mw-gamma": "processing",
            "mw-delta": "legacy",
        }
        records = {record["key"]: record for record in data["records"]}
        assert set(records) == set(expected_states)
        for key, expected_state in expected_states.items():
            workbench = records[key]["workbench"]
            assert set(workbench) == workbench_keys, key
            assert workbench["processing_state"] == expected_state, (key, workbench)
            assert workbench["processing_state"] in STATES
            # The list projection never carries node bodies (T06 contract).
            assert workbench["nodes"] == []
        alpha = records["mw-alpha"]["workbench"]
        assert alpha["record_version"] == 2
        assert alpha["initiator_role"] == "pm"
        assert alpha["selection"] == {"checkpoint_action": {"value": "narrow"}}
        assert alpha["question_summary"], "the registered question is projected"
        delta = records["mw-delta"]["workbench"]
        assert delta["record_version"] is None
        assert delta["initiator_role"] is None
        assert delta["selection"] is None
        assert "workbench" not in json.dumps(data.get("dag_available", "")), (
            "the route never adds a derived dag flag outside the T06 projection"
        )

        # detail: the fixed ten-node DAG from the same read chain.
        status, _headers, detail, _raw = _get(
            instance, "/api/history/" + records["mw-alpha"]["opaque_id"], token=token
        )
        assert status == 200, detail
        nodes = detail["data"]["workbench"]["nodes"]
        assert [node["id"] for node in nodes] == NODE_IDS
        assert all(node["status"] in NODE_STATUSES for node in nodes)
        assert any(node["status"] == "observed" for node in nodes)
        assert any(node["status"] == "missing" for node in nodes)

        # legacy detail keeps nodes empty: no DAG, no guessed association.
        status, _headers, legacy_detail, _raw = _get(
            instance, "/api/history/" + records["mw-delta"]["opaque_id"], token=token
        )
        assert legacy_detail["data"]["workbench"]["nodes"] == []

        # A filtered/limited page does not shrink the dropdown universe.
        status, _headers, filtered, _raw = _get(
            instance, "/api/history?limit=1&key=mw-alpha", token=token
        )
        assert len(filtered["data"]["records"]) == 1
        assert filtered["data"]["facets"] == data["facets"]

        # No second workbench filter contract is invented here (T06 owns it).
        status, _headers, refused, _raw = _get(
            instance, "/api/history?processing_state=completed", token=token
        )
        assert status == 400, refused


# ---------------------------------------------------------------------------
# Node DOM harness (self-contained; no new dependency, no browser)
# ---------------------------------------------------------------------------


DOM_HARNESS_JS = r'''"use strict";
const fs = require("node:fs");
const vm = require("node:vm");

function decodeEntities(text) {
  return text
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&");
}

class TextNode {
  constructor(text) { this.nodeType = 3; this._text = String(text); this.parentNode = null; }
  get textContent() { return this._text; }
  set textContent(value) { this._text = String(value); }
}

class Element {
  constructor(tagName) {
    this.nodeType = 1;
    this.tagName = String(tagName).toUpperCase();
    this.childNodes = [];
    this.parentNode = null;
    this._attrs = Object.create(null);
    this._listeners = Object.create(null);
    this.id = "";
    this.className = "";
    this.value = "";
  }
  get textContent() { return this.childNodes.map((node) => node.textContent).join(""); }
  set textContent(value) {
    this.childNodes.forEach((node) => { node.parentNode = null; });
    this.childNodes = [];
    const text = value === null || value === undefined ? "" : String(value);
    if (text !== "") this.appendChild(new TextNode(text));
  }
  appendChild(node) {
    if (!node) throw new Error("appendChild(null)");
    if (node.parentNode) node.parentNode.removeChild(node);
    node.parentNode = this;
    this.childNodes.push(node);
    return node;
  }
  removeChild(node) {
    const index = this.childNodes.indexOf(node);
    if (index >= 0) { this.childNodes.splice(index, 1); node.parentNode = null; }
    return node;
  }
  replaceChildren(...nodes) {
    this.childNodes.forEach((node) => { node.parentNode = null; });
    this.childNodes = [];
    nodes.forEach((node) => { if (node !== null && node !== undefined) this.appendChild(node); });
  }
  setAttribute(name, value) {
    const key = String(name).toLowerCase();
    const text = String(value);
    this._attrs[key] = text;
    if (key === "id") this.id = text;
    if (key === "class") this.className = text;
    if (key === "value") this.value = text;
  }
  getAttribute(name) {
    const key = String(name).toLowerCase();
    return key in this._attrs ? this._attrs[key] : null;
  }
  hasAttribute(name) { return String(name).toLowerCase() in this._attrs; }
  removeAttribute(name) {
    const key = String(name).toLowerCase();
    delete this._attrs[key];
    if (key === "id") this.id = "";
    if (key === "class") this.className = "";
  }
  addEventListener(type, fn) {
    const key = String(type);
    (this._listeners[key] = this._listeners[key] || []).push(fn);
  }
  dispatchEvent(event) {
    const payload = Object.assign({
      type: "",
      target: this,
      currentTarget: this,
      defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
      stopPropagation() {},
    }, event || {});
    (this._listeners[payload.type] || []).slice().forEach((fn) => fn(payload));
    return !payload.defaultPrevented;
  }
  click() { this.dispatchEvent({ type: "click" }); }
  submit() { this.dispatchEvent({ type: "submit" }); }
}

function matchesSelector(element, selector) {
  let rest = String(selector).trim();
  const tagMatch = /^([A-Za-z][A-Za-z0-9-]*|\*)/.exec(rest);
  if (tagMatch) {
    if (tagMatch[1] !== "*" && element.tagName.toLowerCase() !== tagMatch[1].toLowerCase()) return false;
    rest = rest.slice(tagMatch[0].length);
  }
  while (rest.length) {
    if (rest[0] === "#") {
      const match = /^#([A-Za-z0-9_-]+)/.exec(rest);
      if (!match || element.id !== match[1]) return false;
      rest = rest.slice(match[0].length);
    } else if (rest[0] === ".") {
      const match = /^\.([A-Za-z0-9_-]+)/.exec(rest);
      const classes = element.className.split(/\s+/);
      if (!match || classes.indexOf(match[1]) === -1) return false;
      rest = rest.slice(match[0].length);
    } else if (rest[0] === "[") {
      const match = /^\[([A-Za-z0-9_-]+)(?:="([^"]*)")?\]/.exec(rest);
      if (!match) return false;
      const value = element.getAttribute(match[1]);
      if (value === null) return false;
      if (match[2] !== undefined && value !== match[2]) return false;
      rest = rest.slice(match[0].length);
    } else {
      return false;
    }
  }
  return true;
}

function walk(node, visit) {
  node.childNodes.forEach((child) => {
    if (child.nodeType === 1) { visit(child); walk(child, visit); }
  });
}

function findAll(root, selector) {
  const found = [];
  walk(root, (element) => { if (matchesSelector(element, selector)) found.push(element); });
  return found;
}

function findFirst(root, selector) {
  let found = null;
  walk(root, (element) => { if (found === null && matchesSelector(element, selector)) found = element; });
  return found;
}

const VOID_TAGS = new Set(["meta", "link", "br", "img", "hr", "input", "source", "area", "base", "col", "embed", "param", "track", "wbr"]);

function parseHTML(source) {
  const root = new Element("#document-fragment");
  const stack = [root];
  let index = 0;
  while (index < source.length) {
    const lt = source.indexOf("<", index);
    if (lt === -1) { addText(source.slice(index)); break; }
    if (lt > index) addText(source.slice(index, lt));
    if (source.startsWith("<!--", lt)) {
      const end = source.indexOf("-->", lt);
      index = end === -1 ? source.length : end + 3;
      continue;
    }
    if (source.startsWith("<!", lt)) {
      const end = source.indexOf(">", lt);
      index = end === -1 ? source.length : end + 1;
      continue;
    }
    const gt = source.indexOf(">", lt);
    if (gt === -1) { addText(source.slice(lt)); break; }
    const raw = source.slice(lt + 1, gt).trim();
    if (raw.startsWith("/")) {
      const name = raw.slice(1).trim().toLowerCase();
      for (let depth = stack.length - 1; depth > 0; depth -= 1) {
        if (stack[depth].tagName.toLowerCase() === name) { stack.length = depth; break; }
      }
    } else {
      const selfClosing = raw.endsWith("/");
      const body = selfClosing ? raw.slice(0, -1) : raw;
      const tagMatch = /^([A-Za-z][A-Za-z0-9-]*)/.exec(body);
      const tag = tagMatch ? tagMatch[1] : "div";
      const element = new Element(tag);
      const attrText = body.slice(tagMatch ? tagMatch[1].length : 0);
      const attrRe = /([^\s=/>]+)(?:\s*=\s*"([^"]*)")?/g;
      let match = attrRe.exec(attrText);
      while (match !== null) {
        if (match[1]) element.setAttribute(match[1], match[2] === undefined ? "" : decodeEntities(match[2]));
        match = attrRe.exec(attrText);
      }
      stack[stack.length - 1].appendChild(element);
      if (!selfClosing && !VOID_TAGS.has(tag.toLowerCase())) stack.push(element);
    }
    index = gt + 1;
  }
  function addText(text) {
    if (text) stack[stack.length - 1].appendChild(new TextNode(decodeEntities(text)));
  }
  return root;
}

const htmlPath = process.argv[2];
const jsPath = process.argv[3];
const scenarioPath = process.argv[4];
const scenario = JSON.parse(fs.readFileSync(scenarioPath, "utf8"));
const htmlSource = fs.readFileSync(htmlPath, "utf8");

const documentRoot = parseHTML(htmlSource);
const document = {
  readyState: "complete",
  title: "mw decide monitor",
  cookie: "",
  createElement(tag) { return new Element(tag); },
  createTextNode(text) { return new TextNode(text); },
  getElementById(id) { return findFirst(documentRoot, "#" + id); },
  querySelectorAll(selector) { return findAll(documentRoot, selector); },
  addEventListener() {},
};
document.body = findFirst(documentRoot, "body");
document.documentElement = findFirst(documentRoot, "html");

const location = {
  href: "http://127.0.0.1:43170/",
  protocol: "http:",
  host: "127.0.0.1:43170",
  hostname: "127.0.0.1",
  port: "43170",
  pathname: "/",
  search: "",
  hash: scenario.hash || "",
};
const historyApi = {
  replaceState(_state, _title, url) {
    const parsed = new URL(String(url), location.href);
    location.pathname = parsed.pathname;
    location.search = parsed.search;
    location.hash = parsed.hash;
    location.href = parsed.href;
  },
};

const fetchCalls = [];
const consoleMessages = [];
const storageWrites = [];
function storageTrap(area) {
  return {
    getItem() { return null; },
    removeItem() {},
    setItem(key, value) { storageWrites.push({ area, key: String(key), value: String(value) }); },
    clear() { storageWrites.push({ area, key: "<clear>", value: "" }); },
  };
}

function responseFor(entry) {
  const status = entry && typeof entry.status === "number" ? entry.status : 200;
  const body = entry ? entry.body : { ok: false, data: null, error: { code: "no-mock", message: "no mock" } };
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get() { return null; } },
    async json() { return body; },
    async text() { return JSON.stringify(body); },
  };
}

function pickHistory(url) {
  const offsetMatch = /(?:^|[?&])offset=(\d+)/.exec(url);
  const offset = offsetMatch ? offsetMatch[1] : "0";
  if (scenario.historyByOffset && Object.prototype.hasOwnProperty.call(scenario.historyByOffset, offset)) {
    return scenario.historyByOffset[offset];
  }
  return scenario.history;
}

function routeFor(url) {
  if (url === "/api/bootstrap") return scenario.bootstrap;
  if (url.startsWith("/api/history/")) {
    const opaque = decodeURIComponent(url.slice("/api/history/".length));
    const table = scenario.detailByOpaque || {};
    if (Object.prototype.hasOwnProperty.call(table, opaque)) return table[opaque];
    return scenario.detail;
  }
  if (url.startsWith("/api/history")) return pickHistory(url);
  if (url.startsWith("/api/test/cases")) return scenario.cases;
  if (url === "/api/dps") return scenario.dps;
  if (url === "/api/test/history") return scenario.testHistory;
  if (url === "/api/test/validate") return scenario.validate;
  if (url === "/api/test/submit") return scenario.submit;
  if (url.startsWith("/api/test/submissions/")) return scenario.submission;
  if (url === "/api/test/scaffold") return scenario.scaffold;
  return undefined;
}

async function mockFetch(input, options) {
  const raw = String(input);
  const parsed = new URL(raw, location.href);
  const url = parsed.pathname + parsed.search;
  const opts = options || {};
  const headers = Object.assign({}, opts.headers || {});
  fetchCalls.push({
    url,
    method: String(opts.method || "GET").toUpperCase(),
    headers,
    body: opts.body === undefined || opts.body === null ? null : String(opts.body),
  });
  const entry = routeFor(url);
  if (!entry) {
    return responseFor({ status: 404, body: { ok: false, data: null, error: { code: "unexpected-route", message: url } } });
  }
  return responseFor(entry);
}

const sandbox = {
  document,
  location,
  history: historyApi,
  fetch: mockFetch,
  URL,
  URLSearchParams,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  console: {
    log(...args) { consoleMessages.push(["log", args.map(String)]); },
    warn(...args) { consoleMessages.push(["warn", args.map(String)]); },
    error(...args) { consoleMessages.push(["error", args.map(String)]); },
  },
  localStorage: storageTrap("localStorage"),
  sessionStorage: storageTrap("sessionStorage"),
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

function nodeText(id) {
  const node = document.getElementById(id);
  return node ? node.textContent : null;
}
function hasAttr(id, name) {
  const node = document.getElementById(id);
  return Boolean(node && node.hasAttribute(name));
}
function optionList(id) {
  const node = document.getElementById(id);
  if (!node) return [];
  return node.childNodes.filter((child) => child.nodeType === 1).map((child) => ({
    value: String(child.value === undefined ? "" : child.value),
    text: child.textContent,
  }));
}
function texts(testid) {
  return document.querySelectorAll('[data-testid="' + testid + '"]').map((node) => node.textContent);
}
function headersOf(testid) {
  const table = findFirst(documentRoot, '[data-testid="' + testid + '"]');
  return table ? findAll(table, "th").map((node) => node.textContent) : [];
}
function attrs(testid, name) {
  return document.querySelectorAll('[data-testid="' + testid + '"]').map((node) => node.getAttribute(name));
}
function snapshot(label) {
  return {
    label,
    hash: location.hash,
    href: location.href,
    fetchCalls: fetchCalls.map((call) => ({
      url: call.url,
      method: call.method,
      headers: Object.assign({}, call.headers),
      body: call.body,
    })),
    storage: storageWrites.slice(),
    consoleMessages: consoleMessages.slice(),
    bootStatus: nodeText("boot-status"),
    error: nodeText("error-banner"),
    summary: nodeText("history-summary"),
    pageInfo: nodeText("page-info"),
    facetsNote: nodeText("facets-notes"),
    headers: headersOf("workbench-table"),
    rowCount: document.querySelectorAll('[data-testid="record-row"]').length,
    rows: texts("record-row"),
    rowOpaques: attrs("record-row", "data-opaque"),
    states: texts("record-state"),
    stateValues: attrs("record-state", "data-processing-state"),
    dagOpenCount: document.querySelectorAll('[data-testid="record-dag-open"]').length,
    legacyOpenCount: document.querySelectorAll('[data-testid="record-open"]').length,
    logOpenCount: document.querySelectorAll('[data-testid="record-log-open"]').length,
    dialogVisible: !hasAttr("record-dialog", "hidden"),
    dagTabDisabled: hasAttr("record-dialog-tab-dag", "disabled"),
    dagPanelVisible: !hasAttr("record-dialog-dag-panel", "hidden"),
    logPanelVisible: !hasAttr("record-dialog-log-panel", "hidden"),
    dagSummary: nodeText("record-dialog-dag-summary"),
    dagNodes: document.querySelectorAll('[data-testid="dag-node"]').length,
    dagNodeIds: attrs("dag-node", "data-node-id"),
    dagNodeStates: attrs("dag-node", "data-node-state"),
    dagNodeTexts: texts("dag-node"),
    dagNodeDetail: nodeText("dag-node-detail"),
    legacyNote: nodeText("record-dialog-legacy-note"),
    dialogMeta: nodeText("record-dialog-meta"),
    detailText: nodeText("detail-body"),
    keyOptions: optionList("filter-key"),
    dpOptions: optionList("filter-dp"),
    caseOptions: optionList("case-select"),
    caseStatus: nodeText("pg-case-status"),
    editorValue: (document.getElementById("book-editor") || { value: "" }).value,
    localOut: nodeText("pg-local-out"),
    playgroundVisible: !hasAttr("panel-playground", "hidden"),
    pgDagNodes: document.querySelectorAll('[data-testid="pg-dag-node"]').length,
    pgDagStates: attrs("pg-dag-node", "data-node-state"),
    pgDagTexts: texts("pg-dag-node"),
    imgCount: document.querySelectorAll("img").length,
    scriptTags: document.querySelectorAll("script").length,
    pwned: Boolean(sandbox.PWNED),
    bodyText: document.body ? document.body.textContent : "",
  };
}

async function drain() {
  for (let index = 0; index < 25; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function find(selector) {
  const node = findFirst(documentRoot, selector);
  if (!node) throw new Error("selector not found: " + selector);
  return node;
}

async function run() {
  const vmContext = vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(jsPath, "utf8"), vmContext, { filename: jsPath, timeout: 20000 });
  await drain();
  const snapshots = [snapshot("boot")];
  for (const step of scenario.steps || []) {
    if (step.type === "click") {
      find(step.target).click();
    } else if (step.type === "setValue") {
      find(step.target).value = String(step.value);
    } else if (step.type === "submit") {
      find(step.target).submit();
    } else {
      throw new Error("unknown step " + JSON.stringify(step));
    }
    await drain();
    if (step.snapshot) snapshots.push(snapshot(step.snapshot));
  }
  return { ok: true, snapshots, fetchCalls, storageWrites };
}

run().then((result) => {
  process.stdout.write(JSON.stringify(result));
}).catch((error) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String((error && error.stack) || error), snapshots: [], fetchCalls }));
  process.exitCode = 1;
});
'''


def _run_dom(tmp_path: pathlib.Path, scenario: dict) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is unavailable: the DOM behaviour cannot be exercised here")
    work = tmp_path / "dom"
    work.mkdir(parents=True, exist_ok=True)
    harness = work / "dom_harness.cjs"
    harness.write_text(DOM_HARNESS_JS, encoding="utf-8")
    scenario_path = work / "scenario.json"
    scenario_path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
    process = subprocess.run(
        [
            node,
            str(harness),
            str(ASSET_DIR / "decision_dashboard.html"),
            str(ASSET_DIR / "decision_dashboard.js"),
            str(scenario_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(work),
        timeout=180,
    )
    assert process.stdout, f"node produced no output (stderr={process.stderr})"
    assert process.returncode == 0, process.stdout + "\n--- stderr ---\n" + process.stderr
    result = json.loads(process.stdout.strip().splitlines()[-1])
    assert result.get("ok") is True, process.stdout + "\n--- stderr ---\n" + process.stderr
    return result


def _snapshot(result: dict, label: str) -> dict:
    for snapshot in result["snapshots"]:
        if snapshot["label"] == label:
            return snapshot
    raise AssertionError(f"missing snapshot {label}: {[s['label'] for s in result['snapshots']]}")


def _envelope(data: object) -> dict:
    return {"ok": True, "data": data, "error": None, "capture_status": None}


def _bootstrap(token: str, status: int = 200) -> dict:
    if status != 200:
        return {"status": status, "body": {"ok": False, "data": None, "error": {"code": "bad-boot-code", "message": "bad"}}}
    return {"status": 200, "body": _envelope({"page_token": token})}


def _workbench_dom_payload(tmp_path: pathlib.Path):
    """Real loopback payloads for the DOM scenarios (real T06 fold).

    The page is fed the bytes a real monitor returns for a real record tree, so
    the DOM run exercises the projection the shipped service produces.
    """
    root = _seed_workbench_records(tmp_path)
    spy = _DomPlayground()
    with monitor_suite._running(
        root,
        deps=decision_monitor.MonitorDeps(redactor=REDACTOR, playground=spy),
    ) as instance:
        token = monitor_suite._page_token(instance)
        status, _headers, listed, _raw = _get(instance, "/api/history", token=token)
        assert status == 200, listed
        records = listed["data"]["records"]
        detail_by_opaque = {}
        for record in records:
            opaque = record["opaque_id"]
            status, _headers, payload, _raw = _get(
                instance, "/api/history/" + opaque, token=token
            )
            assert status == 200, payload
            detail_by_opaque[opaque] = {"status": 200, "body": payload}
        status, _headers, cases, _raw = _get(instance, "/api/test/cases", token=token)
        assert status == 200, cases
        status, _headers, dps, _raw = _get(instance, "/api/dps", token=token)
        assert status == 200, dps
        test_history = spy.history()
        submission = {
            "submission_id": "ui-test-1",
            "dp": "dp1-dispatch-type",
            "state": "succeeded",
            "decision_ran": True,
            "decision_id": "dp1-dispatch-type:ui-test-1",
            "call_id": "call-1",
            "zero_call": False,
            "http_attempts": 1,
            "book_ref": "book-1",
            "state_digest": "digest-1",
            "answer_persisted": False,
            "projection_status": "not-recorded",
            "issues": [],
            "outcome": {"status": "suggested", "mode": "auto"},
            "attempts": [],
            "observe_only": True,
        }
    by_key = {
        record["key"]: {
            "opaque": record["opaque_id"],
            "state": record["workbench"]["processing_state"],
            "record_version": record["workbench"]["record_version"],
        }
        for record in records
    }
    return {
        "token": token,
        "default": {"status": 200, "body": listed},
        "detailByOpaque": detail_by_opaque,
        "cases": {"status": 200, "body": cases},
        "dps": {"status": 200, "body": dps},
        "testHistory": {"status": 200, "body": _envelope(test_history)},
        "submission": {"status": 200, "body": _envelope(submission)},
        "submissionId": "ui-test-1",
        "by_key": by_key,
    }


class _DomPlayground:
    """The playground seam used by the DOM scenarios (no model call, no write)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def scaffold(self, dp: str) -> dict:
        self.calls.append(("scaffold", dp))
        return {"dp": dp, "book": {}}

    def validate(self, dp: str, book: object) -> dict:
        self.calls.append(("validate", dp, book))
        return {"dp": dp, "ok": True, "issues": [], "observe_only": True}

    def submit(self, request: dict) -> dict:
        self.calls.append(("submit", request))
        return {
            "submission_id": request["submit_id"],
            "dp": request["dp"],
            "state": "succeeded",
            "accepted": True,
            "observe_only": True,
            "record_status": "recorded",
            "decision_ran": True,
            "zero_call": False,
            "http_attempts": 1,
            "answer_persisted": False,
            "projection_status": "not-recorded",
            "retry_of": request.get("retry_of"),
            "decision_id": f"{request['dp']}:{request['submit_id']}",
            "issues": [],
            "outcome": {"status": "suggested", "mode": "auto"},
            "attempts": [],
        }

    def submission(self, submission_id: str) -> dict | None:
        self.calls.append(("submission", submission_id))
        return None

    def history(self) -> dict:
        self.calls.append(("history",))
        return {
            "source": "test",
            "scope": "test",
            "observe_only": True,
            "records": [
                {
                    "submission_id": "ui-test-1",
                    "dp": "dp1-dispatch-type",
                    "state": "succeeded",
                    "retry_of": None,
                    "call_id": "call-1",
                    "book_ref": "book-1",
                    "zero_call": False,
                    "http_attempts": 1,
                    "answer_persisted": False,
                    "projection_status": "not-recorded",
                    "projection_sha256": None,
                }
            ],
            "total": 1,
            "limit": 50,
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# DOM: workbench table, four states, facets dropdowns
# ---------------------------------------------------------------------------


def test_dom_workbench_table_has_five_columns_four_states_and_facet_dropdowns(tmp_path):
    payloads = _workbench_dom_payload(tmp_path)
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": _bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": payloads["detailByOpaque"],
        "steps": [],
    }
    boot = _snapshot(_run_dom(tmp_path, scenario), "boot")

    assert boot["error"] in (None, "")
    assert boot["storage"] == [], "the page token stays in memory"
    assert all(payloads["token"] not in call["url"] for call in boot["fetchCalls"]), (
        "the page token never appears in a URL"
    )

    # Five business columns, no extra technical column.
    assert [header.strip() for header in boot["headers"]] == [
        "key / task",
        "问题摘要",
        "DP",
        "选择",
        "状态",
    ], boot["headers"]
    assert boot["rowCount"] == 4
    # Every row carries the backend's closed state, mapped by record handle.
    expected = {info["opaque"]: info["state"] for info in payloads["by_key"].values()}
    assert sorted(boot["rowOpaques"]) == sorted(expected)
    assert dict(zip(boot["rowOpaques"], boot["stateValues"])) == expected
    assert set(boot["stateValues"]) == set(STATES)
    assert set(boot["states"]) == set(STATE_LABELS.values())
    for row in boot["rows"]:
        assert "logical_id" not in row, row
        assert "+已行动" not in row and "已接收" not in row, row
    alpha_row = next(
        row for row, opaque in zip(boot["rows"], boot["rowOpaques"])
        if opaque == payloads["by_key"]["mw-alpha"]["opaque"]
    )
    assert "narrow" in alpha_row
    assert "继续" in alpha_row, "the registered dp2 question is the summary"
    delta_row = next(
        row for row, opaque in zip(boot["rows"], boot["rowOpaques"])
        if opaque == payloads["by_key"]["mw-delta"]["opaque"]
    )
    assert "未记录" in delta_row, "a legacy row never invents a question or selection"
    assert "旧数据无状态" in delta_row

    # key/DP dropdowns carry the full facet universe (page-independent).
    expected_keys = sorted(payloads["default"]["body"]["data"]["facets"]["keys"])
    expected_dps = sorted(payloads["default"]["body"]["data"]["facets"]["dps"])
    assert [option["value"] for option in boot["keyOptions"]] == ["", *expected_keys]
    assert [option["value"] for option in boot["dpOptions"]] == ["", *expected_dps]
    assert boot["facetsNote"] in (None, ""), "facet diagnostics are not normal page content"
    assert boot["imgCount"] == 0 and boot["pwned"] is False


def test_dom_legacy_payload_without_facets_never_fabricates_the_universe(tmp_path):
    payloads = _workbench_dom_payload(tmp_path)
    body = json.loads(json.dumps(payloads["default"]["body"]))
    body["data"].pop("facets", None)
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": _bootstrap(payloads["token"]),
        "history": {"status": 200, "body": body},
        "detailByOpaque": payloads["detailByOpaque"],
        "steps": [],
    }
    boot = _snapshot(_run_dom(tmp_path, scenario), "boot")
    assert [option["value"] for option in boot["keyOptions"]] == [""]
    assert [option["value"] for option in boot["dpOptions"]] == [""]
    assert boot["facetsNote"] in (None, ""), "missing facets do not generate debug prose"


# ---------------------------------------------------------------------------
# DOM: v2 DAG dialog vs legacy log-only dialog
# ---------------------------------------------------------------------------


def test_dom_v2_record_opens_ten_node_dag_and_legacy_record_stays_log_only(tmp_path):
    payloads = _workbench_dom_payload(tmp_path)
    alpha = payloads["by_key"]["mw-alpha"]["opaque"]
    delta = payloads["by_key"]["mw-delta"]["opaque"]
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": _bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": payloads["detailByOpaque"],
        "steps": [
            {
                "type": "click",
                "target": '[data-testid="record-dag-open"][data-opaque="' + alpha + '"]',
                "snapshot": "dag",
            },
            {
                "type": "click",
                "target": '[data-testid="dag-node"][data-node-id="key"]',
                "snapshot": "node-detail",
            },
            {"type": "click", "target": "#detail-close"},
            {
                "type": "click",
                "target": '[data-testid="record-open"][data-opaque="' + delta + '"]',
                "snapshot": "legacy",
            },
        ],
    }
    result = _run_dom(tmp_path, scenario)
    boot = _snapshot(result, "boot")
    assert boot["dagOpenCount"] == 3, "only the three v2 records expose a DAG entry"
    assert boot["legacyOpenCount"] == 1, "the legacy row has only the log-only entry"
    assert boot["logOpenCount"] == 3, "a v2 row can also open the technical log"

    dag = _snapshot(result, "dag")
    assert dag["dialogVisible"] is True
    assert dag["dagTabDisabled"] is False
    assert dag["dagPanelVisible"] is True
    assert dag["dagNodes"] == 10, dag["dagNodeIds"]
    assert dag["dagNodeIds"] == NODE_IDS
    assert "10/10" in (dag["dagSummary"] or "")
    assert all(status in NODE_STATUSES for status in dag["dagNodeStates"])
    assert "已记录" in " ".join(dag["dagNodeTexts"])
    assert "未记录" in " ".join(dag["dagNodeTexts"])
    assert "pm" in (dag["dialogMeta"] or ""), dag["dialogMeta"]
    detail_calls = [call for call in dag["fetchCalls"] if call["url"].startswith("/api/history/")]
    assert detail_calls and detail_calls[-1]["headers"].get("X-MW-Monitor-Token") == payloads["token"]

    node = _snapshot(result, "node-detail")
    assert "mw-alpha" in (node["dagNodeDetail"] or "")
    assert "T07-workbench-cases" in (node["dagNodeDetail"] or "")
    assert "logical_id" not in (node["dagNodeDetail"] or "")
    assert "record_version" not in (node["dagNodeDetail"] or "")
    raw_key = next(n for n in payloads["detailByOpaque"][alpha]["body"]["data"]["workbench"]["nodes"] if n["id"] == "key")
    assert raw_key["detail"]["logical_id"]
    assert raw_key["detail"]["record_version"] == 2
    assert node["pwned"] is False

    legacy = _snapshot(result, "legacy")
    assert legacy["dialogVisible"] is True
    assert legacy["dagTabDisabled"] is True, "legacy records have no DAG entry"
    assert legacy["dagPanelVisible"] is False
    assert legacy["logPanelVisible"] is True
    assert legacy["dagNodes"] == 0
    assert "旧数据无状态" in (legacy["legacyNote"] or ""), legacy["legacyNote"]
    assert "接收与处理结果" in (legacy["detailText"] or "")
    assert "决策本" not in (legacy["detailText"] or "")


def test_dom_incomplete_dag_projection_is_reported_not_filled(tmp_path):
    payloads = _workbench_dom_payload(tmp_path)
    alpha = payloads["by_key"]["mw-alpha"]["opaque"]
    working = json.loads(json.dumps(payloads["detailByOpaque"]))
    v2_detail = working[alpha]
    v2_detail["body"]["data"]["workbench"]["nodes"] = v2_detail["body"]["data"]["workbench"]["nodes"][:8]
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": _bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": working,
        "steps": [
            {
                "type": "click",
                "target": '[data-testid="record-dag-open"][data-opaque="' + alpha + '"]',
                "snapshot": "incomplete",
            },
        ],
    }
    dag = _snapshot(_run_dom(tmp_path, scenario), "incomplete")
    assert dag["dagNodes"] == 8
    assert "8/10" in (dag["dagSummary"] or "")
    assert "不补造" in (dag["dagSummary"] or "")


# ---------------------------------------------------------------------------
# DOM: offline case load + local check (zero model, zero credential, zero POST)
# ---------------------------------------------------------------------------


def test_dom_offline_case_loads_and_local_validate_makes_no_network_write(tmp_path):
    payloads = _workbench_dom_payload(tmp_path)
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": _bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": payloads["detailByOpaque"],
        "cases": payloads["cases"],
        "steps": [
            {"type": "click", "target": "#tab-playground"},
            {"type": "click", "target": "#pg-load", "snapshot": "loaded"},
            {"type": "click", "target": "#pg-cases-load", "snapshot": "cases"},
            {"type": "setValue", "target": "#case-select", "value": "dp3-worker-clarify"},
            {"type": "click", "target": "#pg-case-open", "snapshot": "opened"},
            {"type": "click", "target": "#pg-local-validate", "snapshot": "local"},
        ],
    }
    result = _run_dom(tmp_path, scenario)

    loaded = _snapshot(result, "loaded")
    assert loaded["playgroundVisible"] is True
    assert any(call["url"] == "/api/dps" for call in loaded["fetchCalls"])

    cases = _snapshot(result, "cases")
    assert [option["value"] for option in cases["caseOptions"]] == ["", *LEGACY_CASE_FILES]
    assert "4" in (cases["caseStatus"] or "")

    opened = _snapshot(result, "opened")
    shipped_dp3 = json.loads((CASES_DIR / "dp3.json").read_text(encoding="utf-8"))
    assert json.loads(opened["editorValue"]) == shipped_dp3["book"]
    assert shipped_dp3["title"] not in opened["editorValue"]
    assert shipped_dp3["note"] not in opened["editorValue"]
    assert "dp3-worker-clarify" in opened["editorValue"]

    local = _snapshot(result, "local")
    posts = [call for call in local["fetchCalls"] if call["method"] == "POST" and call["url"] != "/api/bootstrap"]
    assert posts == [], f"loading and local validation never POST: {posts}"
    assert "本地校验" in (local["localOut"] or "")
    assert "通过" in (local["localOut"] or "")
    assert local["pwned"] is False


def test_dom_local_validate_refuses_placeholders_and_incomplete_material(tmp_path):
    payloads = _workbench_dom_payload(tmp_path)
    broken = json.loads((CASES_DIR / "dp3.json").read_text(encoding="utf-8"))["book"]
    broken["state"]["handling_options"] = broken["state"]["handling_options"][:1]
    broken["state"]["question"] = "<string: question>"
    editor_text = json.dumps(broken, ensure_ascii=False, indent=2)
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": _bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": payloads["detailByOpaque"],
        "cases": payloads["cases"],
        "steps": [
            {"type": "click", "target": "#tab-playground"},
            {"type": "click", "target": "#pg-load"},
            {"type": "click", "target": "#pg-cases-load"},
            {"type": "setValue", "target": "#case-select", "value": "dp3-worker-clarify"},
            {"type": "click", "target": "#pg-case-open", "snapshot": "opened"},
            {"type": "setValue", "target": "#book-editor", "value": editor_text},
            {"type": "click", "target": "#pg-local-validate", "snapshot": "local"},
        ],
    }
    local = _snapshot(_run_dom(tmp_path, scenario), "local")
    out = local["localOut"] or ""
    assert "未通过" in out, out
    assert "占位符" in out and "候选" in out, out
    posts = [call for call in local["fetchCalls"] if call["method"] == "POST" and call["url"] != "/api/bootstrap"]
    assert posts == []


# ---------------------------------------------------------------------------
# DOM: the 25-DP playground keeps observe-only submit + precise submission link
# ---------------------------------------------------------------------------


def test_dom_playground_submit_stays_observe_only_and_retry_points_at_the_previous_id(tmp_path):
    payloads = _workbench_dom_payload(tmp_path)
    book = json.loads((CASES_DIR / "dp1.json").read_text(encoding="utf-8"))["book"]
    scenario = {
        "hash": "#boot=dom-boot-code",
        "bootstrap": _bootstrap(payloads["token"]),
        "history": payloads["default"],
        "detailByOpaque": payloads["detailByOpaque"],
        "cases": payloads["cases"],
        "dps": payloads["dps"],
        "testHistory": payloads["testHistory"],
        "submission": payloads["submission"],
        "submit": {"status": 200, "body": _envelope({
            "submission_id": "ui-sent",
            "dp": "dp1-dispatch-type",
            "state": "succeeded",
            "accepted": True,
            "observe_only": True,
            "record_status": "recorded",
            "decision_ran": True,
            "zero_call": False,
            "http_attempts": 1,
            "answer_persisted": False,
            "projection_status": "not-recorded",
            "issues": [],
            "outcome": {"status": "suggested", "mode": "auto"},
            "attempts": [],
        })},
        "steps": [
            {"type": "click", "target": "#tab-playground"},
            {"type": "click", "target": "#pg-load"},
            {"type": "setValue", "target": "#dp-select", "value": "dp1-dispatch-type"},
            {"type": "setValue", "target": "#book-editor", "value": json.dumps(book, ensure_ascii=False, indent=2)},
            {"type": "click", "target": "#pg-submit", "snapshot": "submitted"},
            {"type": "click", "target": "#pg-retry", "snapshot": "retried"},
            {"type": "click", "target": '[data-testid="pg-history-open"]', "snapshot": "pg-dag"},
        ],
    }
    result = _run_dom(tmp_path, scenario)
    submitted = _snapshot(result, "submitted")
    submit_calls = [call for call in submitted["fetchCalls"] if call["url"] == "/api/test/submit"]
    assert len(submit_calls) == 1
    body = json.loads(submit_calls[0]["body"])
    assert body["observe_only"] is True
    assert body["dp"] == "dp1-dispatch-type"
    assert body["book"] == book
    assert isinstance(body["submit_id"], str) and body["submit_id"]
    assert "retry_of" not in body

    retried = _snapshot(result, "retried")
    retry_calls = [call for call in retried["fetchCalls"] if call["url"] == "/api/test/submit"]
    assert len(retry_calls) == 2
    retry_body = json.loads(retry_calls[1]["body"])
    assert retry_body["observe_only"] is True
    assert retry_body["retry_of"] == body["submit_id"]
    assert retry_body["submit_id"] != body["submit_id"], "a retry uses a new submission id"

    # The submission detail renders its own honest DAG (observe-only action).
    pg_dag = _snapshot(result, "pg-dag")
    assert pg_dag["pgDagNodes"] == 10
    assert "not-executed" in pg_dag["pgDagStates"]
    assert "未执行" in " ".join(pg_dag["pgDagTexts"])


# ---------------------------------------------------------------------------
# Shipped assets: CSP / textContent / token-safety scaffolding
# ---------------------------------------------------------------------------


def test_shipped_assets_keep_csp_textcontent_and_token_discipline():
    html = (ASSET_DIR / "decision_dashboard.html").read_text(encoding="utf-8")
    js = (ASSET_DIR / "decision_dashboard.js").read_text(encoding="utf-8")
    css = (ASSET_DIR / "decision_dashboard.css").read_text(encoding="utf-8")

    for needle in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert needle not in js, needle
    assert "textContent" in js
    assert "localStorage" not in js and "sessionStorage" not in js and "document.cookie" not in js
    assert "X-MW-Monitor-Token" in js
    assert "@import" not in css
    assert not re.search(r"<[^>]+\son[a-z]+\s*=", html), "no inline event handler attributes"
    assert "<script>" not in html and "javascript:" not in html

    csp = decision_monitor._CSP
    assert csp.startswith("default-src 'none'")
    assert "script-src 'self'" in csp
    assert "form-action 'none'" in csp
    assert "'unsafe-inline'" not in csp and "unsafe-eval" not in csp

    # The workbench ids the DOM contract relies on are present exactly once.
    for element_id in (
        "filter-key",
        "filter-dp",
        "history-safety",
        "record-dialog",
        "record-dialog-tab-dag",
        "record-dialog-dag-panel",
        "dag-graph",
        "dag-node-detail",
        "case-select",
        "pg-cases-load",
        "pg-case-open",
        "pg-local-validate",
        "pg-local-out",
    ):
        assert html.count(' id="' + element_id + '"') == 1, element_id

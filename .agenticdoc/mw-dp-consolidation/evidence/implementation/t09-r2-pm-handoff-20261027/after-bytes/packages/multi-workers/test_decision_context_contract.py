"""T09 contract: the decision book and its stdin preparer.

The consolidated eight entries (spec §1.1) share one book surface:

* the book is layered -- ``material`` (business facts only), ``preparation``
  (the PM-prepared basis catalog + ``prepared_at``), local ``meta`` (key/task/
  role/logical_id, never sent) and optional engineered ``context``;
* every rule is the registry's: ``decision_points.entry_material_issues``,
  ``preparation_issues``, ``role_issues`` and the retirement table decide, so a
  book can never pass with material the transport would refuse (D-056 single
  judge);
* a retired id is refused **before** any material/preparation/replay work, and
  the pre-consolidation ``state``/``questions`` book shapes are history: they are
  refused instead of being upgraded or used to bypass the active gate;
* illegal state is refused first: when the business material is illegal the
  preparation is not even judged, so the reported defect is the real one.

No real provider, HTTP endpoint, decision CLI or service is touched: the only
backend is :class:`decision.FakeBackend`, the only ledger is a temp fixture, and
the credential environment is emptied per test.
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import sys
from unittest import mock

import pytest

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR))
sys.path.insert(0, str(PACKAGE_DIR / "scripts"))

import decision  # noqa: E402
import decision_book as books  # noqa: E402
import decision_context  # noqa: E402
import decision_points as dpts  # noqa: E402

ACTIVE = dpts.ACTIVE_DP_IDS
RETIRED = tuple(record.id for record in dpts.RETIRED_DP_REGISTRY)
META_KEYS = ("key", "task_key", "trigger_id", "actor_role", "logical_id")
PREPARED_AT = "2026-10-27T08:00:00+00:00"
GENEROUS_LIMITS = {
    "max_state_bytes": 200_000,
    "max_state_plus_question_tokens": 200_000,
    "max_total_tokens": 200_000,
}
CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)


# ---------------------------------------------------------------------------
# Legal business material per active entry (model-visible facts only)
# ---------------------------------------------------------------------------

LEGAL_MATERIAL: dict[str, dict] = {
    "dp-w-type": {
        "task_goal": "把八入口收敛进决策本，并保留真实业务材料。",
        "task_requirements": "book 只装业务事实；本地身份留在 meta；依据独立完整。",
        "task_deliverables": "book 合同实现、契约测试、证据与报告。",
        "images_required": False,
    },
    "dp-pm-steer": {
        "task_goal": "判断 checkpoint 应继续、拆小、直执还是上抛人。",
        "task_requirements": "PM 主动触发；任务原文与决策背景齐全。",
        "task_deliverables": "一次 checkpoint 判断及后续 PM 处理。",
        "pm_decision_background": "剩余预算只够完成一小块，拆分后两个任务都要重新取证。",
        "worker_execution": "已完成 A 与 B；剩余 C；无阻塞；剩余时间预算 20m。",
    },
    "dp-w-check-task": {
        "task_goal": "判断当前任务在授权与预算内是否可完成。",
        "reachability_facts": "依赖的 registry 单源已落地，测试可离线运行。",
        "completed": "合同与生成物已读；测试骨架已存在。",
        "remaining": "补齐 book 合同与回归测试。",
        "blockers": "无。",
        "constraints": "只能写本卡两个副本文件；无新预算。",
    },
    "dp-QG": {
        "review_requirements": "八入口材料合同成立，非法材料零发送。",
        "review_evidence": ["notes.txt:1"],
        "review_findings": "合法材料通过；旧 state 形状与退役 ID 被明确拒绝。",
        "uncovered_scope": "未跑完整 npm check 与真实 provider。",
    },
    "dp-gate-approve": {
        "gate_background": "S2 前向 stage 启动审批：八入口 book 合同待放行。",
        "current_state": "book 层红测已建立，实现尚未完成。",
        "condition_evidence": ["notes.txt:1"],
        "pm_note": {
            "subject": "放行 T09 book 合同实现",
            "planned_action": "只改本卡两个副本文件并跑本卡测试",
            "basis": {
                "goal": "goal.md 的 Agent Team 决策收敛目标",
                "evidence": "notes.txt:1 的隔离红测记录",
                "budget": "沿用原卡硬预算，不追加",
                "authority": "已批准隔离实施写面",
            },
        },
    },
    "dp-sign-key": {
        "delivery_goal": "八入口 book 合同落地；验收条件是生产路径拒绝非法材料且不丢核心证据。",
        "actual_completion": "book 分层、退役拒绝与依据校验已实现；报告待写。",
        "verification_evidence": {
            "verified": ["pytest test_decision_context_contract.py 全绿"],
            "unverified": ["完整 npm check 尚未运行"],
        },
        "unfinished_impact": ["报告缺失会让下游无法迁移"],
    },
    "dp-auto": {
        "question": "签收文件应该由 PM 直接写，还是先经用户确认？",
        "background": {
            "task_goal": "让 dp-sign-key 在材料充分时一次收尾。",
            "current_state": "签收写入路径已存在，尚无完整案例验证。",
            "tried": "已补三条签收数组证据并要求同次 finalize。",
            "unknowns": "用户是否接受当前验收范围仍未知。",
            "constraints": "不得扩大授权，不得超过硬预算。",
        },
        "handling_options": [
            {
                "id": "act-now",
                "label": "PM 直接写签收",
                "description": "材料与前置门都满足时立即原子写入，无需二次批准。",
                "consequence": "本轮交付立即收尾。",
                "risk": "若证据不足，签收会被下游复核推翻。",
                "conditions": "三条数组均为真实证据且无未完成阻断。",
            },
            {
                "id": "hold-for-user",
                "label": "先问用户再写",
                "description": "PM 给出具体待确认项，用户答复前不写签收文件。",
                "consequence": "本轮停在等待用户确认。",
                "risk": "阻塞收尾但不扩大授权。",
                "conditions": "存在验收范围歧义。",
            },
        ],
    },
    "dp-route": {
        "decision_actor": "PM 窗口（真实进程绑定，不是自报字段）",
        "decision_object": "T09 的 book 合同是否放行",
        "question": "这个问题应该交给哪一个业务入口判断？",
    },
}

#: The material fact each entry's basis catalog can cite (a real key of it).
BASIS_REFERENCE = {
    "dp-w-type": "task_goal",
    "dp-pm-steer": "pm_decision_background",
    "dp-w-check-task": "reachability_facts",
    "dp-QG": "review_requirements",
    "dp-gate-approve": "gate_background",
    "dp-sign-key": "delivery_goal",
    "dp-auto": "question",
    "dp-route": "question",
}


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated HOME plus an empty credential environment for every test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in list(os.environ):
        if name in CRED_ENV_VARS or name.upper().endswith(decision._CRED_ENV_SUFFIXES):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dpts, "ARCHIVE_WRITER", None, raising=False)
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


@pytest.fixture
def project(tmp_path: pathlib.Path) -> pathlib.Path:
    """One isolated project with the evidence file every book cites."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "notes.txt").write_text(
        "synthetic evidence line\n" * 6, encoding="utf-8"
    )
    return root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def material_for(dp_id: str) -> dict:
    return copy.deepcopy(LEGAL_MATERIAL[dp_id])


def preparation_for(dp_id: str, material: dict | None = None) -> dict:
    material = material_for(dp_id) if material is None else material
    return {
        "basis_catalog": [
            {
                "id": "basis-real",
                "text": f"{dp_id}: 已按真实材料准备本理由，引用真实事实。",
                "material_refs": [BASIS_REFERENCE[dp_id]],
                "applies_to": list(dpts.resolve_entry_choices(dp_id, material)),
            }
        ],
        "prepared_at": PREPARED_AT,
    }


def evidence_for(dp_id: str) -> dict:
    return {path: "notes.txt:1" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}


def meta_for(dp_id: str) -> dict:
    return {
        "key": "mw-dp-consolidation",
        "task_key": "dpc-t09-books",
        "trigger_id": "t09-books",
        "actor_role": dpts.ENTRY_ROLES[dp_id],
        "logical_id": f"t09-{dp_id}",
    }


def legal_book(dp_id: str) -> dict:
    material = material_for(dp_id)
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "material": material,
        "preparation": preparation_for(dp_id, material),
        "meta": meta_for(dp_id),
        "notes": {"evidence": evidence_for(dp_id)},
    }


def check(book: dict, project: pathlib.Path, **kwargs) -> list:
    options = {
        "project_dir": project,
        "repo_root": project,
        "limits": GENEROUS_LIMITS,
    }
    options.update(kwargs)
    return books.check_book(book, **options)


def codes(issues) -> set[str]:
    return {issue.code for issue in issues}


def rendered(issues) -> list[str]:
    return [issue.format() for issue in issues]


def set_path(target: dict, dotted: str, value: object) -> None:
    parts = dotted.split(".")
    current = target
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = value


def _flatten(value: object, prefix: str = "") -> dict[str, object]:
    """``{dotted_path: leaf}`` for a nested material/meta object."""
    if isinstance(value, dict) and value:
        out: dict[str, object] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten(child, child_prefix))
        return out
    return {prefix: value}


def has_issue(issues, path: str, detail_fragment: str = "") -> bool:
    for issue in issues:
        if issue.path == path and detail_fragment in issue.detail:
            return True
    return False


def backend_with_answers(dp_id: str, material: dict, preparation: dict):
    """A faux backend answering the business question and the prepared basis.

    The choice is picked per entry: a branch that only needs material already in
    the book (``dp-QG`` pass / ``dp-w-check-task`` continue) so the test proves the
    book layers reach the transport, not a conditional branch's extra material.
    """
    conditional_free = {"dp-QG": "pass", "dp-w-check-task": "continue"}
    legal = dpts.resolve_entry_choices(dp_id, material)
    choice = conditional_free.get(dp_id) or (legal[0] if legal else "x")
    basis_id = preparation["basis_catalog"][0]["id"]
    answers = {
        question_id: {"value": choice, "confidence": 0.9}
        for question_id in dpts.questions_map(dp_id)
    }
    answers[decision.BASIS_QUESTION_ID] = {"value": basis_id, "confidence": 0.9}
    backend = decision.FakeBackend(
        [
            {
                "available": True,
                "reason": None,
                "retryable": False,
                "answers": answers,
                "latency_ms": 1,
            }
        ]
    )
    client = decision.DecisionClient(
        cfg=decision.DecisionConfig(enabled=True),
        backend=backend,
        evidence_path=None,
    )
    return backend, client


# ---------------------------------------------------------------------------
# 1. The book is the eight-entry material/meta/preparation surface
# ---------------------------------------------------------------------------


def test_imports_bind_the_isolated_copy() -> None:
    for module in (books, decision, dpts, decision_context):
        assert pathlib.Path(module.__file__).resolve().is_relative_to(
            PACKAGE_DIR.resolve()
        ), module.__file__


def test_book_covers_exactly_the_eight_active_entries() -> None:
    assert tuple(ACTIVE) == (
        "dp-w-type",
        "dp-pm-steer",
        "dp-w-check-task",
        "dp-QG",
        "dp-gate-approve",
        "dp-sign-key",
        "dp-auto",
        "dp-route",
    )
    for dp_id in ACTIVE:
        scaffold = books.scaffold_book(dp_id)
        assert scaffold["decision_point"] == dp_id
    assert len(RETIRED) == 25


def test_the_book_is_layered_as_material_meta_and_preparation() -> None:
    assert books.BOOK_SCHEMA_VERSION == 3
    assert "state" not in books.BOOK_TOP_LEVEL_KEYS
    assert set(books.BOOK_TOP_LEVEL_KEYS) == {
        "schema_version",
        "decision_point",
        "material",
        "preparation",
        "meta",
        "context",
        "notes",
    }
    for dp_id in ACTIVE:
        scaffold = books.scaffold_book(dp_id)
        assert set(scaffold) <= set(books.BOOK_TOP_LEVEL_KEYS)
        assert scaffold["schema_version"] == books.BOOK_SCHEMA_VERSION
        # The scaffold carries no local identity: meta is the producer's, not a
        # template invention.
        assert "meta" not in scaffold
        assert set(_flatten(scaffold["material"])) == set(
            dpts.REQUIRED_STATE_FIELDS[dp_id]
        )
        assert set(scaffold["preparation"]) == set(dpts.PREPARATION_KEYS)
        assert books.book_material(scaffold) == scaffold["material"]
        assert books.book_preparation(scaffold) == scaffold["preparation"]
        # Accessors copy: a caller cannot mutate the book through them.
        books.book_material(scaffold)["task_goal"] = "mutated"
        assert scaffold["material"].get("task_goal") != "mutated"


def test_preparation_carries_the_pm_prepared_basis_not_a_model_reason() -> None:
    assert dpts.PREPARATION_KEYS == ("basis_catalog", "prepared_at")
    assert dpts.BASIS_SOURCE == "pm-prepared"
    for dp_id in ACTIVE:
        scaffold = books.scaffold_book(dp_id)
        item = scaffold["preparation"]["basis_catalog"][0]
        assert set(item) == set(dpts.BASIS_ITEM_KEYS)
        # The model's same-call selection is never pre-filled by the book.
        assert "basis_id" not in scaffold["material"]
        assert "choice" not in scaffold["material"]


def test_every_required_material_path_reaches_the_model_projection() -> None:
    for dp_id in ACTIVE:
        sent = set(dpts.MODEL_STATE_FIELDS[dp_id])
        required = set(dpts.REQUIRED_STATE_FIELDS[dp_id])
        optional = set(dpts.OPTIONAL_STATE_FIELDS.get(dp_id, ()))
        assert required <= sent, f"{dp_id}: a required business fact would be dropped"
        assert optional <= sent, f"{dp_id}: an optional business fact would be dropped"
        for path in required | optional:
            assert path in dpts.STATE_FIELD_DESCRIPTIONS, f"{dp_id}/{path}"


def test_route_targets_and_auto_candidates_come_from_the_single_source() -> None:
    assert dpts.ENTRY_CHOICES["dp-route"] == tuple(
        entry for entry in ACTIVE if entry != "dp-route"
    )
    assert len(dpts.ENTRY_CHOICES["dp-route"]) == 7
    assert dpts.ENTRY_CHOICES["dp-auto"] == ()
    bounds = dpts.ENTRY_CANDIDATE_BOUNDS["dp-auto"]
    assert bounds["min"] == 2 and bounds["max"] is None
    assert bounds["id_scheme"] == "free"
    assert dpts.ENTRY_CANDIDATE_SOURCE["dp-auto"] == "pm-supplied:handling_options"


def test_issue_codes_keep_the_original_seven_and_add_the_new_layers() -> None:
    for original in (
        "book-schema",
        "book-state",
        "book-placeholder",
        "book-context",
        "book-evidence",
        "book-budget",
        "book-secret",
    ):
        assert original in books.ISSUE_CODES
    assert "book-preparation" in books.ISSUE_CODES
    assert "book-meta" in books.ISSUE_CODES


# ---------------------------------------------------------------------------
# 2. Legal material is accepted for every entry (AC-004 / AC-040 / AC-042)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_id", ACTIVE)
def test_book_accepts_legal_material_for_every_entry(
    dp_id: str, project: pathlib.Path
) -> None:
    issues = check(legal_book(dp_id), project)
    assert issues == [], rendered(issues)


def test_sign_key_keeps_the_four_parts_and_three_arrays(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-sign-key")
    issues = check(book, project)
    assert issues == [], rendered(issues)
    assert set(book["material"]) == {
        "delivery_goal",
        "actual_completion",
        "verification_evidence",
        "unfinished_impact",
    }
    assert "basis_catalog" not in book["material"]
    assert book["material"]["verification_evidence"]["unverified"]
    # [] is the real "none" for all three arrays.
    empty = legal_book("dp-sign-key")
    set_path(empty["material"], "verification_evidence.verified", [])
    set_path(empty["material"], "verification_evidence.unverified", [])
    set_path(empty["material"], "unfinished_impact", [])
    issues = check(empty, project)
    assert issues == [], rendered(issues)


def test_null_or_missing_sign_arrays_are_refused_with_the_material_path(
    project: pathlib.Path,
) -> None:
    for path in (
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    ):
        nulled = legal_book("dp-sign-key")
        set_path(nulled["material"], path, None)
        issues = check(nulled, project)
        assert has_issue(issues, f"material.{path}", "must be an array"), rendered(issues)
        assert "book-state" in codes(issues)
        assert [] != nulled["material"][path.split(".")[0]]


def test_gate_note_and_the_model_basis_stay_separate_business_inputs(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-gate-approve")
    assert check(book, project) == []
    note = book["material"]["pm_note"]
    assert set(note) == {"subject", "planned_action", "basis"}
    assert set(note["basis"]) == {"goal", "evidence", "budget", "authority"}
    basis = book["preparation"]["basis_catalog"][0]
    assert basis["text"] != note["subject"]
    assert set(basis) == set(dpts.BASIS_ITEM_KEYS)
    # The note is a required business input, not a free-form extra.
    broken = legal_book("dp-gate-approve")
    del broken["material"]["pm_note"]["basis"]["authority"]
    issues = check(broken, project)
    assert has_issue(
        issues, "material.pm_note.basis.authority", "must be a non-empty string"
    ), rendered(issues)


def test_auto_accepts_free_candidate_ids_and_any_count_above_one(
    project: pathlib.Path,
) -> None:
    many = legal_book("dp-auto")
    base = many["material"]["handling_options"][0]
    letters = "abcdefghij"
    many["material"]["handling_options"] = [
        {
            **base,
            "id": f"do-{letters[index]}",  # deliberately not c1..cN
            "label": f"候选方案 {letters[index]}",
        }
        for index in range(5)
    ]
    many["preparation"] = preparation_for("dp-auto", many["material"])
    assert check(many, project) == []

    one = legal_book("dp-auto")
    one["material"]["handling_options"] = one["material"]["handling_options"][:1]
    issues = check(one, project)
    assert has_issue(issues, "material.handling_options", "at least 2"), rendered(issues)
    assert "book-state" in codes(issues)

    duplicated = legal_book("dp-auto")
    duplicated["material"]["handling_options"][1]["id"] = (
        duplicated["material"]["handling_options"][0]["id"]
    )
    issues = check(duplicated, project)
    assert has_issue(
        issues, "material.handling_options[1].id", "unique"
    ), rendered(issues)

    for key in ("description", "consequence", "risk", "conditions"):
        incomplete = legal_book("dp-auto")
        incomplete["material"]["handling_options"][0][key] = ""
        issues = check(incomplete, project)
        assert has_issue(
            issues, f"material.handling_options[0].{key}", "non-empty string"
        ), rendered(issues)

    invented = legal_book("dp-auto")
    invented["material"]["handling_options"][0]["reason"] = "a model-free reason"
    issues = check(invented, project)
    assert has_issue(
        issues, "material.handling_options[0]", "unknown candidate keys"
    ), rendered(issues)


def test_route_is_material_only_and_cannot_carry_a_target_business_fact(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-route")
    assert check(book, project) == []
    assert set(book["material"]) == {
        "decision_actor",
        "decision_object",
        "question",
    }
    smuggled = legal_book("dp-route")
    smuggled["material"]["task_goal"] = "a target entry's business fact"
    issues = check(smuggled, project)
    assert has_issue(issues, "material.task_goal", "closed key set"), rendered(issues)


def test_vision_material_carries_only_the_real_image_fact(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-w-type")
    book["material"]["images_required"] = True
    assert check(book, project) == []
    wrong = legal_book("dp-w-type")
    wrong["material"]["images_required"] = "yes"
    issues = check(wrong, project)
    assert has_issue(issues, "material.images_required", "boolean"), rendered(issues)
    claim = legal_book("dp-w-type")
    claim["material"]["image_capability"] = "proven"
    issues = check(claim, project)
    assert has_issue(
        issues, "material.image_capability", "closed key set"
    ), rendered(issues)


def test_w_check_task_investigation_plan_is_optional_material(
    project: pathlib.Path,
) -> None:
    plain = legal_book("dp-w-check-task")
    assert check(plain, project) == []
    planned = legal_book("dp-w-check-task")
    planned["material"].update(
        {
            "investigation": {
                "unknown": "该 provider 是否支持图像输入",
                "evidence_source": "models.generated.ts 的 vision 字段",
                "budget": "剩余 10 分钟只读检查",
                "stop_condition": "读到明确字段即结束",
            }
        }
    )
    planned["notes"]["evidence"]["investigation.unknown"] = "notes.txt:1"
    planned["notes"]["evidence"]["investigation.evidence_source"] = "notes.txt:2"
    planned["notes"]["evidence"]["investigation.budget"] = "notes.txt:3"
    planned["notes"]["evidence"]["investigation.stop_condition"] = "notes.txt:4"
    assert check(planned, project) == []


def test_scaffold_is_loadable_but_never_sendable(
    tmp_path: pathlib.Path, project: pathlib.Path
) -> None:
    path = tmp_path / "scaffold.json"
    for dp_id in ACTIVE:
        scaffold = books.scaffold_book(dp_id)
        path.write_text(json.dumps(scaffold), encoding="utf-8")
        assert books.load_book(path) == scaffold
        issues = check(scaffold, project)
        assert issues, dp_id
        if dp_id == "dp-auto":
            # dp-auto's candidate array is a shape placeholder ([]): the
            # material gate refuses it first (illegal state before placeholders).
            assert "book-state" in codes(issues), (dp_id, rendered(issues))
        else:
            assert "book-placeholder" in codes(issues), (dp_id, rendered(issues))
        prepared, prep_issues = books.prepare_request(
            scaffold,
            project_dir=project,
            repo_root=project,
            limits=GENEROUS_LIMITS,
        )
        assert prepared is None
        assert prep_issues


# ---------------------------------------------------------------------------
# 3. Illegal state is refused first, with the material path (AC-012 / AC-043)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_id", ACTIVE)
def test_every_entry_refuses_illegal_material_before_the_preparation(
    dp_id: str, project: pathlib.Path
) -> None:
    book = legal_book(dp_id)
    first_required = dpts.REQUIRED_STATE_FIELDS[dp_id][0]
    set_path(book["material"], first_required, "")
    # The preparation is illegal too; the material defect must be the one
    # reported (an unjudgeable basis is not a second, invented defect).
    book["preparation"]["basis_catalog"][0]["text"] = ""
    book["preparation"]["prepared_at"] = "not-a-timestamp"
    issues = check(book, project)
    assert issues
    assert issues[0].path == f"material.{first_required}", rendered(issues)
    assert has_issue(issues, f"material.{first_required}", "missing or blank")
    assert not [issue for issue in issues if issue.path.startswith("preparation")]
    assert not [issue for issue in issues if issue.code == "book-preparation"]


@pytest.mark.parametrize("dp_id", ACTIVE)
def test_every_entry_refuses_unknown_material_keys(
    dp_id: str, project: pathlib.Path
) -> None:
    book = legal_book(dp_id)
    book["material"]["legacy_field"] = "old contract leftover"
    issues = check(book, project)
    assert has_issue(
        issues, "material.legacy_field", "closed key set"
    ), rendered(issues)


def test_identity_and_association_facts_belong_to_meta_not_to_material(
    project: pathlib.Path,
) -> None:
    for key in ("key", "task_key", "trigger_id", "schema_version", "decision_point"):
        book = legal_book("dp-w-type")
        book["material"][key] = "local identity"
        issues = check(book, project)
        assert has_issue(
            issues, f"material.{key}", "meta"
        ), (key, rendered(issues))


def test_missing_or_mistyped_material_layer_is_refused(
    project: pathlib.Path,
) -> None:
    missing = legal_book("dp-w-type")
    del missing["material"]
    issues = check(missing, project)
    assert has_issue(issues, "material", "required top-level key"), rendered(issues)

    wrong = legal_book("dp-w-type")
    wrong["material"] = ["task_goal"]
    issues = check(wrong, project)
    assert has_issue(issues, "material", "must be a JSON object"), rendered(issues)

    empty = legal_book("dp-w-type")
    empty["material"] = {}
    issues = check(empty, project)
    assert has_issue(issues, "material.task_goal", "missing or blank"), rendered(issues)


def test_preparation_is_required_and_its_defects_are_named(
    project: pathlib.Path,
) -> None:
    missing = legal_book("dp-w-type")
    del missing["preparation"]
    issues = check(missing, project)
    assert has_issue(issues, "preparation", "required"), rendered(issues)

    not_object = legal_book("dp-w-type")
    not_object["preparation"] = "prepared"
    issues = check(not_object, project)
    assert "book-schema" in codes(issues)

    empty_catalog = legal_book("dp-w-type")
    empty_catalog["preparation"]["basis_catalog"] = []
    issues = check(empty_catalog, project)
    assert has_issue(
        issues, "preparation.basis_catalog", "non-empty list"
    ), rendered(issues)
    assert "book-preparation" in codes(issues)

    no_timestamp = legal_book("dp-w-type")
    no_timestamp["preparation"]["prepared_at"] = "2026-10-27 08:00:00"
    issues = check(no_timestamp, project)
    assert has_issue(
        issues, "preparation.prepared_at", "ISO-8601"
    ), rendered(issues)

    unknown = legal_book("dp-w-type")
    unknown["preparation"]["note"] = "not a preparation key"
    issues = check(unknown, project)
    assert has_issue(
        issues, "preparation", "unknown preparation keys"
    ), rendered(issues)

    preselected = legal_book("dp-w-type")
    preselected["preparation"]["basis_id"] = "basis-real"
    issues = check(preselected, project)
    assert has_issue(
        issues, "preparation", "unknown preparation keys"
    ), rendered(issues)


def test_a_failure_reason_or_probability_is_not_a_prepared_basis(
    project: pathlib.Path,
) -> None:
    for key, value in (("reason", "provider failure"), ("probability", 0.4)):
        book = legal_book("dp-w-type")
        book["preparation"]["basis_catalog"][0][key] = value
        issues = check(book, project)
        assert has_issue(
            issues, "preparation.basis_catalog[0]", "not a prepared basis"
        ), rendered(issues)


def test_basis_must_reference_real_material_and_a_legal_choice(
    project: pathlib.Path,
) -> None:
    absent = legal_book("dp-w-type")
    absent["preparation"]["basis_catalog"][0]["material_refs"] = ["task_summary"]
    issues = check(absent, project)
    assert has_issue(
        issues,
        "preparation.basis_catalog[0].material_refs[0]",
        "does not reference a fact",
    ), rendered(issues)

    invented = legal_book("dp-w-type")
    invented["preparation"]["basis_catalog"][0]["applies_to"] = ["teleport"]
    issues = check(invented, project)
    assert has_issue(
        issues,
        "preparation.basis_catalog[0].applies_to[0]",
        "not a legal choice id",
    ), rendered(issues)

    duplicated = legal_book("dp-w-type")
    duplicated["preparation"]["basis_catalog"].append(
        copy.deepcopy(duplicated["preparation"]["basis_catalog"][0])
    )
    issues = check(duplicated, project)
    assert has_issue(
        issues, "preparation.basis_catalog[1].id", "unique"
    ), rendered(issues)


def test_auto_basis_applies_only_to_the_prepared_candidate_ids(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-auto")
    assert check(book, project) == []
    stale = legal_book("dp-auto")
    stale["preparation"]["basis_catalog"][0]["applies_to"] = ["c1"]
    issues = check(stale, project)
    assert has_issue(
        issues,
        "preparation.basis_catalog[0].applies_to[0]",
        "not a legal choice id",
    ), rendered(issues)


# ---------------------------------------------------------------------------
# 4. Retired ids and legacy book shapes (AC-002)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("retired_id", RETIRED)
def test_every_retired_id_is_refused_before_any_material_or_preparation(
    retired_id: str, project: pathlib.Path
) -> None:
    record = dpts.retired_dp(retired_id)
    assert record is not None
    book = legal_book("dp-w-type")
    book["decision_point"] = retired_id
    issues = check(book, project)
    assert len(issues) == 1, rendered(issues)
    issue = issues[0]
    assert issue.code == "book-schema"
    assert issue.path == "decision_point"
    assert "retired" in issue.detail
    assert record.disposition in issue.detail
    assert "not aliases" in issue.detail

    with pytest.raises(books.BookError) as excinfo:
        books.scaffold_book(retired_id)
    assert "retired" in str(excinfo.value)

    prepared, prep_issues = books.prepare_request(
        book,
        project_dir=project,
        repo_root=project,
        limits=GENEROUS_LIMITS,
    )
    assert prepared is None
    assert prep_issues and prep_issues[0].code == "book-schema"


def test_retired_ids_are_refused_before_the_replay_lookup(
    project: pathlib.Path,
) -> None:
    """The request entry refuses a retired id before replay/backend/credential."""

    def _explode(*_args: object) -> bool:
        raise AssertionError("the replay lookup ran for a retired id")

    material = material_for("dp-w-type")
    preparation = preparation_for("dp-w-type", material)
    rejected = 0
    for retired_id in RETIRED:
        backend, client = backend_with_answers("dp-w-type", material, preparation)
        result = client.request_prepared(
            retired_id,
            material,
            preparation,
            actor_role="pm",
            logical_id="t09-retired",
            replay_check=_explode,
        )
        assert result["available"] is False, retired_id
        assert result["business_decisions"] == 0, retired_id
        assert result["attempts"] == 0 and result["transport_attempts"] == 0
        assert backend.calls == [], retired_id
        rejected += 1
    assert rejected == 25
    # The same request under the active id does reach the transport.
    backend, client = backend_with_answers("dp-w-type", material, preparation)
    accepted = client.request_prepared(
        "dp-w-type", material, preparation, actor_role="pm"
    )
    assert accepted["available"] is True, accepted.get("detail")
    assert accepted["business_decisions"] == 1
    assert len(backend.calls) == 1


def test_the_legacy_state_book_is_refused_not_upgraded(
    tmp_path: pathlib.Path, project: pathlib.Path
) -> None:
    legacy = {
        "schema_version": 2,
        "decision_point": "dp-w-type",
        "state": material_for("dp-w-type"),
        "context": {},
        "notes": {"evidence": evidence_for("dp-w-type")},
    }
    issues = check(legacy, project)
    assert issues
    assert "book-schema" in codes(issues)
    detail = " ".join(issue.detail for issue in issues)
    assert "state" in detail

    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    with pytest.raises(books.BookError) as excinfo:
        books.load_book(path)
    assert "legacy" in str(excinfo.value).lower()
    prepared, prep_issues = books.prepare_request(
        path, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert prepared is None and prep_issues


def test_a_book_may_not_bring_its_own_question_set(
    project: pathlib.Path,
) -> None:
    for key in ("questions", "legacy_questions"):
        book = legal_book("dp-w-type")
        book[key] = {"triage_type": {"type": "choice", "choices": ["coding"]}}
        issues = check(book, project)
        if key == "questions":
            assert has_issue(
                issues, "questions", "may not carry its own question set"
            ), (key, rendered(issues))
        else:
            # Any other question-shaped key is simply not part of the book.
            assert has_issue(
                issues, "book", "unknown top-level keys"
            ), (key, rendered(issues))
    notes = legal_book("dp-w-type")
    notes["notes"]["legacy_questions"] = {"x": 1}
    issues = check(notes, project)
    assert has_issue(issues, "notes", "unknown notes keys"), rendered(issues)


# ---------------------------------------------------------------------------
# 5. Evidence, context, meta, budget and secrets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_id", ACTIVE)
def test_every_required_material_path_needs_real_evidence(
    dp_id: str, project: pathlib.Path
) -> None:
    book = legal_book(dp_id)
    path = dpts.REQUIRED_STATE_FIELDS[dp_id][0]
    del book["notes"]["evidence"][path]
    issues = check(book, project)
    assert has_issue(
        issues, f"notes.evidence.{path}", "missing evidence"
    ), rendered(issues)

    placeholder = legal_book(dp_id)
    placeholder["notes"]["evidence"][path] = books.EVIDENCE_PLACEHOLDER
    issues = check(placeholder, project)
    assert has_issue(
        issues, f"notes.evidence.{path}", "still the scaffold placeholder"
    ), rendered(issues)


def test_evidence_must_be_a_path_line_or_a_command(
    tmp_path: pathlib.Path, project: pathlib.Path
) -> None:
    for reference, fragment in (
        ("notes.txt:99", "> "),
        ("notes.txt", "expected 'path:line'"),
        ("../outside.txt:1", "outside the repository"),
        ("missing.txt:1", "does not exist"),
        ("cmd: ", "command evidence is empty"),
    ):
        book = legal_book("dp-w-type")
        book["notes"]["evidence"]["task_goal"] = reference
        issues = check(book, project)
        assert has_issue(issues, "notes.evidence.task_goal", fragment), (
            reference,
            rendered(issues),
        )
    accepted = legal_book("dp-w-type")
    accepted["notes"]["evidence"]["task_goal"] = "cmd: python -m pytest -q"
    assert check(accepted, project) == []
    absolute = legal_book("dp-w-type")
    absolute["notes"]["evidence"]["task_goal"] = f"{project / 'notes.txt'}:2"
    assert check(absolute, project) == []


def test_evidence_keys_are_closed_to_material_and_used_context_slots(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-w-type")
    book["notes"]["evidence"]["basis_catalog"] = "notes.txt:1"
    issues = check(book, project)
    assert has_issue(
        issues, "notes.evidence.basis_catalog", "neither a required field nor"
    ), rendered(issues)


def test_meta_is_local_and_role_eligibility_is_checked(
    project: pathlib.Path,
) -> None:
    assert books.META_KEYS == META_KEYS
    book = legal_book("dp-w-type")
    assert check(book, project) == []
    assert set(books.book_meta(book, project / "notes.txt")["evidence"]) == set(
        evidence_for("dp-w-type")
    )

    wrong_role = legal_book("dp-w-type")
    wrong_role["meta"]["actor_role"] = "worker"
    issues = check(wrong_role, project)
    assert has_issue(issues, "meta.actor_role", "role-forbidden"), rendered(issues)
    assert "book-meta" in codes(issues)

    unknown = legal_book("dp-w-type")
    unknown["meta"]["self_reported_role"] = "pm"
    issues = check(unknown, project)
    assert has_issue(issues, "meta", "unknown meta keys"), rendered(issues)

    empty = legal_book("dp-w-type")
    empty["meta"]["key"] = ""
    issues = check(empty, project)
    assert has_issue(issues, "meta.key", "non-empty string"), rendered(issues)

    # The Worker entry is not submittable by the PM and vice versa (AC-041).
    worker_entry = legal_book("dp-w-check-task")
    worker_entry["meta"]["actor_role"] = "pm"
    issues = check(worker_entry, project)
    assert has_issue(issues, "meta.actor_role", "role-forbidden"), rendered(issues)


def test_context_is_only_the_entry_s_own_slots_with_a_source(
    project: pathlib.Path,
) -> None:
    assert decision_context.slot_names_for("dp-QG") == ("error_excerpt",)
    book = legal_book("dp-QG")
    book["context"] = {"error_excerpt": "assert 1 == 2"}
    book["notes"]["evidence"]["context.error_excerpt"] = "notes.txt:1"
    assert check(book, project) == []

    no_source = legal_book("dp-QG")
    no_source["context"] = {"error_excerpt": "assert 1 == 2"}
    issues = check(no_source, project)
    assert has_issue(
        issues,
        "notes.evidence.context.error_excerpt",
        "every used slot needs a source",
    ), rendered(issues)

    not_its_slot = legal_book("dp-sign-key")
    not_its_slot["context"] = {"error_excerpt": "not this entry's slot"}
    not_its_slot["notes"]["evidence"]["context.error_excerpt"] = "notes.txt:1"
    issues = check(not_its_slot, project)
    assert has_issue(issues, "context.error_excerpt", "slot not allowed"), rendered(issues)

    retired_slot = legal_book("dp-QG")
    retired_slot["context"] = {"task_excerpt": "an old producer's slot"}
    retired_slot["notes"]["evidence"]["context.task_excerpt"] = "notes.txt:1"
    issues = check(retired_slot, project)
    assert has_issue(issues, "context.task_excerpt", "slot not allowed"), rendered(issues)


def test_over_budget_material_is_refused_never_truncated(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-w-type")
    issues = check(
        book,
        project,
        limits={
            "max_state_bytes": 16,
            "max_state_plus_question_tokens": 200_000,
            "max_total_tokens": 200_000,
        },
    )
    assert "book-budget" in codes(issues), rendered(issues)


def test_known_secrets_are_refused_without_echoing_them(
    project: pathlib.Path,
) -> None:
    known = "t09-known-value-xyz"
    redactor = decision.known_secret_redactor(extra_secrets=[known])
    book = legal_book("dp-w-type")
    book["material"]["task_goal"] = f"goal carrying {known}"
    issues = check(book, project, redactor=redactor)
    assert "book-secret" in codes(issues), rendered(issues)
    assert all(known not in issue.format() for issue in issues)

    basis = legal_book("dp-w-type")
    basis["preparation"]["basis_catalog"][0]["text"] = f"basis carrying {known}"
    issues = check(basis, project, redactor=redactor)
    assert has_issue(
        issues, "preparation.basis_catalog[0].text", "credential-looking text"
    ), rendered(issues)
    assert all(known not in issue.format() for issue in issues)

    shaped = legal_book("dp-w-type")
    shaped["material"]["task_requirements"] = "token sk-" + "a" * 24
    issues = check(shaped, project)
    assert "book-secret" in codes(issues), rendered(issues)


# ---------------------------------------------------------------------------
# 6. The book feeds the prepared request (producer -> consumer)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_id", ACTIVE)
def test_prepared_request_consumes_exactly_the_book_layers(
    dp_id: str, project: pathlib.Path
) -> None:
    book = legal_book(dp_id)
    prepared, issues = books.prepare_request(
        book, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert not issues, rendered(issues)
    assert prepared is not None
    material, preparation = prepared.layers()
    assert material == book["material"]
    assert preparation == book["preparation"]
    assert prepared.meta == book["meta"]

    backend, client = backend_with_answers(dp_id, material, preparation)
    result = client.request_prepared(
        dp_id, material, preparation, actor_role=book["meta"]["actor_role"]
    )
    assert result["available"] is True, (dp_id, result.get("detail"), result.get("issues"))
    assert result["business_decisions"] == 1
    assert len(backend.calls) == 1
    sent = backend.calls[0]["state"]
    assert set(sent) == {"material", "preparation"}
    assert sent["material"] == dpts.model_state_for(dp_id, material)
    assert sent["preparation"]["basis_catalog"] == preparation["basis_catalog"]
    # Local meta never rides along.
    for key in META_KEYS:
        assert key not in sent["material"]
        assert key not in sent["preparation"]
    assert "basis_id" not in sent["material"]
    assert result["basis_id"] == preparation["basis_catalog"][0]["id"]
    for forbidden in ("actual_action", "executed", "settled", "actor", "executor"):
        assert forbidden not in result or result.get(forbidden) in (None, ""), forbidden


@pytest.mark.parametrize("dp_id", ACTIVE)
def test_an_illegal_book_never_reaches_the_transport(
    dp_id: str, project: pathlib.Path
) -> None:
    book = legal_book(dp_id)
    set_path(book["material"], dpts.REQUIRED_STATE_FIELDS[dp_id][0], "")
    prepared, issues = books.prepare_request(
        book, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert prepared is None
    assert issues

    # Defence in depth: even a caller that ignored the refusal cannot spend a
    # model call on the same material/preparation.
    backend, client = backend_with_answers(
        dp_id, material_for(dp_id), preparation_for(dp_id)
    )
    result = client.request_prepared(
        dp_id, book["material"], book["preparation"], actor_role=book["meta"]["actor_role"]
    )
    assert result["available"] is False
    assert result["business_decisions"] == 0
    assert result["attempts"] == 0 and result["transport_attempts"] == 0
    assert backend.calls == []


def test_stdin_preparer_reads_one_request_and_refuses_a_bundle(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-w-type")
    prepared, issues = books.prepare_stdin_request(
        json.dumps(book),
        project_dir=project,
        repo_root=project,
        limits=GENEROUS_LIMITS,
    )
    assert not issues, rendered(issues)
    assert prepared is not None and prepared.decision_point == "dp-w-type"
    assert prepared.book_path is None and prepared.file_sha256 is None

    bundle = {"books": {"dp-w-type": legal_book("dp-w-type")}}
    prepared, issues = books.prepare_stdin_request(
        json.dumps(bundle),
        project_dir=project,
        repo_root=project,
        limits=GENEROUS_LIMITS,
    )
    assert prepared is None
    assert has_issue(issues, "book", "one request"), rendered(issues)

    prepared, issues = books.prepare_stdin_request(
        "{not json",
        project_dir=project,
        repo_root=project,
        limits=GENEROUS_LIMITS,
    )
    assert prepared is None
    assert has_issue(issues, "<stdin>", "not valid JSON"), rendered(issues)

    prepared, issues = books.prepare_stdin_request(
        legal_book("dp-w-type"),
        project_dir=project,
        repo_root=project,
        limits=GENEROUS_LIMITS,
    )
    assert not issues and prepared is not None


# ---------------------------------------------------------------------------
# 7. File/bundle surface and the book receipt writer
# ---------------------------------------------------------------------------


def test_check_book_file_reports_each_book_separately(
    tmp_path: pathlib.Path, project: pathlib.Path
) -> None:
    good = legal_book("dp-sign-key")
    bad = legal_book("dp-w-type")
    del bad["material"]["task_goal"]
    path = tmp_path / "books.json"
    path.write_text(
        json.dumps({"books": {"sign": good, "wtype": bad}}), encoding="utf-8"
    )
    report = books.check_book_file(
        path, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert report.ok is False
    by_label = {entry["label"]: entry for entry in report.books}
    assert by_label["sign"]["ok"] is True
    assert by_label["wtype"]["ok"] is False
    assert any(
        issue.path == "material.task_goal" for issue in by_label["wtype"]["issues"]
    )
    assert report.sha256 == books.book_sha256(path)
    assert report.as_dict()["ok"] is False

    legacy = tmp_path / "legacy-bundle.json"
    legacy.write_text(json.dumps([{"schema_version": 2, "state": {}}]), encoding="utf-8")
    report = books.check_book_file(
        legacy, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert report.ok is False

    prepared, issues = books.prepare_request(
        path, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert prepared is None and issues
    single = tmp_path / "one.json"
    single.write_text(json.dumps(legal_book("dp-sign-key")), encoding="utf-8")
    prepared, issues = books.prepare_request(
        single, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert not issues, rendered(issues)
    assert prepared is not None
    assert prepared.book_path == str(single)
    assert prepared.file_sha256 == books.book_sha256(single)


def test_the_book_receipt_writer_records_the_real_layers(
    tmp_path: pathlib.Path, project: pathlib.Path
) -> None:
    book = legal_book("dp-sign-key")
    path = project / "book.json"
    path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
    report = books.check_book_file(
        path, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert report.ok, [issue.format() for issue in report.issues]

    meta = books.book_meta(book, path, root=project)
    assert meta["path"] == "book.json"
    assert meta["file_sha256"] == books.book_sha256(path)
    assert meta["evidence"] == book["notes"]["evidence"]

    receipt = books.append_book_receipt(
        project,
        meta=meta,
        state=books.book_state(book),
        preparation=books.book_preparation(book),
        available=True,
        decision_id="dp-sign-key:t09",
        transport="fake",
        now="2026-10-27T08:30:00Z",
    )
    rows = [
        json.loads(line)
        for line in receipt.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["ts"] == "2026-10-27T08:30:00Z"
    assert row["dp"] == "dp-sign-key"
    assert row["decision_id"] == "dp-sign-key:t09"
    assert row["book_path"] == "book.json"
    assert row["file_sha256"] == books.book_sha256(path)
    assert row["evidence"] == book["notes"]["evidence"]
    assert row["material_digest"] and row["preparation_digest"]
    assert row["available"] is True and row["transport"] == "fake"
    assert row["state_digest"] == row["material_digest"]
    # The row is a reference, not a second copy of the business material.
    assert "material" not in row and "preparation" not in row
    body = receipt.read_text(encoding="utf-8")
    assert book["material"]["delivery_goal"] not in body


def test_the_observation_seam_refuses_a_book_without_the_book_layers(
    tmp_path: pathlib.Path,
) -> None:
    """The registered validator is the book contract (fail-closed, T05b F2)."""
    # A self-contained fixture project (its own repo marker) so the evidence
    # anchor is this fixture, never the surrounding checkout.
    root = tmp_path / "project"
    (root / ".git").mkdir(parents=True)
    (root / "notes.txt").write_text("synthetic evidence line\n" * 6, encoding="utf-8")
    book = legal_book("dp-sign-key")
    assert books.observation_book_issues(book, root) == ()
    legacy = {"schema_version": 2, "state": book["material"]}
    issues = books.observation_book_issues(legacy, root)
    assert issues
    paths = [path for path, _detail in issues]
    assert any(path == "state" or path.startswith("book") for path in paths), paths


def test_the_book_never_reads_the_live_transport_config(
    project: pathlib.Path,
) -> None:
    """The book is an offline artifact: a live `.mw/decide.json` never changes it."""
    (project / ".mw").mkdir()
    (project / ".mw" / "decide.json").write_text(
        json.dumps({"enabled": True, "max_state_bytes": 1}), encoding="utf-8"
    )
    book = legal_book("dp-w-type")
    issues = books.check_book(book, project_dir=project, repo_root=project)
    assert issues == [], rendered(issues)
    strict = books.check_book(
        book,
        project_dir=project,
        repo_root=project,
        limits={
            "max_state_bytes": 16,
            "max_state_plus_question_tokens": 200_000,
            "max_total_tokens": 200_000,
        },
    )
    assert "book-budget" in codes(strict), rendered(strict)


def test_book_state_merges_only_the_used_context_slots(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-QG")
    book["context"] = {"error_excerpt": "assert 1 == 2"}
    book["notes"]["evidence"]["context.error_excerpt"] = "notes.txt:1"
    state = books.book_state(book)
    assert state["context"] == {"error_excerpt": "assert 1 == 2"}
    assert set(state) == set(book["material"]) | {"context"}
    empty = books.book_state(books.scaffold_book("dp-QG"))
    assert "context" not in empty
    assert set(empty) == set(dpts.REQUIRED_STATE_FIELDS["dp-QG"])


# ---------------------------------------------------------------------------
# 8. R2 boundary regressions (four reproduced PM fixture roots)
#
# 1. stdin carries exactly one book object: a parsed non-object (null/array/
#    bool/int/float, and a JSON string that names a real book file) is a
#    ``book-schema`` refusal, never a filesystem lookup and never an escaped
#    TypeError. ``prepare_request(path)`` stays the only file authority.
# 2. an unloadable file keeps a complete, serializable ``BookReport``
#    (``ok=false`` + the concrete issue), so ``as_dict()`` never raises.
# 3. schema refusals never echo a known secret; the details stay specific.
# 4. ``schema_version`` must be the real non-bool integer 3, not 3.0.
# ---------------------------------------------------------------------------

#: Synthetic known-secret sentinel of this card (never a real credential).
KNOWN_SECRET = "pm-known-opaque-business-secret"


def _no_file_authority(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("a non-object stdin payload must never load a file")


@pytest.mark.parametrize(
    ("value", "json_kind"),
    [
        (None, "null"),
        ([], "array"),
        ([{"schema_version": 3, "decision_point": "dp-w-type"}], "array"),
        (True, "boolean"),
        (17, "integer"),
        (3.14, "number"),
    ],
    ids=["null", "empty-array", "array-of-books", "boolean", "integer", "number"],
)
def test_stdin_refuses_every_non_object_json_shape_as_a_schema_issue(
    value: object, json_kind: str, project: pathlib.Path
) -> None:
    with mock.patch.object(books, "load_book", _no_file_authority), mock.patch.object(
        books, "_read_json", _no_file_authority
    ), mock.patch.object(books, "book_sha256", _no_file_authority):
        prepared, issues = books.prepare_stdin_request(
            json.dumps(value),
            project_dir=project,
            repo_root=project,
            limits=GENEROUS_LIMITS,
        )
    assert prepared is None
    assert issues, json_kind
    assert issues[0].code == "book-schema", rendered(issues)
    assert has_issue(issues, "book", "one book object"), rendered(issues)
    assert json_kind in issues[0].detail, rendered(issues)
    # Nothing on disk was consulted or written (no ledger, no receipt).
    assert sorted(path.name for path in project.iterdir()) == ["notes.txt"]


def test_stdin_json_string_is_data_and_never_a_file_path(
    project: pathlib.Path,
) -> None:
    book = legal_book("dp-w-type")
    path = project / "book.json"
    path.write_text(json.dumps(book), encoding="utf-8")
    with mock.patch.object(books, "load_book", _no_file_authority), mock.patch.object(
        books, "_read_json", _no_file_authority
    ), mock.patch.object(books, "book_sha256", _no_file_authority):
        prepared, issues = books.prepare_stdin_request(
            json.dumps(str(path)),
            project_dir=project,
            repo_root=project,
            limits=GENEROUS_LIMITS,
        )
    assert prepared is None
    assert issues and issues[0].code == "book-schema", rendered(issues)
    assert has_issue(issues, "book", "one book object"), rendered(issues)
    # The file API remains the only path authority, and it still works.
    prepared, issues = books.prepare_request(
        path, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert not issues, rendered(issues)
    assert prepared is not None
    assert prepared.book_path == str(path)
    assert prepared.file_sha256 == books.book_sha256(path)


def test_an_invalid_book_file_report_is_serializable_and_still_failed(
    tmp_path: pathlib.Path, project: pathlib.Path
) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "decision_point": "dp-w-type",
                "state": material_for("dp-w-type"),
            }
        ),
        encoding="utf-8",
    )
    report = books.check_book_file(
        legacy, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    data = report.as_dict()
    assert data["ok"] is False
    assert data["issues"] and data["issues"][0]["code"] == "book-schema"
    assert [entry["ok"] for entry in data["books"]] == [False]
    assert data["books"][0]["issues"] == data["issues"]
    assert data["books"][0]["label"] is None
    assert data["sha256"] == books.book_sha256(legacy)
    assert report.ok is False and report.issues

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    data = books.check_book_file(
        broken, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    ).as_dict()
    assert data["ok"] is False
    assert data["books"][0]["ok"] is False
    assert "not valid JSON" in data["issues"][0]["detail"]


@pytest.mark.parametrize(
    "layer",
    [
        "unknown-top-key",
        "unknown-notes-key",
        "bad-version",
        "unknown-dp",
        "unknown-meta-key",
        "unknown-context-key",
    ],
)
def test_schema_refusals_never_echo_a_known_secret(
    layer: str, project: pathlib.Path
) -> None:
    known = KNOWN_SECRET
    redactor = decision.known_secret_redactor(extra_secrets=[known])
    book = legal_book("dp-w-type")
    if layer == "unknown-top-key":
        book[known] = "x"
        expected = ("book-schema", "book", "unknown top-level keys")
    elif layer == "unknown-notes-key":
        book["notes"][known] = "x"
        expected = ("book-schema", "notes", "unknown notes keys")
    elif layer == "bad-version":
        book["schema_version"] = known
        expected = ("book-schema", "schema_version", "must be 3")
    elif layer == "unknown-dp":
        book["decision_point"] = known
        expected = ("book-schema", "decision_point", "unknown decision point id")
    elif layer == "unknown-meta-key":
        book["meta"][known] = "x"
        expected = ("book-meta", "meta", "unknown meta keys")
    else:
        book["context"] = {known: "x"}
        expected = ("book-context", "context.<key>", "slot not allowed")
    issues = check(book, project, redactor=redactor)
    code, path, fragment = expected
    assert issues, layer
    assert has_issue(issues, path, fragment), (layer, rendered(issues))
    assert code in codes(issues), (layer, rendered(issues))
    assert all(known not in issue.format() for issue in issues), rendered(issues)


def test_a_schema_refusal_on_load_never_echoes_a_known_secret(
    tmp_path: pathlib.Path, project: pathlib.Path
) -> None:
    known = KNOWN_SECRET
    redactor = decision.known_secret_redactor(extra_secrets=[known])
    book = legal_book("dp-w-type")
    book[known] = "x"
    path = tmp_path / "secret-top-key.json"
    path.write_text(json.dumps(book), encoding="utf-8")
    with pytest.raises(books.BookError) as excinfo:
        books.load_book(path, redactor=redactor)
    message = str(excinfo.value)
    assert known not in message
    assert "unknown top-level keys" in message
    report = books.check_book_file(
        path,
        project_dir=project,
        repo_root=project,
        limits=GENEROUS_LIMITS,
        redactor=redactor,
    )
    assert report.ok is False
    assert all(known not in issue.format() for issue in report.issues)


def test_schema_details_stay_specific_for_non_secret_values(
    project: pathlib.Path,
) -> None:
    unknown_dp = legal_book("dp-w-type")
    unknown_dp["decision_point"] = "dp-not-a-real-entry"
    assert has_issue(
        check(unknown_dp, project), "decision_point", "dp-not-a-real-entry"
    ), rendered(check(unknown_dp, project))

    old_version = legal_book("dp-w-type")
    old_version["schema_version"] = 2
    assert has_issue(
        check(old_version, project), "schema_version", "must be 3"
    ), rendered(check(old_version, project))

    extra_note = legal_book("dp-w-type")
    extra_note["notes"]["extra_note"] = "x"
    assert has_issue(
        check(extra_note, project), "notes", "unknown notes keys"
    ), rendered(check(extra_note, project))


@pytest.mark.parametrize(
    "value",
    [3.0, 2, "3", True, None, [3]],
    ids=["float-3.0", "int-2", "string-3", "bool-true", "null", "array"],
)
def test_schema_version_must_be_the_real_non_bool_integer_three(
    value: object, tmp_path: pathlib.Path, project: pathlib.Path
) -> None:
    book = legal_book("dp-w-type")
    book["schema_version"] = value
    issues = check(book, project)
    assert has_issue(issues, "schema_version", "must be 3"), rendered(issues)
    assert "book-schema" in codes(issues)
    prepared, prep_issues = books.prepare_request(
        book, project_dir=project, repo_root=project, limits=GENEROUS_LIMITS
    )
    assert prepared is None and prep_issues
    path = tmp_path / "version.json"
    path.write_text(json.dumps(book), encoding="utf-8")
    with pytest.raises(books.BookError) as excinfo:
        books.load_book(path)
    assert "schema_version" in str(excinfo.value)
    # The legal control: the real integer 3 still passes the schema gate.
    assert "schema_version" not in {
        issue.path for issue in check(legal_book("dp-w-type"), project)
    }

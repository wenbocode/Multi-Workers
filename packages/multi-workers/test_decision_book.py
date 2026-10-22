"""test_decision_book.py — W7: 决策本（book new / book check / --book 先验后发）。

Hermetic pytest suite (key mw-decision-substitution, spec §14 AC-018/AC-019/AC-021):

* ``decision_book.scaffold_book`` —— 骨架的键集合与顺序 == 注册表
  ``required_state_fields``（24 个 dp 全跑），值一律是类型占位符，
  ``notes.evidence`` 为每个必填字段留待填项，``context`` 只留该 dp 的槽位；
* ``decision_book.load_book`` —— JSON 可解析 + 顶层键封闭 + ``schema_version``；
* ``decision_book.check_book`` —— 七类失败码（封闭键集合、占位符、上下文、证据、
  预算、密钥）；
* ``mw decide book new/check`` 与 ``mw decide ask/run --book`` —— 先验后发，
  失败零 HTTP，成功落 ``book_path`` + ``file_sha256`` + ``notes.evidence``。

Everything runs under ``tmp_path``; the transport is a ``decision.FakeBackend``
and the credential resolvers are patched, so no network call or ~/.pi credential
is ever touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

DP3 = "dp3-worker-clarify"
DP6 = "dp6-qg-verdict"
TEMPLATE = pathlib.Path(__file__).parent / "decide_book_template.json"
CRED_ENV_VARS = ("TIMI_API_KEY",)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(decision_backends, "resolve_timi_api_key", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Helpers: a repo-like root, a legal book, CLI argv namespaces
# ---------------------------------------------------------------------------


def make_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """A repo-like root: ``.git`` (evidence anchor) + a 5-line evidence file."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "notes.txt").write_text(
        "line1\nline2\nline3\nline4\nline5\n", encoding="utf-8", newline="\n"
    )
    return root


def questions_version(dp_id: str = DP3) -> str:
    return str({p["id"]: p for p in dpts.registry_snapshot()["points"]}[dp_id]["questions_version"])


def valid_state(dp_id: str = DP3) -> dict:
    return {
        "schema_version": 2,
        "decision_point": dp_id,
        "key": "mw-decision-substitution",
        "phase": "EXECUTE",
        "task_type": "coding",
        "risk": "mid",
        "risk_source": "pm-label",
        "authority_tier": "P2",
        "task_summary": "worker asks which file holds the decide-points table",
        "questions_version": questions_version(dp_id),
        "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
        "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
    }


def valid_book(dp_id: str = DP3, *, state: dict | None = None, evidence: dict | None = None) -> dict:
    required = books.required_state_paths(dp_id)
    slots = books.context_slots(dp_id)
    context: dict = {}
    context_evidence: dict = {}
    if "change_summary" in slots:
        context["change_summary"] = "one file changed"
        context_evidence["context.change_summary"] = "notes.txt:1"
    if "candidate_snippets" in slots:
        context["candidate_snippets"] = [
            {"id": "c1", "path": "notes.txt", "line": 2, "text": "line2", "source": "notes.txt:2"}
        ]
        context_evidence["context.candidate_snippets"] = "notes.txt:2"
    if evidence is None:
        evidence = {path: "notes.txt:1" for path in required}
        evidence.update(context_evidence)
    return {
        "schema_version": 2,
        "decision_point": dp_id,
        "state": dict(valid_state(dp_id) if state is None else state),
        "context": context,
        "notes": {"evidence": evidence},
    }


def codes(issues) -> list[str]:
    return [issue.code for issue in issues]


def paths(issues, code: str) -> list[str]:
    return [issue.path for issue in issues if issue.code == code]


def write_book(root: pathlib.Path, book: dict, name: str = "book.json") -> pathlib.Path:
    path = root / name
    path.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def _args(action: str, root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {"subcommand": "decide", "decide_action": action, "project": str(root), "json": False}
    base.update(kw)
    return argparse.Namespace(**base)


def book_args(root: pathlib.Path, action: str, **kw) -> argparse.Namespace:
    return _args("book", root, book_action=action, **kw)


def run_args(root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {"json": True, "request_file": None, "dp": None, "book": None}
    base.update(kw)
    return _args("run", root, **base)


def ask_args(root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "state": None,
        "state_file": None,
        "noul": [],
        "noul_criteria": [],
        "choice": [],
        "score": [],
        "model": None,
        "book": None,
        "json": True,
    }
    base.update(kw)
    return _args("ask", root, **base)


def enable_decide(root: pathlib.Path) -> None:
    path = root / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": True}), encoding="utf-8", newline="\n")


def inject_backend(monkeypatch: pytest.MonkeyPatch, backend) -> None:
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)


def dp3_answers() -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers={
            "answer_kind": {"value": "fact", "confidence": 0.93},
            "answerable": {"value": 0.9},
            "candidate": {"value": "c1", "confidence": 0.91},
        },
        latency_ms=9,
        detail="",
    )


# ---------------------------------------------------------------------------
# scaffold_book: 键集合/顺序/占位符/证据/上下文全部由配置决定
# ---------------------------------------------------------------------------


def test_scaffold_state_key_set_matches_registry_for_every_dp() -> None:
    for point in dpts.registry_snapshot()["points"]:
        dp_id = point["id"]
        book = books.scaffold_book(dp_id)
        flat = set(books._flatten(book["state"]))
        required = set(books.required_state_paths(dp_id))
        assert required <= flat, dp_id
        # 封闭集合：除了注册表必填，只允许三个通用身份字段（builder 对每个 dp 都写）。
        assert flat - required <= set(books.STRUCTURAL_STATE_FIELDS), dp_id


def test_scaffold_state_order_matches_registry() -> None:
    book = books.scaffold_book(DP3)
    assert list(book["state"]) == [
        "schema_version",
        "decision_point",
        "key",
        "phase",
        "task_type",
        "risk",
        "risk_source",
        "authority_tier",
        "task_summary",
        "questions_version",
        "ambiguity",
        "local_candidates",
    ]
    assert list(book["state"]["ambiguity"]) == ["kind", "question"]


def test_scaffold_prefills_structural_fields_and_questions_version() -> None:
    for dp_id in (DP3, DP6):
        book = books.scaffold_book(dp_id)
        assert book["state"]["schema_version"] == 2
        assert book["state"]["decision_point"] == dp_id
        assert book["state"]["questions_version"] == questions_version(dp_id)
        assert book["decision_point"] == dp_id
        assert book["schema_version"] == 2


def test_scaffold_uses_type_placeholders() -> None:
    book = books.scaffold_book("dp2-checkpoint-split")
    state = book["state"]
    assert state["risk"].startswith("<string: ")
    assert state["progress"]["elapsed_minutes"] == -1
    assert state["progress"]["artifact_present"] is False
    assert books.scaffold_book("dp1-dispatch-type")["state"]["scope"]["file_extensions"] == []


def test_scaffold_evidence_has_one_entry_per_required_field() -> None:
    book = books.scaffold_book(DP3)
    evidence = book["notes"]["evidence"]
    assert list(evidence) == list(books.required_state_paths(DP3))
    assert all(value == books.EVIDENCE_PLACEHOLDER for value in evidence.values())


def test_scaffold_context_only_holds_the_dp_slots() -> None:
    for dp_id in ("dp1-dispatch-type", DP3, DP6, "dp5-test-triage"):
        book = books.scaffold_book(dp_id)
        assert list(book["context"]) == list(books.context_slots(dp_id))
    # 未使用的槽位是空值（与 decision_context 同形），不是占位包装。
    assert books.scaffold_book(DP3)["context"] == {"change_summary": "", "candidate_snippets": []}


def test_scaffold_top_level_keys_are_the_closed_set() -> None:
    book = books.scaffold_book(DP3)
    assert set(book) == set(books.BOOK_TOP_LEVEL_KEYS)
    # 决策本只写输入：任何「预期答案」式的键都不存在。
    assert not {"answers", "answer", "expected", "expected_answer"} & set(book)


def test_scaffold_unknown_dp_raises_book_schema() -> None:
    with pytest.raises(books.BookError) as excinfo:
        books.scaffold_book("dp99-nope")
    assert excinfo.value.issue.code == "book-schema"
    assert excinfo.value.issue.path == "decision_point"


# ---------------------------------------------------------------------------
# load_book / load_books
# ---------------------------------------------------------------------------


def test_load_book_roundtrips_the_scaffold(tmp_path: pathlib.Path) -> None:
    path = write_book(tmp_path, books.scaffold_book(DP3))
    assert books.load_book(path) == books.scaffold_book(DP3)


def test_load_book_rejects_invalid_json(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(books.BookError) as excinfo:
        books.load_book(path)
    assert excinfo.value.issue.code == "book-schema"
    assert "not valid JSON" in excinfo.value.issue.detail


def test_load_book_rejects_non_object(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(books.BookError):
        books.load_book(path)


def test_load_book_rejects_unknown_top_level_key(tmp_path: pathlib.Path) -> None:
    book = books.scaffold_book(DP3)
    book["questions"] = {}
    path = write_book(tmp_path, book)
    with pytest.raises(books.BookError) as excinfo:
        books.load_book(path)
    assert "questions" in excinfo.value.issue.detail


def test_load_book_rejects_wrong_schema_version(tmp_path: pathlib.Path) -> None:
    book = books.scaffold_book(DP3)
    book["schema_version"] = 1
    path = write_book(tmp_path, book)
    with pytest.raises(books.BookError) as excinfo:
        books.load_book(path)
    assert excinfo.value.issue.path == "schema_version"


def test_load_book_rejects_unknown_decision_point(tmp_path: pathlib.Path) -> None:
    book = books.scaffold_book(DP3)
    book["decision_point"] = "dp99-nope"
    path = write_book(tmp_path, book)
    with pytest.raises(books.BookError) as excinfo:
        books.load_book(path)
    assert "dp99-nope" in excinfo.value.issue.detail


def test_load_books_reads_a_bundle(tmp_path: pathlib.Path) -> None:
    doc = {"books": {DP3: books.scaffold_book(DP3), DP6: books.scaffold_book(DP6)}}
    path = write_book(tmp_path, doc)
    loaded = books.load_books(path)
    assert [label for label, _book in loaded] == [DP3, DP6]


# ---------------------------------------------------------------------------
# check_book: 合法 / 封闭键集合 / 类型 / 占位符
# ---------------------------------------------------------------------------


def test_check_book_passes_a_legal_book(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    assert books.check_book(valid_book(), project_dir=root) == []


def test_check_book_flags_unreplaced_placeholders() -> None:
    issues = books.check_book(books.scaffold_book(DP3))
    assert "book-placeholder" in codes(issues)
    assert "state.key" in paths(issues, "book-placeholder")
    assert "state.local_candidates" in paths(issues, "book-placeholder")


def test_check_book_flags_missing_required_field(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    del book["state"]["task_summary"]
    issues = books.check_book(book, project_dir=root)
    assert "state.task_summary" in paths(issues, "book-state")
    assert any("missing required field" in issue.detail for issue in issues)


def test_check_book_flags_extra_state_key(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["state"]["expected_answer"] = "split"
    issues = books.check_book(book, project_dir=root)
    assert "state.expected_answer" in paths(issues, "book-state")
    assert any("closed key set" in issue.detail for issue in issues)


def test_check_book_flags_extra_nested_state_key(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["state"]["ambiguity"]["expected"] = "intent"
    issues = books.check_book(book, project_dir=root)
    assert "state.ambiguity.expected" in paths(issues, "book-state")


def test_check_book_flags_type_mismatch(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["state"]["risk"] = 3
    issues = books.check_book(book, project_dir=root)
    assert "state.risk" in paths(issues, "book-state")
    assert any("expected string" in issue.detail for issue in issues)


def test_check_book_flags_negative_integer_placeholder(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book("dp2-checkpoint-split")
    book["state"]["progress"] = {
        "elapsed_minutes": -1,
        "budget_minutes": 30,
        "phases_done": 2,
        "phases_total": 4,
        "artifact_present": False,
    }
    issues = books.check_book(book, project_dir=root)
    assert "book-placeholder" in codes(issues)
    assert "state.progress.elapsed_minutes" in paths(issues, "book-placeholder")
    # 布尔 false 是真实取值，不是占位符。
    assert "state.progress.artifact_present" not in paths(issues, "book-placeholder")


def test_check_book_allows_structural_fields_for_a_dp_without_required_fields() -> None:
    book = {
        "schema_version": 2,
        "decision_point": DP6,
        "state": {
            "schema_version": 2,
            "decision_point": DP6,
            "questions_version": questions_version(DP6),
        },
        "notes": {"evidence": {}},
    }
    assert books.check_book(book) == []


def test_check_book_flags_questions_version_drift(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["state"]["questions_version"] = "q-deadbeef"
    issues = books.check_book(book, project_dir=root)
    assert "state.questions_version" in paths(issues, "book-state")


def test_check_book_flags_decision_point_mismatch(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["state"]["decision_point"] = "dp6-qg-verdict"
    issues = books.check_book(book, project_dir=root)
    assert "state.decision_point" in paths(issues, "book-state")


def test_check_book_flags_a_scalar_where_an_object_is_required(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["state"]["ambiguity"] = "fact"
    issues = books.check_book(book, project_dir=root)
    assert "state.ambiguity" in paths(issues, "book-state")
    assert "state.ambiguity.kind" in paths(issues, "book-state")


def test_check_book_flags_schema_level_problems() -> None:
    book = books.scaffold_book(DP3)
    book["questions"] = {}
    book["state"] = "not-an-object"
    issues = books.check_book(book)
    assert "book" in paths(issues, "book-schema")
    assert "state" in paths(issues, "book-schema")


# ---------------------------------------------------------------------------
# check_book: context 槽位
# ---------------------------------------------------------------------------


def test_check_book_flags_unknown_context_slot(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book(DP6, state={"schema_version": 2, "decision_point": DP6})
    book["context"] = {"task_excerpt": "card body"}
    issues = books.check_book(book, project_dir=root)
    assert "context.task_excerpt" in paths(issues, "book-context")


def test_check_book_flags_a_used_slot_without_source(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    del book["notes"]["evidence"]["context.change_summary"]
    issues = books.check_book(book, project_dir=root)
    assert "notes.evidence.context.change_summary" in paths(issues, "book-context")


def test_check_book_flags_an_over_long_slot(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    limit = books.context_slot_spec("change_summary").limit
    book["context"]["change_summary"] = "x" * (limit + 1)
    issues = books.check_book(book, project_dir=root)
    assert "context.change_summary" in paths(issues, "book-context")
    assert any(f"limit {limit}" in issue.detail for issue in issues)


def test_check_book_flags_too_many_candidate_snippets(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    limit = books.context_slot_spec("candidate_snippets").limit
    book["context"]["candidate_snippets"] = [
        {"text": "line1", "source": "notes.txt:1"} for _index in range(limit + 1)
    ]
    issues = books.check_book(book, project_dir=root)
    assert "context.candidate_snippets" in paths(issues, "book-context")


def test_check_book_flags_a_candidate_item_without_source(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["context"]["candidate_snippets"] = [{"text": "line1"}]
    issues = books.check_book(book, project_dir=root)
    assert "context.candidate_snippets[0].source" in paths(issues, "book-context")


def test_check_book_ignores_empty_context_slots(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    # scaffold 形状（空串/空数组）= 未使用，不算失败。
    book["context"] = books.scaffold_context(DP3)
    assert books.check_book(book, project_dir=root) == []


# ---------------------------------------------------------------------------
# check_book: 证据
# ---------------------------------------------------------------------------


def test_check_book_flags_missing_evidence_for_a_required_field(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    del book["notes"]["evidence"]["task_summary"]
    issues = books.check_book(book, project_dir=root)
    assert "notes.evidence.task_summary" in paths(issues, "book-evidence")


def test_check_book_flags_an_out_of_range_line(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["notes"]["evidence"]["task_summary"] = "notes.txt:99"
    issues = books.check_book(book, project_dir=root)
    assert "notes.evidence.task_summary" in paths(issues, "book-evidence")
    assert any("99 >" in issue.detail for issue in issues)


def test_check_book_flags_a_missing_evidence_file(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["notes"]["evidence"]["task_summary"] = "missing.txt:1"
    issues = books.check_book(book, project_dir=root)
    assert any("does not exist" in issue.detail for issue in issues)


def test_check_book_flags_an_evidence_path_outside_the_repository(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("a\nb\n", encoding="utf-8")
    book = valid_book()
    book["notes"]["evidence"]["task_summary"] = f"{outside.as_posix()}:1"
    issues = books.check_book(book, project_dir=root)
    assert any("outside the repository" in issue.detail for issue in issues)


def test_check_book_accepts_command_evidence(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["notes"]["evidence"]["questions_version"] = "rg -n 'questions_version' decision_points.py"
    book["notes"]["evidence"]["schema_version"] = "notes.txt:1-2"
    assert books.check_book(book, project_dir=root) == []


def test_check_book_flags_placeholder_evidence(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["notes"]["evidence"]["task_summary"] = books.EVIDENCE_PLACEHOLDER
    issues = books.check_book(book, project_dir=root)
    assert "notes.evidence.task_summary" in paths(issues, "book-placeholder")


# ---------------------------------------------------------------------------
# check_book: 预算 + 密钥
# ---------------------------------------------------------------------------


def test_check_book_flags_the_state_plus_question_budget(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    issues = books.check_book(
        book,
        project_dir=root,
        limits={"max_state_plus_question_tokens": 10, "max_total_tokens": 65536},
    )
    assert "state" in paths(issues, "book-budget")
    assert any("max_state_plus_question_tokens=10" in issue.detail for issue in issues)


def test_check_book_flags_the_total_budget(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    issues = books.check_book(
        book,
        project_dir=root,
        limits={"max_state_plus_question_tokens": 32768, "max_total_tokens": 10},
    )
    assert any("max_total_tokens=10" in issue.detail for issue in issues)


def test_check_book_flags_credential_looking_text(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["state"]["task_summary"] = "use sk-abcdef123456 when calling the endpoint"
    issues = books.check_book(book, project_dir=root)
    assert "state.task_summary" in paths(issues, "book-secret")


def test_check_book_flags_a_credential_in_the_context(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    book = valid_book()
    book["context"]["change_summary"] = "token sk-abcdef123456"
    issues = books.check_book(book, project_dir=root)
    assert "context.change_summary" in paths(issues, "book-secret")


# ---------------------------------------------------------------------------
# check_book_file / CLI: book new + book check
# ---------------------------------------------------------------------------


def test_check_book_file_report_structure(tmp_path: pathlib.Path) -> None:
    root = make_root(tmp_path)
    path = write_book(root, books.scaffold_book(DP3))
    report = books.check_book_file(path, project_dir=root)
    payload = report.as_dict()
    assert payload["path"] == str(path)
    assert payload["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert payload["ok"] is False
    assert payload["books"][0]["decision_point"] == DP3
    assert {"code", "path", "detail"} == set(payload["issues"][0])
    assert set(payload) == {"path", "sha256", "ok", "books", "issues"}


def test_cli_book_new_prints_to_stdout_without_writing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    before = sorted(p.name for p in root.iterdir())
    rc = mw.cmd_decide(book_args(root, "new", dp=DP3, out=None))
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == books.scaffold_book(DP3)
    assert sorted(p.name for p in root.iterdir()) == before


def test_cli_book_new_out_writes_the_skeleton(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    out = root / "evidence" / "books" / "dp3.json"
    rc = mw.cmd_decide(book_args(root, "new", dp=DP3, out=str(out), json=True))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dp"] == DP3
    assert payload["out"] == str(out)
    assert payload["file_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert json.loads(out.read_text(encoding="utf-8")) == books.scaffold_book(DP3)


def test_cli_book_new_unknown_dp_exits_2(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    assert mw.cmd_decide(book_args(root, "new", dp="dp99-nope", out=None)) == 2
    assert "book-schema" in capsys.readouterr().err


def test_cli_book_check_fails_with_exit_2_and_a_table(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    path = write_book(root, books.scaffold_book(DP3))
    assert mw.cmd_decide(book_args(root, "check", file=str(path))) == 2
    out = capsys.readouterr().out
    assert "FAIL book-placeholder state.key" in out
    assert "issue(s)" in out


def test_cli_book_check_passes_with_exit_0_and_json(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    path = write_book(root, valid_book())
    assert mw.cmd_decide(book_args(root, "check", file=str(path), json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["books"][0]["decision_point"] == DP3


def test_cli_book_check_reports_unparseable_json(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    path = root / "broken.json"
    path.write_text("{", encoding="utf-8")
    assert mw.cmd_decide(book_args(root, "check", file=str(path), json=True)) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["issues"][0]["code"] == "book-schema"


def test_decide_book_template_is_book_new_output() -> None:
    doc = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert set(doc) == {"books"}
    assert set(doc["books"]) == {DP3, DP6}
    assert doc["books"][DP3] == books.scaffold_book(DP3)
    assert doc["books"][DP6] == books.scaffold_book(DP6)


# ---------------------------------------------------------------------------
# --book: 先验后发（失败零 HTTP，成功落 book_path + sha256）
# ---------------------------------------------------------------------------


def test_cli_run_book_with_invalid_book_sends_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    enable_decide(root)
    backend = decision.FakeBackend([dp3_answers()])
    inject_backend(monkeypatch, backend)
    path = write_book(root, books.scaffold_book(DP3))
    assert mw.cmd_decide(run_args(root, book=str(path))) == 2
    assert backend.calls == []
    err = capsys.readouterr().err
    assert "book-placeholder" in err
    assert "zero HTTP" in err


def test_cli_ask_book_with_invalid_book_sends_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    enable_decide(root)
    backend = decision.FakeBackend([dp3_answers()])
    inject_backend(monkeypatch, backend)
    path = write_book(root, books.scaffold_book(DP3))
    rc = mw.cmd_decide(ask_args(root, book=str(path), noul=["urgent=是否紧急"]))
    assert rc == 2
    assert backend.calls == []
    assert "zero HTTP" in capsys.readouterr().err


def test_cli_ask_book_is_exclusive_with_state(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_root(tmp_path)
    backend = decision.FakeBackend([dp3_answers()])
    inject_backend(monkeypatch, backend)
    path = write_book(root, valid_book())
    rc = mw.cmd_decide(ask_args(root, book=str(path), state="text", noul=["q=text"]))
    assert rc == 2
    assert backend.calls == []


def test_cli_run_book_success_records_path_sha_and_evidence(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    enable_decide(root)
    backend = decision.FakeBackend([dp3_answers()])
    inject_backend(monkeypatch, backend)
    path = write_book(root, valid_book())
    rc = mw.cmd_decide(run_args(root, book=str(path)))
    assert rc == 0, capsys.readouterr().err
    result = json.loads(capsys.readouterr().out)
    assert result["available"] is True
    assert result["book"]["path"] == path.relative_to(root).as_posix()
    assert result["book"]["file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    evidence = {field: "notes.txt:1" for field in books.required_state_paths(DP3)}
    evidence["context.change_summary"] = "notes.txt:1"
    evidence["context.candidate_snippets"] = "notes.txt:2"
    assert result["book"]["evidence"] == evidence
    # 上下文随 state 一起发出（形状与 decision_context 一致，未被截断）。
    sent = backend.calls[0]["state"]
    assert sent["context"]["change_summary"] == "one file changed"
    receipt_path = root / books.RECEIPTS_RELATIVE_PATH
    receipt = json.loads(receipt_path.read_text(encoding="utf-8").splitlines()[-1])
    assert receipt["dp"] == DP3
    assert receipt["book_path"] == path.relative_to(root).as_posix()
    assert receipt["file_sha256"] == result["book"]["file_sha256"]
    assert receipt["evidence"] == result["book"]["evidence"]
    assert receipt["available"] is True
    assert receipt["state_digest"]
    # 决策行仍然落在既有 decisions.jsonl（book 元数据不进去，字段矩阵是封闭的）。
    decisions = root / ".agenticdoc" / "_autopilot" / "decisions.jsonl"
    assert decisions.exists()


def test_cli_run_book_rejects_a_dp_flag_that_disagrees(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    enable_decide(root)
    backend = decision.FakeBackend([dp3_answers()])
    inject_backend(monkeypatch, backend)
    path = write_book(root, valid_book())
    assert mw.cmd_decide(run_args(root, book=str(path), dp=DP6)) == 2
    assert backend.calls == []
    assert "disagrees" in capsys.readouterr().err


def test_book_state_merges_context_into_state(tmp_path: pathlib.Path) -> None:
    book = valid_book()
    state = books.book_state(book)
    assert state["context"]["change_summary"] == "one file changed"
    # 原始 book 不被修改（检查器/发送面都不写回）。
    assert "context" not in book["state"]


def test_book_state_drops_unused_scaffold_slots() -> None:
    state = books.book_state(books.scaffold_book(DP3))
    assert "context" not in state

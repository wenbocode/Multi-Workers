"""
test_dispatch_decide_prepare.py — L1 tests for the `decide_prepare` worker type
(mw-decision-substitution W8, renamed W10).

Three contracts are locked here:

  1. vocabulary: `decide_prepare` is a dispatchable type AND a dispatch role
     (`mw_common.TASK_TYPE_TO_ROLE`, `DISPATCH_ROLES`, derived
     `FALLBACK_TASK_TYPES`), with the read-only tool set + `bash` that the
     worker runtime's `TOOL_ALLOWLISTS` entry mirrors item for item. The old
     `decision` value is NOT an alias (W10 requirement 1);
  2. dispatch gate: a decide_prepare card missing any of `- dp:` / `- 证据来源:` /
     `- 分支后果:` / `- allow-send:` is refused with zero side effects, a dp
     without `required_state_fields` is refused, and `allow-send: no` refuses
     the send (`decide run|ask --book`);
  3. write face: the type default is narrowed to `<key>/evidence/books/**`,
     a wider card face wins, and both outcomes are recorded in task.md as a
     `narrowed_by` line.

Fixtures are plain tmp_path project trees (card + queue file); no provider
APIs, no keys, no network.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
from autopilot import dispatch


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()), flush=True)


CARD_ITEMS = (
    "- dp: dp3-worker-clarify",
    "- 证据来源: .mw/decide.json:3 + `mw decide book new dp3-worker-clarify`",
    "- 分支后果: 误判会把需要澄清的任务直接执行",
    "- allow-send: no",
)


def _write_card(project: pathlib.Path, stem: str = "d-01", items=CARD_ITEMS, extra: str = "") -> pathlib.Path:
    card = project / ".agenticdoc" / "k1" / "tasks" / f"{stem}.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join([
        "- type: decide_prepare",
        "- key: k1",
        "",
        "## 上下文",
        "",
        "dp3 澄清判定：按 goal.md 的收敛目标写一本决策本。",
        "",
        "## 要求",
        "",
        "读配置、收集证据、填本、过检；证据见 decide_registry.json:105。",
        "",
        "## 派发参数",
        "",
        *items,
        "",
        extra,
        "",
    ])
    card.write_text(body, encoding="utf-8")
    return card


def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / ".agenticdoc").mkdir()
    return tmp_path


def _dispatch(project: pathlib.Path, stem: str = "d-01", task_type: str = "decide_prepare"):
    return dispatch.dispatch(
        project, "k1", stem, task_type,
        "Write the dp3 decision book. Do not send.",
        loop=f"exec:k1:{stem}", attempt=1,
    )


def _queue_keys(project: pathlib.Path) -> list[str]:
    return [
        row["task_key"]
        for row in mw_common.parse_workers_file(mw_common.workers_path(project))
    ]


def _task_md(project: pathlib.Path) -> str:
    return (
        project / ".agenticdoc" / "k1" / "workers" / "ap-k1-d-01" / "task.md"
    ).read_text(encoding="utf-8")


# ── 1. vocabulary ────────────────────────────────────────────────────────────

def test_vocabulary_contains_decide_prepare() -> None:
    assert mw_common.TASK_TYPE_TO_ROLE["decide_prepare"] == "decide_prepare"
    assert "decide_prepare" in mw_common.FALLBACK_TASK_TYPES
    assert "decide_prepare" in mw_common.DISPATCH_ROLES
    _verify("W8-V1", type_role="decide_prepare", roles=len(mw_common.DISPATCH_ROLES))


def test_fallback_task_types_derives_from_the_role_map() -> None:
    # FALLBACK_TASK_TYPES is derived (`tuple(TASK_TYPE_TO_ROLE)`), so adding the
    # type must not need a second edit — and cannot silently drift.
    assert mw_common.FALLBACK_TASK_TYPES == tuple(mw_common.TASK_TYPE_TO_ROLE)
    assert mw_common.FALLBACK_TASK_TYPES[-1] == "decide_prepare"


def test_registry_decide_prepare_tools() -> None:
    assert dispatch.tool_set("decide_prepare") == ("read", "find", "grep", "ls", "bash")
    entry = dispatch.REGISTRY["decide_prepare"]
    assert (entry.cli, entry.provider) == ("pi", "timi")
    assert entry.requires_read_scope is False
    # The conductor may dispatch it (it is not a PM-only type like rag-research).
    assert entry.conductor_dispatchable is True
    _verify("W8-V2", tools=len(entry.tools))


def test_old_decision_value_is_not_an_alias() -> None:
    # W10 requirement 1: the rename is one-shot, no alias. The old type is
    # unregistered and the old role is not a valid dispatch.yml key.
    assert "decision" not in mw_common.DISPATCH_ROLES
    assert "decision" not in mw_common.TASK_TYPE_TO_ROLE
    assert dispatch.tool_set("decision") == ()
    assert "decision" not in dispatch.REGISTRY


# ── 2. role validation (`.mw/dispatch.yml`) ──────────────────────────────────

def test_role_validation_allows_decide_prepare(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".mw").mkdir()
    (tmp_path / ".mw" / "dispatch.yml").write_text(
        "models:\n  decide_prepare: timi/glm-5.3-air\n", encoding="utf-8",
    )
    config, err = mw_common.load_dispatch_config(tmp_path)
    assert err is None, err
    assert config["models"] == {"decide_prepare": "timi/glm-5.3-air"}


def test_role_validation_rejects_the_old_decision_role(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".mw").mkdir()
    (tmp_path / ".mw" / "dispatch.yml").write_text(
        "models:\n  decision: timi/glm-5.3-air\n", encoding="utf-8",
    )
    config, err = mw_common.load_dispatch_config(tmp_path)
    assert config == {} and err and "decision" in err


def test_role_validation_still_rejects_an_unknown_role(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".mw").mkdir()
    (tmp_path / ".mw" / "dispatch.yml").write_text(
        "models:\n  villain: timi/x\n", encoding="utf-8",
    )
    config, err = mw_common.load_dispatch_config(tmp_path)
    assert config == {} and err and "villain" in err


def test_decide_prepare_model_defaults_to_the_coding_role() -> None:
    value, source = mw_common.resolve_dispatch_model(
        task_type="decide_prepare", cli="pi", entry_model="",
        config_models={"coding": "timi/glm-5.3"}, window_model="",
    )
    assert (value, source) == ("timi/glm-5.3", "config:coding")
    explicit, source2 = mw_common.resolve_dispatch_model(
        task_type="decide_prepare", cli="pi", entry_model="",
        config_models={"coding": "timi/glm-5.3", "decide_prepare": "timi/glm-5.3-air"},
        window_model="",
    )
    assert (explicit, source2) == ("timi/glm-5.3-air", "config:decide_prepare")
    # `dispatch_worker.model` (the task's own model) still wins over the role.
    entry, source3 = mw_common.resolve_dispatch_model(
        task_type="decide_prepare", cli="pi", entry_model="timi/gpt-6.1-sol",
        config_models={"decide_prepare": "timi/glm-5.3-air"}, window_model="",
    )
    assert (entry, source3) == ("timi/gpt-6.1-sol", "task")
    _verify("W8-V3", default_role="coding", explicit="decide_prepare")


def test_decide_prepare_fallback_models_borrow_coding() -> None:
    fallbacks = {"coding": ["timi/glm-5.3-air"]}
    assert mw_common.fallback_models_for_task_type(fallbacks, "decide_prepare") == [
        "timi/glm-5.3-air",
    ]


# ── 3. card required items (each one ⇒ exit 2 / refusal) ─────────────────────

@pytest.mark.parametrize("dropped", ["dp", "证据来源", "分支后果", "allow-send"])
def test_missing_card_item_is_refused(tmp_path: pathlib.Path, dropped: str) -> None:
    project = _project(tmp_path)
    items = [item for item in CARD_ITEMS if not item.startswith(f"- {dropped}:")]
    _write_card(project, "d-01", items=items)
    result = _dispatch(project)
    assert result.ok is False
    assert result.reason == f"decision-card-invalid: missing-item:{dropped}"
    # Zero side effects: no task dir, no queue row.
    assert not (project / ".agenticdoc" / "k1" / "workers" / "ap-k1-d-01").exists()
    assert _queue_keys(project) == []
    issue = dispatch.decision_card_issues(
        _write_card(project, "d-01", items=items).read_text(encoding="utf-8"),
    )
    assert [i.code for i in issue] == [f"missing-item:{dropped}"]
    _verify("W8-V4", dropped=dropped, refused="true")


def test_card_less_decide_prepare_dispatch_is_refused(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    result = _dispatch(project)
    assert result.ok is False
    assert result.reason == "decision-card-invalid: card-missing"
    assert _queue_keys(project) == []


def test_allow_send_defaults_to_no() -> None:
    fields = dispatch.decision_card_fields("\n".join(CARD_ITEMS[:3]))
    assert "allow-send" not in fields
    assert dispatch.decision_allows_send(fields) is False
    assert dispatch.decision_allows_send({"allow-send": "yes"}) is True
    assert dispatch.decision_allows_send({"allow-send": "YES"}) is True


def test_allow_send_no_refuses_the_book_send(tmp_path: pathlib.Path) -> None:
    card = _write_card(tmp_path)
    book = tmp_path / "book.json"
    book.write_text("{}", encoding="utf-8")
    assert dispatch.main(["check", "--card", str(card), "--book", str(book)]) == 2
    codes = [
        issue.code
        for issue in dispatch.decision_card_issues(
            card.read_text(encoding="utf-8"), book=str(book),
        )
    ]
    assert codes == ["book-send-refused"]

    yes_card = _write_card(
        tmp_path, "d-02",
        items=(*CARD_ITEMS[:3], "- allow-send: yes"),
    )
    assert dispatch.main(["check", "--card", str(yes_card), "--book", str(book)]) == 0
    _verify("W8-V5", allow_send_no="refused", allow_send_yes="accepted")


# ── 4. dp criterion (required_state_fields) ──────────────────────────────────

def test_dp_without_required_state_fields_is_refused(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    items = ("- dp: dp4-failure-handling", *CARD_ITEMS[1:])
    card = _write_card(project, "d-01", items=items)
    result = _dispatch(project)
    assert result.ok is False
    assert result.reason == (
        "decision-card-invalid: dp-required-state-fields-missing:dp4-failure-handling"
    )
    # The refusal CODE is the stable token on the result; the prose ("先给该 dp
    # 定义必填字段") is what the checker prints for the operator.
    detail = dispatch.decision_card_issues(card.read_text(encoding="utf-8"))[0].detail
    assert "先给该 dp 定义必填字段" in detail
    assert dispatch.main(["check", "--card", str(card)]) == 2
    assert _queue_keys(project) == []
    _verify("W8-V6", dp="dp4-failure-handling", exited="2")


def test_unknown_dp_is_refused(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    items = ("- dp: dp99-not-a-dp", *CARD_ITEMS[1:])
    _write_card(project, "d-01", items=items)
    result = _dispatch(project)
    assert result.ok is False
    assert result.reason == "decision-card-invalid: dp-unknown:dp99-not-a-dp"


def test_defined_dps_pass_the_registry_probe() -> None:
    # dp1/dp2/dp3 are the dps that define required_state_fields today.
    for dp in ("dp1-dispatch-type", "dp2-checkpoint-split", "dp3-worker-clarify"):
        assert dispatch.main(["check", "--dp", dp]) == 0, dp
    _verify("W8-V7", dps_with_fields="3", exit="0")


# ── 5. write face (narrowed to the books dir, card wins + narrowed_by) ───────

def test_write_face_is_narrowed_to_the_books_dir(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_card(project, "d-01")
    result = _dispatch(project)
    assert result.ok is True, result.reason
    task_md = _task_md(project)
    assert (
        "write_face: .agenticdoc/k1/workers/ap-k1-d-01/evidence/books/**" in task_md
    ), task_md
    assert "- write_face_carrier: type-default" in task_md
    assert "- narrowed_by: type-default:evidence/books/**" in task_md
    _verify("W8-V8", write_face="evidence/books/**", carrier="type-default")


def test_wider_card_write_face_wins_and_is_recorded(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_card(
        project, "d-01",
        extra="## 写入允许面\n\n- `.agenticdoc/k1/**`\n",
    )
    result = _dispatch(project)
    assert result.ok is True, result.reason
    task_md = _task_md(project)
    assert "write_face: .agenticdoc/k1/**" in task_md, task_md
    assert "- write_face_carrier: card-wider" in task_md
    assert "- narrowed_by: card-wider:" in task_md
    _verify("W8-V9", carrier="card-wider", narrowed_by="recorded")


def test_decide_prepare_params_section_reaches_task_md(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_card(project, "d-01")
    assert _dispatch(project).ok is True
    task_md = _task_md(project)
    assert "## 决策本参数" in task_md
    assert "- dp: dp3-worker-clarify" in task_md
    assert "- allow-send: no" in task_md
    assert "/evidence/books/dp3-worker-clarify-book.json" in task_md
    _verify("W8-V10", params_section="present", allow_send="no")


def test_check_cli_json_reports_ok(tmp_path: pathlib.Path) -> None:
    card = _write_card(tmp_path)
    assert dispatch.main(["check", "--card", str(card), "--json"]) == 0
    _verify("W8-V11", cli="check --json", exit="0")

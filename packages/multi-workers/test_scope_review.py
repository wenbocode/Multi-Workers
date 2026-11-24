import json
import re

import pytest

import replan_tasks as replan
import scope_review
from autopilot import advance, dispatch


GOAL = (
    "Goal ID: ueperf-t43/GOAL-01\n"
    "目标: T25 通过版本化 JSON 合同只读复验固定帧 CSV 完成证据。\n"
    "范围边界: T43 交付 JSON 消费合同，公共 C++ API 和真实采集另有归属。\n"
    "停止条件: 正控复验通过，缺件、篡改或错哈希具名失败，当前 AC 全部通过。"
)
FIX = "修复错哈希被接受，verify 对不匹配的预期哈希具名返回非零"
EXTRA = "新增公共 C++ API，方便 T25 直接调用 evaluator"


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def review(approve):
    return {
        "verdict": "approve" if approve else "reject",
        "anchor": "AC-305",
        "entry": "tools/t43_qualification.py verify",
        "failure": "错哈希被接受" if approve else "JSON 入口仍可完成复验",
        "minimum": FIX if approve else "沿用只读 JSON 合同",
    }


def card(deliverable):
    return (
        "type: coding\ntimeout: 8\n\n## 上下文\nAC-305\n"
        f"## 要求\n{deliverable}\n## 交付格式\n{deliverable}\n"
        "## 写入允许面\n- tools/t43_qualification.py\n"
        "## 写入禁止面\n其它\n## 验收命令\npython tools/t43_qualification.py verify\n## 改动历史\nfirst\n"
    )


@pytest.fixture
def t43(tmp_path):
    key = tmp_path.resolve() / ".agenticdoc" / "ueperf-t43"
    write(key / "spec.md", f"## §0 Goal Alignment\n### spec_goal\n{GOAL}\n\n## AC\n| AC-305 | 固定哈希复验 |\n")
    write(key.parent / "target.yml", "active: single\n")
    write(key / "plan.md",
          f"## 保留任务\n| 任务 | 产出 |\n| --- | --- |\n| T-fix | {FIX} |\n"
          "## 闭环覆盖\n| AC-305 | T-fix | VC-305 |\n")
    write(key / "tasks/T-fix.md", card(FIX))
    ledger = {
        "goal_sha256": scope_review.sha(GOAL),
        "plan_sha256": scope_review.sha(scope_review.read(key / "plan.md")),
        "plan": {"T-fix": review(True)},
        "cards": {"tasks/T-fix.md": {**review(True), "sha256": dispatch.card_digest(key / "tasks/T-fix.md")}},
    }
    write(key / scope_review.REVIEW_FILE, json.dumps(ledger))
    return key, ledger


def test_plan_gate_checks_t43_scope_before_invoking_native_phase(t43, monkeypatch):
    key, ledger = t43
    project = key.parents[1]
    script = project / "advance_phase.py"
    write(script, "print('native phase invoked')\n")
    write(script.with_name("plan_closure.py"), "")
    monkeypatch.setattr(advance, "advance_script", lambda _: script)
    assert advance.advance(key.name, "tasks", project) == (0, "native phase invoked\n", "")

    plan = scope_review.read(key / "plan.md").replace(FIX, EXTRA)
    write(key / "plan.md", plan)
    ledger["plan_sha256"] = scope_review.sha(plan)
    ledger["plan"]["T-fix"] = review(False)
    write(key / scope_review.REVIEW_FILE, json.dumps(ledger))
    assert advance.advance(key.name, "tasks", project) == (
        1, "", "   - PLAN CLOSURE: scope-review: plan/T-fix: scope review approval required"
    )


def test_dispatch_blocks_unreviewed_scope_and_card_edits_before_queue(t43):
    key, ledger = t43
    project = key.parents[1]

    def send(stem):
        return dispatch.dispatch(project, key.name, stem, "phase-writer", "deliver",
                                 loop=f"exec:{key.name}:{stem}", attempt=1)

    write(key / "tasks/T-api.md", card(EXTRA))
    rejected = send("T-api")
    assert not rejected.ok and "scope review approval required" in rejected.reason
    assert not (key / "workers").exists()
    ledger["cards"]["tasks/T-api.md"] = {**review(True), "sha256": dispatch.card_digest(key / "tasks/T-api.md")}
    write(key / scope_review.REVIEW_FILE, json.dumps(ledger))
    assert "must be assigned by the retained plan" in send("T-api").reason
    write(key / "tasks/T-fix.md", card(FIX + "，并" + EXTRA))
    assert "reviewed content changed" in send("T-fix").reason
    write(key / "tasks/T-fix.md", card(FIX))
    assert send("T-fix").ok
    assert ledger["cards"]["tasks/T-fix.md"]["anchor"] == "AC-305"


def test_replan_requires_exact_scope_review_even_with_same_ac(t43):
    key, ledger = t43
    current = {
        "closure": {"T-fix": {"AC-305"}}, "coverage": ["AC-305"], "issue": "T43", "snapshot": "frozen",
        "facts": {"task": "T-fix", "card": "tasks/T-fix.md", "status": "unstarted"}, "live_workers": [],
    }

    def remaining(deliverable):
        return {"action": "narrow", "reason": deliverable, "units": [{
            "id": "T-next", "markdown": card(deliverable), "covers": ["AC-305"], "depends_on": [],
            "resources": [], "reuse": "现有验证器", "first_check": "verify with wrong hash", "expected": "nonzero",
        }]}

    good = remaining(FIX)
    bad = remaining(EXTRA)
    for proposal, verdict in [(good, True), (bad, False)]:
        with pytest.raises(ValueError, match=r"replans/([0-9a-f]{64})") as refused:
            replan.preview(key.parents[1], key, current, proposal)
        version = re.search(r"replans/([0-9a-f]{64})", str(refused.value))[1]
        ledger.setdefault("replans", {})[version] = review(verdict)
        write(key / scope_review.REVIEW_FILE, json.dumps(ledger))
    assert replan.preview(key.parents[1], key, current, good)["initial_batch"] == ["T-next"]
    with pytest.raises(ValueError, match="scope review approval required"):
        replan.preview(key.parents[1], key, current, bad)
    write(key / "spec.md", scope_review.read(key / "spec.md").replace("正控复验通过", "无需复验"))
    with pytest.raises(ValueError, match="review current goal_sha256"):
        replan.preview(key.parents[1], key, current, good)

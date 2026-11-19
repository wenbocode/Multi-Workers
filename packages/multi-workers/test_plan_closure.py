import hashlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from autopilot import advance, audit_evidence, conductor
FRAMEWORK = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "agentic-task"
INSTALLED = FRAMEWORK.parents[2] / ".claude" / "scripts"

SPEC = """# Spec

| AC | 描述 |
| --- | --- |
| AC-001 | 从 CLI 发布结果 |
- AC-002: 无效请求返回错误
> - AC-099: 引用的示例
"""

DESIGN = """## Function Flow

### 必要功能路径

| 路径 | 入口 | 结果 | 验证 |
| --- | --- | --- | --- |
| FLOW-001 | CLI 有效请求 | 发布结果 | VC-001 |
| FLOW-002 | CLI 无效请求 | 返回错误 | VC-002 |

## Verification Contract

VC-001: CLI 输出已发布的结果
VC-002: 错误退出码和诊断可观察
"""

PLAN = """# Plan

## 计划裁剪

- 移出 T-09-dashboard。该界面独立于目标与验收标准。

## 保留任务

| 任务 | 产出 |
| --- | --- |
| T-01-cli | CLI 发布和验收 |

## 闭环覆盖

| 条目 | 来源 | VC |
| --- | --- | --- |
| AC-001 | T-01-cli | VC-001 |
| AC-002 | existing: evidence/invalid.md | VC-002 |
| FLOW-001 | T-01-cli | VC-001 |
| FLOW-002 | existing: evidence/invalid.md | VC-002 |
"""


@pytest.fixture
def key_dir(tmp_path):
    if not (FRAMEWORK / "scripts" / "plan_closure.py").is_file():
        pytest.skip("Native AgenticTask plan closure not installed")
    directory = tmp_path / ".agenticdoc" / "sample"
    (directory / "evidence").mkdir(parents=True)
    (tmp_path / ".agentic-framework").write_text(f"repo={FRAMEWORK}\n", encoding="utf-8")
    for name, content in {
        "spec.md": SPEC, "design.md": DESIGN, "plan.md": PLAN,
        "pm-state.md": "- Phase: PLAN\n- Updated: 2026-11-19 00:00\n",
        "evidence/invalid.md": "Ran local CLI with invalid input. Exit 2 and diagnostic observed.\n",
    }.items():
        (directory / name).write_text(content, encoding="utf-8")
    return directory


@pytest.mark.parametrize(("before", "after", "diagnostic"), [
    ("## 计划裁剪", "## Other", "计划裁剪"),
    ("| AC-002 | existing: evidence/invalid.md | VC-002 |", "", "闭环覆盖缺少 AC-002"),
    ("| FLOW-002 | existing: evidence/invalid.md | VC-002 |", "", "闭环覆盖缺少 FLOW-002"),
    ("| FLOW-002 | existing: evidence/invalid.md | VC-002 |",
     "| FLOW-002 | existing: evidence/invalid.md | VC-001 |", "遗漏设计规定的路径 VC"),
    ("| AC-001 | T-01-cli | VC-001 |", "| AC-001 | T-09-dashboard | VC-999 |", "AC-001 未关联"),
    ("existing: evidence/invalid.md", "existing: evidence/missing.md", "有效的已有能力证据"),
    ("existing: evidence/invalid.md", "existing: evidence/../spec.md", "有效的已有能力证据"),
    ("## 闭环覆盖", "~~~md\n## 闭环覆盖", "闭环覆盖缺少"),
])
def test_gate_blocks_incomplete_or_invalid_plan(key_dir, before, after, diagnostic):
    (key_dir / "plan.md").write_text(PLAN.replace(before, after), encoding="utf-8")
    assert any(diagnostic in error for error in advance.inspect_plan(key_dir.parents[1], key_dir.name))


def test_gate_requires_design_path_inventory(key_dir):
    (key_dir / "design.md").write_text(DESIGN.replace("### 必要功能路径", "### Flow"), encoding="utf-8")
    assert any("缺少有效的“必要功能路径”" in error for error in advance.inspect_plan(key_dir.parents[1], key_dir.name))


def test_audit_and_advance_share_gate(key_dir):
    project = key_dir.parents[1]
    plan = key_dir / "plan.md"
    plan.write_text(PLAN.replace("| FLOW-001 | T-01-cli | VC-001 |", ""), encoding="utf-8")
    state = key_dir / "pm-state.md"
    original = state.read_bytes()
    dossier = audit_evidence.build_dossier("sample", project)
    assert dossier["gaps"] == [{
        "item": "plan.md 闭环覆盖缺少 FLOW-001", "rule": "plan-closure", "severity": "blocking",
    }]
    code, _, error = advance.advance("sample", "tasks", project)
    assert code == 1 and dossier["gaps"][0]["item"] in error
    assert state.read_bytes() == original

    plan.write_text(PLAN, encoding="utf-8")
    assert audit_evidence.build_dossier("sample", project)["gaps"] == []
    code, _, error = advance.advance("sample", "tasks", project)
    assert code == 0, error
    assert "- Phase: TASKS" in state.read_text(encoding="utf-8")


@pytest.mark.parametrize("scripts", [
    FRAMEWORK / "scripts", FRAMEWORK / "core" / "scripts", FRAMEWORK / "claude" / "scripts", INSTALLED,
], ids=["canonical", "core", "claude-mirror", "installed-claude"])
def test_direct_native_command_updates_phase_only_after_closure_passes(key_dir, scripts):
    if not (scripts / "advance_phase.py").is_file():
        pytest.skip(f"Framework scripts absent: {scripts}")
    project = key_dir.parents[1]
    (project / ".agentic-framework").unlink()
    index = key_dir.parent / "_index.parallel"
    index.write_text(
        "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |\n"
        "|-----|--------|-------|---------|------|------|---------|\n"
        "| sample | idle | PLAN | — | — | test | 2026-11-19 |\n",
        encoding="utf-8",
    )
    script = scripts / "advance_phase.py"
    command = [sys.executable, "-X", "utf8", str(script), "sample", "tasks"]
    print(f"[VERIFY] {scripts}: advance={hashlib.sha256(script.read_bytes()).hexdigest()} "
          f"plan_closure={hashlib.sha256((scripts / 'plan_closure.py').read_bytes()).hexdigest()}")
    plan = key_dir / "plan.md"
    plan.write_text(PLAN.replace("## 闭环覆盖", "## Other"), encoding="utf-8")
    result = subprocess.run(command, cwd=project, capture_output=True, encoding="utf-8", timeout=30)
    assert result.returncode == 1 and "PLAN CLOSURE: plan.md 闭环覆盖缺少" in result.stderr
    assert "| sample | idle | PLAN |" in index.read_text(encoding="utf-8")

    plan.write_text(PLAN, encoding="utf-8")
    result = subprocess.run(command, cwd=project, capture_output=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "- Phase: TASKS" in (key_dir / "pm-state.md").read_text(encoding="utf-8")
    assert "| sample | idle | TASKS |" in index.read_text(encoding="utf-8")


def test_autopilot_routes_gap_to_repair_before_task_writer(key_dir, monkeypatch):
    project = key_dir.parents[1]
    plan = key_dir / "plan.md"
    plan.write_text(PLAN.replace("## 计划裁剪", "## Other"), encoding="utf-8")
    monkeypatch.setattr(conductor.state, "read_key_states", lambda _: {"sample": SimpleNamespace(phase="PLAN")})
    dispatched = []
    hard_failures = []

    monkeypatch.setattr(advance, "inspect_plan", lambda *a, **kw: pytest.fail("duplicate plan preflight"))
    monkeypatch.setattr(advance, "recovery_enforced", lambda _project: True)
    monkeypatch.setattr(advance, "advance_allowed", lambda *a: (True, "", None))
    monkeypatch.setattr(advance, "record_failure", lambda *a: hard_failures.append(a))

    def dispatch_stub(_project, _key, stem, kind, prompt, **_options):
        dispatched.append((stem, kind, prompt))
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(conductor.dispatch, "dispatch", dispatch_stub)
    st = SimpleNamespace(timeline=None)
    cfg = {"round_budget": 2}
    rm_path = project / "roadmap.md"
    assert conductor._advance_key(project, st, "sample", [], {}, cfg, rm_path)
    assert dispatched[-1][1] == "verifier"
    assert "计划裁剪" in dispatched[-1][2]

    assert conductor._advance_key(project, st, "sample", [], {"l2:sample:plan-to-tasks": 1}, cfg, rm_path)
    assert dispatched[-1][0] == "l2-fix-plan-to-tasks-a1"
    assert "移除次要项" in dispatched[-1][2]
    assert not (key_dir / "tasks").exists()
    assert hard_failures == []


def test_only_retained_items_need_cards(key_dir):
    tasks = key_dir / "tasks"
    tasks.mkdir()
    (tasks / "01-cli.md").write_text("# CLI", encoding="utf-8")
    assert conductor._missing_plan_tasks(key_dir) == []
    (tasks / "T-09-dashboard.md").write_text("# Dashboard", encoding="utf-8")
    assert conductor._missing_plan_tasks(key_dir) == [{
        "item": "tasks/T-09-dashboard.md 不在已复核的保留任务表", "rule": "execute-gate",
    }]

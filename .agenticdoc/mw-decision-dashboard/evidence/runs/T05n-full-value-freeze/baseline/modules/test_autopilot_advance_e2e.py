"""
test_autopilot_advance_e2e.py — end-to-end root-location regression for the
autopilot phase-advance channel (mw-autopilot-advance-root, AC-005).

The failure this guards against: the AgenticTask framework is installed
*outside* the target project (the project's .agentic-framework marker points at
another repo that is itself an AgenticTask project). The framework's
advance_phase.py used to resolve .agenticdoc from Path(__file__), i.e. the
framework repo's own .agenticdoc, so phase advance mkdir'd key dirs and failed
gates in the wrong repository.

The test drives the real framework clone when present (skip otherwise) and
asserts the target project advances while the framework repo is untouched.
"""
import pathlib
import sys
import uuid

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import advance as adv  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FRAMEWORK = REPO_ROOT / ".agents" / "skills" / "agentic-task"

# design-gate compliant: >= 500 bytes, numbered AC, spec research evidence.
# goal.md / memory docs are absent in the tmp project, so those gates skip.
_SPEC = (
    "# Spec: probe\n\n"
    "## §0 Goal Alignment\n\n- 对齐：probe\n- 预期收益：probe\n\n"
    "## §1 概述\n\n"
    + ("x" * 600)
    + "\n\n## §3 验收标准（AC）\n\n"
    "| AC 编号 | 描述 |\n|--------|------|\n| AC-001 | probe 通过 design 门禁 |\n\n"
    "### 可复用资产\n- probe\n\n### 需规避坑点\n- probe\n"
)
_RESEARCH = "# Research: probe (spec)\n## 决策问题\n根定位\n## 调研方法与出处\nprobe\n"


def test_advance_targets_project_root_outside_framework(tmp_path: pathlib.Path) -> None:
    if not (FRAMEWORK / "scripts" / "advance_phase.py").is_file():
        pytest.skip("AgenticTask framework clone not present under .agents/skills")

    project = tmp_path / "proj"
    key = "e2e-probe-" + uuid.uuid4().hex[:8]
    key_dir = project / ".agenticdoc" / key
    (key_dir / "evidence" / "research").mkdir(parents=True)
    (key_dir / "spec.md").write_text(_SPEC, encoding="utf-8")
    (key_dir / "evidence" / "research" / "spec-probe.md").write_text(
        _RESEARCH, encoding="utf-8"
    )
    (project / ".agentic-framework").write_text(
        f"framework=AgenticTask\nrepo={FRAMEWORK}\n", encoding="utf-8"
    )

    wrong_root = REPO_ROOT / ".agenticdoc" / key
    assert not wrong_root.exists()  # pre-condition: framework repo is clean

    adv.invalidate_script_cache()
    code, out, err = adv.advance(key, "design", project)
    assert code == 0, f"exit={code}\nstdout={out}\nstderr={err}"

    pm_state = key_dir / "pm-state.md"
    assert pm_state.is_file()
    assert "- Phase: DESIGN" in pm_state.read_text(encoding="utf-8")
    # the framework repo's own .agenticdoc must not have been touched
    assert not wrong_root.exists(), "phase advance wrote into the framework repo"
    print(f"[VERIFY] VC-005: e2e_advance={code} target={key_dir}")

"""
test_autopilot_audit.py — L1 evidence audit CLI tests (goal-autopilot T-08, AC-007 / VC-009).

Runs autopilot/audit_evidence.py as a subprocess against tmp_path key fixtures
that mirror the real .agenticdoc/{key} layout: a locked spec.md with an errata
blockquote, a design.md with `### D-NNN` sections plus a summary decision table
(including a table-only decision and a `{date}` placeholder citation), and
evidence/research/ files. The last test audits the real goal-autopilot key of
this repository (read-only) against its locked AC/decision fingerprints.
"""

import json
import pathlib
import re
import subprocess
import sys

import pytest

_MW_DIR = pathlib.Path(__file__).parent
AUDIT_CLI = _MW_DIR / "autopilot" / "audit_evidence.py"
_REPO_ROOT = _MW_DIR.parent.parent

# Locked-errata spec format (mirrors .agenticdoc/goal-autopilot/spec.md §3):
# lock marker, errata blockquote mentioning an AC id that is also a table row,
# AC table, and a prose AC mention that must not enter the checklist.
_SPEC = """# Spec: sample-key

> Key: sample-key
> 状态: locked

## §1 功能概述

（调研：evidence/research/spec-survey.md）

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-10T00:00:00Z，编号永不回收

> **Errata（2026-09-10，编号与语义不变，仅措辞勘误）**
> - AC-002 「旧行为二」→ 「行为二（勘误后措辞）」；意图不变

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在给定输入的条件下，行为一 |
| AC-002 | 在另一条件的条件下，行为二（勘误后措辞） |
| AC-003 | 行为三 |

## §4 风险

- 风险：正文括号引用（AC-002）不是表格行，不得计入 AC 清单
"""

# D-201/D-202 as section headers, D-203 only as a summary-table row (union test);
# D-202 cites a {date} placeholder (must be skipped); D-203's citation lives in
# its summary-table row.
_DESIGN = """# Design: sample-key

## §1 架构选型

### D-201 模块布局

**推荐**：A

**理由**：简单。调研：`evidence/research/design-d201-survey.md`

### D-202 数据格式

**推荐**：JSON

**理由**：机械可解析。报告命名 `evidence/quality-gate-report-{date}.md` 为占位符，不计入字面引用。

## §10 决策记录

| D-ID | 决策点 | 选择 | 否决 | 理由 |
|------|--------|------|------|------|
| D-201 | 模块布局 | A | B | 简单 |
| D-202 | 数据格式 | JSON | YAML | 机械可解析 |
| D-203 | 时间戳 | UTC | 本地时区 | 见 evidence/research/design-d203-tz.md |
"""

_PM_STATE = """# PM State: sample-key

## Section 1: Snapshot
- Key: sample-key
- Claim-Id: —
- Phase: DESIGN
- Updated: 2026-09-10 00:00
"""

_SPEC_SURVEY = """# Research: spec 调研

## 结论

- 现有能力满足需求（无决策引用）
"""

_D201_SURVEY = """# Research: D-201 模块布局调研

## 结论 → 决策映射

- D-201 模块布局选 A：同构增量
- D-202 数据格式选 JSON：机械可解析
"""

_D203_TZ = """# Research: 时间戳约定

## 结论

- D-203 时间戳用 UTC（Z 后缀）
"""


def _make_key(
    project: pathlib.Path,
    key: str,
    *,
    with_spec: bool = True,
    with_pm_state: bool = True,
    with_evidence: bool = True,
) -> pathlib.Path:
    """Build a key directory under {project}/.agenticdoc/{key}."""
    key_dir = project / ".agenticdoc" / key
    key_dir.mkdir(parents=True)
    if with_spec:
        (key_dir / "spec.md").write_text(_SPEC, encoding="utf-8")
    (key_dir / "design.md").write_text(_DESIGN, encoding="utf-8")
    if with_pm_state:
        (key_dir / "pm-state.md").write_text(_PM_STATE, encoding="utf-8")
    if with_evidence:
        research = key_dir / "evidence" / "research"
        research.mkdir(parents=True)
        (research / "spec-survey.md").write_text(_SPEC_SURVEY, encoding="utf-8")
        (research / "design-d201-survey.md").write_text(_D201_SURVEY, encoding="utf-8")
        (research / "design-d203-tz.md").write_text(_D203_TZ, encoding="utf-8")
    return key_dir


def _run_audit(project: pathlib.Path, key: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AUDIT_CLI), "--key", key, "--project", str(project)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        cwd=str(_MW_DIR),
    )


def _emit_verify(capsys: pytest.CaptureFixture[str], line: str) -> None:
    """Print a [VERIFY] line for quality-gate extraction, bypassing pytest capture."""
    with capsys.disabled():
        print(line)


# ── VC-009: complete sample — exit 0 + three dossier keys ────────────────────


def test_audit_complete_sample_exit0_three_keys(tmp_path, capsys):
    """Complete fixture: exit 0 and the dossier carries ac_list/decision_map/gaps."""
    _make_key(tmp_path, "sample-complete")
    result = _run_audit(tmp_path, "sample-complete")
    assert result.returncode == 0, result.stderr
    dossier = json.loads(result.stdout)
    for field in ("ac_list", "decision_map", "gaps"):
        assert field in dossier
    assert dossier["key"] == "sample-complete"
    assert dossier["phase_edge"] == "DESIGN"
    assert dossier["gaps"] == []
    _emit_verify(capsys, "[VERIFY] VC-009: audit_complete=0")


# ── VC-009: missing research 留底 sample — exit 1 + gaps non-empty ────────────


def test_audit_missing_research_sample_exit1_gaps_nonempty(tmp_path, capsys):
    """Missing research 留底 (no evidence/ dir): exit 1 with a non-empty gap list."""
    _make_key(tmp_path, "sample-missing", with_evidence=False)
    result = _run_audit(tmp_path, "sample-missing")
    assert result.returncode == 1
    dossier = json.loads(result.stdout)
    gaps = dossier["gaps"]
    assert gaps, "gaps must be non-empty for the missing-research sample"
    rules = {gap["rule"] for gap in gaps}
    assert "research-evidence-missing" in rules  # DESIGN edge, no design-*.md
    assert "evidence-ref-missing" in rules  # dangling spec/design citations
    assert "decision-without-evidence" in rules
    for gap in gaps:
        assert gap["item"]
        assert gap["severity"] in ("blocking", "non-blocking")
    assert any(
        gap["rule"] == "research-evidence-missing" and gap["severity"] == "blocking"
        for gap in gaps
    )
    _emit_verify(capsys, "[VERIFY] VC-009: audit_missing=1 gaps_nonempty=true")


# ── VC-009: spec AC table extraction (locked errata format) ──────────────────


def test_ac_extraction_locked_errata_format(tmp_path, capsys):
    """AC checklist comes from table rows only; errata blockquote and prose
    mentions of AC ids must not add or duplicate entries."""
    _make_key(tmp_path, "sample-ac")
    result = _run_audit(tmp_path, "sample-ac")
    assert result.returncode == 0, result.stderr
    dossier = json.loads(result.stdout)
    ac_list = dossier["ac_list"]
    assert ac_list == ["AC-001", "AC-002", "AC-003"]
    assert len(ac_list) == len(set(ac_list))  # errata/prose mentions add nothing
    _emit_verify(capsys, "[VERIFY] VC-009: ac_extract=correct")


# ── VC-009: decision_map key set == design decision set ──────────────────────


def test_decision_map_keys_equal_design_decisions(tmp_path, capsys):
    """decision_map keys are exactly the design decision set (headers ∪ summary
    table rows); both mapping directions are exercised."""
    _make_key(tmp_path, "sample-dm")
    result = _run_audit(tmp_path, "sample-dm")
    assert result.returncode == 0, result.stderr
    dossier = json.loads(result.stdout)
    decision_ids = [entry["decision"] for entry in dossier["decision_map"]]
    # D-203 exists only as a summary-table row — the union must include it.
    assert set(decision_ids) == {"D-201", "D-202", "D-203"}
    by_id = {entry["decision"]: entry["evidence_files"] for entry in dossier["decision_map"]}
    # Cited by the decision (section text citation).
    assert by_id["D-201"] == ["evidence/research/design-d201-survey.md"]
    # Citing the decision (research file mentions D-202; the {date} placeholder
    # citation in D-202's own text is skipped).
    assert by_id["D-202"] == ["evidence/research/design-d201-survey.md"]
    # Cited by the decision via its summary-table row.
    assert by_id["D-203"] == ["evidence/research/design-d203-tz.md"]
    _emit_verify(capsys, "[VERIFY] VC-009: decision_map_parity=true")


# ── phase_edge extraction ─────────────────────────────────────────────────────


def test_phase_edge_null_when_pm_state_missing(tmp_path):
    """Unreadable pm-state.md yields phase_edge null and no error."""
    _make_key(tmp_path, "sample-nophase", with_pm_state=False)
    result = _run_audit(tmp_path, "sample-nophase")
    assert result.returncode == 0, result.stderr
    dossier = json.loads(result.stdout)
    assert dossier["phase_edge"] is None


def test_spec_missing_reports_blocking_gap(tmp_path):
    """Absent spec.md is a blocking gap; the audit still emits a full dossier."""
    _make_key(tmp_path, "sample-nospec", with_spec=False)
    result = _run_audit(tmp_path, "sample-nospec")
    assert result.returncode == 1
    dossier = json.loads(result.stdout)
    assert dossier["ac_list"] == []
    assert [gap["rule"] for gap in dossier["gaps"]] == ["spec-missing"]
    assert dossier["gaps"][0]["severity"] == "blocking"


# ── real key (read-only): locked fingerprints must parse ─────────────────────


def test_real_goal_autopilot_key_dossier():
    """Audit the real goal-autopilot key: the locked spec errata format and the
    D-101..D-116 design must parse; AC ids match the locked fingerprint
    (evidence-requirement.md). Exit 0/1 both valid — real gaps are normal input."""
    result = _run_audit(_REPO_ROOT, "goal-autopilot")
    assert result.returncode in (0, 1)
    dossier = json.loads(result.stdout)
    assert dossier["key"] == "goal-autopilot"
    assert dossier["ac_list"] == [f"AC-{i:03d}" for i in range(1, 26)]
    assert [entry["decision"] for entry in dossier["decision_map"]] == [
        f"D-{i}" for i in range(101, 117)
    ]
    # phase_edge mirrors the live pm-state.md `- Phase:` line (read-only check).
    pm_state = (_REPO_ROOT / ".agenticdoc" / "goal-autopilot" / "pm-state.md").read_text(
        encoding="utf-8"
    )
    phase_line = re.search(r"^\s*-\s*Phase:\s*(\S.*?)\s*$", pm_state, re.MULTILINE)
    assert dossier["phase_edge"] == (phase_line.group(1) if phase_line else None)
    for gap in dossier["gaps"]:
        assert gap["item"]
        assert gap["rule"]
        assert gap["severity"] in ("blocking", "non-blocking")

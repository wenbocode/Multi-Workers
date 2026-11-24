"""Offline L0 regression for reachable AgenticTask workflow active-key readers.

This module only reads UTF-8 Markdown and static source anchors. It does not run
a claim, quality gate, sign-off, decision service, model, build, or install.
T-10 checks the actual M5 and /pm-key new text; they remain L0 text assertions
and do not prove runtime window identity, which other groups/PM must verify.
"""

from pathlib import Path
import re

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

WORKFLOW_PATHS = (
    ".agents/skills/agentic-task/SKILL.md",
    ".agents/skills/agentic-task/capabilities.md",
    ".agents/skills/agentic-task/claude/commands/agentic.md",
    ".agents/skills/agentic-task/claude/commands/pm-key.md",
    ".agents/skills/agentic-task/claude/agents/agentic-pm.md",
    ".agents/skills/agentic-task/claude/skills/workflow-requirements/SKILL.md",
    ".agents/skills/agentic-task/claude/skills/workflow-quality-gate/SKILL.md",
    ".agents/skills/agentic-task/claude/skills/pm-mind/SKILL.md",
    ".agents/skills/agentic-task/core/workflows/requirements.md",
    ".agents/skills/agentic-task/core/workflows/quality-gate.md",
    ".agents/skills/agentic-task/core/pm-mind.md",
    ".agents/skills/agentic-task/references/workflow-requirements.md",
    ".agents/skills/agentic-task/references/workflow-quality-gate.md",
    ".agents/skills/agentic-task/references/pm-mind.md",
    ".claude/commands/agentic.md",
    ".claude/commands/pm-key.md",
    ".claude/agents/agentic-pm.md",
    ".claude/skills/workflow-requirements/SKILL.md",
    ".claude/skills/workflow-quality-gate/SKILL.md",
    ".claude/skills/pm-mind/SKILL.md",
)

JUNCTION_PREFIX = ".agents/skills/agentic-task/"
PHYSICAL_SOURCE_ROOT = Path("packages/multi-workers/.tmp/agentic-task")

PHYSICAL_SOURCE_ALIASES = tuple(
    (
        path,
        (PHYSICAL_SOURCE_ROOT / path[len(JUNCTION_PREFIX) :]).as_posix(),
    )
    for path in WORKFLOW_PATHS
    if path.startswith(JUNCTION_PREFIX)
)

MIRROR_GROUPS = (
    (
        ".agents/skills/agentic-task/claude/commands/agentic.md",
        (".claude/commands/agentic.md",),
    ),
    (
        ".agents/skills/agentic-task/claude/commands/pm-key.md",
        (".claude/commands/pm-key.md",),
    ),
    (
        ".agents/skills/agentic-task/claude/agents/agentic-pm.md",
        (".claude/agents/agentic-pm.md",),
    ),
    (
        ".agents/skills/agentic-task/claude/skills/workflow-requirements/SKILL.md",
        (
            ".agents/skills/agentic-task/core/workflows/requirements.md",
            ".agents/skills/agentic-task/references/workflow-requirements.md",
            ".claude/skills/workflow-requirements/SKILL.md",
        ),
    ),
    (
        ".agents/skills/agentic-task/claude/skills/workflow-quality-gate/SKILL.md",
        (
            ".agents/skills/agentic-task/core/workflows/quality-gate.md",
            ".agents/skills/agentic-task/references/workflow-quality-gate.md",
            ".claude/skills/workflow-quality-gate/SKILL.md",
        ),
    ),
    (
        ".agents/skills/agentic-task/claude/skills/pm-mind/SKILL.md",
        (
            ".agents/skills/agentic-task/core/pm-mind.md",
            ".agents/skills/agentic-task/references/pm-mind.md",
            ".claude/skills/pm-mind/SKILL.md",
        ),
    ),
)

QG_PATHS = tuple(
    path for path in WORKFLOW_PATHS if "workflow-quality-gate" in path or path.endswith("quality-gate.md")
)

PM_KEY_PATHS = (
    ".agents/skills/agentic-task/claude/commands/pm-key.md",
    ".claude/commands/pm-key.md",
)

QG_T10_PATHS = (
    *QG_PATHS,
    "packages/multi-workers/.tmp/agentic-task/claude/skills/workflow-quality-gate/SKILL.md",
    "packages/multi-workers/.tmp/agentic-task/core/workflows/quality-gate.md",
    "packages/multi-workers/.tmp/agentic-task/references/workflow-quality-gate.md",
)

PM_KEY_T10_PATHS = (
    *PM_KEY_PATHS,
    "packages/multi-workers/.tmp/agentic-task/claude/commands/pm-key.md",
)

T10_PATHS = QG_T10_PATHS + PM_KEY_T10_PATHS

CLAIM_ENTRANCE_PATHS = (
    ".agents/skills/agentic-task/claude/commands/agentic.md",
    ".agents/skills/agentic-task/claude/commands/pm-key.md",
    ".claude/commands/agentic.md",
    ".claude/commands/pm-key.md",
    ".agents/skills/agentic-task/claude/skills/workflow-requirements/SKILL.md",
    ".agents/skills/agentic-task/core/workflows/requirements.md",
    ".agents/skills/agentic-task/references/workflow-requirements.md",
    ".claude/skills/workflow-requirements/SKILL.md",
)

ALLOWED_LEGACY_NOTE = "The legacy single-value scalar format is unsupported."
ALLOWED_EXPLANATION_MARKERS = (
    ALLOWED_LEGACY_NOTE,
    "不从所有 active 任取 current-key",
    "不额外 release 旧 key",
)

COMMON_MARKERS = (
    "Active-key contract:",
    "`active_keys: <JSON string array>`",
    "(`[]` when empty)",
    "complete projection, never an authorization",
    "只投影不授权",
    ALLOWED_LEGACY_NOTE,
    "Owner resolution:",
    "`status=active`",
    "`windowClaimId`",
    "Multiple active keys are not permission ambiguity when one's own row is unique.",
    "show the whole set and require an explicit choice",
    "never pick first, latest, or array index 0.",
    "Claim mutations:",
    "shared lock",
    "A markdown-only write never creates a claim or grants authority",
    "without a mutation tool, stop and report unbound",
    "Caller boundary:",
    "`switch_key`",
    "short-lived script and is not a window identity",
    "`--claim-id`",
    "existing ClaimId fields only",
    "current or direct-parent live process",
    "never adds columns",
    "never guesses common ancestors through multi-level shell chains",
    "call a real window tool or report unbound",
    "never fabricate `host:pid`",
)

QG_MARKERS = (
    "> QG gate contract: Step 1-5, M1-M6, all preconditions, pass thresholds, and the external dp-QG material/basis/signoff checks remain unchanged; only the Evidence path key binding changes.",
    "### Step 1 — 加载基准文档",
    "### Step 2 — 提炼问题清单",
    "### Step 3 — 证据链核查",
    "### Step 4 — 二次印证",
    "### Step 5 — 输出质检报告",
    "### Step M1 — 检测 migrator 配置",
    "### Step M2 — 执行全量验证",
    "### Step M3 — 读取验证结果",
    "### Step M4 — 在会话中展示结果",
    "### Step M5 — 写入 Evidence Ledger",
    "### Step M6 — 质检门禁判定",
    "spec.md 存在 AC 编号",
    "design.md 存在 VC 编号",
    "AC→VC 映射覆盖 100%",
    "evidence-requirement.md 存在",
    "ac_fingerprint 一致",
    "evidence/baseline/ 非空",
    "每个 task 有非空 ac_refs/vc_refs",
    "## 质检门禁通过标准",
    "Stage 完成质检",
    "全量质检（合入前）",
    "紧急合入",
    "override",
    "### AC 覆盖",
    "| AC-021 |",
    "migrator validate --all",
    "| $(date -I) | migrator validate --all | engine-build=PASS game-build=FAIL | VC-010~014 |",
    "`KEY` 仅用于定位报告路径，不授予写权限",
    "顶部共同合同只是语义声明",
    "本节不提供独立 shell 可执行追加命令",
    "经写面检查的窗口写入工具",
    "明确 `unbound` 并停止写",
    "不扩大写面、不新增签收许可、不执行真实门禁",
)

FORBIDDEN_PATTERNS = {
    "legacy-scalar-line": re.compile(r"(?m)^[ \t]*active[ \t]*:"),
    "legacy-scalar-grep": re.compile(r"grep\s+['\"]active[ \t]*:"),
    "legacy-scalar-write": re.compile(
        r"(?:更新|写入)[^\n]{0,80}_index\.md[^\n]{0,80}active[ \t]*:"
    ),
    "legacy-scalar-example": re.compile(
        r"active[ \t]*:[ \t]*(?:\{key|<key>|my-feature-key|key-name)"
    ),
    "legacy-active-grep-awk": re.compile(
        r"grep\s+['\"]active[ \t]*:.*awk\s+\{\s*print\s+\$2\s*\}"
    ),
    "active-array-index-zero": re.compile(r"active_keys\s*\[\s*0\s*\]"),
    "active-key-from-projection": re.compile(
        r"ACTIVE_KEY\s*=\s*[^\n]*(?:grep|active_keys)"
    ),
    "global-release": re.compile(
        r"claim-first-then-release|release\s+<current-key>|release\s+\$?current-key"
    ),
    "global-current-guess": re.compile(
        r"获取当前 active key|current-key（可能为空）|(?<!不)从所有\s*active[^\n]*current-key"
    ),
    "legacy-active-count-branch": re.compile(
        r"active_count\s*(?:>\s*1|=\s*1)\s*→"
    ),
    "markdown-only-claim": re.compile(r"仅写\s*_index\.md"),
}

QG_FORBIDDEN_PATTERNS = {
    "grep-active-scalar": re.compile(r"grep\s+['\"]active[ \t]*:"),
    "awk-second-field": re.compile(r"awk\s+\{\s*print\s+\$2\s*\}"),
    "projected-active-key": re.compile(r"ACTIVE_KEY=|active_keys\s*\[\s*0\s*\]"),
    "bare-append": re.compile(r">>"),
    "current-claim-assignment": re.compile(r"(?m)^\s*CURRENT_CLAIM\s*="),
}

M5_START = "### Step M5 — 写入 Evidence Ledger"
M5_END = "### Step M6 — 质检门禁判定"
M5_REQUIRED_ANCHORS = (
    "`KEY` 仅用于定位报告路径，不授予写权限",
    "顶部共同合同只是语义声明",
    "本节不提供独立 shell 可执行追加命令",
    "原子前置核对",
    "具可信 `windowClaimId` 的当前窗口",
    "经写面检查的窗口写入工具",
    "独立 shell 不提供可信窗口身份",
    "不能设置任意 `CURRENT_CLAIM`",
    "不能伪造 `host:pid`",
    "也不能用 `--claim-id` 字符串替代窗口身份",
    "`detect_root.py`",
    "小写 kebab-case 合法性校验",
    "目标 `KEY` 行唯一",
    "`status=active`",
    "`ClaimId` 与 `windowClaimId` 精确相等",
    "`active + exact self` 行唯一",
    "验证 `${AGENTICDOC_ROOT}/${KEY}/pm-state.md` 存在",
    "目标路径唯一",
    "写面检查通过",
    "无可靠窗口工具",
    "明确 `unbound` 并停止写",
    "由同一窗口工具在写面校验下追加以下原 Evidence 记录",
    "不扩大写面、不新增签收许可、不执行真实门禁",
    "| $(date -I) | migrator validate --all | engine-build=PASS game-build=FAIL | VC-010~014 |",
    "`guard_pm_state.py` 不是身份授权",
)
M5_FORBIDDEN_PATTERNS = {
    "bare-append": re.compile(r">>"),
    "shell-append-command": re.compile(r"(?m)^\s*(?:echo|printf)\b.*>>"),
    "current-claim-assignment": re.compile(r"(?m)^\s*CURRENT_CLAIM\s*="),
    "claim-id-template": re.compile(r"--claim-id\s+<"),
    "host-pid-assignment": re.compile(r"host:pid\s*="),
}

PM_KEY_NEW_START = "### `/pm-key new <key-name> [--desc <一句话说明>] [--deps <dep1,dep2>]`"
PM_KEY_NEW_END = "### `/pm-key switch <key-name>`"
PM_KEY_NEW_REQUIRED_ANCHORS = (
    "按运行环境分流",
    "pi 活窗口：调用 `switch_key(key-name)`（真实 `windowClaimId`）",
    "这是唯一可直接进入步骤 4 的 live 窗口绑定路径",
    "独立 Python CLI",
    'python {PLATFORM_DIR}/scripts/update_index.py claim {key-name} --desc "<desc>" --deps "<deps>"',
    "保留为显式独立管理用途",
    "默认 claim 是短命脚本自身 ID，不能把脚本 ID 当 window",
    "不能直接宣称激活 live 窗口或 `current_key` 绑定",
    "仅当现有 ClaimId 可验证为当前或直接父真实活进程时",
    "一次性管理命令",
    "`--claim-id <verified>`",
    "只桥接 current/direct parent，不写猜测 ancestor 脚本",
    "shell 多层不猜共同祖先",
    "不设置任意 `CURRENT_CLAIM`",
    "不伪造 `host:pid`",
    "无可靠窗口工具或受验桥接时明确 `unbound` 并停止",
    "不进入步骤 4",
    "也不执行任何需窗口归属的后续操作",
    "仅当步骤 3a 的真实 `switch_key` 绑定成功且权威行 exact self/active 唯一回读通过时",
    "否则输出 `unbound` 并停止，不记 `current_key = {key-name}`",
)
PM_KEY_NEW_FORBIDDEN_PATTERNS = {
    "default-claim-activates-agent": re.compile(r"默认[^\n]{0,80}(?:激活 PM Agent|激活 live 窗口)"),
    "default-claim-sets-current-key": re.compile(r"默认[^\n]{0,80}current_key\s*="),
    "guessed-ancestor-script": re.compile(r"(?<!不)写猜测\s*ancestor\s*脚本"),
    "current-claim-assignment": re.compile(r"(?m)^\s*CURRENT_CLAIM\s*="),
    "claim-id-current-claim": re.compile(r"--claim-id\s+\$CURRENT_CLAIM"),
    "fabricated-host-pid-assignment": re.compile(r"host:pid\s*=\s*['\"]"),
}

QG_PRESERVED_HEADINGS = (
    "### Step 1 — 加载基准文档",
    "### Step 2 — 提炼问题清单",
    "### Step 3 — 证据链核查",
    "### Step 4 — 二次印证",
    "### Step 5 — 输出质检报告",
    "#### 前置门禁（任一不满足即报告 ❌ 并中止）",
    "### Step M1 — 检测 migrator 配置",
    "### Step M2 — 执行全量验证",
    "### Step M3 — 读取验证结果",
    "### Step M4 — 在会话中展示结果",
    "### Step M5 — 写入 Evidence Ledger",
    "### Step M6 — 质检门禁判定",
    "## 质检门禁通过标准",
    "### AC 覆盖",
)
QG_SEVEN_PRECONDITIONS = (
    "spec.md 存在 AC 编号",
    "design.md 存在 VC 编号",
    "AC→VC 映射覆盖 100%",
    "evidence-requirement.md 存在",
    "ac_fingerprint 一致",
    "evidence/baseline/ 非空",
    "每个 task 有非空 ac_refs/vc_refs",
)
QG_PASS_OVERRIDE_ANCHORS = (
    "Stage 完成质检",
    "全量质检（合入前）",
    "紧急合入",
    "override",
)


def read_text(relative_path: str) -> str:
    path = REPO_ROOT / relative_path
    data = path.read_bytes()
    data.decode("utf-8")
    return data.decode("utf-8").replace("\r\n", "\n")


def extract_section(text: str, start: str, end: str) -> str:
    assert start in text, f"missing section start: {start}"
    assert end in text, f"missing section end: {end}"
    return start + text.split(start, 1)[1].split(end, 1)[0]


def scrub_allowed_explanations(text: str) -> str:
    kept = []
    for line in text.splitlines():
        if any(marker in line for marker in ALLOWED_EXPLANATION_MARKERS):
            continue
        kept.append(line)
    return "\n".join(kept)


def test_path_coverage_is_complete() -> None:
    assert len(WORKFLOW_PATHS) == 20
    assert len(set(WORKFLOW_PATHS)) == 20
    assert len(PHYSICAL_SOURCE_ALIASES) == 14
    assert len(QG_PATHS) == 4
    assert len(CLAIM_ENTRANCE_PATHS) == 8
    assert len(QG_T10_PATHS) == 7
    assert len(PM_KEY_T10_PATHS) == 3
    assert len(T10_PATHS) == 10
    for path in WORKFLOW_PATHS:
        assert not path.startswith("packages/multi-workers/.tmp/dpc")


@pytest.mark.parametrize("relative_path", WORKFLOW_PATHS)
def test_all_reachable_workflow_paths_exist_and_are_utf8(relative_path: str) -> None:
    text = read_text(relative_path)
    assert text
    assert "\r" not in text.replace("\r\n", "")


@pytest.mark.parametrize(("junction_path", "physical_path"), PHYSICAL_SOURCE_ALIASES)
def test_vc008_physical_junction_source_aliases_match(junction_path: str, physical_path: str) -> None:
    assert (REPO_ROOT / physical_path).read_bytes() == (REPO_ROOT / junction_path).read_bytes()


@pytest.mark.parametrize("relative_path", WORKFLOW_PATHS)
def test_vc007_active_key_contract_is_present_in_every_workflow(relative_path: str) -> None:
    text = read_text(relative_path)
    missing = [marker for marker in COMMON_MARKERS if marker not in text]
    assert not missing, f"{relative_path}: missing {missing}"


@pytest.mark.parametrize("relative_path", WORKFLOW_PATHS)
def test_vc007_no_legacy_scalar_or_global_release_patterns(relative_path: str) -> None:
    text = scrub_allowed_explanations(read_text(relative_path))
    hits = {
        name: pattern.search(text).group(0)
        for name, pattern in FORBIDDEN_PATTERNS.items()
        if pattern.search(text) is not None
    }
    assert not hits, f"{relative_path}: forbidden patterns {hits}"


def test_allowed_explanations_do_not_count_as_legacy_patterns() -> None:
    note = ALLOWED_LEGACY_NOTE
    prohibition = "不从所有 active 任取 current-key，不额外 release 旧 key"
    assert scrub_allowed_explanations(note) == ""
    assert scrub_allowed_explanations(prohibition) == ""
    assert not any(pattern.search(note) for pattern in FORBIDDEN_PATTERNS.values())
    assert not any(pattern.search(prohibition) for pattern in FORBIDDEN_PATTERNS.values())


@pytest.mark.parametrize("relative_path", CLAIM_ENTRANCE_PATHS)
def test_vc008_claim_entrances_use_verified_mutation_and_no_global_release(relative_path: str) -> None:
    text = read_text(relative_path)
    assert "`switch_key`" in text
    assert "markdown-only" in text
    assert "stop and report unbound" in text
    assert "current or direct-parent live process" in text
    assert "claim-first-then-release" not in text
    assert "release <current-key>" not in text
    assert "获取当前 active key" not in text
    assert not re.search(r"(?<!不)从所有\s*active[^\n]*current-key", text)
    assert "不手工写 `_index.md`" in text or "禁止手工写 `_index.md`" in text


@pytest.mark.parametrize("relative_path", QG_PATHS)
def test_vc008_qg_uses_bound_key_and_preserves_all_gate_conditions(relative_path: str) -> None:
    text = read_text(relative_path)
    missing = [marker for marker in QG_MARKERS if marker not in text]
    assert not missing, f"{relative_path}: missing QG anchors {missing}"
    hits = {
        name: pattern.search(text).group(0)
        for name, pattern in QG_FORBIDDEN_PATTERNS.items()
        if pattern.search(text) is not None
    }
    assert not hits, f"{relative_path}: forbidden QG key lookup {hits}"


@pytest.mark.parametrize("relative_path", QG_T10_PATHS)
def test_t10_qg_m5_has_no_unvalidated_shell_append_and_requires_exact_self_owner(relative_path: str) -> None:
    text = read_text(relative_path)
    section = extract_section(text, M5_START, M5_END)
    missing = [anchor for anchor in M5_REQUIRED_ANCHORS if anchor not in section]
    assert not missing, f"{relative_path}: M5 missing actual owner-check text {missing}"
    hits = {
        name: pattern.search(section).group(0)
        for name, pattern in M5_FORBIDDEN_PATTERNS.items()
        if pattern.search(section) is not None
    }
    assert not hits, f"{relative_path}: M5 executable/shortcut patterns {hits}"
    assert section.count(">>") == 0


@pytest.mark.parametrize("relative_path", QG_T10_PATHS)
def test_t10_qg_preserves_steps_preconditions_pass_override_and_ac_coverage(relative_path: str) -> None:
    text = read_text(relative_path)
    required = (*QG_PRESERVED_HEADINGS, *QG_SEVEN_PRECONDITIONS, *QG_PASS_OVERRIDE_ANCHORS)
    missing = [anchor for anchor in required if anchor not in text]
    assert not missing, f"{relative_path}: QG gate contract missing {missing}"
    assert "external dp-QG material/basis/signoff checks remain unchanged" in text


@pytest.mark.parametrize("relative_path", PM_KEY_T10_PATHS)
def test_t10_pm_key_new_splits_pi_and_cli_and_never_treats_script_id_as_window(relative_path: str) -> None:
    text = read_text(relative_path)
    section = extract_section(text, PM_KEY_NEW_START, PM_KEY_NEW_END)
    missing = [anchor for anchor in PM_KEY_NEW_REQUIRED_ANCHORS if anchor not in section]
    assert not missing, f"{relative_path}: /pm-key new missing actual environment split {missing}"
    hits = {
        name: pattern.search(section).group(0)
        for name, pattern in PM_KEY_NEW_FORBIDDEN_PATTERNS.items()
        if pattern.search(section) is not None
    }
    assert not hits, f"{relative_path}: /pm-key new identity spoof or guessed ancestor {hits}"
    cli_lines = [
        line for line in section.splitlines()
        if "python {PLATFORM_DIR}/scripts/update_index.py claim" in line
    ]
    assert cli_lines, f"{relative_path}: explicit independent CLI management command was removed"
    for line in cli_lines:
        assert "激活" not in line, f"{relative_path}: default CLI line claims activation: {line}"
        assert "current_key" not in line, f"{relative_path}: default CLI line claims current_key: {line}"


def test_t10_static_text_checks_do_not_claim_runtime_identity() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert "do not prove runtime window identity" in source
    assert "decision_service_not_executed=true" in source


@pytest.mark.parametrize(("source", "mirrors"), MIRROR_GROUPS)
def test_vc008_installed_and_framework_mirrors_are_byte_identical(
    source: str, mirrors: tuple[str, ...]
) -> None:
    source_bytes = (REPO_ROOT / source).read_bytes()
    for mirror in mirrors:
        assert (REPO_ROOT / mirror).read_bytes() == source_bytes


def test_vc009_caller_boundary_and_decision_gate_anchors_are_static_only() -> None:
    decision_points = (REPO_ROOT / "packages/multi-workers/decision_points.py").read_text(encoding="utf-8")
    decision_validity = (REPO_ROOT / "packages/multi-workers/decision_validity.py").read_text(encoding="utf-8")
    assert "dp-QG" in decision_points
    assert "prepared_request_issues" in decision_points
    assert "basis_issue" in decision_points
    assert "material" in decision_points
    assert "assess_signoff" in decision_validity
    assert "signoff" in decision_validity


@pytest.fixture(scope="session", autouse=True)
def _emit_l0_vc_markers(request):
    yield
    session = request.session
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None or session.testsfailed != 0 or session.testscollected < 90:
        return
    reporter.write_line("")
    reporter.write_line("[VERIFY] VC-007: collection_safe=true layer=L0/static-docs")
    reporter.write_line("[VERIFY] VC-008: entrances_aligned=true layer=L0/workflow-docs")
    reporter.write_line("[VERIFY] VC-009: caller_boundary_documented=true layer=L0/static-docs")
    reporter.write_line("[VERIFY] T-10: m5_owner_checked=true cli_boundary_split=true layer=L0/static-docs")
    reporter.write_line("[VERIFY] L0: static_docs_only=true decision_service_not_executed=true")

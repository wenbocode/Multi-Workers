"""build_decide_cases.py - offline generator for the four DP workbench cases.

The decision workbench ships exactly four *synthetic* decision books (design
D007 / §4.5): one for each of ``dp1``, ``dp2``, ``dp3`` and ``dp25``. They exist
so a human can pick a complete, editable book on the DP test page and observe
the real decision chain without inventing material by hand.

This script is the case's only writer and it is deliberately boring:

* **offline** - it reads the registry (``decision_points``) and this file's own
  bytes; it never reads a credential, opens a socket, starts a service or calls
  a model;
* **complete** - every business field carries real prose. There are no
  placeholders, no ellipses and no TODO markers, so a case never turns into a
  half-filled book that the observation gate would have to refuse;
* **single authority** - the business field names are the design §2 / plan
  names. ``schema_version``, ``decision_point`` and ``questions_version`` come
  from the registry/scaffold authority, never from a second hand-kept list;
* **honest provenance** - every business field's ``notes.evidence`` points at
  the exact line of this generator that defines that material (``path:line``).
  The evidence is therefore resolvable in the repository, not a scaffold
  placeholder;
* **budget respected** - the existing no-truncation state budget is checked
  here and a too-large case fails loudly instead of being shortened.

Regenerate (no network, no credential, no model)::

    python scripts/build_decide_cases.py

The drift guard in ``test_decision_context_workbench.py`` re-runs
:func:`write_cases` and compares the result byte-for-byte with the shipped
files, so a hand edit that forgets to regenerate is caught.

Typed registry validation (``decision_book.check_book`` against the *new*
dp1/dp2/dp3/dp25 contract) still belongs to T01/T08: this module only reports
what the current registry says, without pretending the contract is final.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Mapping

# The generator is also runnable as a plain script (``python scripts/build_decide_cases.py``),
# where sys.path[0] is the scripts directory; the decision modules live one level up.
_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

import decision  # noqa: E402 - path bootstrap above
import decision_book  # noqa: E402
import decision_points  # noqa: E402

#: Shell version of the case container
#: (``{case_version, dp, title, note, questions, book}``).
CASE_VERSION = 1

#: The only four case ids the workbench serves (design D007 - no other dp gets
#: a bundled case, and the route never scans a directory).
CASE_IDS: dict[str, str] = {
    "dp1-dispatch-type": "dp1.json",
    "dp2-checkpoint-split": "dp2.json",
    "dp3-worker-clarify": "dp3.json",
    "dp25-signoff-conclusion": "dp25.json",
}

HERE = pathlib.Path(__file__).resolve()
ASSET_DIR = HERE.parent.parent
DEFAULT_OUT_DIR = ASSET_DIR / "decide_cases"

REGISTRY_PATH = "packages/multi-workers/decide_registry.json"
DECISION_BOOK_PATH = "packages/multi-workers/decision_book.py"

#: Title/note live in the case *shell* only: the monitor never forwards them to
#: validate/submit, so they can never reach the model state (design §4.5).
TITLES: dict[str, str] = {
    "dp1-dispatch-type": "旧记录只读筛选：任务类型判定",
    "dp2-checkpoint-split": "检查点：收窄、拆分、直接执行还是上抛人",
    "dp3-worker-clarify": "旧记录 signoff 摘录：候选与影响",
    "dp25-signoff-conclusion": "AC-011~016 工作台收尾签收判断",
}

NOTES: dict[str, str] = {
    "dp1-dispatch-type": (
        "合成 case：材料取自本次工作台设计的只读筛选范围，用于观察 dp1 的类型判定；"
        "不含任何凭证或生产记录正文。"
    ),
    "dp2-checkpoint-split": (
        "合成 case：PM 正在判断检查点动作，附一段真实形态的 worker 执行情况；"
        "选项仍由 registry 原文提供，case 不改写问题。"
    ),
    "dp3-worker-clarify": (
        "合成 case：提问者带着两个可区分候选请求澄清，用于观察 dp3 的动态候选消费；"
        "候选说明原文随材料发送。"
    ),
    "dp25-signoff-conclusion": (
        "合成 case：按交付目标、实际完成、已验与未验、未完成影响四段整理，"
        "用于观察 dp25 的收尾判断；不以任务数代替证据。"
    ),
}

#: Business material, exactly the design §2 / plan field names. Strings are
#: verbatim source text; dp3 uses the typed background/candidates shape and
#: dp25 the typed four-section shape (design allows typed or string, one
#: authority - here: typed where the design declares structure).
MATERIALS: dict[str, dict[str, object]] = {
    "dp1-dispatch-type": {
        "task_goal": (
            "给 mw decide monitor 增加旧记录只读筛选，不重构页面，也不改动任何写入链路。"
        ),
        "task_requirements": (
            "只读，不写 archive/signoff/authority；不新增第二套事件协议；"
            "不改动其余 21 个 DP 的既有契约。"
        ),
        "task_deliverables": (
            "旧记录只读筛选的结论说明；本任务的 worker report.md 与定向 GREEN 日志。"
        ),
    },
    "dp2-checkpoint-split": {
        "task_goal": (
            "在旧记录只读筛选完成后判断检查点动作：收窄、拆分、直接执行还是上抛人。"
        ),
        "task_requirements": (
            "主表五列与四个处理状态必须保留；旧记录不得展开 DAG；"
            "不得按 key 或时间推断关联。"
        ),
        "task_deliverables": (
            "workbench 投影的接线说明；旧记录日志弹窗；四状态与 DAG 的 DOM 断言日志。"
        ),
        "pm_decision_background": (
            "T06 的 history 投影尚未交付，T07 已独立完成表结构、弹窗与本地 case；"
            "facets 下拉与 workbench 正文仍等后端。当前预算只够一块，"
            "需要判断是收窄到 facets 接线、拆成投影与路由两个任务、PM 直接做完，"
            "还是以高风险上抛给人。"
        ),
        "worker_execution": (
            "已完成：五列表结构、四状态渲染、十节点 DAG 弹窗与日志弹窗。"
            "剩余：facets 下拉接线与 workbench 正文渲染，等 T06 投影。"
            "阻塞：旧记录 detail 无 workbench 字段，只能显示未记录。"
            "尝试：改过两版 DAG 节点顺序，最终按后端投影顺序渲染。"
            "时间预算：已用 35 分钟，剩余 25 分钟。"
        ),
    },
    "dp3-worker-clarify": {
        "question": "旧记录详情里能否展示该 key 已有的 signoff 记录来佐证状态？",
        "background": {
            "task_goal": "为工作台的旧记录提供可核对的状态说明。",
            "current_state": "详情弹窗只列日志结构，尚未摘录 signoff 行。",
            "decision_reason": "是否展示会直接影响用户对旧数据状态的解读。",
            "constraints_impact": "只能只读展示，不得推断链路，也不得改写历史记录。",
        },
        "handling_options": [
            {
                "id": "c1",
                "label": "展示已有 signoff 记录（只读）",
                "description": (
                    "只列历史文件里真实存在的签收行与时间，不做关联推断，缺字段标未记录。"
                ),
            },
            {
                "id": "c2",
                "label": "不展示，统一标未记录",
                "description": (
                    "最保守：旧记录只显示已有日志结构，signoff 一律显示未记录，零推断。"
                ),
            },
        ],
    },
    "dp25-signoff-conclusion": {
        "delivery_goal": (
            "AC-011~016 在工作台可用：四状态主表、十节点 DAG、旧记录无 DAG、"
            "重试精确关联。"
        ),
        "actual_completion": (
            "已完成五列表、四状态渲染、DAG 与日志弹窗、离线 case 选择与本地校验；"
            "测试记录保持独立 scope=test，观察提交未执行任何业务动作。"
        ),
        "verification_evidence": {
            "verified": [
                "test_decision_context_workbench.py 的四状态与 DAG DOM 用例",
                "离线 case 生成器漂移守卫（生成物逐字节一致）",
            ],
            "unverified": [
                "真实浏览器窗口可见性",
                "真实 Jev 选择质量",
                "编辑正文经真实 loopback 发送的断言（待 T01 契约）",
            ],
        },
        "unfinished_impact": [
            "facets 下拉与 workbench 正文依赖 T06 投影；未接线前只显示未记录。",
            "真实浏览器与真实 Jev 验收未执行，不得据此声称整条链路已验。",
        ],
    },
}


# ---------------------------------------------------------------------------
# Provenance: point every business field at its own definition line
# ---------------------------------------------------------------------------


def _first_leaf(value: object, *, minimum: int = 8) -> str:
    """First substantive string of a material value (short ids are not anchors)."""
    if isinstance(value, str):
        return value if len(value.strip()) >= minimum else ""
    if isinstance(value, Mapping):
        for item in value.values():
            leaf = _first_leaf(item, minimum=minimum)
            if leaf:
                return leaf
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            leaf = _first_leaf(item, minimum=minimum)
            if leaf:
                return leaf
        return ""
    return ""


def _line_of(text: str, needle: str, *, what: str) -> int:
    """1-based line of ``needle`` in ``text``; a missing/ambiguous needle fails."""
    matches = [
        index
        for index, line in enumerate(text.splitlines(), start=1)
        if needle and needle in line
    ]
    if not matches:
        raise SystemExit(f"build_decide_cases: cannot locate {what} in {HERE.name}")
    if len(matches) > 1:
        raise SystemExit(
            f"build_decide_cases: {what} is ambiguous ({len(matches)} lines); "
            "make the case material text distinct"
        )
    return matches[0]


def _evidence_reference(prefix: str, *, what: str) -> str:
    """``path:line`` of the unique source line carrying this material.

    Material literals may be wrapped across lines, so the longest prefix that
    still matches exactly one source line is used. No match means the shipped
    literal and the recorded material drifted apart - fail loudly instead of
    pointing evidence at a random line.
    """
    text = HERE.read_text(encoding="utf-8")
    for length in range(min(len(prefix), 60), 7, -1):
        candidate = prefix[:length]
        matches = [
            index
            for index, line in enumerate(text.splitlines(), start=1)
            if candidate in line
        ]
        if len(matches) == 1:
            return f"packages/multi-workers/scripts/{HERE.name}:{matches[0]}"
    raise SystemExit(f"build_decide_cases: {what} has no unique source line in {HERE.name}")


def _structural_evidence(dp: str) -> dict[str, str]:
    """Evidence for the identity fields the registry currently expects."""
    references: dict[str, str] = {}
    allowed = set(decision_book.required_state_paths(dp)) | set(
        decision_book.optional_state_paths(dp)
    )
    if "schema_version" in allowed:
        book_text = (ASSET_DIR / "decision_book.py").read_text(encoding="utf-8")
        for index, line in enumerate(book_text.splitlines(), start=1):
            if line.startswith("BOOK_SCHEMA_VERSION") and "=" in line:
                references["schema_version"] = f"{DECISION_BOOK_PATH}:{index}"
                break
        else:  # pragma: no cover - the constant always exists in this module
            raise SystemExit("build_decide_cases: BOOK_SCHEMA_VERSION is missing")
    for name in ("decision_point", "questions_version"):
        if name in allowed:
            references[name] = f"{REGISTRY_PATH}:1"
    return references


# ---------------------------------------------------------------------------
# Case construction
# ---------------------------------------------------------------------------


def _structural_state(dp: str) -> dict[str, object]:
    """Identity fields from the registry authority (no second field list)."""
    state: dict[str, object] = {
        "schema_version": decision_book.BOOK_SCHEMA_VERSION,
        "decision_point": dp,
    }
    point = decision_points.get_decision_point(dp)
    if point.questions_version:
        state["questions_version"] = point.questions_version
    return state


def _business_state(dp: str) -> dict[str, object]:
    material = MATERIALS.get(dp)
    if material is None:
        raise SystemExit(f"build_decide_cases: no material for {dp!r}")
    return json.loads(json.dumps(material, ensure_ascii=False))


_MISSING = object()


def _lookup(state: object, dotted: str) -> object:
    current = state
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _evidence_for_state(dp: str, state: Mapping[str, object]) -> dict[str, str]:
    """One ``path:line`` evidence entry per registry-declared state path.

    The registry is the authority for *which* paths need evidence (T01's
    contract): required paths must be present in the material, optional paths
    get evidence when the case uses them. A required path the material does not
    define is a real contract drift and fails the generator instead of shipping
    an incomplete case.
    """
    evidence: dict[str, str] = {}
    required = decision_book.required_state_paths(dp)
    optional = decision_book.optional_state_paths(dp)
    for path in required:
        value = _lookup(state, path)
        if value is _MISSING:
            raise SystemExit(
                f"build_decide_cases: {dp} requires the registry field {path!r} but the "
                "case material does not define it"
            )
        leaf = _first_leaf(value)
        if not leaf:
            raise SystemExit(f"build_decide_cases: {dp}.{path} has no substantive material")
        evidence[path] = _evidence_reference(leaf, what=f"{dp}.{path}")
    for path in optional:
        value = _lookup(state, path)
        if value is _MISSING:
            continue
        leaf = _first_leaf(value)
        if leaf:
            evidence[path] = _evidence_reference(leaf, what=f"{dp}.{path}")
    evidence.update(_structural_evidence(dp))
    return evidence


def build_case(dp: str) -> dict[str, object]:
    """One complete case shell for ``dp`` (deterministic, offline).

    The shell carries the DP's *complete native questions* from the registry
    (T10): the case's default question set is the registry's own, including the
    model-facing instructions and criteria, so the test page can show and edit
    them. Only ``instructions`` is editable on the observation path; dp3 keeps
    ``state.handling_options`` as its only candidate source (the request builder
    generates its criteria from the state, and the case ships no second copy).
    """
    if dp not in CASE_IDS:
        raise SystemExit(f"build_decide_cases: {dp!r} is not one of the four case ids")
    state = _business_state(dp)
    state.update(_structural_state(dp))

    evidence = _evidence_for_state(dp, state)

    book: dict[str, object] = {
        "schema_version": decision_book.BOOK_SCHEMA_VERSION,
        "decision_point": dp,
        "state": state,
        "notes": {"evidence": evidence},
    }
    encoded = decision._encode_state(state)
    if len(encoded) > decision_points.MAX_STATE_BYTES:
        raise SystemExit(
            f"build_decide_cases: {dp} state is {len(encoded)} bytes > "
            f"{decision_points.MAX_STATE_BYTES}; shorten the material instead of truncating"
        )
    # The native questions are the registry's (single authority). They live in
    # the case *shell* only: the monitor forwards them to validate/submit as the
    # observation override and they never enter the sent book.
    questions = decision_points.questions_map(decision_points.get_decision_point(dp))
    issues = decision_points.question_override_issues(dp, questions, state)
    if issues:
        detail = "; ".join(f"{path}: {issue}" for path, issue in issues)
        raise SystemExit(f"build_decide_cases: {dp} questions are not legal ({detail})")
    return {
        "case_version": CASE_VERSION,
        "dp": dp,
        "title": TITLES[dp],
        "note": NOTES[dp],
        "questions": questions,
        "book": book,
    }


def build_cases() -> dict[str, dict[str, object]]:
    """Every case, keyed by dp id (deterministic order of :data:`CASE_IDS`)."""
    return {dp: build_case(dp) for dp in CASE_IDS}


def render_case(case: Mapping[str, object]) -> str:
    """Canonical on-disk form (stable key order, UTF-8, trailing newline)."""
    return json.dumps(case, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

def write_cases(out_dir: pathlib.Path | str = DEFAULT_OUT_DIR) -> list[pathlib.Path]:
    """Write the four case files; returns the written paths."""
    target = pathlib.Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[pathlib.Path] = []
    for dp, name in CASE_IDS.items():
        path = target / name
        path.write_text(render_case(build_case(dp)), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def typed_status(cases: Mapping[str, Mapping[str, object]]) -> list[str]:
    """What the *current* registry says about each case (no pretending).

    The new dp1/dp2/dp3/dp25 contract is T01's deliverable, so this report is
    informational: ``ok`` means the shipped contract already matches the case,
    any other value lists the registry-typed issues the final integration
    (T01/T08) still has to resolve.
    """
    report: list[str] = []
    for dp, case in cases.items():
        book = case["book"]
        assert isinstance(book, Mapping)
        questions = case.get("questions")
        if not isinstance(questions, Mapping):
            report.append(f"{dp}: case shell has no questions mapping")
            continue
        question_issues = decision_points.question_override_issues(dp, questions, book.get("state"))
        if question_issues:
            codes = sorted({f"{path}: {issue}" for path, issue in question_issues})
            report.append(f"{dp}: case questions are not legal: " + "; ".join(codes))
            continue
        try:
            issues = decision_book.check_book(book, project_dir=ASSET_DIR)
        except Exception as exc:  # noqa: BLE001 - report, never crash the generator
            report.append(f"{dp}: check_book raised {type(exc).__name__}")
            continue
        if not issues:
            report.append(f"{dp}: ok (registry-typed validation passes)")
            continue
        codes = sorted({f"{issue.code}@{issue.path}" for issue in issues})
        report.append(f"{dp}: pending registry contract ({len(issues)} issue(s)): " + ", ".join(codes))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT_DIR),
        help="output directory (default: the shipped packages/multi-workers/decide_cases)",
    )
    parser.add_argument("--quiet", action="store_true", help="only print the written paths")
    args = parser.parse_args(argv)
    cases = build_cases()
    written = write_cases(args.out)
    for path in written:
        print(f"wrote {path.name} ({path.stat().st_size} bytes)")
    if not args.quiet:
        print("registry-typed validation (T01 contract, informational):")
        for line in typed_status(cases):
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

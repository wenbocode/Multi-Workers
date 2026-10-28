"""Read-only final audit of the T10 R2 stage-B worker's own delivery.

No import of any product; only bytes, hashes, path existence and text headings.
Prints one JSON object and exits 0 only when every check passes.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

EVIDENCE = Path(
    ".agenticdoc/mw-dp-consolidation/evidence/implementation/"
    "dpc-t10-lifecycle-state/rework-r2/product-repair"
)
WORKTREE = Path(
    ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers"
)
LIVE = Path("packages/multi-workers")

PRODUCTS = ("decision_wire.py", "decision_lifecycle.py", "decision_task_state.py")
TESTS = {
    "test_decision_context_lifecycle.py": "1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9",
    "test_decision_task_state.py": "30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f",
}
LIVE_SHA = {
    "decision_wire.py": "076fd3dee161a038fcc3597815863609d34b181da3f9f7646a8f0ee3dd911579",
    "decision_lifecycle.py": "e4ea5183cd28167a9ef35915c054d472c12b5b474817b93436564d2958d33248",
    "decision_task_state.py": "e82fc6b94f120d1d4ee561b6160d969b5ef36a86b6e3a0e8a3774c59a37e35e9",
    "test_decision_context_lifecycle.py": "106f17198a9de3552d2dc3e43aeb1c67474a6e4cb9c597811e792640d87a24f8",
    "test_decision_task_state.py": "c3de3c0456269aa3c8d1e0dfaf3f2098d9c9c657f6673ce93dc8cd5e7e54aff5",
}
HEADINGS = ("## 结论", "## 证据", "## 改动清单", "## 残留与未验证", "## 上下文来源")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    report: dict[str, object] = {"checks": {}, "observed": {}, "problems": []}
    problems: list[str] = []
    checks: dict[str, bool] = {}

    after = {}
    for name in PRODUCTS:
        after[name] = _sha(WORKTREE / name)
        checks[f"after_bytes_equal_worktree::{name}"] = (
            (EVIDENCE / "after-bytes" / name).read_bytes() == (WORKTREE / name).read_bytes()
        )
        if not checks[f"after_bytes_equal_worktree::{name}"]:
            problems.append(f"{name}: after-bytes copy differs from the worktree product")
    report["observed"]["after_sha256"] = after

    for name, expected in TESTS.items():
        digest = _sha(WORKTREE / name)
        checks[f"test_unchanged::{name}"] = digest == expected
        if digest != expected:
            problems.append(f"{name}: assigned test is not byte-identical to its protected digest")
    for name, expected in LIVE_SHA.items():
        digest = _sha(LIVE / name)
        checks[f"live_untouched::{name}"] = digest == expected
        if digest != expected:
            problems.append(f"{name}: live file differs from the PM-recorded live digest")

    pyc = sorted(
        path for path in Path(
            ".agenticdoc/mw-dp-consolidation/implementation-worktree"
        ).rglob("*.pyc")
    )
    checks["pyc_count_is_14"] = len(pyc) == 14
    report["observed"]["pyc_count"] = len(pyc)
    if len(pyc) != 14:
        problems.append(f"worktree pyc count is {len(pyc)}, expected 14")

    report_text = (EVIDENCE / "report.md").read_text(encoding="utf-8")
    output_text = (EVIDENCE / "output.md").read_text(encoding="utf-8")
    checks["report_equals_output"] = report_text == output_text
    if not checks["report_equals_output"]:
        problems.append("report.md and output.md differ")
    checks["report_has_five_sections_in_order"] = all(
        heading in report_text for heading in HEADINGS
    ) and [heading for heading in HEADINGS if heading in report_text] == list(HEADINGS)
    if not checks["report_has_five_sections_in_order"]:
        problems.append("report.md does not carry the five required sections")
    checks["report_has_change_table_header"] = "| 文件 |" in report_text
    if not checks["report_has_change_table_header"]:
        problems.append("report.md change table does not start with the 文件 header")
    checks["report_has_no_absolute_path"] = "H:\\" not in report_text and "/mnt/" not in report_text
    if not checks["report_has_no_absolute_path"]:
        problems.append("report.md contains an absolute path")

    report["checks"] = checks
    report["problems"] = problems
    report["ok"] = not problems
    sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())

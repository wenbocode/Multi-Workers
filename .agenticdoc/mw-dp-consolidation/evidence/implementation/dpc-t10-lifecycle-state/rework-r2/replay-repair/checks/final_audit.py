"""Read-only delivery audit for the R2 replay repair (no product import, no writes).

Checks, on bytes only:

* the two stored checker results have ``problems == []`` and their recorded
  product SHAs still equal the worktree bytes;
* the recorded stage C / PM-probe immutable SHAs still equal the files;
* each ``diff/*.diff`` is byte-identical to the diff regenerated from the
  baseline copy and the current product (no hand-edited diff);
* ``report.md`` and ``output.md`` are byte-identical, carry the five required
  sections in order, and the change table header starts with ``文件``;
* every file this role created under ``replay-repair/`` is listed in that table
  (its own stdout/rc/stderr artifacts excepted, they are produced by this run);
* this process imported no product, test module or pytest.

Usage:
  python -B <this file> <worktree-dir> <baseline-copy-dir> <replay-repair-dir>

Prints one JSON document on stdout; exit code 1 when ``problems`` is non-empty.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import pathlib
import sys

PRODUCTS = ("decision_wire.py", "decision_lifecycle.py", "decision_task_state.py")
PROTECTED_TESTS = {
    "test_decision_context_lifecycle.py": "1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9",
    "test_decision_task_state.py": "30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f",
}
SECTIONS = ("## 结论", "## 证据", "## 残留与未验证", "## 上下文来源", "## 改动清单")
FORBIDDEN_IMPORTS = {"decision_lifecycle", "decision_wire", "decision_task_state", "decision", "decision_points", "pytest"}
#: This audit's own artifacts are produced by the run that writes them.
SELF_ARTIFACTS = {
    "checks/final_audit.stdout.json",
    "checks/final_audit.stderr",
    "checks/final_audit.rc",
}
REPO_PREFIX = ".agenticdoc/mw-dp-consolidation/"
EVIDENCE_PREFIX = REPO_PREFIX + "evidence/implementation/dpc-t10-lifecycle-state/rework-r2/"
WORKTREE_PREFIX = REPO_PREFIX + "implementation-worktree/packages/multi-workers/"
BASELINE_LABEL = EVIDENCE_PREFIX + "product-repair/after-bytes"
WORKTREE_LABEL = WORKTREE_PREFIX.rstrip("/")


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regenerated_diff(baseline: pathlib.Path, worktree: pathlib.Path, name: str) -> str:
    old = (baseline / name).read_bytes()
    new = (worktree / name).read_bytes()
    if old == new:
        return f"identical: {name} {len(old)} bytes sha256 {hashlib.sha256(old).hexdigest()}\n"
    return "".join(
        difflib.unified_diff(
            old.decode("utf-8").splitlines(keepends=True),
            new.decode("utf-8").splitlines(keepends=True),
            fromfile=f"{BASELINE_LABEL}/{name} ({len(old)} bytes, sha256 {hashlib.sha256(old).hexdigest()})",
            tofile=f"{WORKTREE_LABEL}/{name} ({len(new)} bytes, sha256 {hashlib.sha256(new).hexdigest()})",
            n=3,
        )
    )


def table_paths(text: str) -> list[str]:
    """Rows of the ``## 改动清单`` table (the delivery inventory)."""
    changes_at = text.rfind("## 改动清单")
    body = text[changes_at:] if changes_at >= 0 else text
    rows: list[str] = []
    in_table = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("| 文件"):
            in_table = True
            continue
        if not in_table:
            continue
        if not stripped.startswith("|"):
            break
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        first = cells[0].strip("`") if cells else ""
        if not first or set(first) <= {"-", ":"} or first == "文件":
            continue
        rows.append(first)
    return rows


def main(argv: list[str]) -> int:
    worktree = pathlib.Path(argv[1])
    baseline = pathlib.Path(argv[2])
    evidence = pathlib.Path(argv[3])
    problems: list[str] = []
    report: dict[str, object] = {"checker": "final_audit.py"}

    static = json.loads((evidence / "checks/static_verify.stdout.json").read_text(encoding="utf-8"))
    base = json.loads((evidence / "checks/baseline_verify.stdout.json").read_text(encoding="utf-8"))
    if static.get("problems"):
        problems.append(f"static_verify recorded problems: {static['problems']}")
    if base.get("problems"):
        problems.append(f"baseline_verify recorded problems: {base['problems']}")

    # recorded SHAs must still describe the live bytes
    for name in PRODUCTS:
        recorded = static["products"][name]["after_sha256"]
        live = sha(worktree / name)
        if recorded != live:
            problems.append(f"{name}: recorded after {recorded} != live {live}")
    for name, expected in PROTECTED_TESTS.items():
        if sha(worktree / name) != expected:
            problems.append(f"{name}: no longer equals the protected digest")
    for label, recorded in base["immutable_evidence_sha256"].items():
        target = {
            "pm/postfix-first-report": "pm-postfix-tests/runs/t10-r2-postfix-first/report.json",
            "pm/postfix-second-report": "pm-postfix-tests/runs/t10-r2-postfix-second/report.json",
            "pm/probe-run-meta": "pm-postfix-tests/runs/t10-r2-replay-probe-first/pytest-replay.meta.json",
            "pm/probe-run-stdout": "pm-postfix-tests/runs/t10-r2-replay-probe-first/pytest-replay.stdout",
            "pm/probe-test": "pm-postfix-tests/test_replay_probe.py",
            "stageB/report": "product-repair/report.md",
            "stageC/run_pm_tests.py": "verification-preparation/run_pm_tests.py",
            "stageC/static_verify.result.json": "verification-preparation/checks/static_verify.result.json",
            "stageC/test_t10_r2_boundaries.py": "verification-preparation/test_t10_r2_boundaries.py",
        }[label]
        live = sha(evidence.parent / target)
        if live != recorded:
            problems.append(f"{label}: immutable artifact changed ({recorded} -> {live})")

    # the stored diffs must be exactly what the bytes produce
    for name in PRODUCTS:
        stored = (evidence / "diff" / f"{name}.diff").read_text(encoding="utf-8")
        if stored != regenerated_diff(baseline, worktree, name):
            problems.append(f"diff/{name}.diff is not the regenerated diff for the current bytes")
    report["diffs_verified"] = [f"diff/{name}.diff" for name in PRODUCTS]

    # report == output, five sections in order, table header and inventory
    report_text = (evidence / "report.md").read_text(encoding="utf-8")
    output_text = (evidence / "output.md").read_text(encoding="utf-8")
    if report_text != output_text:
        problems.append("report.md and output.md differ")
    positions = [report_text.find(section) for section in SECTIONS]
    if any(position < 0 for position in positions):
        missing = [section for section, position in zip(SECTIONS, positions) if position < 0]
        problems.append(f"report.md is missing section(s) {missing}")
    elif positions != sorted(positions):
        problems.append(f"report.md sections are out of order: {list(zip(SECTIONS, positions))}")
    if "| 文件 |" not in report_text:
        problems.append("report.md change table header does not start with 文件")
    if "| 文件 |" not in output_text:
        problems.append("output.md change table header does not start with 文件")
    listed = table_paths(report_text)
    table_ok = []
    for path in listed:
        if not path.startswith(REPO_PREFIX):
            problems.append(f"table row is not a canonical .agenticdoc path: {path}")
            continue
        if not path.startswith((EVIDENCE_PREFIX + "replay-repair/", WORKTREE_PREFIX)):
            problems.append(f"table row is outside this role's write face: {path}")
            continue
        target = pathlib.Path(".").joinpath(*path.split("/"))
        relative = path[len(EVIDENCE_PREFIX + "replay-repair/") :] if path.startswith(EVIDENCE_PREFIX + "replay-repair/") else ""
        if relative in SELF_ARTIFACTS:
            # this audit's own stdout/rc/stderr are written by this very run
            table_ok.append(path)
        elif target.exists():
            table_ok.append(path)
        else:
            problems.append(f"table row names a missing file: {path}")
    inventory: list[str] = []
    for path in sorted((evidence).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(evidence).as_posix()
        inventory.append(relative)
        if relative in SELF_ARTIFACTS:
            continue
        canonical = EVIDENCE_PREFIX + "replay-repair/" + relative
        if canonical not in listed:
            problems.append(f"created file is not listed in the change table: {relative}")
    report["table_rows"] = len(listed)
    report["inventory"] = inventory
    report["forbidden_modules_imported"] = sorted(FORBIDDEN_IMPORTS & set(sys.modules))
    if report["forbidden_modules_imported"]:
        problems.append(f"audit imported forbidden module(s) {report['forbidden_modules_imported']}")

    report["problems"] = problems
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

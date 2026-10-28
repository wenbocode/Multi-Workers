"""Read-only baseline/integrity record for the R2 replay repair (no product import).

Reads bytes only: the byte-exact product baseline copies left by the stage-B
repair (``rework-r2/product-repair/after-bytes/``), the two assigned suites, and
the immutable evidence of stages C and the PM probe. It writes nothing and
imports no product, no test module and no pytest.

Usage:
  python -B <this file> <worktree-dir> <baseline-copy-dir> <replay-repair-dir>

Prints one JSON document on stdout.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

#: The before SHAs the dispatch card declares (and the PM's fresh-before record
#: in ``t10-r2-green-replay-disposition-20261028/check.json`` repeats).
DECLARED_PRODUCTS = {
    "decision_wire.py": "429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc",
    "decision_lifecycle.py": "73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5",
    "decision_task_state.py": "b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d",
}

#: The two assigned suites, byte-protected by the card (unchanged by this role).
PROTECTED_TESTS = {
    "test_decision_context_lifecycle.py": "1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9",
    "test_decision_task_state.py": "30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f",
}

#: Read-only stage C / PM-probe artifacts whose bytes this role must not touch.
#: Paths are relative to the ``rework-r2`` evidence root.
IMMUTABLES = {
    "stageC/test_t10_r2_boundaries.py": "verification-preparation/test_t10_r2_boundaries.py",
    "stageC/run_pm_tests.py": "verification-preparation/run_pm_tests.py",
    "stageC/static_verify.result.json": "verification-preparation/checks/static_verify.result.json",
    "pm/probe-test": "pm-postfix-tests/test_replay_probe.py",
    "pm/probe-run-meta": "pm-postfix-tests/runs/t10-r2-replay-probe-first/pytest-replay.meta.json",
    "pm/probe-run-stdout": "pm-postfix-tests/runs/t10-r2-replay-probe-first/pytest-replay.stdout",
    "pm/postfix-first-report": "pm-postfix-tests/runs/t10-r2-postfix-first/report.json",
    "pm/postfix-second-report": "pm-postfix-tests/runs/t10-r2-postfix-second/report.json",
    "stageB/report": "product-repair/report.md",
}


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str]) -> int:
    worktree = pathlib.Path(argv[1])
    baseline = pathlib.Path(argv[2])
    evidence = pathlib.Path(argv[3])

    problems: list[str] = []
    products: dict[str, object] = {}
    for name, expected in DECLARED_PRODUCTS.items():
        copy = baseline / name
        if not copy.exists():
            problems.append(f"missing baseline copy {copy.as_posix()}")
            continue
        data = copy.read_bytes()
        got = hashlib.sha256(data).hexdigest()
        if got != expected:
            problems.append(f"{name}: baseline copy sha {got} != declared before {expected}")
        products[name] = {
            "baseline_copy": f"rework-r2/product-repair/after-bytes/{name}",
            "bytes": len(data),
            "lines": data.count(b"\n"),
            "sha256": got,
            "declared_before_sha256": expected,
            "equal_to_declared": got == expected,
            "worktree_equal_to_baseline_now": (worktree / name).exists()
            and digest(worktree / name) == got,
        }

    tests: dict[str, object] = {}
    for name, expected in PROTECTED_TESTS.items():
        path = worktree / name
        got = digest(path)
        if got != expected:
            problems.append(f"{name}: sha {got} != protected {expected}")
        tests[name] = {"bytes": path.stat().st_size, "sha256": got, "equal_to_protected": got == expected}

    immutable: dict[str, str] = {}
    for label, relative in IMMUTABLES.items():
        path = evidence / relative
        if not path.exists():
            problems.append(f"missing immutable artifact {path.as_posix()}")
            continue
        immutable[label] = digest(path)

    document = {
        "checker": "baseline_verify.py",
        "mode": "read-only bytes; no product import, no pytest, no writes",
        "declared_before_products": products,
        "protected_tests": tests,
        "immutable_evidence_sha256": immutable,
        "problems": problems,
    }
    print(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

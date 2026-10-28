"""Install the regenerated eight case files from this attempt's private output.

Only the eight declared case products (and the template check) are touched; the
bytes come from the real generator run recorded in ``logs/generate-private-out``
and each product file is verified byte-identical to that private output.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE.parent
KEY = EVIDENCE.parents[3]
PKG = KEY / "implementation-worktree" / "packages" / "multi-workers"
PRIVATE = EVIDENCE / "fixture" / "generator-out"

CASE_IDS = {
    "dp-w-type": "dp-w-type.json",
    "dp-pm-steer": "dp-pm-steer.json",
    "dp-w-check-task": "dp-w-check-task.json",
    "dp-QG": "dp-QG.json",
    "dp-gate-approve": "dp-gate-approve.json",
    "dp-sign-key": "dp-sign-key.json",
    "dp-auto": "dp-auto.json",
    "dp-route": "dp-route.json",
}
LEGACY = {
    "dp1.json": "3131c02f4830b96994e3bea94efe1be8511fd7936f8c983cf579596218a6c9ff",
    "dp2.json": "a03e1a29540ba9636a0a37bf478598bb530c357fc65d54b5eaaf6326e16342ea",
    "dp3.json": "82ff47e50ab5f24cfd84c793c07e2d15484ea89c24a90c8595306c468f407f2d",
    "dp25.json": "bda25144a8c5cd73978603a3dc4c9b429d8d451485679d99ef46cfcc4c2cc7fd",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    rows = []
    for dp, name in CASE_IDS.items():
        generated = (PRIVATE / name).read_bytes()
        target = PKG / "decide_cases" / name
        previous = target.read_bytes()
        target.write_bytes(generated)
        installed = target.read_bytes()
        rows.append(
            {
                "file": f".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/{name}",
                "bytes": len(installed),
                "sha256": sha(installed),
                "byte_identical_to_private_out": installed == generated,
                "changed": installed != previous,
                "previous_sha256": sha(previous),
            }
        )
    legacy = {
        name: {"sha256": sha((PKG / "decide_cases" / name).read_bytes()), "expected": expected}
        for name, expected in LEGACY.items()
    }
    payload = {
        "source": "agent-report",
        "private_out": PRIVATE.as_posix(),
        "cases": rows,
        "legacy_cases_unchanged": all(item["sha256"] == item["expected"] for item in legacy.values()),
        "legacy_cases": legacy,
    }
    (EVIDENCE / "case-install.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "all_installed_byte_identical": all(r["byte_identical_to_private_out"] for r in rows),
                "changed": [r["file"].rsplit("/", 1)[1] for r in rows if r["changed"]],
                "legacy_cases_unchanged": payload["legacy_cases_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    ok = payload["legacy_cases_unchanged"] and all(r["byte_identical_to_private_out"] for r in rows)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Capture the T05 before-image (bytes/SHA256/EOL/existing diff/absence).

Read-only over the isolated implementation copy; writes only into this card's
evidence directory (``evidence/implementation/dpc-t05-eight-cases``).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

KEY_ROOT = pathlib.Path(__file__).resolve().parents[3]  # .agenticdoc/mw-dp-consolidation
CARD = "dpc-t05-eight-cases"
WORKTREE = KEY_ROOT / "implementation-worktree"
EVIDENCE = pathlib.Path(__file__).resolve().parent
PKG_REL = "packages/multi-workers"

PRODUCT_FILES = [
    f"{PKG_REL}/scripts/build_decide_cases.py",
    f"{PKG_REL}/decide_book_template.json",
    f"{PKG_REL}/test_decision_context_workbench.py",
    f"{PKG_REL}/decide_cases/dp-w-type.json",
    f"{PKG_REL}/decide_cases/dp-pm-steer.json",
    f"{PKG_REL}/decide_cases/dp-w-check-task.json",
    f"{PKG_REL}/decide_cases/dp-QG.json",
    f"{PKG_REL}/decide_cases/dp-gate-approve.json",
    f"{PKG_REL}/decide_cases/dp-sign-key.json",
    f"{PKG_REL}/decide_cases/dp-auto.json",
    f"{PKG_REL}/decide_cases/dp-route.json",
]

#: The four pre-consolidation cases: byte-locked, never generated or edited here.
LEGACY_FILES = [
    f"{PKG_REL}/decide_cases/dp1.json",
    f"{PKG_REL}/decide_cases/dp2.json",
    f"{PKG_REL}/decide_cases/dp3.json",
    f"{PKG_REL}/decide_cases/dp25.json",
]


def eol_counts(data: bytes) -> tuple[int, int]:
    return data.count(b"\n") - data.count(b"\r\n"), data.count(b"\r\n")


def describe(rel: str) -> dict:
    path = WORKTREE / rel
    if not path.is_file():
        return {"path": rel, "exists": False, "sha256": None, "bytes": None, "lf": None, "crlf": None}
    data = path.read_bytes()
    lf, crlf = eol_counts(data)
    return {
        "path": rel,
        "exists": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "lf": lf,
        "crlf": crlf,
    }


def git_diff(rel: str) -> str:
    proc = subprocess.run(
        ["git", "diff", "--", rel],
        cwd=str(WORKTREE),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.stdout


def main() -> int:
    before = EVIDENCE / "before-bytes"
    diffs = EVIDENCE / "existing-diffs"
    (before / PKG_REL).mkdir(parents=True, exist_ok=True)
    (before / PKG_REL / "decide_cases").mkdir(parents=True, exist_ok=True)
    diffs.mkdir(parents=True, exist_ok=True)

    rows = []
    for rel in PRODUCT_FILES + LEGACY_FILES:
        info = describe(rel)
        rows.append(info)
        if info["exists"]:
            target = before / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((WORKTREE / rel).read_bytes())
            (diffs / rel).parent.mkdir(parents=True, exist_ok=True)
            (diffs / (rel + ".diff")).write_text(git_diff(rel), encoding="utf-8")
    (EVIDENCE / "before-metadata.json").write_text(
        json.dumps(
            {
                "captured_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(),
                "worktree": str(WORKTREE),
                "product_files": rows[: len(PRODUCT_FILES)],
                "legacy_files": rows[len(PRODUCT_FILES) :],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps([{k: row[k] for k in ("path", "exists", "sha256", "bytes")} for row in rows], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

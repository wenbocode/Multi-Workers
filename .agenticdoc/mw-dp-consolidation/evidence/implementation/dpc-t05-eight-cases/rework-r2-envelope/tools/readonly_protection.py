"""Record the read-only faces this attempt must not touch, and check the entry face.

Covers: the dispatched task.md write_face (12 entries = 11 products + this
evidence dir), the card SHA the dispatch envelope claims, the PM handoff
negative fixtures/probe, the pre-dispatch baseline, pm-state, both DAGs, the
original T05/T10 worker evidence, and the original bad-R2 evidence. Read-only:
it only writes ``readonly-protection.json``.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE.parent
KEY = EVIDENCE.parents[3]
ROOT = KEY.parents[1]
EVID = KEY / "evidence" / "implementation"

TASK = KEY / "workers" / "dpc-t05-eight-cases-r2-envelope" / "task.md"
CARD = KEY / "tasks" / "isolated" / "T05-eight-cases-r2-envelope.md"

PROTECTED = {
    "pm_handoff": [
        EVID / "t05-pm-handoff-20261027" / name
        for name in ("probe.py", "probe.json", "check.py", "check.json", "report.md")
    ],
    "pm_pre_dispatch": [
        EVID / "t05-r2-envelope-pre-dispatch-20261027" / name
        for name in ("check.json", "carrier.json", "before-metadata.json", "T05-R2-envelope-card.md")
    ],
    "pm_state_and_dag": [
        KEY / "pm-state.md",
        KEY / "implementation-dag.json",
        KEY / "implementation-isolated-dag.json",
        KEY / "spec.md",
        KEY / "design.md",
    ],
    "original_worker_evidence": [
        EVID / "dpc-t05-eight-cases" / name
        for name in ("report.md", "before-metadata.json", "comparison-baseline-vs-final.json")
    ]
    + [
        KEY / "workers" / "dpc-t05-eight-cases" / name for name in ("output.md", "run.json")
    ],
    "original_r2_envelope_blocker": [
        EVID / "dpc-t05-eight-cases" / "rework-r2" / name
        for name in ("report.md", "output.md", "blocker/face-mismatch.json", "blocker/guard-refusal.json")
    ]
    + [
        KEY / "workers" / "dpc-t05-eight-cases-r2" / name for name in ("task.md", "output.md", "run.json", "worker.log")
    ],
    "t10_evidence": [
        EVID / "dpc-t10-lifecycle-state" / name
        for name in ("report.md", "report.json", "mirror-before.json")
        if (EVID / "dpc-t10-lifecycle-state" / name).is_file()
    ]
    + [KEY / "workers" / "dpc-t10-lifecycle-state" / name for name in ("output.md", "run.json")],
}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_face_entries(text: str) -> list[str]:
    match = re.search(r"^write_face:\s*(.+)$", text, re.MULTILINE)
    assert match, "task.md has no write_face header"
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def main() -> int:
    task_text = TASK.read_text(encoding="utf-8")
    entries = write_face_entries(task_text)
    header = re.search(r"^card_sha256:\s*(\S+)$", task_text, re.MULTILINE)
    rows = {
        group: [
            {
                "file": path.as_posix(),
                "exists": path.is_file(),
                "sha256": sha(path) if path.is_file() else None,
            }
            for path in paths
        ]
        for group, paths in PROTECTED.items()
    }
    payload = {
        "source": "agent-report",
        "entry_face": {
            "task_md": TASK.as_posix(),
            "write_face_entries": len(entries),
            "entries": entries,
            "eleven_products_plus_own_evidence": len(entries) == 12
            and entries[:11]
            == [
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/scripts/build_decide_cases.py",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_book_template.json",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decision_context_workbench.py",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-type.json",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-pm-steer.json",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-w-check-task.json",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-QG.json",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-gate-approve.json",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-sign-key.json",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-auto.json",
                ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_cases/dp-route.json",
            ]
            and entries[11]
            == ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2-envelope/**",
            "evidence_glob_is_own_attempt_dir": entries[11]
            == ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2-envelope/**",
        },
        "card": {
            "file": CARD.as_posix(),
            "sha256": sha(CARD),
            "sha256_claimed_by_task_header": header.group(1) if header else None,
            "matches": bool(header) and sha(CARD) == header.group(1),
        },
        "protected": rows,
        "root": ROOT.as_posix(),
    }
    (EVIDENCE / "readonly-protection.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "write_face_entries": len(entries),
                "eleven_products_plus_own_evidence": payload["entry_face"]["eleven_products_plus_own_evidence"],
                "card_sha256_matches": payload["card"]["matches"],
                "protected_files_recorded": sum(len(v) for v in rows.values()),
                "missing": [row["file"] for group in rows.values() for row in group if not row["exists"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    ok = payload["entry_face"]["eleven_products_plus_own_evidence"] and payload["card"]["matches"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

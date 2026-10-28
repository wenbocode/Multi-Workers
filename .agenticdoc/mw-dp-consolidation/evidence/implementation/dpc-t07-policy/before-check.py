"""T07 before-snapshot: card bytes/SHA256/EOL + target-file absence + peer faces.

Read-only. Writes only inside this card's evidence directory.
Run: python -B before-check.py
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import time

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[4]
WORKTREE = REPO / ".agenticdoc/mw-dp-consolidation/implementation-worktree"
PKG = WORKTREE / "packages/multi-workers"

CARD = REPO / ".agenticdoc/mw-dp-consolidation/tasks/isolated/T07-policy.md"
TASK = REPO / ".agenticdoc/mw-dp-consolidation/workers/dpc-t07-policy/task.md"
TARGETS = [PKG / "decision_policy.py", PKG / "test_dp_consolidation_recovery.py"]
PEERS = [
    PKG / "decision_validity.py",
    PKG / "test_dp_consolidation_concurrency.py",
    PKG / "decision.py",
    PKG / "decision_backends.py",
    PKG / "test_dp_consolidation_materials.py",
]


def _file_state(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"path": str(path.relative_to(REPO)).replace("\\", "/"), "exists": False}
    data = path.read_bytes()
    text = data.decode("utf-8", errors="strict")
    return {
        "path": str(path.relative_to(REPO)).replace("\\", "/"),
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "eol": "crlf" if "\r\n" in text else "lf",
        "trailing_newline": text.endswith("\n"),
        "lines": text.count("\n") + (0 if text.endswith("\n") else 1),
    }


def main() -> int:
    snapshot = {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "card": _file_state(CARD),
        "task_envelope": _file_state(TASK),
        "filtered_task_envelope": {
            "note": "task.md carries the dispatch envelope; the full card was read to EOF from tasks/isolated/T07-policy.md",
        },
        "targets": [_file_state(p) for p in TARGETS],
        "peer_faces": [_file_state(p) for p in PEERS],
        "single_writer": {
            "claim": "no other writer on the two T07 target files; both absent before this worker",
            "concurrent_peer_tasks": ["T06 decision_validity.py", "T08 decision.py/decision_backends.py"],
        },
        "frozen_config_units_read_only": ["round_budget", "worker_timeout_min"],
    }
    out = EVIDENCE / "before-check.json"
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

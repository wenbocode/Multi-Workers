"""T06 write-scope / before-after check (read-only).

Compares the current isolated-worktree inventory with the before inventory
saved by ``capture_baseline.py`` and classifies every difference:

* ``own``      - one of this card's two product files;
* ``other_task`` - a path declared in another task's write face (T07/T08 run
  concurrently); reported separately and never claimed by this card;
* ``unexpected`` - anything else, which would be a write-face violation.

Also records the final bytes/SHA256/EOL of the two own files and the evidence
files' presence, so the report can quote exact values.

Usage: python write_scope_check.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib

EVIDENCE = pathlib.Path(__file__).resolve().parent
KEY_ROOT = EVIDENCE.parents[2]
WORKTREE = KEY_ROOT / "implementation-worktree"
DAG = KEY_ROOT / "implementation-isolated-dag.json"
BEFORE = EVIDENCE / "baseline" / "before.json"
OWN = {
    "packages/multi-workers/decision_validity.py",
    "packages/multi-workers/test_dp_consolidation_concurrency.py",
}


def describe(rel: str) -> dict:
    path = WORKTREE / rel
    if not path.is_file():
        return {"path": rel, "exists": False}
    data = path.read_bytes()
    text = data.decode("utf-8")
    return {
        "path": rel,
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "crlf": data.count(b"\r\n"),
        "bare_lf": data.count(b"\n") - data.count(b"\r\n"),
        "final_newline": data.endswith(b"\n"),
        "lines": text.count("\n"),
        "first_sha256_16": hashlib.sha256(
            text.splitlines()[0].encode("utf-8")
        ).hexdigest()[:16],
    }


def inventory() -> dict[str, str]:
    entries: dict[str, str] = {}
    for path in sorted(WORKTREE.rglob("*")):
        if path.is_file():
            entries[path.relative_to(WORKTREE).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return entries


def main() -> int:
    before = json.loads(BEFORE.read_text(encoding="utf-8"))
    before_inventory = before["worktree_inventory"]
    after_inventory = inventory()
    before_paths = set(before_inventory)
    after_paths = set(after_inventory)
    added = sorted(after_paths - before_paths)
    removed = sorted(before_paths - after_paths)
    modified = sorted(
        path
        for path in before_paths & after_paths
        if before_inventory[path] != after_inventory[path]
    )

    dag = json.loads(DAG.read_text(encoding="utf-8"))
    other_faces: dict[str, set[str]] = {}
    for task in dag["tasks"]:
        if task["id"] in {"T06"}:
            continue
        for path in task.get("source_product_write_face") or []:
            other_faces.setdefault(path, set()).add(task["id"])

    def classify(rel: str) -> dict:
        if rel in OWN:
            return {"class": "own", "tasks": ["T06"]}
        if "__pycache__/" in rel or rel.endswith(".pyc"):
            return {"class": "concurrent_bytecode", "tasks": []}
        if rel in other_faces:
            return {"class": "other_task", "tasks": sorted(other_faces[rel])}
        return {"class": "unexpected", "tasks": []}

    changes = {
        "added": [{"path": rel, **classify(rel)} for rel in added],
        "modified": [{"path": rel, **classify(rel)} for rel in modified],
        "removed": [{"path": rel, **classify(rel)} for rel in removed],
    }
    payload = {
        "before_file_count": len(before_inventory),
        "after_file_count": len(after_inventory),
        "own_files": [describe(rel) for rel in sorted(OWN)],
        "changes": changes,
        "unexpected": [
            change for group in changes.values() for change in group
            if change["class"] == "unexpected"
        ],
        "own_changes": [
            change for group in changes.values() for change in group
            if change["class"] == "own"
        ],
        "other_task_changes": [
            change for group in changes.values() for change in group
            if change["class"] == "other_task"
        ],
        "concurrent_bytecode": [
            change for group in changes.values() for change in group
            if change["class"] == "concurrent_bytecode"
        ],
    }
    (EVIDENCE / "write-scope.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not payload["unexpected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

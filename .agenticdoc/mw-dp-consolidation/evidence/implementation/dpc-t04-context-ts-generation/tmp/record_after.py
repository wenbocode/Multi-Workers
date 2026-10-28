"""Record T04 after-bytes/SHA/EOL, the full diff, and the mirror write inventory.

* copies the five allowed files into evidence/after/ (exact bytes);
* writes after-manifest.json with bytes/sha256/EOL counts + before/after change;
* writes changed-files.diff (unified diff of every changed allowed file);
* recomputes the whole worktree file inventory and compares it with the
  pre-dispatch inventory, so "only the write face changed" is evidence, not a
  claim (added/removed files are listed separately).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"H:\git\Multi-Workers")
WT = REPO / ".agenticdoc/mw-dp-consolidation/implementation-worktree"
EVID = REPO / ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t04-context-ts-generation"
BASE = EVID / "baseline"
AFTER = EVID / "after"
PREDISPATCH_INVENTORY = (
    REPO
    / ".agenticdoc/mw-dp-consolidation/evidence/implementation/t04-pre-dispatch-20261026/mirror-inventory.json"
)

FILES = [
    "packages/multi-workers/decision_context.py",
    "packages/multi-workers/scripts/gen_decide_registry_ts.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/test_decide_registry_ts_lock.py",
    "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts",
]

SKIP_DIRS = {"__pycache__", "node_modules", ".pytest_cache", ".git", ".mw"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory(root: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        rows[rel.as_posix()] = sha(path.read_bytes())
    return rows


rows = []
diffs: list[str] = []
for rel in FILES:
    before = (BASE / rel).read_bytes()
    after = (WT / rel).read_bytes()
    dst = AFTER / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(after)
    rows.append(
        {
            "path": rel,
            "before_sha256": sha(before),
            "after_sha256": sha(after),
            "before_bytes": len(before),
            "after_bytes": len(after),
            "before_crlf": before.count(b"\r\n"),
            "after_crlf": after.count(b"\r\n"),
            "before_lf": before.count(b"\n") - before.count(b"\r\n"),
            "after_lf": after.count(b"\n") - after.count(b"\r\n"),
            "changed": before != after,
            "readback_equal": dst.read_bytes() == after,
        }
    )
    if before != after:
        before_text = before.decode("utf-8").splitlines(keepends=True)
        after_text = after.decode("utf-8").splitlines(keepends=True)
        diffs.append(
            "".join(
                difflib.unified_diff(
                    before_text,
                    after_text,
                    fromfile=f"before/{rel}",
                    tofile=f"after/{rel}",
                )
            )
        )

(AFTER / "changed-files.diff").write_text("\n".join(diffs), encoding="utf-8", newline="\n")

current = inventory(WT)
predispatch = json.loads(PREDISPATCH_INVENTORY.read_text(encoding="utf-8"))
added = sorted(set(current) - set(predispatch))
removed = sorted(set(predispatch) - set(current))
changed = sorted(
    rel for rel in set(current) & set(predispatch) if current[rel] != predispatch[rel]
)

manifest = {
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "files": rows,
    "changed_paths": [row["path"] for row in rows if row["changed"]],
    "mirror": {
        "predispatch_files": len(predispatch),
        "current_files": len(current),
        "added": added,
        "removed": removed,
        "changed": changed,
        "changed_outside_write_face": [
            rel for rel in changed if rel not in FILES
        ],
    },
    "live_samefile": {
        rel: os.path.samefile(WT / rel, REPO / rel) for rel in FILES
    },
}
(AFTER / "after-manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps(manifest, indent=2, ensure_ascii=False))

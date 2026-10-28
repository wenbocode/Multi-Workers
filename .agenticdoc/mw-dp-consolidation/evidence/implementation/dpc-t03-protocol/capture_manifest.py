"""T03 evidence helper: byte/EOL manifest for the four approved copy files.

Read-only w.r.t. product files: it copies the *current* bytes into this card's
evidence dir and records sha256/bytes/CRLF/bare-LF/line count. Usage:
    python capture_manifest.py before|after <label>
Writes ``<label>-manifest.json`` plus ``<label>/`` byte copies next to it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
WORKTREE = EVIDENCE.parents[2] / "implementation-worktree"
FILES = (
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/test_decide_registry_contract.py",
    "packages/multi-workers/test_dp_consolidation_registry.py",
)


def measure(path: pathlib.Path) -> dict:
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    return {
        "path": str(path.relative_to(WORKTREE)).replace("\\", "/"),
        "exists": path.is_file(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "crlf": crlf,
        "bare_lf": lf - crlf,
        "lines": len(raw.splitlines()),
    }


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("before", "after"):
        print(__doc__)
        return 2
    stage, label = sys.argv[1], sys.argv[2]
    out_dir = EVIDENCE / f"{label}-bytes"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"stage": stage, "label": label, "root": "implementation-worktree", "files": []}
    for relative in FILES:
        source = WORKTREE / relative
        row = measure(source) if source.is_file() else {
            "path": relative,
            "exists": False,
        }
        manifest["files"].append(row)
        if source.is_file():
            target = out_dir / pathlib.PurePosixPath(relative).name
            shutil.copyfile(source, target)
    (EVIDENCE / f"{label}-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

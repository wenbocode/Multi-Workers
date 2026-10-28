"""Record T04 before-bytes/SHA/EOL for the five allowed product files.

Reads each file fully (bytes), writes an exact copy plus a manifest into
``evidence/implementation/dpc-t04-context-ts-generation/baseline``.
Also records whether the worktree copy is a hardlink/samefile of the live tree.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"H:\git\Multi-Workers")
WT = REPO / ".agenticdoc/mw-dp-consolidation/implementation-worktree"
EVID = REPO / ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t04-context-ts-generation"
BASE = EVID / "baseline"

FILES = [
    "packages/multi-workers/decision_context.py",
    "packages/multi-workers/scripts/gen_decide_registry_ts.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/test_decide_registry_ts_lock.py",
    "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts",
]

PREDISPATCH = {
    "packages/multi-workers/decision_context.py": "5eeb860518593b194aa1f48a9262f06b9113d96cbd62c03625b4b6a2dab58b06",
    "packages/multi-workers/scripts/gen_decide_registry_ts.py": "a0ed7a80edf816c6fafb4dab6e3437690c4d45aed3a11809bf947f658317077d",
    "packages/multi-workers/decide_registry.json": "cc017e343f2f7702cf2fcdafc1239d543be472b4e6ab6b92d6adaaee7a06c604",
    "packages/multi-workers/test_decide_registry_ts_lock.py": "dc6332f140f06ce9d0ca494245c1500f2f2ee14ce584c3dcf4ad821872b2a92e",
    "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts": "699719c2bf7e64cbb51866f8fda39784c6d0ee9b09d7762c9c49e5fbb30127e4",
}

rows = []
for rel in FILES:
    src = WT / rel
    data = src.read_bytes()
    dst = BASE / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    samefile = False
    try:
        samefile = os.path.samefile(src, REPO / rel)
    except OSError:
        samefile = False
    crlf = data.count(b"\r\n")
    rows.append(
        {
            "path": rel,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "crlf": crlf,
            "bare_lf": data.count(b"\n") - crlf,
            "samefile_live": samefile,
            "exists_before": True,
            "predispatch_sha256": PREDISPATCH[rel],
            "matches_predispatch": hashlib.sha256(data).hexdigest() == PREDISPATCH[rel],
            "baseline_copy": str(dst.relative_to(REPO)).replace("\\", "/"),
            "readback_equal": dst.read_bytes() == data,
        }
    )

manifest = {
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "implementation_root": str(WT),
    "files": rows,
    "all_match_predispatch": all(row["matches_predispatch"] for row in rows),
}
(BASE / "before-manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
)
for row in rows:
    print(row["path"], row["sha256"], row["bytes"], f"crlf={row['crlf']}", f"lf={row['bare_lf']}", f"match={row['matches_predispatch']}")
print("all_match_predispatch", manifest["all_match_predispatch"])

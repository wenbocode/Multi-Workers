"""Capture the T08 before-bytes (bytes/SHA256/EOL) of the assigned copy files.

Read-only over the implementation copy; the copies themselves are written into
this card's evidence directory (before-bytes/).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib

ROOT = pathlib.Path(".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers")
EVIDENCE = pathlib.Path(".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t08-transport")


def stats(path: pathlib.Path) -> dict:
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    return {
        "path": str(path).replace("\\", "/"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "crlf": crlf,
        "bare_lf": lf - crlf,
        "ends_with_newline": raw.endswith(b"\n"),
        "lines": raw.count(b"\n"),
    }


def main() -> None:
    out_dir = EVIDENCE / "before-bytes" / "packages" / "multi-workers"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for name in ("decision.py", "decision_backends.py", "test_dp_consolidation_materials.py"):
        path = ROOT / name
        if not path.exists():
            files.append({"path": str(path).replace("\\", "/"), "exists": False})
            continue
        record = {"exists": True, **stats(path)}
        files.append(record)
        target = out_dir / name
        target.write_bytes(path.read_bytes())
        assert target.read_bytes() == path.read_bytes(), name
    doc = {
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "copy_root": str(ROOT.resolve()).replace("\\", "/"),
        "files": files,
    }
    target = EVIDENCE / "before-bytes.json"
    target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(doc, indent=2))


if __name__ == "__main__":
    main()

"""R2 evidence: record before bytes/SHA256/EOL and the protected pyc inventory.

Reads the two product faces of the isolated copy and the existing __pycache__
(14 pyc) once, writes only inside this R2 evidence directory.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
KEY = HERE.parents[3]
ROOT = KEY.parents[1]
PKG = KEY / "implementation-worktree" / "packages" / "multi-workers"
FILES = ("decision_book.py", "test_decision_context_contract.py")

snapshot = HERE / "before-bytes"
snapshot.mkdir(parents=True, exist_ok=True)

rows: dict[str, dict[str, object]] = {}
for name in FILES:
    path = PKG / name
    data = path.read_bytes()
    copy = snapshot / f"{name}.before"
    copy.write_bytes(data)
    text = data.decode("utf-8")
    rows[name] = {
        "product_path": path.relative_to(ROOT).as_posix(),
        "snapshot_path": copy.relative_to(ROOT).as_posix(),
        "snapshot_sha256": hashlib.sha256(copy.read_bytes()).hexdigest(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "total_newlines": text.count("\n"),
        "lf": text.count("\n") - text.count("\r\n"),
        "crlf": text.count("\r\n"),
        "utf8_bom": data.startswith(b"\xef\xbb\xbf"),
        "ends_with_newline": text.endswith("\n"),
    }

pyc = [
    {
        "path": entry.relative_to(ROOT).as_posix(),
        "bytes": entry.stat().st_size,
        "sha256": hashlib.sha256(entry.read_bytes()).hexdigest(),
    }
    for entry in sorted(PKG.rglob("*.pyc"))
]

payload = {
    "source": "agent-report",
    "observed_at": "2026-10-27T09:22:13Z",
    "products": rows,
    "pyc_count": len(pyc),
    "pyc": pyc,
}
(HERE / "before-bytes.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps(payload, ensure_ascii=False, indent=2))

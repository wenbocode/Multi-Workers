"""R2 evidence: after bytes/SHA/EOL, incremental diffs and the pyc inventory.

Writes after-bytes.json and diffs/<product>.diff (unified diff of the frozen
pre-fix snapshot against the current product file). Never rewrites a product.
"""
from __future__ import annotations

import difflib
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

diffs_dir = HERE / "diffs"
diffs_dir.mkdir(parents=True, exist_ok=True)

rows: dict[str, dict[str, object]] = {}
for name in FILES:
    path = PKG / name
    before_path = HERE / "before-bytes" / f"{name}.before"
    before_bytes = before_path.read_bytes()
    after_bytes = path.read_bytes()
    after_text = after_bytes.decode("utf-8")
    before_text = before_bytes.decode("utf-8")
    before_lines = before_text.splitlines(keepends=True)
    after_lines = after_text.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/packages/multi-workers/{name}",
            tofile=f"b/packages/multi-workers/{name}",
            n=3,
        )
    )
    diff_text = "".join(diff_lines)
    (diffs_dir / f"{name}.diff").write_text(diff_text, encoding="utf-8", newline="\n")
    hunks = sum(1 for line in diff_lines if line.startswith("@@"))
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    rows[name] = {
        "product_path": path.relative_to(ROOT).as_posix(),
        "before_sha256": hashlib.sha256(before_bytes).hexdigest(),
        "after_sha256": hashlib.sha256(after_bytes).hexdigest(),
        "before_bytes": len(before_bytes),
        "after_bytes": len(after_bytes),
        "after_lines": after_text.count("\n"),
        "lf": after_text.count("\n") - after_text.count("\r\n"),
        "crlf": after_text.count("\r\n"),
        "utf8_bom": after_bytes.startswith(b"\xef\xbb\xbf"),
        "ends_with_newline": after_text.endswith("\n"),
        "diff_path": (diffs_dir / f"{name}.diff").relative_to(ROOT).as_posix(),
        "diff_bytes": len(diff_text.encode("utf-8")),
        "diff_hunks": hunks,
        "diff_added_lines": added,
        "diff_removed_lines": removed,
    }

pyc = [
    {
        "path": entry.relative_to(ROOT).as_posix(),
        "bytes": entry.stat().st_size,
        "sha256": hashlib.sha256(entry.read_bytes()).hexdigest(),
    }
    for entry in sorted(PKG.rglob("*.pyc"))
]
before_payload = json.loads((HERE / "before-bytes.json").read_text(encoding="utf-8"))
payload = {
    "source": "agent-report",
    "observed_at": "2026-10-27T09:41:52Z",
    "products": rows,
    "pyc_count": len(pyc),
    "pyc_unchanged": pyc == before_payload["pyc"],
    "pyc": pyc,
}
(HERE / "after-bytes.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps({key: payload[key] for key in ("products", "pyc_count", "pyc_unchanged")}, ensure_ascii=False, indent=2))

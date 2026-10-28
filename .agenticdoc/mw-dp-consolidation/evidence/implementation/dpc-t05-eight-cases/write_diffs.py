"""Write the T05 before/after diff and the changed-files table into evidence."""

from __future__ import annotations

import difflib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
KEY_ROOT = HERE.parents[2]
WORKTREE = KEY_ROOT / "implementation-worktree"
BEFORE = HERE / "before-bytes"
DIFFS = HERE / "diffs"


def main() -> int:
    meta = json.loads((HERE / "after-metadata.json").read_text(encoding="utf-8"))
    DIFFS.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in meta["changed_files"]:
        rel = row["file"]
        before_path = BEFORE / rel
        after_path = WORKTREE / rel
        before_text = (
            before_path.read_text(encoding="utf-8", errors="replace")
            if before_path.is_file()
            else ""
        )
        after_text = after_path.read_text(encoding="utf-8", errors="replace")
        diff = "".join(
            difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile=f"before/{rel}" if row["before_exists"] else "/dev/null",
                tofile=f"after/{rel}",
                n=3,
            )
        )
        name = rel.replace("/", "__")
        (DIFFS / (name + ".diff")).write_text(diff, encoding="utf-8")
        added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
        rows.append(
            {
                "文件": rel,
                "before_sha256": row["before_sha256"],
                "after_sha256": row["after_sha256"],
                "before_bytes": row["before_bytes"],
                "after_bytes": row["after_bytes"],
                "added_lines": added,
                "removed_lines": removed,
                "changed": row["changed"],
                "diff": f"diffs/{name}.diff",
            }
        )
    lines = [
        "| 文件 | before_sha256 | after_sha256 | before_bytes | after_bytes | +行 | -行 | 变化 | diff |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {文件} | {before_sha256} | {after_sha256} | {before_bytes} | {after_bytes} | "
            "{added_lines} | {removed_lines} | {changed} | {diff} |".format(**row)
        )
    (HERE / "changed-files.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (HERE / "changed-files.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("\n".join(f"{row['文件']}: +{row['added_lines']} -{row['removed_lines']}" for row in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

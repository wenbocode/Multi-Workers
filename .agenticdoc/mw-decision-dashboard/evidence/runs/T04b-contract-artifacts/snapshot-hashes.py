"""T04b: hash the formatter-visible working-tree files before/after `npm run check`.

`npm run check` starts with `biome check --write .`, which can rewrite files that
belong to other sessions. This snapshot proves exactly what that command changed
(and whether it touched anything outside this card's write face).

Usage (repo root):
    python .../snapshot-hashes.py <out-file>
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

SUFFIXES = {".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".jsonc"}
SKIP_DIRS = {".git", "node_modules", "dist", ".artifacts", "__pycache__", ".tmp", ".mw"}
ROOT = pathlib.Path(__file__).resolve().parents[5]


def git_paths(args: list[str]) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    out = pathlib.Path(argv[0])
    paths = sorted(set(git_paths(["ls-files", "-m", "-o", "--exclude-standard"])))
    rows: list[str] = []
    for raw in paths:
        path = ROOT / raw
        if path.suffix.lower() not in SUFFIXES or not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        rows.append(f"{digest}  {raw}")
    out.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    print(f"hashed {len(rows)} paths -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

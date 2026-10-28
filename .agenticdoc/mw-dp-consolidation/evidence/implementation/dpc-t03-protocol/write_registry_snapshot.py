"""T03 single-source snapshot writer: regenerate decide_registry.json offline.

Uses only the existing pure API (``decision_points.registry_snapshot_text``) from
the isolated copy; no ``mw`` CLI, no generator from T04/T05, no other output.
Writes exactly one file: the card's copy of ``decide_registry.json`` (UTF-8, LF,
one trailing newline, the serializer's canonical formatting), then re-reads it and
verifies bytes == the writer output.

Usage: python write_registry_snapshot.py [--check]
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
PACKAGE = EVIDENCE.parents[2] / "implementation-worktree" / "packages" / "multi-workers"
TARGET = PACKAGE / "decide_registry.json"
CHECK_ONLY = "--check" in sys.argv

sys.path.insert(0, str(PACKAGE))

import decision_points as dpts  # noqa: E402


def main() -> int:
    text = dpts.registry_snapshot_text()
    payload = text.encode("utf-8")
    before = TARGET.read_bytes() if TARGET.is_file() else None
    if CHECK_ONLY:
        print(f"expected sha={hashlib.sha256(payload).hexdigest()} bytes={len(payload)}")
        print(f"current  sha={hashlib.sha256(before).hexdigest() if before else None}")
        return 0
    TARGET.write_bytes(payload)
    written = TARGET.read_bytes()
    if written != payload:
        raise SystemExit("read-back mismatch: the snapshot writer output is not the file")
    print(f"wrote {TARGET}")
    print(f"sha_before={hashlib.sha256(before).hexdigest() if before else None}")
    print(f"sha_after={hashlib.sha256(written).hexdigest()}")
    print(f"bytes={len(written)} crlf={written.count(chr(13).encode())}")
    print(f"points={len(dpts.registry_snapshot()['points'])} retired={len(dpts.RETIRED_DP_REGISTRY)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

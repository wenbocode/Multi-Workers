"""Capture the T08 after-bytes/SHA/EOL and the T08-only full diff.

Compares the current implementation copy against the bytes this card captured
before encoding (evidence/.../dpc-t08-transport/before-bytes/). The pre-existing
mirror diff against git HEAD is *not* the T08 delta and is only reported as a
separate, untouched fact.
"""

from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers")
EVIDENCE = pathlib.Path(".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t08-transport")
BEFORE = EVIDENCE / "before-bytes" / "packages" / "multi-workers"
FILES = ("decision.py", "decision_backends.py", "test_dp_consolidation_materials.py")


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


def git(cwd: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return (proc.stdout or "") + (proc.stderr or "")


def main() -> None:
    after_dir = EVIDENCE / "after-bytes" / "packages" / "multi-workers"
    after_dir.mkdir(parents=True, exist_ok=True)
    diff_dir = EVIDENCE / "t08-diff"
    diff_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "copy_root": str(ROOT.resolve()).replace("\\", "/"),
        "files": [],
    }
    for name in FILES:
        current = ROOT / name
        record = {"exists": True, **stats(current)}
        before = BEFORE / name
        if before.exists():
            record["before"] = stats(before)
            # Normalise EOL for the textual diff only; the byte files stay exact.
            old_lines = before.read_text(encoding="utf-8").splitlines(keepends=True)
            new_lines = current.read_text(encoding="utf-8").splitlines(keepends=True)
            diff = "".join(
                difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"before/{name}",
                    tofile=f"after/{name}",
                    n=3,
                )
            )
            # Byte-exact LF copy: a text-mode write would translate to CRLF on
            # Windows and make the stored diff disagree with the source EOLs.
            (diff_dir / f"{name}.diff").write_bytes(diff.encode("utf-8"))
            record["t08_diff_bytes"] = len(diff.encode("utf-8"))
            record["t08_diff_added"] = sum(
                1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
            )
            record["t08_diff_removed"] = sum(
                1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")
            )
        else:
            record["before"] = {"exists": False}
        after = after_dir / name
        after.write_bytes(current.read_bytes())
        assert after.read_bytes() == current.read_bytes(), name
        doc["files"].append(record)
    # The mirror carries pre-existing diffs from earlier cards; this card added
    # to them and never reset them. Record the status read-only.
    status = git(EVIDENCE.parents[4], "status", "--porcelain", "--", "packages/multi-workers/decision.py", "packages/multi-workers/decision_backends.py")
    (EVIDENCE / "mirror-git-status.txt").write_text(status, encoding="utf-8")
    doc["mirror_git_status"] = status.strip().splitlines()
    (EVIDENCE / "after-bytes.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(doc, indent=2))


if __name__ == "__main__":
    main()

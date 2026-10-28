"""T03-R2 evidence helper: capture the after state and the write-scope proof.

Read-only w.r.t. product files. Writes, next to this script:
- ``after-manifest.json``: sha256/bytes/CRLF/bare-LF/lines per product file, plus
  the 13 handoff-path hashes (before vs after), the main-tree source hashes
  (must be unchanged), the original T03 evidence dir state (must be untouched)
  and the write-scope scan;
- ``after-bytes/``: byte copies of the four product files;
- ``r2-changes.diff``: unified diff of the four files against ``before-bytes``;
- ``write-scope-check.json``: every file under the implementation copy whose
  mtime is >= the R2 start and the exact allowed set.

Usage: ``python capture_after.py``.
"""

from __future__ import annotations

import datetime
import difflib
import hashlib
import json
import pathlib
import shutil
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
KEY = EVIDENCE.parents[3]
WORKTREE = KEY / "implementation-worktree"
MAIN_TREE = KEY.parents[1]
R2_START = datetime.datetime(2026, 10, 26, 3, 33, 0, tzinfo=datetime.timezone.utc)

FILES = (
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/test_decide_registry_contract.py",
    "packages/multi-workers/test_dp_consolidation_registry.py",
)
HANDOFF = (
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/decision_context.py",
    "packages/multi-workers/decision_book.py",
    "packages/multi-workers/decision.py",
    "packages/multi-workers/mw.py",
    "packages/multi-workers/scripts/gen_decide_registry_ts.py",
    "packages/multi-workers/decide_cases/dp1.json",
    "packages/multi-workers/decide_cases/dp2.json",
    "packages/multi-workers/decide_cases/dp3.json",
    "packages/multi-workers/decide_cases/dp25.json",
    "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts",
)
EXPECTED_CHANGED = {
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/test_decide_registry_contract.py",
    "packages/multi-workers/test_dp_consolidation_registry.py",
}
PRUNE = {"node_modules", "dist", "__pycache__", ".pytest_cache", ".git"}
ORIGINAL_T03 = EVIDENCE.parent


def measure(raw: bytes) -> dict:
    lf = raw.count(b"\n")
    crlf = raw.count(b"\r\n")
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "crlf": crlf,
        "bare_lf": lf - crlf,
        "lines": len(raw.splitlines()),
    }


def main() -> int:
    out_bytes = EVIDENCE / "after-bytes"
    out_bytes.mkdir(parents=True, exist_ok=True)
    before = json.loads((EVIDENCE / "before-manifest.json").read_text(encoding="utf-8"))
    before_files = {row["path"]: row for row in before["files"]}
    manifest: dict = {"stage": "after-r2", "r2_start": R2_START.isoformat(), "files": []}
    diff_chunks: list[str] = []
    for relative in FILES:
        path = WORKTREE / relative
        raw = path.read_bytes()
        row = {"path": relative, "exists": True, **measure(raw)}
        shutil.copyfile(path, out_bytes / pathlib.PurePosixPath(relative).name)
        previous = before_files[relative]
        row["before_sha256"] = previous["sha256"]
        row["changed"] = previous["sha256"] != row["sha256"]
        row["expected_changed"] = relative in EXPECTED_CHANGED
        before_raw = (EVIDENCE / "before-bytes" / pathlib.PurePosixPath(relative).name).read_bytes()
        if before_raw != raw:
            diff_chunks.extend(
                line + "\n"
                for line in difflib.unified_diff(
                    before_raw.decode("utf-8").splitlines(),
                    raw.decode("utf-8").splitlines(),
                    fromfile=f"before-r2/{relative}",
                    tofile=f"after-r2/{relative}",
                    lineterm="",
                )
            )
        if relative in before_files and before_files[relative].get("main_tree_sha256"):
            row["main_tree_unchanged"] = (
                hashlib.sha256((MAIN_TREE / relative).read_bytes()).hexdigest()
                == before_files[relative]["main_tree_sha256"]
            )
        manifest["files"].append(row)
    (EVIDENCE / "after-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "r2-changes.diff").write_text("".join(diff_chunks), encoding="utf-8")

    inventory = json.loads(
        (EVIDENCE.parent / "handoff-inventory.json").read_text(encoding="utf-8")
    )
    handoff_before = inventory["handoff_files"]
    scope: dict = {"r2_start": R2_START.isoformat(), "handoff": {}, "write_scope": {}}
    for relative in HANDOFF:
        current = hashlib.sha256((WORKTREE / relative).read_bytes()).hexdigest()
        previous = handoff_before[relative]["sha256"]
        scope["handoff"][relative] = {
            "before_sha256": previous,
            "after_sha256": current,
            "changed": current != previous,
            "expected_changed": relative in EXPECTED_CHANGED,
        }
    scope["handoff_ok"] = all(
        row["changed"] == row["expected_changed"] for row in scope["handoff"].values()
    )

    touched: list[str] = []
    for path in WORKTREE.rglob("*"):
        if not path.is_file() or PRUNE & set(path.parts):
            continue
        if datetime.datetime.fromtimestamp(
            path.stat().st_mtime, tz=datetime.timezone.utc
        ) >= R2_START:
            touched.append(str(path.relative_to(WORKTREE)).replace("\\", "/"))
    scope["write_scope"] = {
        "touched": sorted(touched),
        "expected": sorted(EXPECTED_CHANGED),
        "unexpected": sorted(set(touched) - EXPECTED_CHANGED),
        "missing": sorted(EXPECTED_CHANGED - set(touched)),
        "ok": set(touched) == EXPECTED_CHANGED,
    }

    untouched = []
    newer = []
    for path in ORIGINAL_T03.rglob("*"):
        if not path.is_file() or "rework-r2" in path.parts:
            continue
        row = {
            "path": str(path.relative_to(KEY)).replace("\\", "/"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "mtime": datetime.datetime.fromtimestamp(
                path.stat().st_mtime, tz=datetime.timezone.utc
            ).isoformat(),
        }
        untouched.append(row)
        if datetime.datetime.fromtimestamp(
            path.stat().st_mtime, tz=datetime.timezone.utc
        ) >= R2_START:
            newer.append(row["path"])
    scope["original_t03_evidence"] = {
        "files": len(untouched),
        "touched_after_r2_start": newer,
        "ok": newer == [],
    }
    (EVIDENCE / "write-scope-check.json").write_text(
        json.dumps(scope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in scope.items() if key != "handoff"}, indent=2))
    for relative, row in scope["handoff"].items():
        if row["changed"] != row["expected_changed"]:
            print("HANDOFF MISMATCH", relative, row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

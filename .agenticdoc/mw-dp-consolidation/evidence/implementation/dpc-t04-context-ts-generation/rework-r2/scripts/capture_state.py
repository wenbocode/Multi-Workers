#!/usr/bin/env python3
"""Capture a read-only state snapshot of this task's write face + its guards.

Usage: python capture_state.py <label>      # label = before | after | mid

Writes JSON under rework-r2/<label>/ and copies the allowed test bytes.
Read-only: it never writes inside implementation-worktree or the live tree.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
REWORK = HERE.parent.parent                     # .../rework-r2
REPO = pathlib.Path("H:/git/Multi-Workers")
WT = REPO / ".agenticdoc/mw-dp-consolidation/implementation-worktree"
MW = WT / "packages/multi-workers"
ORIGINAL_T04 = REPO / ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t04-context-ts-generation"

ALLOWED_TEST = MW / "test_decide_registry_ts_lock.py"
READONLY_PEERS = [
    MW / "decision_context.py",
    MW / "decision_points.py",
    MW / "scripts/gen_decide_registry_ts.py",
    MW / "decide_registry.json",
    WT / "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts",
]
LEGACY_CASES = [MW / "decide_cases" / name for name in ("dp1.json", "dp2.json", "dp3.json", "dp25.json")]
EXT = WT / "packages/coding-agent/src/extensions/agent-team-loop"
OTHER_GUARDS = [
    MW / "test_decide_registry_contract.py",   # T03 protocol test (r3 write face)
    MW / "test_decision_context.py",           # unowned test, explicitly not writable
    EXT / "pm/decision-tool.ts",                # T11 consumer
    EXT / "pm/triage-client.ts",                # T11 consumer
    EXT / "shared/decide-policy.ts",            # T11 consumer
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_facts(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    return {
        "path": path.relative_to(WT).as_posix() if WT in path.parents else str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "crlf": data.count(b"\r\n"),
        "bare_lf": data.count(b"\n") - data.count(b"\r\n"),
        "mtime_ns": path.stat().st_mtime_ns,
    }


def inventory(root: pathlib.Path, exclude: tuple[str, ...] = ()) -> dict:
    records = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel == item or rel.startswith(item + "/") for item in exclude):
            continue
        records[rel] = file_facts(path)["sha256"]
    return {"root": root.name, "files": len(records), "sha256": records}


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "before"
    out = REWORK / label
    out.mkdir(parents=True, exist_ok=True)

    allowed = file_facts(ALLOWED_TEST)
    (out / "allowed-test.bytes.py").write_bytes(ALLOWED_TEST.read_bytes())
    doc = {
        "label": label,
        "allowed_test": allowed,
        "readonly_peers": [file_facts(p) for p in READONLY_PEERS],
        "legacy_cases": [file_facts(p) for p in LEGACY_CASES],
        "legacy_case_dir_listing": sorted(p.name for p in (MW / "decide_cases").iterdir()),
        "other_guards": [file_facts(p) for p in OTHER_GUARDS if p.exists()],
        "missing_guards": [str(p) for p in OTHER_GUARDS if not p.exists()],
        "mirror_inventory": inventory(WT),
        # The R2 subdirectory lives inside the original T04 evidence dir and is
        # this attempt's own write face, so it is not part of the 112-file
        # read-only original evidence.
        "original_t04_evidence": inventory(ORIGINAL_T04, exclude=("rework-r2",)),
    }
    (out / "state.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    git = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True, check=False
    )
    (out / "live-git-status.txt").write_text(git.stdout, encoding="utf-8")
    print(
        f"{label}: test={allowed['sha256'][:12]} bytes={allowed['bytes']} "
        f"mirror={doc['mirror_inventory']['files']} "
        f"orig_evidence={doc['original_t04_evidence']['files']} "
        f"git_lines={len(git.stdout.splitlines())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

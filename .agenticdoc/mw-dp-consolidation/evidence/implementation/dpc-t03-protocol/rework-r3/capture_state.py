"""Capture the R3 before/after state (read-only; writes only this evidence dir).

usage: python capture_state.py before|after
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

EVIDENCE = pathlib.Path(__file__).resolve().parent
KEY = EVIDENCE.parents[3]
WORKTREE = KEY / "implementation-worktree"
PACKAGE = WORKTREE / "packages" / "multi-workers"
MAIN_ROOT = KEY.parents[1]
R2 = KEY / "evidence" / "implementation" / "dpc-t03-protocol" / "rework-r2"
ORIGINAL = KEY / "evidence" / "implementation" / "dpc-t03-protocol"

PRODUCT = [
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/test_decide_registry_contract.py",
    "packages/multi-workers/test_dp_consolidation_registry.py",
]

#: Product-adjacent files the card keeps read-only (not part of the 13-row table).
PROTECTED_EXTRA = [
    "packages/multi-workers/scripts/gen_decide_registry_ts.py",
    "packages/multi-workers/mw.py",
    "packages/multi-workers/decision.py",
    "packages/multi-workers/decision_context.py",
    "packages/multi-workers/decision_book.py",
    "packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def measure(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    return {
        "exists": path.is_file(),
        "bytes": len(data),
        "sha256": sha(data),
        "crlf": data.count(b"\r\n"),
        "bare_lf": data.count(b"\n") - data.count(b"\r\n"),
        "lines": len(data.splitlines()),
        "last_byte": data[-1] if data else None,
        "mtime_ns": path.stat().st_mtime_ns if path.exists() else None,
    }


def main() -> int:
    stage = sys.argv[1]
    assert stage in ("before", "after"), stage
    started = datetime.now(timezone.utc).isoformat()
    handoff_table = json.loads((R2 / "write-scope-check.json").read_text(encoding="utf-8"))["handoff"]

    files = []
    for relative in PRODUCT:
        record = {"path": relative, **measure(WORKTREE / relative)}
        record["main_tree"] = measure(MAIN_ROOT / relative) if (MAIN_ROOT / relative).is_file() else {"exists": False}
        files.append(record)
        if stage == "before":
            (EVIDENCE / "before-bytes" / pathlib.Path(relative).name).write_bytes(
                (WORKTREE / relative).read_bytes()
            )
        else:
            (EVIDENCE / "after-bytes" / pathlib.Path(relative).name).write_bytes(
                (WORKTREE / relative).read_bytes()
            )

    handoff = {}
    for relative, record in handoff_table.items():
        current = measure(WORKTREE / relative)
        handoff[relative] = {
            "r2_before_sha256": record["before_sha256"],
            "r2_after_sha256": record["after_sha256"],
            "current_sha256": current["sha256"],
            "current_matches_r2_after": current["sha256"] == record["after_sha256"],
        }

    protected = {relative: measure(WORKTREE / relative) for relative in PROTECTED_EXTRA}

    boundary = {}
    for label, root in (("original-t03", ORIGINAL), ("rework-r2", R2)):
        entries = {}
        for path in sorted(root.rglob("*")):
            if not path.is_file() or EVIDENCE in path.parents:
                continue
            relative = path.relative_to(KEY).as_posix()
            data = path.read_bytes()
            entries[relative] = {"bytes": len(data), "sha256": sha(data)}
        boundary[label] = {"files": len(entries), "sha256": entries}

    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *PRODUCT, "packages/multi-workers/scripts"],
        cwd=MAIN_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (EVIDENCE / f"{stage}-git-status.log").write_text(
        f"cwd={MAIN_ROOT}\nargv={['git', 'status', '--porcelain', '--', *PRODUCT]}\nrc={status.returncode}\nstdout:\n{status.stdout}\nstderr:\n{status.stderr}\n",
        encoding="utf-8",
    )

    doc = {
        "stage": stage,
        "observed_at_utc": started,
        "worktree": str(WORKTREE),
        "package": str(PACKAGE),
        "main_root": str(MAIN_ROOT),
        "main_head": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=MAIN_ROOT, env=env, capture_output=True, text=True
        ).stdout.strip(),
        "files": files,
        "handoff_rows": len(handoff),
        "handoff": handoff,
        "protected_extra": protected,
        "evidence_boundary": boundary,
    }
    (EVIDENCE / f"{stage}-manifest.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: doc[k] for k in ("stage", "observed_at_utc", "main_head", "handoff_rows")}, ensure_ascii=False))
    for record in files:
        print(record["path"], record["bytes"], record["sha256"], "crlf=", record["crlf"], "bare_lf=", record["bare_lf"])
    changed = [p for p, r in handoff.items() if not r["current_matches_r2_after"]]
    print("handoff rows not at R2 after:", changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

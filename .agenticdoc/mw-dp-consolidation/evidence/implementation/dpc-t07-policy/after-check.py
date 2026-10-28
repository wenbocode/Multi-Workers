"""T07 after-snapshot: bytes/SHA256/EOL/EOF of my two files + import binding.

Read-only outside this card's evidence directory. Also records the current
peer faces so the net mirror diff can be attributed (T06/T08 are different
exact write faces and are not authored by this worker).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import time

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[4]
WORKTREE = REPO / ".agenticdoc/mw-dp-consolidation/implementation-worktree"
PKG = WORKTREE / "packages/multi-workers"

MINE = ["decision_policy.py", "test_dp_consolidation_recovery.py"]
PEERS = [
    "decision_validity.py",
    "test_dp_consolidation_concurrency.py",
    "decision.py",
    "decision_backends.py",
    "test_dp_consolidation_materials.py",
]


def _state(rel: str) -> dict:
    path = PKG / rel
    if not path.exists():
        return {"file": rel, "exists": False}
    data = path.read_bytes()
    text = data.decode("utf-8", errors="strict")
    return {
        "file": rel,
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "eol": "crlf" if "\r\n" in text else "lf",
        "trailing_newline": text.endswith("\n"),
        "ends_at_eof": text[-120:].splitlines()[-1] if text.splitlines() else "",
        "lines": text.count("\n") + (0 if text.endswith("\n") else 1),
    }


def _pycache_dirs() -> list[str]:
    return sorted(
        str(p.relative_to(WORKTREE)).replace("\\", "/")
        for p in WORKTREE.rglob("__pycache__")
        if p.is_dir()
    )


def _probe() -> dict:
    env = {"PYTHONDONTWRITEBYTECODE": "1", "PATH": ""}
    cmd = [
        sys.executable,
        "-B",
        "-c",
        "import json,decision_policy as m; print(json.dumps({'file': m.__file__,"
        " 'version': m.POLICY_SCHEMA_VERSION,"
        " 'frozen_units': sorted(m.FROZEN_CONFIG_UNITS)}))",
    ]
    proc = subprocess.run(
        cmd, cwd=str(PKG), env=env, capture_output=True, text=True, encoding="utf-8"
    )
    return {
        "cwd": str(PKG),
        "argv": cmd,
        "rc": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main() -> int:
    git = subprocess.run(
        ["git", "status", "--porcelain", "--", str(WORKTREE)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    snapshot = {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mine": [_state(name) for name in MINE],
        "peer_faces_not_authored_here": [_state(name) for name in PEERS],
        "import_binding_probe": _probe(),
        "pycache_dirs_in_worktree": _pycache_dirs(),
        "pytest_cache_dirs_in_worktree": sorted(
            str(p.relative_to(WORKTREE)).replace("\\", "/")
            for p in WORKTREE.rglob(".pytest_cache")
            if p.is_dir()
        ),
        "git_status_scope": {
            "cmd": f"git status --porcelain -- {WORKTREE}",
            "rc": git.returncode,
            "stdout_head": git.stdout.splitlines()[:20],
            "note": "the whole worktree copy is untracked in the origin repo; "
            "exact-file bytes above are the authoritative before/after record",
        },
    }
    out = EVIDENCE / "after-check.json"
    out.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

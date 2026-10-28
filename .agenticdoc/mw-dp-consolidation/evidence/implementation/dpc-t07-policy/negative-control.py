"""T07 negative control: mutate three fail-closed branches and expect red.

The real product file is only *read*; the mutants live beside this script in
the card evidence directory. This is not part of the product and is not a
"red test first" substitute - it proves the assigned suite actually fails when
the fail-closed logic is removed.

Usage: python -B negative-control.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE = HERE.parents[2] / "implementation-worktree"
PKG = WORKTREE / "packages" / "multi-workers"
CONTROL = HERE / "negative-control"

MUTATIONS = {
    # AC-008: drop the policy fail-closed reasons from the gate verdict
    "gate_policy_issues": (
        "    if not load.usable:\n        reasons.extend(load.issues)\n"
        "    if not isinstance(hard_checks, Mapping) or not hard_checks:\n",
        "    if not load.usable:\n        reasons.extend(())\n"
        "    if not isinstance(hard_checks, Mapping) or not hard_checks:\n",
    ),
    # AC-021: let a spend overrun the hard limit
    "budget_overrun": (
        "    if used_after > limit.limit:",
        "    if False:",
    ),
    # AC-035: let a technical approval lift a user stop
    "user_stop": (
        "        if (\n            resolution.record is None\n"
        "            or resolution.record.kind not in HUMAN_AUTHORITY_KINDS\n        ):\n",
        "        if False:\n",
    ),
    # AC-036: accept the tripped chain as its own recovery channel
    "breaker_self_approval": (
        "    if tripped and channel and channel == tripped:",
        "    if False:",
    ),
}


def main() -> int:
    CONTROL.mkdir(parents=True, exist_ok=True)
    source = (PKG / "decision_policy.py").read_text(encoding="utf-8")
    text = source
    applied = []
    for name, (old, new) in MUTATIONS.items():
        count = text.count(old)
        assert count == 1, (name, count)
        text = text.replace(old, new)
        applied.append(name)
    (CONTROL / "decision_policy.py").write_text(text, encoding="utf-8", newline="\n")
    test_copy = CONTROL / "test_dp_consolidation_recovery.py"
    test_copy.write_text(
        (PKG / "test_dp_consolidation_recovery.py").read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )
    env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONIOENCODING": "utf-8",
        "HOME": str(HERE / "fixture" / "home"),
        "USERPROFILE": str(HERE / "fixture" / "home"),
        "TMPDIR": str(HERE / "fixture" / "tmp"),
        "TEMP": str(HERE / "fixture" / "tmp"),
        "TMP": str(HERE / "fixture" / "tmp"),
        "DPC_T07_FIXTURE_ROOT": str(HERE / "fixture"),
        "PATH": __import__("os").environ.get("PATH", ""),
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
        "WINDIR": __import__("os").environ.get("WINDIR", ""),
    }
    cmd = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        str(test_copy),
    ]
    proc = subprocess.run(
        cmd, cwd=str(PKG), env=env, capture_output=True, text=True, encoding="utf-8"
    )
    result = {
        "mutations": applied,
        "product_file_sha256": __import__("hashlib").sha256(
            (PKG / "decision_policy.py").read_bytes()
        ).hexdigest(),
        "argv": cmd,
        "rc": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-2000:],
    }
    (HERE / "negative-control.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({k: result[k] for k in ("mutations", "rc")}, ensure_ascii=False))
    print(proc.stdout[-3000:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

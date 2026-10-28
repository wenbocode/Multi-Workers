"""Mutant check for T02c: revert ONLY the metadata-key policy in a temp copy.

The worktree ``decision_wire.py`` is untracked, so git cannot produce the
pre-fix module. This script rebuilds the audited behaviour (mapping keys passed
through as schema labels) in ``%TEMP%/t02c-mutant`` and re-runs the new tests.
Every new key-safety test must be RED there; the worktree is never touched.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parents[4] / "packages" / "multi-workers"
SOURCE = PKG / "decision_wire.py"
TESTS = ("test_decision_wire_store.py", "test_decision_wire_transport.py")

K = "metadata keys and values"
NEW_MAPPING_BRANCH = (
    "    if isinstance(value, Mapping):\n"
    "        return _sanitize_mapping(\n"
    "            scope, value, limit=limit, depth=depth, closed_keys=closed_keys\n"
    "        )\n"
)
OLD_MAPPING_BRANCH = (
    "    if isinstance(value, Mapping):\n"
    "        return {\n"
    "            key: _sanitize_metadata(\n"
    "                scope, item, limit=limit, depth=depth + 1, closed_keys=closed_keys\n"
    "            )\n"
    "            for key, item in value.items()\n"
    "        }\n"
)
SELECT = (
    "usage_mapping_keys or policy_nested_mapping_keys or metadata_mapping_keys "
    "or colliding_redacted or redacted_key_colliding "
    "or counter_label_that_is_itself or metadata_key_sanitizing "
    "or oversized_metadata_keys or persisted_line_never_holds_a_usage_key "
    "or usage_key_from_a_real_response or metadata_without_a_redactor_omits"
)


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    if NEW_MAPPING_BRANCH not in source:
        raise SystemExit("new mapping branch not found; source moved")
    start = source.index("def _sanitize_mapping(")
    end = source.index("def _sanitize_metadata(")
    mutant = source[:start] + source[end:]
    mutant = mutant.replace(NEW_MAPPING_BRANCH, OLD_MAPPING_BRANCH, 1)
    # The key policy is gone; _sanitize_metadata_key must not linger unused.
    mutant = re.sub(
        r"\ndef _sanitize_metadata_key\(.*?\n\ndef _sanitize_metadata\(",
        "\ndef _sanitize_metadata(",
        mutant,
        count=1,
        flags=re.S,
    )
    if "def _sanitize_metadata_key(" in mutant or "def _sanitize_mapping(" in mutant:
        raise SystemExit("mutant still carries the key policy")

    root = pathlib.Path(tempfile.mkdtemp(prefix="t02c-mutant-"))
    (root / "decision_wire.py").write_text(mutant, encoding="utf-8")
    for name in TESTS:
        shutil.copy(PKG / name, root / name)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PKG)
    argv = [
        sys.executable,
        "-m",
        "pytest",
        *TESTS,
        "-q",
        "-k",
        SELECT,
    ]
    print(f"mutant root: {root}")
    print(f"cwd: {root}")
    print("cmd: " + " ".join(argv))
    completed = subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True)
    print(completed.stdout)
    print(completed.stderr)
    print(f"exit={completed.returncode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

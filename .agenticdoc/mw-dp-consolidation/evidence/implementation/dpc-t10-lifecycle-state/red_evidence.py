"""T10 RED evidence: run the new tests against the pre-change (HEAD) sources.

The three product modules are restored from ``git show HEAD:<path>`` into a
throw-away copy under the OS temp root; the two (new) test files are copied from
the isolated worktree. Nothing in the worktree or the live repo is written.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORKTREE_PKG = HERE.parents[2] / "implementation-worktree" / "packages" / "multi-workers"
#: ``packages/multi-workers`` is untracked in this repo, so the pre-change bytes
#: are the live copies (verified byte-identical to the worktree baseline).
LIVE_PKG = HERE.parents[4] / "packages" / "multi-workers"
PRODUCT = ("decision_wire.py", "decision_lifecycle.py", "decision_task_state.py")
TESTS = ("test_decision_context_lifecycle.py", "test_decision_task_state.py")


def main() -> int:
    label = "red-prefix"
    root = pathlib.Path(tempfile.gettempdir()) / "dpc-t10-lifecycle-state" / label
    pkg = root / "pkg"
    if pkg.exists():
        def _force(func, path, _exc):
            os.chmod(path, 0o700)
            func(path)

        shutil.rmtree(pkg, onexc=_force)
    shutil.copytree(
        WORKTREE_PKG,
        pkg,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "node_modules"),
    )
    restored = {}
    for name in PRODUCT:
        before = (LIVE_PKG / name).read_bytes()
        (pkg / name).write_bytes(before)
        restored[name] = hashlib.sha256(before).hexdigest()
    for name in TESTS:
        shutil.copyfile(WORKTREE_PKG / name, pkg / name)

    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "HOME": str(root / "home"),
        "USERPROFILE": str(root / "home"),
        "TEMP": str(root / "temp"),
        "TMP": str(root / "temp"),
        "XDG_CACHE_HOME": str(root / "temp" / "cache"),
        "PYTHONPYCACHEPREFIX": str(root / "temp" / "pycache"),
    }
    for key in ("home", "temp"):
        (root / key).mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        *TESTS,
    ]
    completed = subprocess.run(
        argv,
        cwd=str(pkg),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (HERE / f"{label}.stdout").write_text(completed.stdout, encoding="utf-8", newline="\n")
    (HERE / f"{label}.stderr").write_text(completed.stderr, encoding="utf-8", newline="\n")
    (HERE / f"{label}.rc").write_text(f"{completed.returncode}\n", encoding="utf-8", newline="\n")
    meta = {
        "label": label,
        "argv": argv,
        "cwd": str(pkg),
        "restored_head_product_bytes": restored,
        "rc": completed.returncode,
        "note": "pre-change product modules + post-change tests: expected RED",
    }
    (HERE / f"{label}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"label": label, "rc": completed.returncode}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

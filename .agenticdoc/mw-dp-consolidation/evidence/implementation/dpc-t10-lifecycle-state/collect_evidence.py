"""T10 evidence collector: after-bytes/diffs, mirror + live drift, AST preservation,
pyc inventory and import resolution. Read-only; writes only into this evidence dir.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import difflib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
KEY = REPO / ".agenticdoc" / "mw-dp-consolidation"
WT = KEY / "implementation-worktree"
LIVE = REPO / "packages" / "multi-workers"
WT_PKG = WT / "packages" / "multi-workers"
FILES = (
    "decision_wire.py",
    "decision_lifecycle.py",
    "decision_task_state.py",
    "test_decision_context_lifecycle.py",
    "test_decision_task_state.py",
)
S2 = KEY / "evidence" / "implementation" / "s2-t05-t10-pre-dispatch-20261027"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_info(path: pathlib.Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "exists": True,
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "lf": data.count(b"\n"),
        "crlf": data.count(b"\r\n"),
        "eol": "lf" if data.count(b"\r\n") == 0 else "crlf",
        "ends_with_lf": data.endswith(b"\n"),
    }


def unified(before: bytes, after: bytes, name: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.decode("utf-8").splitlines(keepends=True),
            after.decode("utf-8").splitlines(keepends=True),
            fromfile=f"before/{name}",
            tofile=f"after/{name}",
            n=3,
        )
    )


def mirror_drift() -> dict[str, object]:
    """Drift of the isolated mirror against the PM pre-dispatch inventory.

    ``s2-t05-t10-pre-dispatch-20261027/mirror-inventory.json`` hashes the
    *worktree mirror* (repo-relative keys, 1883 entries), not the live repo: a
    module that only exists in the mirror (``decision_policy.py``) is listed
    there and absent from the live tree. Comparing the live repo against that
    inventory is therefore meaningless and is not claimed here.
    """
    inventory = json.loads((S2 / "mirror-inventory.json").read_text(encoding="utf-8"))
    wt_changed: list[str] = []
    wt_missing: list[str] = []
    for rel, expected in inventory.items():
        path = WT / rel
        if not path.exists():
            wt_missing.append(rel)
            continue
        if sha256_bytes(path.read_bytes()) != expected:
            wt_changed.append(rel)
    worktree_files = sorted(
        p.relative_to(WT).as_posix() for p in WT.rglob("*") if p.is_file()
    )
    return {
        "inventory_entries": len(inventory),
        "worktree_changed": sorted(wt_changed),
        "worktree_missing": sorted(wt_missing),
        "worktree_file_count": len(worktree_files),
        "worktree_files_not_in_inventory": [
            rel for rel in worktree_files if rel not in inventory
        ],
        "live_product_files_unchanged_since_baseline": {
            name: sha256_bytes((LIVE / name).read_bytes()) == json.loads(
                (HERE / "baseline.json").read_text(encoding="utf-8")
            )["files"][name]["live"]["sha256"]
            for name in FILES
        },
    }


def ast_preservation() -> dict[str, object]:
    report: dict[str, object] = {}
    for name in ("test_decision_context_lifecycle.py", "test_decision_task_state.py"):
        before_tree = ast.parse((LIVE / name).read_text(encoding="utf-8"))
        after_tree = ast.parse((WT_PKG / name).read_text(encoding="utf-8"))

        def functions(tree: ast.Module) -> dict[str, str]:
            return {
                node.name: ast.dump(node)
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }

        before = functions(before_tree)
        after = functions(after_tree)
        changed = [key for key in before if after.get(key) != before[key]]
        report[name] = {
            "before_functions": len(before),
            "after_functions": len(after),
            "missing_original_functions": sorted(set(before) - set(after)),
            "changed_original_functions": changed,
            "added_functions": sorted(set(after) - set(before)),
        }
    return report


def pyc_inventory() -> dict[str, object]:
    snapshot = json.loads((S2 / "pyc-protection.json").read_text(encoding="utf-8"))
    worktree = {}
    for rel in snapshot:
        path = WT / rel
        worktree[rel] = (
            {"sha256": sha256_bytes(path.read_bytes()), "bytes": path.stat().st_size}
            if path.exists()
            else None
        )
    worktree_pyc = [
        {
            "path": path.relative_to(WT).as_posix(),
            "sha256": sha256_bytes(path.read_bytes()),
            "bytes": path.stat().st_size,
            "in_protected_set": path.relative_to(WT).as_posix() in snapshot,
        }
        for path in sorted(WT_PKG.rglob("*.pyc"))
    ]
    return {
        "protected_paths": len(snapshot),
        "protected_present": sum(1 for value in worktree.values() if value),
        "protected_missing": sorted(rel for rel, value in worktree.items() if not value),
        "protected_unchanged": sorted(
            rel
            for rel, value in worktree.items()
            if value and value["sha256"] == snapshot[rel]
        ),
        "protected_changed": sorted(
            rel
            for rel, value in worktree.items()
            if value and value["sha256"] != snapshot[rel]
        ),
        "worktree_pyc_count": len(worktree_pyc),
        "worktree_pyc": worktree_pyc,
        "note": (
            "the protected 14 pyc live in the worktree mirror (7 top-level + 7 "
            "autopilot); every worker python run uses -B + "
            "PYTHONDONTWRITEBYTECODE=1 + PYTHONPYCACHEPREFIX, so no pyc is written"
        ),
    }


def import_resolution() -> dict[str, object]:
    root = pathlib.Path(tempfile.gettempdir()) / "dpc-t10-lifecycle-state" / "imports"
    root.mkdir(parents=True, exist_ok=True)
    code = (
        "import json, pathlib, sys\n"
        "import decision_wire, decision_lifecycle, decision_task_state, decision_history, decision_book\n"
        "print(json.dumps({'sys_path0': sys.path[0], 'cwd': str(pathlib.Path.cwd()), "
        "'modules': {name: module.__file__ for name, module in ("
        "('decision_wire', decision_wire), ('decision_lifecycle', decision_lifecycle),"
        "('decision_task_state', decision_task_state), ('decision_history', decision_history),"
        "('decision_book', decision_book))}}))\n"
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPYCACHEPREFIX": str(root / "pycache"),
        "HOME": str(root / "home"),
        "USERPROFILE": str(root / "home"),
        "TEMP": str(root / "temp"),
        "TMP": str(root / "temp"),
    }
    (root / "home").mkdir(exist_ok=True)
    (root / "temp").mkdir(exist_ok=True)
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=str(WT_PKG),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    payload = json.loads(completed.stdout) if completed.returncode == 0 else {}
    modules = payload.get("modules", {})
    return {
        "rc": completed.returncode,
        "stderr": completed.stderr[-400:],
        "sys_path0": payload.get("sys_path0"),
        "cwd": payload.get("cwd"),
        "modules": modules,
        "all_inside_worktree": all(
            pathlib.Path(path).resolve().is_relative_to(WT.resolve())
            for path in modules.values()
        )
        if modules
        else False,
    }


def main() -> int:
    after: dict[str, object] = {}
    for name in FILES:
        before_bytes = (LIVE / name).read_bytes()
        after_bytes = (WT_PKG / name).read_bytes()
        diff = unified(before_bytes, after_bytes, name)
        after[name] = {
            "before": file_info(LIVE / name),
            "after": file_info(WT_PKG / name),
            "diff_hunks": diff.count("\n@@"),
            "diff_bytes": len(diff.encode("utf-8")),
        }
        (HERE / f"diff-{name}.diff").write_text(diff, encoding="utf-8", newline="\n")
    payload = {
        "source": "agent-report",
        "files": after,
        "mirror": mirror_drift(),
        "ast": ast_preservation(),
        "pyc": pyc_inventory(),
        "imports": import_resolution(),
    }
    (HERE / "after.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"ok": True, "files": list(after)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

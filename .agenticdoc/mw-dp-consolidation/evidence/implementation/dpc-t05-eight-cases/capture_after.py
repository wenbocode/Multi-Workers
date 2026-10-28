"""Capture the T05 after-image and the real verification facts.

Read-only over the isolated implementation copy; writes only into this card's
evidence directory. It records:

* before/after SHA256 + bytes + EOL for the card's product write face;
* the four legacy case files (must be byte-identical to the before image);
* the 14 protected ``__pycache__`` entries from the pre-dispatch inventory;
* the T10 shared read-dependency files (SHA256 + imported ``__file__``);
* the byte equality of the shipped eight cases against an isolated generator
  run (``--out`` into this evidence directory).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
KEY_ROOT = HERE.parents[2]  # .agenticdoc/mw-dp-consolidation
WORKTREE = KEY_ROOT / "implementation-worktree"
PKG = WORKTREE / "packages" / "multi-workers"
EVIDENCE = HERE

PRODUCT_FILES = [
    "packages/multi-workers/scripts/build_decide_cases.py",
    "packages/multi-workers/decide_book_template.json",
    "packages/multi-workers/test_decision_context_workbench.py",
    "packages/multi-workers/decide_cases/dp-w-type.json",
    "packages/multi-workers/decide_cases/dp-pm-steer.json",
    "packages/multi-workers/decide_cases/dp-w-check-task.json",
    "packages/multi-workers/decide_cases/dp-QG.json",
    "packages/multi-workers/decide_cases/dp-gate-approve.json",
    "packages/multi-workers/decide_cases/dp-sign-key.json",
    "packages/multi-workers/decide_cases/dp-auto.json",
    "packages/multi-workers/decide_cases/dp-route.json",
]
LEGACY_FILES = [
    "packages/multi-workers/decide_cases/dp1.json",
    "packages/multi-workers/decide_cases/dp2.json",
    "packages/multi-workers/decide_cases/dp3.json",
    "packages/multi-workers/decide_cases/dp25.json",
]
T10_DEPENDENCIES = [
    "packages/multi-workers/decision_lifecycle.py",
    "packages/multi-workers/decision_task_state.py",
    "packages/multi-workers/decision_wire.py",
]
PYC_PROTECTION = HERE.parent / "s2-t05-t10-pre-dispatch-20261027" / "pyc-protection.json"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(rel: str) -> dict:
    path = WORKTREE / rel
    if not path.is_file():
        return {"path": rel, "exists": False, "sha256": None, "bytes": None}
    data = path.read_bytes()
    return {
        "path": rel,
        "exists": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "lf": data.count(b"\n") - data.count(b"\r\n"),
        "crlf": data.count(b"\r\n"),
    }


def import_probe(rel: str) -> dict:
    name = pathlib.Path(rel).stem
    if str(PKG) not in sys.path:
        sys.path.insert(0, str(PKG))
    importlib.invalidate_caches()
    spec = importlib.util.find_spec(name)
    module_file = str(pathlib.Path(spec.origin).resolve()) if spec and spec.origin else None
    return {
        "module": name,
        "imported_from": module_file,
        "inside_copy": bool(module_file and pathlib.Path(module_file).is_relative_to(PKG)),
        "sha256": sha256(pathlib.Path(module_file)) if module_file else None,
    }


def generator_out(out_dir: pathlib.Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "scripts/build_decide_cases.py", "--out", str(out_dir), "--quiet"],
        cwd=str(PKG),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **{k: v for k, v in __import__("os").environ.items() if not k.upper().endswith("_API_KEY")},
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        },
    )
    return {
        "argv": ["python", "-B", "-X", "utf8", "scripts/build_decide_cases.py", "--out", str(out_dir), "--quiet"],
        "cwd": str(PKG),
        "rc": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "files": sorted(path.name for path in out_dir.glob("*.json")),
    }


def main() -> int:
    before = json.loads((EVIDENCE / "before-metadata.json").read_text(encoding="utf-8"))
    before_rows = {row["path"]: row for row in before["product_files"] + before["legacy_files"]}
    after_rows = [describe(rel) for rel in PRODUCT_FILES + LEGACY_FILES]

    changed = []
    for row in after_rows:
        old = before_rows.get(row["path"], {"sha256": None, "bytes": None, "exists": False})
        changed.append(
            {
                "file": row["path"],
                "before_exists": old["exists"],
                "before_sha256": old["sha256"],
                "before_bytes": old["bytes"],
                "after_exists": row["exists"],
                "after_sha256": row["sha256"],
                "after_bytes": row["bytes"],
                "lf": row.get("lf"),
                "crlf": row.get("crlf"),
                "changed": old["sha256"] != row["sha256"],
            }
        )

    protected = json.loads(PYC_PROTECTION.read_text(encoding="utf-8")) if PYC_PROTECTION.is_file() else {}
    pyc = {}
    for rel, expected in protected.items():
        path = WORKTREE / rel
        pyc[rel] = {
            "expected": expected,
            "actual": sha256(path) if path.is_file() else None,
            "unchanged": path.is_file() and sha256(path) == expected,
        }

    isolated = EVIDENCE / "generator-out"
    run = generator_out(isolated) if not isolated.exists() else {
        "note": "already generated in an earlier step; re-used",
        "files": sorted(path.name for path in isolated.glob("*.json")),
    }
    shipped_vs_generated = {}
    for row in after_rows:
        name = pathlib.Path(row["path"]).name
        if not row["path"].startswith("packages/multi-workers/decide_cases/"):
            continue
        shipped = WORKTREE / row["path"]
        generated = isolated / name
        if generated.is_file():
            shipped_vs_generated[name] = {
                "generated": True,
                "equal": shipped.read_bytes() == generated.read_bytes(),
                "sha256": row["sha256"],
            }

    payload = {
        "captured_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "worktree": str(WORKTREE),
        "changed_files": changed,
        "pyc_protection": pyc,
        "t10_shared_read_dependencies": [import_probe(rel) for rel in T10_DEPENDENCIES],
        "isolated_generator_run": run,
        "shipped_vs_generated": shipped_vs_generated,
    }
    (EVIDENCE / "after-metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(
        {
            "changed": [row["file"] for row in changed if row["changed"]],
            "unchanged_legacy": [
                row["file"] for row in changed
                if row["file"] in LEGACY_FILES and not row["changed"]
            ],
            "pyc_all_unchanged": all(item["unchanged"] for item in pyc.values()),
            "pyc_count": len(pyc),
            "shipped_equal": all(item["equal"] for item in shipped_vs_generated.values()),
            "generator_rc": run.get("rc"),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())

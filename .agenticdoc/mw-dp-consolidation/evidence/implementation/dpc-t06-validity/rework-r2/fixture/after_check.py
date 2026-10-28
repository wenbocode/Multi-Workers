"""Mechanical after-state evidence for the T06 R2 rework.

Writes (all inside this card's rework-r2 evidence directory):
- ``after-bytes/<file>``: exact current bytes of the two assigned products;
- ``after.json``: bytes / LF / CRLF / SHA256 for the before and after copies;
- ``product.diff``: unified diff before -> after (mechanically generated);
- ``pycache.json``: every ``.pyc`` in the copy with its hash;
- ``net-inventory-diff.json``: whole-copy file hashes compared with the PM
  after-inventory (read-only source) so net changes stay attributable.

Read-only outside this card's evidence directory and the two products.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import pathlib

FIXTURE = pathlib.Path(__file__).resolve().parent
EVIDENCE = FIXTURE.parent
KEY_ROOT = EVIDENCE.parents[3]
COPY_ROOT = KEY_ROOT / "implementation-worktree"
PACKAGE = COPY_ROOT / "packages" / "multi-workers"
PM_EVIDENCE = (
    KEY_ROOT
    / "evidence"
    / "implementation"
    / "t06-pm-handoff-20261026"
)
FILES = ("decision_validity.py", "test_dp_consolidation_concurrency.py")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def describe(data: bytes) -> dict[str, object]:
    lf = data.count(b"\n")
    crlf = data.count(b"\r\n")
    return {
        "bytes": len(data),
        "lf": lf,
        "crlf": crlf,
        "sha256": digest(data),
    }


def main() -> None:
    (EVIDENCE / "after-bytes").mkdir(exist_ok=True)
    state: dict[str, dict[str, object]] = {}
    for name in FILES:
        after = (PACKAGE / name).read_bytes()
        before = (EVIDENCE / "before-bytes" / name).read_bytes()
        (EVIDENCE / "after-bytes" / name).write_bytes(after)
        state[name] = {
            "before": describe(before),
            "after": describe(after),
            "same_bytes": before == after,
        }
        if before != after:
            diff = difflib.unified_diff(
                before.decode("utf-8").splitlines(keepends=True),
                after.decode("utf-8").splitlines(keepends=True),
                fromfile=f"before/{name}",
                tofile=f"after/{name}",
                n=3,
            )
            text = "".join(diff)
            (EVIDENCE / f"{name}.diff").write_text(text, encoding="utf-8")
            state[name]["diff_bytes"] = len(text.encode("utf-8"))
            state[name]["diff_sha256"] = digest(text.encode("utf-8"))

    (EVIDENCE / "after.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    pyc = {}
    for path in sorted(COPY_ROOT.rglob("*.pyc")):
        pyc[str(path.relative_to(COPY_ROOT)).replace("\\", "/")] = digest(
            path.read_bytes()
        )
    (EVIDENCE / "pycache.json").write_text(
        json.dumps(
            {"count": len(pyc), "files": pyc}, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )

    baseline = json.loads(
        (PM_EVIDENCE / "after-inventory.json").read_text(encoding="utf-8")
    )
    current = {}
    for path in sorted(COPY_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(COPY_ROOT)).replace("\\", "/")
        current[rel] = digest(path.read_bytes())
    net = {
        "baseline_entries": len(baseline),
        "current_entries": len(current),
        "added": sorted(set(current) - set(baseline)),
        "removed": sorted(set(baseline) - set(current)),
        "changed": sorted(
            key for key in set(current) & set(baseline) if current[key] != baseline[key]
        ),
    }
    (EVIDENCE / "net-inventory-diff.json").write_text(
        json.dumps(net, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(state, indent=2, sort_keys=True))
    print("pyc_count=", len(pyc))
    print("added=", net["added"])
    print("removed=", net["removed"])
    print("changed=", net["changed"])


if __name__ == "__main__":
    main()

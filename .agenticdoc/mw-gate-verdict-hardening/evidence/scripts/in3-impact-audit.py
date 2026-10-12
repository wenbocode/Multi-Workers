"""IN-3 impact audit (read-only).

Classifies every file under .agenticdoc touched in the two re-run windows and
flags the ones that are *products* (durable deliverables) vs run-internal
artifacts, plus anything that looks truncated.
"""

import datetime
import pathlib
import sys

ROOT = pathlib.Path("H:/git/Multi-Workers/.agenticdoc")

WINDOWS = [
    ("W1", datetime.datetime(2026, 10, 9, 20, 5, 0), datetime.datetime(2026, 10, 9, 20, 55, 0)),
    ("W2", datetime.datetime(2026, 10, 10, 10, 50, 0), datetime.datetime(2026, 10, 10, 11, 35, 0)),
]

PRODUCT_NAMES = {"output.md", "report.md", "report-output.md", "achieved.md", "progress.md"}
PHASE_DOCS = {"spec.md", "design.md", "plan.md", "pm-state.md", "key-decision.md", "goal.md"}


def kind_of(rel: str, name: str) -> str:
    parts = rel.split("/")
    if name in ("trace.log", "worker.log"):
        return "run-internal"
    if "evidence" in parts:
        return "evidence"
    if name in PRODUCT_NAMES:
        return "worker-product"
    if name in PHASE_DOCS:
        return "PHASE-DOC"
    if name in ("task.md",):
        return "task-card"
    if "workers" in parts:
        return "worker-other"
    return "other"


def main() -> int:
    rows = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        mtime = datetime.datetime.fromtimestamp(st.st_mtime)
        for tag, lo, hi in WINDOWS:
            if lo <= mtime <= hi:
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                rows.append((tag, rel, path.name, kind_of(rel, path.name), st.st_size, mtime))
                break

    per_kind: dict[str, int] = {}
    for _tag, _rel, _name, kind, _size, _mt in rows:
        per_kind[kind] = per_kind.get(kind, 0) + 1
    print("== touched files by kind (W1+W2) ==")
    for kind, n in sorted(per_kind.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:16} {n}")

    for tag, _lo, _hi in WINDOWS:
        sel = [r for r in rows if r[0] == tag]
        print(f"\n== {tag}: {len(sel)} files ==")

    print("\n== products touched (evidence + worker-product), by size asc (truncation hunt) ==")
    products = [r for r in rows if r[3] in ("evidence", "worker-product")]
    print(f"  total products touched: {len(products)}")
    for tag, rel, _name, kind, size, mt in sorted(products, key=lambda r: r[4])[:25]:
        print(f"  {size:8}  {mt:%m-%d %H:%M:%S}  {tag}  {kind:15} {rel}")

    print("\n== PHASE-DOC writes in the windows (governance check) ==")
    for tag, rel, _name, _kind, size, mt in [r for r in rows if r[3] == "PHASE-DOC"]:
        print(f"  {size:8}  {mt:%m-%d %H:%M:%S}  {tag}  {rel}")

    zero = [r for r in rows if r[4] == 0]
    print(f"\n== zero-byte files touched: {len(zero)} ==")
    for tag, rel, _n, kind, _s, mt in zero[:20]:
        print(f"  {mt:%m-%d %H:%M:%S}  {tag}  {kind}  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

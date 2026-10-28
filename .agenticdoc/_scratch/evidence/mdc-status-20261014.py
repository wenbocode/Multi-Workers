"""PM status snapshot: index rows + MDC terminal states + open work."""
import json
import pathlib

REPO = pathlib.Path(r"H:\git\Multi-Workers")
idx = (REPO / ".agenticdoc/_index.parallel").read_text(encoding="utf-8")
print("=== _index.parallel rows (key | status | phase | claim | deps) ===")
for line in idx.splitlines():
    if not line.startswith("|") or line.startswith("|--"):
        continue
    c = [x.strip() for x in line.strip("|").split("|")]
    if len(c) >= 5 and c[0].lower() != "key":
        print(f"{c[0]:<32} {c[1]:<8} {c[2]:<9} {c[3]:<20} {c[4]}")

base = REPO / ".agenticdoc/mw-dynamic-concurrency"
print("\n=== MDC worker run.json ===")
for d in sorted((base / "workers").iterdir()):
    rj = d / "run.json"
    if rj.exists():
        data = json.loads(rj.read_text(encoding="utf-8"))
        print(f"{d.name:<32} {data.get('status')}")

print("\n=== MDC closure artifacts ===")
for rel in ("achieved.md", "pm-state.md", "evidence-requirement.md", "plan.md",
            "evidence/quality-gate-report-20261014.md"):
    p = base / rel
    print(f"{rel:<45} {'OK' if p.exists() else 'MISSING'}  {p.stat().st_size if p.exists() else 0} B")
print("baseline files :", len(list((base / "evidence/baseline").glob("*"))))
print("runs files     :", len(list((base / "evidence/runs").glob("*"))))

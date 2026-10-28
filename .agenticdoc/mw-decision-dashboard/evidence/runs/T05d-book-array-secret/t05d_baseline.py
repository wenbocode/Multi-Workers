import hashlib
import pathlib
import subprocess
import time

files = [
    "packages/multi-workers/decision_book.py",
    "packages/multi-workers/test_decision_input_contract_migration.py",
]
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
lines = [
    f"# captured {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
    f"# git HEAD {head}",
]
for name in files:
    data = pathlib.Path(name).read_bytes()
    blob = subprocess.run(["git", "hash-object", name], capture_output=True, text=True).stdout.strip()
    lines.append(
        f"{name}\tsha256={hashlib.sha256(data).hexdigest()}\tblob={blob}\tsize={len(data)}"
    )
lines.append("# git status --short (my write surface)")
status = subprocess.run(["git", "status", "--short", "--", *files], capture_output=True, text=True)
lines.extend(status.stdout.strip().splitlines())
dest = pathlib.Path(
    ".agenticdoc/mw-decision-dashboard/evidence/runs/T05d-book-array-secret/baseline-hashes.txt"
)
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
print("\n".join(lines))

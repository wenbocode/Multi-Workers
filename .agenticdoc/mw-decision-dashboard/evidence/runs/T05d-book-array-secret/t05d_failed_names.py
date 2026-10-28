import pathlib
import re

evidence = pathlib.Path(".agenticdoc/mw-decision-dashboard/evidence/runs/T05d-book-array-secret")
text = (evidence / "red-new-tests.txt").read_text(encoding="utf-8")
names = [line.strip() for line in text.splitlines() if line.startswith("FAILED ")]
(evidence / "red-failed-names.txt").write_text(
    "\n".join(names) + "\n", encoding="utf-8", newline="\n"
)
print("\n".join(names))
print(f"count={len(names)}")

"""Dump the two newly-red tests' bodies to judge whether they encode the old
"re-dispatch a non-terminal identity succeeds" behaviour that M-04 invalidated."""

import pathlib
import re

PKG = pathlib.Path(r"H:\git\Multi-Workers\packages\multi-workers")
TARGETS = [
    ("test_rag_launcher.py", "test_dispatch_end_to_end_is_stable"),
    ("test_rag_init.py", "test_vc204_zero_interaction"),
]
out = []
for fname, test in TARGETS:
    text = (PKG / fname).read_text(encoding="utf-8")
    lines = text.splitlines()
    idx = [j for j, l in enumerate(lines) if test in l]
    out.append("=" * 78)
    out.append(f"{fname} :: {test}  (occurrences: {[j + 1 for j in idx]})")
    if not idx:
        out.append("  NOT FOUND")
        continue
    start = idx[-1]
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j]
        if s.strip() and (len(s) - len(s.lstrip())) <= indent and re.match(r"\s*(def |class |@)", s):
            end = j
            break
    for j in range(start, min(end, start + 90)):
        out.append(f"{j + 1}: {lines[j].rstrip()[:155]}")

dest = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\_scratch\evidence\mdc-rag-reds-20261014.txt")
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")

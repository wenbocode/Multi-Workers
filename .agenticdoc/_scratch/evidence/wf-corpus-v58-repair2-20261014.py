"""One-off repair #2: V58 is the LAST element of the `overlap` array, so its row
must not carry a trailing comma either.  Strip it and verify."""

import hashlib
import json
import pathlib

PATH = pathlib.Path(r"H:\git\Multi-Workers\packages\multi-workers\test\fixtures\write-face-corpus.json")
lines = PATH.read_text(encoding="utf-8").splitlines()
hits = [i for i, line in enumerate(lines) if "V58 state-machine fallback pair" in line]
print("candidates:", hits)
for i in hits:
    stripped = lines[i].rstrip()
    if stripped.endswith(","):
        lines[i] = stripped[:-1]
        print(f"stripped comma on line {i + 1}")
PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
raw = PATH.read_text(encoding="utf-8")
corpus = json.loads(raw)
print("json ok | lines", len(lines), "| overlap", len(corpus["overlap"]), "| counts", corpus["counts"]["parse"], corpus["counts"]["overlap"])
row = corpus["overlap"][-1]
print("V58:", row["name"], "| a[0] len", len(row["a"][0]), "| entries", len(row["a"]), len(row["b"]))
print("notes", len(corpus["notes"]), "| protocol keys", sorted(corpus["protocol"].keys()))
print("sha256", hashlib.sha256(raw.encode("utf-8")).hexdigest())
print("bytes", len(raw.encode("utf-8")))

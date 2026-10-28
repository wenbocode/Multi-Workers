"""One-off repair: the V58 patch script appended the new note as the last array
element while still carrying a trailing comma, which makes the JSON invalid.
Strip that comma and re-verify."""

import hashlib
import json
import pathlib

PATH = pathlib.Path(r"H:\git\Multi-Workers\packages\multi-workers\test\fixtures\write-face-corpus.json")
lines = PATH.read_text(encoding="utf-8").splitlines()
hits = [i for i, line in enumerate(lines) if line.rstrip().endswith('are not corpus rows.",')]
print("candidates:", hits)
for i in hits:
    lines[i] = lines[i].rstrip()[:-1]
PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
raw = PATH.read_text(encoding="utf-8")
corpus = json.loads(raw)
print("json ok | overlap rows", len(corpus["overlap"]), "| counts", corpus["counts"]["parse"], corpus["counts"]["overlap"])
row = corpus["overlap"][-1]
print("V58:", row["name"], "| a[0] len", len(row["a"][0]), "| expect", json.dumps(row["expect"]))
print("entries a", len(row["a"]), "b", len(row["b"]))
print("notes", len(corpus["notes"]))
print("sha256", hashlib.sha256(raw.encode("utf-8")).hexdigest())
print("bytes", len(raw.encode("utf-8")))

import pathlib

p = pathlib.Path("packages/multi-workers/CHANGELOG.md")
t = p.read_text(encoding="utf-8")
old = 'is no longer conflated with "no verdict" \u2014 it emits'
new = 'is no longer conflated with "no verdict": it emits'
assert t.count(old) == 1, t.count(old)
p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
bad = sorted({c for c in t if ord(c) > 127 and c != "\u2014"})
print("non-ascii (excluding em-dash) left:", bad[:10])

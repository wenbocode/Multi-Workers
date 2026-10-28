import pathlib

path = pathlib.Path(r"H:\git\Multi-Workers\packages\multi-workers\test\fixtures\write-face-corpus.json")
lines = path.read_text(encoding="utf-8").splitlines()
print("total lines", len(lines))
for n in (12, 13, 14, 126, 127):
    print(n, repr(lines[n - 1]))
tests = ['"notes"', '"overlap_note"', '"extended"']
for i, line in enumerate(lines, 1):
    for needle in tests:
        if needle in line:
            print(f"{i}: {line[:150]!r}")
last = len(lines)
for k in range(last - 3, last):
    print(k + 1, repr(lines[k][:160]))

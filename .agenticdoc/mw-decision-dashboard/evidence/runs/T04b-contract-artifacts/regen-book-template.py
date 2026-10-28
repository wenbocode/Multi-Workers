"""T04b: regenerate `decide_book_template.json` from the shipped renderer.

The template is the example bundle the card test locks: dp3 + dp6 scaffolds from
`decision_book.scaffold_book` (the same renderer `mw decide book new` uses), so
it is regenerated, never hand-edited.

Run from packages/multi-workers:
    python .../regen-book-template.py [--write]
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.cwd()))

import decision_book as books  # noqa: E402

DP3 = "dp3-worker-clarify"
DP6 = "dp6-qg-verdict"
TARGET = pathlib.Path("decide_book_template.json")


def render() -> str:
    doc = {"books": {DP3: books.scaffold_book(DP3), DP6: books.scaffold_book(DP6)}}
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    text = render()
    if "--write" in sys.argv:
        TARGET.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {TARGET} ({len(text.encode('utf-8'))} bytes)")
    elif "--out" in sys.argv:
        out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out} ({len(text.encode('utf-8'))} bytes)")
    else:
        sys.stdout.write(text)

"""IN-3 source-write attribution (read-only).

For every source file under packages/** written during the W2 incident window,
look for re-run worker trace logs (also in W2) that mention the file, so the
write can be attributed either to a re-run worker or to a live key doing
legitimate work.
"""

import datetime
import pathlib
import re

REPO = pathlib.Path("H:/git/Multi-Workers")
LO = datetime.datetime(2026, 10, 10, 10, 50, 0)
HI = datetime.datetime(2026, 10, 10, 11, 45, 0)

SKIP = ("node_modules", "\\dist\\", "\\.tmp\\", "__pycache__", ".pytest_cache", "\\.git\\")


def in_window(mt: float) -> bool:
    return LO <= datetime.datetime.fromtimestamp(mt) <= HI


def main() -> None:
    src = []
    for path in (REPO / "packages").rglob("*"):
        if not path.is_file() or any(s in str(path) for s in SKIP):
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        if in_window(st.st_mtime):
            src.append((path, st.st_size, datetime.datetime.fromtimestamp(st.st_mtime)))

    traces = []
    for path in (REPO / ".agenticdoc").rglob("trace.log"):
        try:
            st = path.stat()
        except OSError:
            continue
        if in_window(st.st_mtime):
            task = path.parent.name
            owner = path.parent.parent.parent.name
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            traces.append((f"{owner}::{task}", text))

    print(f"source files written in W2: {len(src)}  |  worker traces live in W2: {len(traces)}")
    print()
    for path, size, mt in sorted(src, key=lambda r: r[2]):
        rel = str(path.relative_to(REPO)).replace("\\", "/")
        base = path.name
        hits = [name for name, text in traces if base in text]
        tag = "RE-RUN?" if hits else "unattributed"
        print(f"{mt:%H:%M:%S}  {size:7}  {tag:12} {rel}")
        for name in hits[:4]:
            print(f"            ^ mentioned in {name}")


if __name__ == "__main__":
    main()
